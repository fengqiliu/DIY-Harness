"""Inspect a run or append a single stage outcome under a SQLite transaction."""

import argparse
from contextlib import closing
import json

from harness import OUTCOMES, advance, cli, nonempty, now, open_run, read_run, text_list


def print_event(event):
    print(f"#{event['seq']}  {event['recorded']}  {event['stage']} / {event['outcome']}")
    print(f"  {event['summary']}")
    for item in event["evidence"]:
        print(f"  · {item}")


def print_status(plan, history, index):
    print(f"{plan['run_id']} | {plan['title']} | 修订 {len(history)}")
    print(f"目标　{plan['task']}")
    if index == len(plan["stages"]):
        print("已完成全部阶段")
    else:
        stage = plan["stages"][index]
        print(f"当前阶段　{stage['id']} | {stage['role']} | {stage['skill']} | {stage['model']}")
        print(f"交付要求　{stage['deliverable']}")
        if history and history[-1]["outcome"] != "pass":
            last = history[-1]
            print(f"上次结果　{last['stage']} / {last['outcome']}　{last['summary']}")


def print_brief(plan, history, index):
    if index == len(plan["stages"]):
        return
    stage = plan["stages"][index]
    print(f"\n{stage['role_text']}\n\n{stage['skill_text']}")
    if history:
        print("\n## 最近交接（完整记录见 --history）")
        print_event(history[-1])
    labels = {"within_scope": "已授权范围内可执行", "confirm_if_unauthorized": "缺少授权时先确认",
              "data_handling": "资料处理"}
    print("\n## 权限约定")
    for key, lines in plan["permissions"].items():
        print(labels.get(key, key))
        for line in lines:
            print(f"- {line}")
    for name, content in plan["context"].items():
        print(f"\n--- {name} ---\n{content}")


def main():
    parser = argparse.ArgumentParser(description="查看阶段、恢复上下文或登记一次实际工作结果")
    parser.add_argument("run_id")
    view = parser.add_mutually_exclusive_group()
    view.add_argument("--history", action="store_true", help="查看全部交接和证据")
    view.add_argument("--brief", action="store_true", help="查看冻结的当前阶段完整指引")
    parser.add_argument("--stage", help="执行时看到的阶段 ID")
    parser.add_argument("--outcome", choices=OUTCOMES)
    parser.add_argument("--summary", help="本次观察或阻塞原因")
    parser.add_argument("--evidence", action="append", help="证据引用或观察值，可重复")
    parser.add_argument("--revision", type=int, help="仅当修订号与开始工作时一致才登记")
    args = parser.parse_args()
    fields = (args.stage, args.outcome, args.summary, args.evidence, args.revision)
    write = any(field is not None for field in fields)
    if write:
        if args.history or args.brief:
            parser.error("查看详情与登记结果请分别执行")
        if not args.stage or not args.outcome:
            parser.error("登记结果需要 --stage 和 --outcome")
        summary = nonempty(args.summary, "结论 --summary")
        evidence = text_list(args.evidence, "证据 --evidence")

    with closing(open_run(args.run_id, write=write)) as db, db:
        if write:
            db.execute("BEGIN IMMEDIATE")
        plan, history, index = read_run(db, args.run_id)
        if write:
            if args.revision is not None and args.revision != len(history):
                raise ValueError(f"修订已变化，当前为 {len(history)}，请先查看最新交接")
            index = advance(plan["stages"], index, args.stage, args.outcome)
            event = {"seq": len(history) + 1, "stage": args.stage, "outcome": args.outcome,
                     "summary": summary, "evidence": evidence, "recorded": now()}
            db.execute("""INSERT INTO events (seq, stage, outcome, summary, evidence, recorded)
                          VALUES (:seq, :stage, :outcome, :summary, :evidence, :recorded)""",
                       {**event, "evidence": json.dumps(evidence, ensure_ascii=False)})
            history.append(event)
    print_status(plan, history, index)
    if args.history:
        for event in history:
            print_event(event)
    if args.brief:
        print_brief(plan, history, index)


if __name__ == "__main__":
    cli(main)
