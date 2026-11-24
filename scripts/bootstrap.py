"""Create a run with a snapshot of the selected workflow and instructions."""

import argparse
from datetime import datetime
from uuid import uuid4

from harness import cli, create_run, load_plans


def main():
    parser = argparse.ArgumentParser(description="初始化本地任务并冻结阶段简报")
    parser.add_argument("workflow", help="config/workflows.yaml 中的流程名")
    parser.add_argument("--task", required=True, help="任务目标，可含目标仓库和验收条件")
    parser.add_argument("--run-id", help="便于恢复的任务 ID，省略时自动生成")
    args = parser.parse_args()
    plans = load_plans()
    if args.workflow not in plans:
        raise ValueError(f"可用工作流：{', '.join(plans)}")
    run_id = args.run_id
    if run_id is None:
        run_id = f"{datetime.now():%Y%m%d}-{uuid4().hex[:12]}"
    run = create_run(run_id, args.task, plans[args.workflow])
    print(f"已创建 {run_id}，首阶段 {run['stages'][0]['id']}")
    print(f"python scripts/checkpoint.py {run_id} --brief")


if __name__ == "__main__":
    cli(main)
