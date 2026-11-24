"""Loopback web workbench backed by the same per-run SQLite files as the Harness CLI."""

import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import sqlite3
from urllib.parse import urlsplit
from uuid import uuid4

from checkpoint import record_checkpoint
from harness import (
    OUTCOMES, ROOT, RUNS, cli, create_run, load_plans, nonempty, now, open_run,
    read_run, run_dir,
)


WORKFLOW = "pacs-delivery"
PUBLIC = ROOT / "workbench"
DEFAULT_PLANNING = {"domain": "未分类", "sprint": "待规划", "priority": "P2"}
MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
    ".ico": "image/x-icon", ".webp": "image/webp", ".woff2": "font/woff2",
}


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def priority(value):
    if value not in ("P1", "P2", "P3"):
        raise ValueError("优先级需为 P1、P2 或 P3")
    return value


def planning(db, plan):
    fields = {**DEFAULT_PLANNING, **plan.get("work_item", {})}
    # CLI-created runs can enter the workbench before any scheduling changes exist.
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='planning'").fetchone()
    if exists:
        latest = db.execute("SELECT * FROM planning ORDER BY seq DESC LIMIT 1").fetchone()
        if latest:
            fields.update(sprint=latest["sprint"], priority=latest["priority"])
            return fields, latest["seq"]
    return fields, 0


def presentation(plan, history, index, fields, changes, *, detailed):
    stages = plan["stages"]
    completed = index == len(stages)
    current = {} if completed else stages[index]
    item = {
        "id": plan["run_id"], "title": plan["task"], **fields, "created": plan["created"],
        "stage": current.get("id", "done"), "role": current.get("role", ""),
        "revision": len(history) + changes, "completed": completed,
        "blocked": bool(history and history[-1]["outcome"] == "blocked"),
    }
    if detailed:
        item.update(history=history, deliverable=current.get("deliverable", ""),
                    role_text=current.get("role_text", ""), skill_text=current.get("skill_text", ""),
                    stages=[{key: s[key] for key in ("id", "role", "deliverable")} for s in stages])
    return item


def load_item(run_id, *, detailed=True, action=None, data=None):
    if not (run_dir(run_id) / "run.sqlite3").is_file():
        raise ApiError(404, "工作项不存在")
    with closing(open_run(run_id, write=action is not None)) as db, db:
        db.execute("BEGIN IMMEDIATE" if action else "BEGIN")
        plan, history, index = read_run(db, run_id)
        if plan.get("workflow") != WORKFLOW:
            raise ApiError(404, "工作项不属于 PACS 交付流程")
        fields, changes = planning(db, plan)
        if action:
            revision = data.get("revision")
            if type(revision) is not int or revision < 0:
                raise ValueError("请提供读取工作项时的整数修订号 revision")
            if revision != len(history) + changes:
                raise ApiError(409, "工作项已更新，请刷新并核对最新交接")
            if index == len(plan["stages"]):
                raise ApiError(409, "工作项已完成")
            if action == "checkpoint":
                stage = nonempty(data.get("stage"), "阶段")
                if stage != plan["stages"][index]["id"]:
                    raise ApiError(409, "阶段已变化，请刷新并检查当前阶段")
                outcome = data.get("outcome")
                if outcome not in OUTCOMES:
                    raise ValueError("结果需为 pass、fail 或 blocked")
                index = record_checkpoint(db, plan, history, index, stage, outcome,
                                          data.get("summary"), data.get("evidence"))
            else:
                if not {"sprint", "priority"}.intersection(data):
                    raise ValueError("请提供迭代或优先级")
                fields["sprint"] = nonempty(data.get("sprint", fields["sprint"]), "迭代")
                fields["priority"] = priority(data.get("priority", fields["priority"]))
                db.execute("""CREATE TABLE IF NOT EXISTS planning (
                    seq INTEGER PRIMARY KEY, sprint TEXT NOT NULL,
                    priority TEXT NOT NULL, recorded TEXT NOT NULL
                )""")
                changes += 1
                db.execute("INSERT INTO planning VALUES (?, ?, ?, ?)",
                           (changes, fields["sprint"], fields["priority"], now()))
        return presentation(plan, history, index, fields, changes, detailed=detailed)


