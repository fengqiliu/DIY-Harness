"""PACS 工作台 HTTP 与 CLI 集成回归。使用本地临时副本和合成工作项。"""

import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
HANDOFFS = (
    ("discovery", "product-manager"),
    ("planning", "project-manager"),
    ("design", "ux-designer"),
    ("implement", "pacs-developer"),
    ("verify", "test-engineer"),
    ("release", "ops-engineer"),
)


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "harness"
        shutil.copytree(
            ROOT, self.root,
            ignore=shutil.ignore_patterns("runs", ".git", ".venv", "__pycache__", "*.pyc"),
        )
        self.opener = build_opener(ProxyHandler({}))
        self.log = (self.root / "test-server.log").open("w+b")
        self.addCleanup(self.log.close)
        self.process = None
        self.addCleanup(self.stop_service)
        self.start_service()

    def start_service(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.origin = f"http://127.0.0.1:{port}"
        self.process = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-B", "scripts/workbench.py", "--port", str(port)],
            cwd=self.root, stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and self.process.poll() is None:
            try:
                self.request("GET", "/api/board")
                return
            except URLError:
                time.sleep(0.05)
        self.log.seek(0)
        self.fail("工作台启动失败：" + self.log.read().decode("utf-8", errors="replace"))

    def stop_service(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=10)

    def request(self, method, path, data=None, *, error=None):
        body = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
        req = Request(
            self.origin + path, data=body, method=method,
            headers={"Content-Type": "application/json", "Origin": self.origin},
        )
        try:
            with self.opener.open(req, timeout=5) as response:
                payload = json.load(response)
        except HTTPError as exc:
            with exc:
                payload = json.load(exc)
            self.assertEqual(exc.code, error, f"{method} {path}: {payload}")
            self.assertTrue(payload["error"])
            return payload
        self.assertIsNone(error, f"{method} {path} 被意外接受：{payload}")
        return payload

    def cli(self, script, *args):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", f"scripts/{script}.py", *args],
            cwd=self.root, capture_output=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def create_item(self):
        return self.request("POST", "/api/items", {
            "title": "合成场景：已审核报告重发后可查询接收回执",
            "domain": "结果分发", "sprint": "合成迭代 01", "priority": "P2",
        })

    def checkpoint(self, item, outcome="pass", *, error=None):
        return self.request("POST", f"/api/items/{item['id']}/checkpoint", {
            "stage": item["stage"], "revision": item["revision"], "outcome": outcome,
            "summary": f"合成记录 {item['stage']} {outcome}",
            "evidence": [f"fixture-{item['stage']}-{outcome}"],
        }, error=error)

    def test_six_role_handoff_and_cli_verification(self):
        self.cli("bootstrap", "feature", "--task", "普通功能合成用例", "--run-id", "generic")
        self.cli("bootstrap", "pacs-delivery", "--task", "命令行创建的合成任务",
                 "--run-id", "cli-created")
        self.cli("checkpoint", "cli-created", "--stage", "discovery", "--outcome", "pass",
                 "--summary", "已核对合成范围", "--evidence", "fixture-cli-discovery")
        imported = self.request("GET", "/api/items/cli-created")
        self.assertEqual(imported["stage"], "planning")
        self.assertIn("fixture-cli-discovery", imported["history"][0]["evidence"])
        item = self.create_item()
        for stage, role in HANDOFFS:
            with self.subTest(stage=stage):
                self.assertEqual((item["stage"], item["role"]), (stage, role))
                self.assertTrue(item["deliverable"].strip())
                self.assertTrue(item["skill_text"].strip())
                self.assertTrue(item["role_text"].strip())
                item = self.checkpoint(item)
        self.assertTrue(item["completed"])
        self.assertEqual([event["stage"] for event in item["history"]], [s for s, _ in HANDOFFS])
        self.cli("verify", item["id"])
        self.assertIn("fixture-release-pass", self.cli("checkpoint", item["id"], "--history"))
        items = self.request("GET", "/api/board")["items"]
        self.assertTrue(next(row for row in items if row["id"] == item["id"])["completed"])
        self.assertNotIn("generic", [row["id"] for row in items])

    def test_blocker_rework_and_restart_preserve_board_and_history(self):
        item = self.create_item()
        item = self.checkpoint(item, "blocked")
        self.assertTrue(item["blocked"])
        self.assertEqual(item["stage"], "discovery")
        for stage, _ in HANDOFFS[:4]:
            self.assertEqual(item["stage"], stage)
            item = self.checkpoint(item)
        self.assertFalse(item["blocked"])
        item = self.checkpoint(item, "fail")
        self.assertEqual(item["stage"], "implement")
        self.stop_service()
        self.start_service()
        restored = self.request("GET", f"/api/items/{item['id']}")
        for field in ("title", "domain", "sprint", "priority", "stage", "revision", "history"):
            self.assertEqual(restored[field], item[field], field)
        for stage, _ in HANDOFFS[3:]:
            self.assertEqual(restored["stage"], stage)
            restored = self.checkpoint(restored)
        self.assertTrue(restored["completed"])
        self.assertIn("fixture-verify-fail", self.cli("checkpoint", item["id"], "--history"))

    def test_stale_edits_preserve_latest_schedule_and_checkpoint(self):
        item = self.create_item()
        path = f"/api/items/{item['id']}"
        assignment = {"sprint": "合成迭代 02", "priority": "P1", "revision": item["revision"]}
        updated = self.request("PATCH", path, assignment)
        self.assertEqual((updated["sprint"], updated["priority"]), ("合成迭代 02", "P1"))
        self.request("PATCH", path, {**assignment, "sprint": "过期排期"}, error=409)
        latest = self.checkpoint(updated, "blocked")
        self.checkpoint(updated, error=409)
        self.assertEqual(self.request("GET", path)["history"], latest["history"])
        self.assertEqual(self.request("GET", path)["sprint"], "合成迭代 02")


if __name__ == "__main__":
    unittest.main()
