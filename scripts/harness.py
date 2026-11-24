"""Shared configuration and run storage for the three CLI entry points."""

import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

try:
    import yaml
except ModuleNotFoundError:
    raise SystemExit("缺少 PyYAML。请在项目根目录运行 python -m pip install -r requirements.txt")


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
COMMON = ("AGENTS.md", "context/profile.md", "context/engineering.md", "context/architecture.md")
OUTCOMES = ("pass", "fail", "blocked")


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 需要非空文本")
    return value.strip()


def identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ValueError(f"{label} 需为 1 至 64 位小写字母、数字、连字符或下划线，首位为字母或数字")
    if re.fullmatch(r"con|prn|aux|nul|(?:com|lpt)[0-9]", value):
        raise ValueError(f"{label} 使用了系统保留名 {value}")
    return value


def mapping(value, label):
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} 需要非空映射")
    return value


def text_list(value, label):
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} 需要至少一项")
    return [nonempty(item, label) for item in value]


class ConfigLoader(yaml.SafeLoader):
    """Reject duplicate keys so an edited routing rule cannot silently disappear."""

    def construct_mapping(self, node, deep=False):
        result = super().construct_mapping(node, deep)
        if len(node.value) != len(result):
            raise ValueError(f"重复的 YAML 键，检查第 {node.start_mark.line + 1} 行附近")
        return result


def markdown(path):
    return nonempty(path.read_text(encoding="utf-8-sig"), str(path))


def read_config(path):
    try:
        value = yaml.load(markdown(path), Loader=ConfigLoader)
        return mapping(value, path.name)
    except (ValueError, yaml.YAMLError) as error:
        raise ValueError(f"{path.name} 配置无效：{error}") from error


def skill_text(name):
    path = ROOT / "skills" / name / "SKILL.md"
    raw = markdown(path)
    front = re.fullmatch(r"---\n(.*?)\n---\n(.+)", raw, flags=re.DOTALL)
    if not front:
        raise ValueError(f"{path} 缺少技能元数据或正文")
    meta = mapping(yaml.load(front[1], Loader=ConfigLoader), path)
    if meta.get("name") != name:
        raise ValueError(f"{path} 的 name 需与技能目录一致")
    nonempty(meta.get("description"), f"{name}.description")
    return nonempty(front[2], str(path))


def compile_workflow(name, path, roles):
    spec = read_config(path)
    stages = []
    seen = set()
    if not isinstance(spec.get("stages"), list) or not spec["stages"]:
        raise ValueError(f"{name} 至少需要一个阶段")
    for raw in spec["stages"]:
        stage = mapping(raw, f"{name}.stages")
        stage_id = identifier(stage.get("id"), "阶段 ID")
        if stage_id in seen:
            raise ValueError(f"{name} 包含重复阶段 {stage_id}")
        seen.add(stage_id)
        fail_to = identifier(stage.get("on_fail", stage_id), "on_fail")
        if fail_to not in seen:
            raise ValueError(f"{stage_id}.on_fail 只能指向当前或前面的阶段")
        role = identifier(stage.get("role"), "角色")
        if role not in roles:
            raise ValueError(f"{stage_id} 引用了未配置模型的角色 {role}")
        skill = identifier(stage.get("skill"), "技能")
        stages.append({
            "id": stage_id, "role": role, "skill": skill, "on_fail": fail_to,
            "deliverable": nonempty(stage.get("deliverable"), f"{stage_id}.deliverable"),
            "role_text": roles[role]["text"], "model": roles[role]["model"],
            "skill_text": skill_text(skill),
        })
    return {"workflow": name, "title": nonempty(spec.get("title"), name), "stages": stages}


