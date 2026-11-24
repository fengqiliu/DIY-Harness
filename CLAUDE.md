# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

协作规范以 [`AGENTS.md`](AGENTS.md) 为正文，本文件只补充本仓库（DIY Personal Harness）专属的命令、结构与实现约束。

## 常用命令

环境：Python 3.10+，唯一第三方依赖 PyYAML（`requirements.txt` 固定 6.0.3），推荐在 PowerShell 中运行。

```powershell
# 安装依赖并做配置校验
python -m pip install -r requirements.txt
python scripts/verify.py

# 回归测试（CLI 黑盒 + 工作台 HTTP 集成）
python -B -m unittest discover -s evals -v

# 运行单个测试
python -B -m unittest evals.test_workflows.WorkflowTests.test_feature_and_bugfix_complete_in_declared_order
python -B -m unittest evals.test_workbench.WorkbenchTests.test_six_role_handoff_and_cli_verification
```

两个测试模块都会把仓库 `copytree` 到临时目录（忽略 `runs/`、`.git/`、`.venv/`）并用 `-X utf8` 起子进程，所以不会污染本机 `runs/`。

### 启动与推进任务

```powershell
# 初始化任务（流程名取自 config/workflows.yaml：feature / bugfix / pacs-delivery）
python scripts/bootstrap.py feature --run-id report-search --task "为本地报告列表增加按检查号精确查找。验收覆盖有匹配和无匹配两种结果。"

# 查看当前阶段指引与历史交接
python scripts/checkpoint.py report-search --brief
python scripts/checkpoint.py report-search --history

# 登记阶段结果（--evidence 可重复；--revision 用于并发保护）
python scripts/checkpoint.py report-search --stage requirements --outcome pass --summary "已确定精确匹配与空结果的验收条件" --evidence "合成验收样例：查 A100 只返回 A100；查 Z999 返回空列表。"

# 校验流程配置，或核验某任务是否闭环
python scripts/verify.py
python scripts/verify.py report-search
```

### 启动 PACS 工作台

```powershell
python scripts/workbench.py --port 0     # 0 = 自动选端口，默认 8765
```

### 阶段结果语义

- `pass`：推进到下一阶段。
- `blocked`：停留在当前阶段，需对同一阶段重新登记结果。
- `fail`：按阶段 `on_fail` 回退；未配置 `on_fail` 时停在当前阶段。

## 整体结构

这是一个**本地任务流程与证据交接 Harness**：把一次任务拆成固定阶段，每阶段留下可复查的结论与证据，并通过两个入口共享同一份运行记录——CLI（`scripts/`）与单机 Web 工作台（`scripts/workbench.py` + `workbench/`）。

### 目录职责

| 目录 | 作用 |
| --- | --- |
| `scripts/` | `bootstrap.py` 创建任务、`checkpoint.py` 查看/登记、`verify.py` 校验配置或任务闭环、`workbench.py` 本地 HTTP 服务；共享逻辑在 `scripts/harness.py`，登记单条结果的逻辑在 `scripts/checkpoint.py:record_checkpoint`（工作台复用）。 |
| `workbench/` | 工作台静态前端（`index.html` / `app.js` / `style.css`，无构建步骤，原生 JS 渲染）与领域说明 `domain.md`。 |
| `config/` | `workflows.yaml` 注册流程名→文件；`models.yaml` 模型别名→角色；`permissions.yaml` 权限分组，会原样嵌入阶段简报。 |
| `workflows/` | 每个 `.yaml` 一组阶段：`id`、`role`、`skill`、`deliverable`、可选 `on_fail`。 |
| `agents/` | 角色定义，阶段简报会把当前角色的 `.md` 全文嵌入。 |
| `skills/` | 技能定义，`skills/<name>/SKILL.md`，YAML frontmatter 的 `name` 必须与目录名一致。 |
| `context/` | 跨任务通用上下文：`profile.md`、`engineering.md`、`architecture.md`，随 `AGENTS.md` 一起进快照。 |
| `memory/` | 人工整理的 `decisions.md`、`lessons.md`，不自动加载，按需查阅。 |
| `runs/` | 每个任务一个 `runs/<run_id>/run.sqlite3`，保存启动快照与全部检查点；已被 `.gitignore` 排除。 |
| `evals/` | CLI 与工作台的黑盒回归。 |

### 关键机制

1. **任务启动时冻结快照**。`bootstrap.py` 把当时的 workflow、角色全文、技能正文、权限与 `context/` 写入 SQLite 的 `run` 表（单行 JSON）。此后改 `workflows/`、`agents/`、`skills/`、`context/` 只影响新任务，已有任务继续用旧快照。`create_run` 先在同级临时目录建库再 `rename`，避免出现半个任务目录。
2. **当前阶段由记录顺序重放得出**。`read_run` 依 `events.seq` 逐条调用 `advance()`，校验阶段顺序与 `on_fail` 路由；`--history` / `--brief` / `verify` 都走同一条重放路径，因此历史被篡改或不连续会直接报错。
3. **并发保护靠修订号**。CLI 的修订号是 `len(history)`，写入在 `BEGIN IMMEDIATE` 事务内先比对 `--revision` 再追加；不一致即报「修订已变化」。
4. **证据强制**。每次登记必须有非空 `--summary` 和至少一项 `--evidence`，`evidence` 以 JSON 数组存入单列。
5. **配置校验在加载期完成**（`load_plans` → `compile_workflow`）：`on_fail` 只能指向当前或更早阶段、角色必须在 `models.yaml` 有模型别名、技能 `name` 必须等于目录名、`workflows.yaml` 的路径必须在 `workflows/` 下、YAML 重复键直接报错（`ConfigLoader`）。`python scripts/verify.py` 只是把这一步跑一遍。
6. **任务 ID 是安全边界**。`identifier()` 限定 1–64 位小写字母/数字/`-`/`_`，拒绝 Windows 保留名，`run_dir()` 还会校验解析后未逃出 `runs/`。

### 工作台与 CLI 的分工

- 服务只监听 `127.0.0.1`，`Handler.check_local()` 校验 `Host` 与 `Origin`，静态文件限定在 `workbench/` 内；角色切换只是视图筛选，**没有身份认证**。
- 工作台只展示快照 `workflow == "pacs-delivery"` 的任务；用 CLI 创建的同类任务会自动出现在看板上。
- 排期（迭代/优先级）存在**独立**的 `planning` 表（按需 `CREATE TABLE IF NOT EXISTS`，每次修改追加一行），不属于阶段记录。
- 因此两处修订号语义不同：工作台 `revision = len(history) + 排期修改次数`，CLI `--revision = len(history)`。跨入口接管时用各自读到的修订号。
- 工作项写操作要求 `revision` 与 `stage` 都匹配，否则返回 409；前端据此提示刷新。

## 进入已有任务时

按 `AGENTS.md` 约定，先读取当前简报和历史证据：

```powershell
python scripts/checkpoint.py RUN_ID --brief
python scripts/checkpoint.py RUN_ID --history
```

然后在任务描述指定的目标仓库完成当前阶段工作，再回 Harness 登记结果。修改流程、角色、技能、配置或工作台后，需重跑 `python scripts/verify.py` 与完整回归。