def board():
    items = []
    for path in RUNS.glob("*/run.sqlite3"):
        if path.parent.name.startswith("."):
            continue  # unpublished staging directory
        try:
            items.append(load_item(path.parent.name, detailed=False))
        except ApiError as error:
            if error.status != 404:
                raise
    items.sort(key=lambda row: (row["created"], row["id"]), reverse=True)
    return {"items": items}


def new_item(data):
    title = nonempty(data.get("title"), "工作项名称")
    metadata = {"domain": nonempty(data.get("domain"), "限界上下文"),
                "sprint": nonempty(data.get("sprint", "待规划"), "迭代"),
                "priority": priority(data.get("priority", "P2"))}
    run_id = f"pacs-{uuid4().hex[:12]}"
    plans = load_plans()
    if WORKFLOW not in plans:
        raise ApiError(500, "缺少 pacs-delivery 工作流配置")
    plan = create_run(run_id, title, {**plans[WORKFLOW], "work_item": metadata})
    return presentation(plan, [], 0, metadata, 0, detailed=True)


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, content, mime):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(content)

    def json_response(self, status, value):
        self.respond(status, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def check_local(self):
        host = self.headers.get("Host", "").lower()
        port = self.server.server_port
        valid_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            valid_hosts.update(("127.0.0.1", "localhost"))
        if host not in valid_hosts:
            raise ApiError(403, "请从本机工作台地址访问")
        if self.command == "GET" and not urlsplit(self.path).path.startswith("/api/"):
            return
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{host}":
            raise ApiError(403, "请从本机工作台所在页面访问")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise ApiError(403, "请直接打开本机工作台")

    def body(self):
        if self.headers.get_content_type() != "application/json":
            raise ApiError(415, "请求需使用 application/json")
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > 256 * 1024:
            raise ApiError(413, "请求正文须在 1 至 262144 字节之间")
        value = json.loads(self.rfile.read(size).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("请求正文需要 JSON 对象")
        return value

    def serve_file(self, path):
        filename = "index.html" if path == "/" else path[1:]
        file = (PUBLIC / filename).resolve()
        if not file.is_relative_to(PUBLIC) or file.suffix not in MIME or not file.is_file():
            raise ApiError(404, "找不到页面资源")
        self.respond(200, file.read_bytes(), MIME[file.suffix])

    def dispatch(self):
        try:
            self.check_local()
            path = urlsplit(self.path).path
            if self.command == "GET" and not path.startswith("/api/"):
                self.serve_file(path)
                return
            if self.command == "GET" and path == "/api/board":
                self.json_response(200, board())
                return
            if self.command == "POST" and path == "/api/items":
                self.json_response(201, new_item(self.body()))
                return
            match = re.fullmatch(r"/api/items/([a-z0-9][a-z0-9_-]{0,63})(/checkpoint)?", path)
            if not match:
                raise ApiError(404, "找不到接口")
            run_id, suffix = match.groups()
            if not suffix and self.command == "GET":
                item = load_item(run_id)
            elif not suffix and self.command == "PATCH":
                item = load_item(run_id, action="schedule", data=self.body())
            elif suffix and self.command == "POST":
                item = load_item(run_id, action="checkpoint", data=self.body())
            else:
                raise ApiError(405, "此接口不支持该请求方式")
            self.json_response(200, item)
        except ApiError as error:
            self.json_response(error.status, {"error": str(error)})
        except (ValueError, RecursionError) as error:
            self.json_response(400, {"error": str(error)})
        except (OSError, sqlite3.Error) as error:
            self.log_error("Store or resource error: %s", error)
            self.json_response(500, {"error": "读取或保存失败，请检查服务日志"})

    do_GET = do_POST = do_PATCH = dispatch


def main():
    parser = argparse.ArgumentParser(description="在本机启动 PACS 团队工作台")
    parser.add_argument("--port", type=int, default=8765, help="本地 HTTP 端口，默认 8765")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("端口范围为 0 至 65535")
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"PACS 工作台 http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    cli(main)
