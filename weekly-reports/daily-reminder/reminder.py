"""核心业务逻辑：判断出差未报日报的人员。"""

from datetime import date, datetime, timezone, timedelta
import config


# 北京时间
BEIJING_TZ = timezone(timedelta(hours=8))


def _check_date() -> date:
    """检查日期：周一检查上周五，周二到周五检查前一天。

    周末不运行（由 GitHub Actions cron 控制），所以不考虑周六日的情况。
    """
    today = datetime.now(BEIJING_TZ).date()
    weekday = today.weekday()  # 周一=0, 周日=6
    if weekday == 0:  # 周一 → 检查上周五
        return today - timedelta(days=3)
    return today - timedelta(days=1)  # 周二~周五 → 检查昨天


def _parse_date(value):
    """解析飞书多维表格中的日期字段。

    飞书日期字段返回 Unix 时间戳（毫秒），也可能是 date/datetime 对象。
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=BEIJING_TZ).date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _extract_text(value):
    """从多维表格字段值中提取纯文本。

    某些字段（如人员字段）返回的是列表，每个元素是 {"name": "..."}。
    """
    if value is None:
        return ""
    if isinstance(value, list):
        texts = []
        for item in value:
            if isinstance(item, dict):
                texts.append(item.get("name", item.get("text", str(item))))
            else:
                texts.append(str(item))
        return ", ".join(texts)
    if isinstance(value, dict):
        return value.get("name", value.get("text", str(value)))
    return str(value)


def check_reminders(client):
    """主逻辑：返回需要提醒的人员列表。"""
    check_date = _check_date()
    print(f"[INFO] 检查日期: {check_date}（昨日）")

    # 1. 获取三个表单的 table_id
    tables = client.list_tables()
    print(f"[INFO] 多维表格中的表单: {list(tables.keys())}")

    supervisor_tid = tables.get(config.SUPERVISOR_TABLE_NAME)
    travel_tid = tables.get(config.TRAVEL_TABLE_NAME)
    report_tid = tables.get(config.DAILY_REPORT_TABLE_NAME)

    missing = []
    for label, tid in [
        ("人员名单", supervisor_tid),
        ("出差记录", travel_tid),
        ("日报记录", report_tid),
    ]:
        if not tid:
            missing.append(label)

    if missing:
        available = ", ".join(tables.keys())
        raise RuntimeError(
            f"未找到表单: {', '.join(missing)}。"
            f"当前多维表格中的表单有: {available}"
        )

    # 2. 读取被监督人员名单
    supervisor_records = client.get_all_records(supervisor_tid)
    supervisor_names = set()
    for rec in supervisor_records:
        name = _extract_text(rec.get(config.SUPERVISOR_NAME_FIELD, "")).strip()
        if name:
            supervisor_names.add(name)
    print(f"[INFO] 被监督人员 ({len(supervisor_names)} 人): {supervisor_names}")

    if not supervisor_names:
        print("[WARN] 人员名单为空，无需检查。")
        return []

    # 3. 读取出差记录，筛选"昨天在出差中"且"申请状态=已通过"的人员
    travel_records = client.get_all_records(travel_tid)
    traveling_persons = {}  # name -> (start_date, end_date)

    for rec in travel_records:
        person = _extract_text(rec.get(config.TRAVEL_PERSON_FIELD, "")).strip()
        if person not in supervisor_names:
            continue

        # 只取"已通过"的申请
        status = _extract_text(rec.get(config.TRAVEL_STATUS_FIELD, "")).strip()
        if status != config.TRAVEL_STATUS_APPROVED:
            continue

        start = _parse_date(rec.get(config.TRAVEL_START_DATE_FIELD))
        end = _parse_date(rec.get(config.TRAVEL_END_DATE_FIELD))

        if start is None or end is None:
            continue

        if start <= check_date <= end:
            traveling_persons[person] = (start, end)

    print(f"[INFO] 昨天在出差中的被监督人员 ({len(traveling_persons)} 人): {list(traveling_persons.keys())}")

    if not traveling_persons:
        print("[INFO] 昨日无出差人员，无需提醒。")
        return []

    # 4. 读取日报记录，筛选"昨天已提交"的人员
    report_records = client.get_all_records(report_tid)
    reported_persons = set()

    for rec in report_records:
        person = _extract_text(rec.get(config.REPORT_PERSON_FIELD, "")).strip()
        content = _extract_text(rec.get(config.REPORT_CONTENT_FIELD, "")).strip()
        report_date = _parse_date(rec.get(config.REPORT_DATE_FIELD))

        if not person or not content:
            continue
        if report_date != check_date:
            continue

        reported_persons.add(person)

    print(f"[INFO] 昨日已提交日报的人员 ({len(reported_persons)} 人): {reported_persons}")

    # 5. 找出差中但昨日未报日报的人员
    missing_persons = []
    for person in traveling_persons:
        if person not in reported_persons:
            start, end = traveling_persons[person]
            missing_persons.append((person, start, end))

    print(f"[INFO] 未报日报人员 ({len(missing_persons)} 人): {[p[0] for p in missing_persons]}")
    return missing_persons


def format_reminder_message(missing_persons):
    """将未报人员列表格式化为飞书群消息文本。"""
    if not missing_persons:
        return None

    # 飞书消息 content 需要是 JSON 字符串
    import json

    lines = ["📋 日报未提交提醒\n"]
    lines.append("以下同事昨日在出差中但未提交日报：\n")
    for person, start, end in missing_persons:
        lines.append(f"• {person}（出差：{start}～{end}）")
    lines.append("\n请尽快提交日报，谢谢配合！")

    text = "\n".join(lines)
    return json.dumps({"text": text})
