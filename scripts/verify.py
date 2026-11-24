"""Check the workflow catalog or replay the evidence history of one run."""

import argparse
from contextlib import closing

from harness import cli, load_plans, open_run, read_run


def main():
    parser = argparse.ArgumentParser(description="校验流程配置，或按启动快照检查某次任务是否闭环")
    parser.add_argument("run_id", nargs="?", help="省略时校验当前流程定义")
    args = parser.parse_args()
    if args.run_id is None:
        for name, plan in load_plans().items():
            stages = " → ".join(stage["id"] for stage in plan["stages"])
            print(f"配置通过　{name}　{stages}")
        return
    with closing(open_run(args.run_id)) as db:
        plan, history, index = read_run(db, args.run_id)
    if index != len(plan["stages"]):
        raise ValueError(f"{args.run_id} 尚未完成，当前阶段 {plan['stages'][index]['id']}")
    print(f"记录核验通过　{args.run_id}　{len(plan['stages'])} 个阶段，{len(history)} 条带证据的记录")


if __name__ == "__main__":
    cli(main)