def load_plans():
    config = ROOT / "config"
    models = read_config(config / "models.yaml")
    profiles = mapping(models.get("profiles"), "profiles")
    roles = {}
    for key, value in profiles.items():
        nonempty(key, "模型别名")
        nonempty(value, str(key))
    for role, alias in mapping(models.get("roles"), "roles").items():
        identifier(role, "角色")
        alias = nonempty(alias, f"{role}.model")
        if alias not in profiles:
            raise ValueError(f"{role} 引用了未定义的模型 {alias}")
        roles[role] = {"text": markdown(ROOT / "agents" / f"{role}.md"),
                       "model": f"{alias}（{profiles[alias]}）"}
    permissions = read_config(config / "permissions.yaml")
    rules = {nonempty(key, "权限分组"): text_list(lines, key) for key, lines in permissions.items()}
    common = {filename: markdown(ROOT / filename) for filename in COMMON}
    plans = {}
    for name, relative in read_config(config / "workflows.yaml").items():
        identifier(name, "流程名")
        path = (ROOT / nonempty(relative, name)).resolve()
        if not path.is_relative_to(ROOT / "workflows") or path.suffix != ".yaml":
            raise ValueError(f"{name} 需要引用 workflows/ 下的 .yaml 文件")
        plan = compile_workflow(name, path, roles)
        plans[name] = {**plan, "permissions": rules, "context": common}
    return plans


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_dir(run_id):
    path = RUNS / identifier(run_id, "任务 ID")
    if path.resolve() != path:
        raise ValueError(f"任务目录指向其他位置：{run_id}")
    return path


def create_run(run_id, task, plan):
    target = run_dir(run_id)
    RUNS.mkdir(exist_ok=True)
    if target.exists():
        raise ValueError(f"任务 ID 已存在：{run_id}")
    snapshot = {"version": 1, "run_id": run_id, "task": nonempty(task, "任务"),
                "created": now(), **plan}
    # Publish a complete directory. Concurrent initializers cannot replace a nonempty run.
    with tempfile.TemporaryDirectory(prefix=".init-", dir=RUNS) as temporary:
        staging = Path(temporary)
        db = sqlite3.connect(staging / "run.sqlite3")
        try:
            with db:
                db.execute("CREATE TABLE run (snapshot TEXT NOT NULL)")
                db.execute("""CREATE TABLE events (
                    seq INTEGER PRIMARY KEY, stage TEXT NOT NULL, outcome TEXT NOT NULL,
                    summary TEXT NOT NULL, evidence TEXT NOT NULL, recorded TEXT NOT NULL
                )""")
                db.execute("INSERT INTO run VALUES (?)", (json.dumps(snapshot, ensure_ascii=False),))
        finally:
            db.close()
        staging.rename(target)
    return snapshot


def open_run(run_id, *, write=False):
    path = run_dir(run_id) / "run.sqlite3"
    if not path.is_file() or path.resolve() != path:
        raise ValueError(f"找不到本地任务记录：{run_id}")
    mode = "rw" if write else "ro"
    db = sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def advance(stages, index, stage_id, outcome):
    if index == len(stages):
        raise ValueError("任务已完成，无法继续登记")
    stage = stages[index]
    if stage_id != stage["id"]:
        raise ValueError(f"当前阶段为 {stage['id']}，收到 {stage_id}")
    if outcome == "pass":
        return index + 1
    if outcome == "blocked":
        return index
    if outcome == "fail":
        return next(i for i, item in enumerate(stages) if item["id"] == stage["on_fail"])
    raise ValueError(f"未知阶段结果 {outcome}")


def read_run(db, run_id):
    row = db.execute("SELECT snapshot FROM run").fetchone()
    if row is None:
        raise ValueError("缺少任务快照")
    plan = json.loads(row[0])
    if plan.get("version") != 1 or plan.get("run_id") != run_id:
        raise ValueError("任务快照版本或 ID 不匹配")
    history = []
    index = 0
    for row in db.execute("SELECT * FROM events ORDER BY seq"):
        event = dict(row)
        if event["seq"] != len(history) + 1:
            raise ValueError("阶段记录序号不连续")
        event["evidence"] = text_list(json.loads(event["evidence"]), "证据")
        nonempty(event["summary"], "结论")
        index = advance(plan["stages"], index, event["stage"], event["outcome"])
        history.append(event)
    return plan, history, index


def cli(main):
    # Keep redirected Chinese handoffs readable on Windows with legacy code pages.
    if sys.platform == "win32" and not os.environ.get("PYTHONIOENCODING"):
        for stream in (sys.stdout, sys.stderr):
            if not stream.isatty():
                stream.reconfigure(encoding="utf-8")
    try:
        main()
    except (ValueError, OSError, sqlite3.Error, yaml.YAMLError) as error:
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(1)
