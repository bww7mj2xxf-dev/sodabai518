#!/usr/bin/env python3
"""日报提醒入口。

用法：
  python main.py                       # 正常执行检查并发送提醒
  python main.py --dry-run             # 仅检查，打印结果，不发送消息
  python main.py --list-chats          # 列出机器人所在群聊，用于查找 chat_id
  python main.py --list-tables         # 列出多维表格中的所有表单
"""

import sys
import traceback
import config
from feishu_client import FeishuClient
from reminder import check_reminders, format_reminder_message


def cmd_dry_run(client):
    """试运行：只打印结果，不发送消息。"""
    print("=" * 50)
    print("[DRY RUN] 试运行模式，不会发送消息")
    print("=" * 50)

    missing = check_reminders(client)

    if not missing:
        print("\n✅ 所有出差人员均已提交日报，无需提醒。")
        return

    msg_json = format_reminder_message(missing)
    if msg_json:
        import json
        content = json.loads(msg_json)
        print(f"\n将发送以下消息到群 {config.FEISHU_CHAT_ID}:\n")
        print(content["text"])


def cmd_remind(client):
    """正常模式：检查并发送提醒。"""
    missing = check_reminders(client)

    if not missing:
        print("[INFO] 无需提醒，任务完成。")
        return

    msg_json = format_reminder_message(missing)
    if not msg_json:
        print("[WARN] 消息格式化为空，跳过发送。")
        return

    client.send_chat_message(config.FEISHU_CHAT_ID, msg_json)
    print(f"[INFO] 已向群 {config.FEISHU_CHAT_ID} 发送提醒消息。")


def cmd_list_chats(client):
    """列出群聊，辅助用户找到 chat_id。"""
    print("获取机器人所在群聊列表...\n")
    try:
        chats = client.list_chats()
    except Exception as e:
        print(f"[ERROR] 获取群列表失败: {e}")
        print("[提示] 请确认应用已添加'机器人'能力，且机器人已被加入目标群。")
        return

    if not chats:
        print("未找到任何群聊。请先将机器人添加到目标飞书群中。")
        return

    print(f"找到 {len(chats)} 个群聊:\n")
    print(f"{'群名称':<30} {'chat_id'}")
    print("-" * 70)
    for c in chats:
        print(f"{c['name']:<30} {c['chat_id']}")


def cmd_list_tables(client):
    """列出多维表格中的所有表单。"""
    print("获取多维表格表单列表...\n")
    tables = client.list_tables()
    if not tables:
        print("未找到任何数据表。")
        return

    print(f"找到 {len(tables)} 个表单:\n")
    print(f"{'表单名称':<30} {'table_id'}")
    print("-" * 60)
    for name, tid in tables.items():
        print(f"{name:<30} {tid}")

    print("\n请确认 config.py 中的表单名称与上表一致。")


def main():
    args = sys.argv[1:]

    client = FeishuClient()

    if "--list-chats" in args:
        cmd_list_chats(client)
        return

    if "--list-tables" in args:
        cmd_list_tables(client)
        return

    if "--dry-run" in args:
        cmd_dry_run(client)
        return

    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    try:
        cmd_remind(client)
    except Exception:
        print("[ERROR] 执行失败:", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
