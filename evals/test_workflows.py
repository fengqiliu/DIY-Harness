"""Personal Harness CLI 黑盒回归。任务、结论和证据引用均为合成数据。"""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


HARNESS = Path(__file__).resolve().parents[1]
FEATURE = ("requirements", "design", "implement", "review", "verify")
BUGFIX = ("reproduce", "fix", "review", "verify")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "harness"
        shutil.copytree(
            HARNESS,
            self.root,
            ignore=shutil.ignore_patterns(
                "runs", ".git", ".venv", "venv", "__pycache__", "*.pyc", ".pytest_cache"
            ),
        )
        (self.root / "runs").mkdir()

    def cli(self, script, *args, success=True):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", f"scripts/{script}.py", *args],
            cwd=self.root,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            encoding="utf-8",
            timeout=30,
        )
        diagnostic = f"{script} {args}\n{result.stdout}\n{result.stderr}"
        if success:
            self.assertEqual(result.returncode, 0, diagnostic)
        else:
            self.assertNotEqual(result.returncode, 0, diagnostic)
        return result.stdout

    def start(self, workflow, run_id, *, success=True):
        self.cli(
            "bootstrap", workflow, "--task", "合成任务：为列表增加排序",
            "--run-id", run_id, success=success,
        )

    def checkpoint(self, run_id, stage, outcome="pass", *evidence, summary=None, success=True):
        args = [
            run_id, "--stage", stage, "--outcome", outcome,
            "--summary", summary or f"合成结论 {stage} {outcome}",
        ]
        for item in evidence:
            args.extend(["--evidence", item])
        return self.cli("checkpoint", *args, success=success)

    def advance(self, run_id, *stages):
        for stage in stages:
            self.checkpoint(run_id, stage, "pass", f"synthetic-check-{stage}")

    def test_feature_and_bugfix_complete_in_declared_order(self):
        self.cli("verify")
        for workflow, stages in [("feature", FEATURE), ("bugfix", BUGFIX)]:
            with self.subTest(workflow=workflow):
                run_id = f"test-{workflow}"
                self.start(workflow, run_id)
                self.cli("verify", run_id, success=False)
                self.assertIn(stages[0], self.cli("checkpoint", run_id))
                self.advance(run_id, *stages)
                self.cli("verify", run_id)
                history = self.cli("checkpoint", run_id, "--history")
                for stage in stages:
                    self.assertIn(f"synthetic-check-{stage}", history)
                self.checkpoint(run_id, "verify", "pass", "late-entry", success=False)
                self.assertNotIn("late-entry", self.cli("checkpoint", run_id, "--history"))

    def test_failed_review_and_verification_send_work_back_for_repair(self):
        # 两条工作流有不同的修复阶段，分别验证回退目标和重新评审。
        for workflow, preparation, repair in [
            ("feature", ("requirements", "design"), "implement"),
            ("bugfix", ("reproduce",), "fix"),
        ]:
            with self.subTest(workflow=workflow):
                run_id = f"rework-{workflow}"
                self.start(workflow, run_id)
                self.advance(run_id, *preparation, repair)
                self.checkpoint(run_id, "review", "fail", "review-finding-A")
                self.checkpoint(run_id, "verify", "pass", "skip-repair", success=False)
                self.advance(run_id, repair, "review")
                self.checkpoint(run_id, "verify", "fail", "verification-finding-B")
                self.cli("verify", run_id, success=False)
                self.checkpoint(run_id, "review", "pass", "skip-second-repair", success=False)
                self.advance(run_id, repair, "review", "verify")
                self.cli("verify", run_id)
                history = self.cli("checkpoint", run_id, "--history")
                self.assertIn("review-finding-A", history)
                self.assertIn("verification-finding-B", history)
                self.assertNotIn("skip-repair", history)

    def test_blocked_stage_resumes_and_keeps_both_evidence_entries(self):
        run_id = "blocked-run"
        self.start("bugfix", run_id)
        self.checkpoint(run_id, "reproduce", "blocked", "fixture-missing")
        self.cli("verify", run_id, success=False)
        self.checkpoint(run_id, "fix", "pass", "skip-reproduction", success=False)
        self.checkpoint(
            run_id, "reproduce", "pass", "fixture-restored", "failure-observed",
            summary="复现时已观察到合成错误",
        )
        self.advance(run_id, "fix", "review", "verify")
        self.cli("verify", run_id)
        history = self.cli("checkpoint", run_id, "--history")
        for entry in ["fixture-missing", "fixture-restored", "failure-observed", "复现时已观察到合成错误"]:
            self.assertIn(entry, history)
        self.assertNotIn("skip-reproduction", history)

    def test_invalid_checkpoint_and_duplicate_run_preserve_original_work(self):
        run_id = "original"
        self.start("feature", run_id)
        self.checkpoint(run_id, "implement", "pass", "premature-edit", success=False)
        for evidence in [(), ("",), ("  ",)]:
            with self.subTest(evidence=evidence):
                self.checkpoint(run_id, "requirements", "pass", *evidence, success=False)
        self.advance(run_id, "requirements")
        self.start("bugfix", run_id, success=False)
        self.advance(run_id, *FEATURE[1:])
        self.cli("verify", run_id)
        history = self.cli("checkpoint", run_id, "--history")
        self.assertIn("synthetic-check-requirements", history)
        self.assertNotIn("premature-edit", history)

    def test_run_id_cannot_escape_run_directory(self):
        for run_id in ["../escaped-run", "nested/run"]:
            with self.subTest(run_id=run_id):
                self.start("feature", run_id, success=False)
                self.cli("checkpoint", run_id, success=False)
                self.cli("verify", run_id, success=False)
        self.assertFalse((self.root / "escaped-run").exists())
        self.assertFalse((self.root / "runs" / "nested").exists())

    def test_existing_run_retains_instructions_after_template_edit(self):
        profile = self.root / "context" / "profile.md"
        profile.write_text("合成偏好 A", encoding="utf-8")
        self.start("feature", "before-edit")
        profile.write_text("合成偏好 B", encoding="utf-8")
        self.start("feature", "after-edit")
        self.assertIn("合成偏好 B", self.cli("checkpoint", "after-edit", "--brief"))

        # A broken new template is reported, while previous runs remain resumable.
        workflow = self.root / "workflows" / "feature.yaml"
        workflow.write_text("title: draft\nstages: []\n", encoding="utf-8")
        self.cli("verify", success=False)
        self.start("feature", "invalid-template", success=False)
        self.assertFalse((self.root / "runs" / "invalid-template").exists())
        brief = self.cli("checkpoint", "before-edit", "--brief")
        self.assertIn("合成偏好 A", brief)
        self.assertNotIn("合成偏好 B", brief)
        self.advance("before-edit", *FEATURE)
        self.cli("verify", "before-edit")

    def test_concurrent_sessions_cannot_both_record_against_same_revision(self):
        self.start("bugfix", "shared")

        def report_blocker(evidence):
            # Both workers submit a valid result for the same stage and revision.
            return subprocess.run(
                [sys.executable, "-X", "utf8", "-B", "scripts/checkpoint.py", "shared",
                 "--revision", "0", "--stage", "reproduce", "--outcome", "blocked",
                 "--summary", "等待合成样本", "--evidence", evidence],
                cwd=self.root, capture_output=True, encoding="utf-8", timeout=30,
            )

        evidence = ("synthetic-worker-A", "synthetic-worker-B")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(report_blocker, evidence))
        self.assertEqual(sorted(result.returncode for result in results), [0, 1], results)
        history = self.cli("checkpoint", "shared", "--history")
        for item, result in zip(evidence, results):
            self.assertEqual(item in history, result.returncode == 0)
        self.advance("shared", *BUGFIX)
        self.cli("verify", "shared")


if __name__ == "__main__":
    unittest.main()
