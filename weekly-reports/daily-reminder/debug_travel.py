import json, sys
sys.path.insert(0, '.')
from feishu_client import FeishuClient
from reminder import _check_date, _parse_date, _extract_text
import config

client = FeishuClient()
tables = client.list_tables()
travel_tid = tables[config.TRAVEL_TABLE_NAME]
report_tid = tables[config.DAILY_REPORT_TABLE_NAME]
supervisor_tid = tables[config.SUPERVISOR_TABLE_NAME]

check_date = _check_date()
print(f"检查日期: {check_date}\n")

# 读被监督人员
supervisor_records = client.get_all_records(supervisor_tid)
supervisor_names = set()
for rec in supervisor_records:
    name = _extract_text(rec.get(config.SUPERVISOR_NAME_FIELD, "")).strip()
    if name:
        supervisor_names.add(name)

# 读出差记录
print("=" * 70)
print("【出差申请流程】所有记录：")
print("=" * 70)
travel_records = client.get_all_records(travel_tid)
for rec in travel_records:
    person = _extract_text(rec.get(config.TRAVEL_PERSON_FIELD, "")).strip()
    status = _extract_text(rec.get(config.TRAVEL_STATUS_FIELD, "")).strip()
    start = _parse_date(rec.get(config.TRAVEL_START_DATE_FIELD))
    end = _parse_date(rec.get(config.TRAVEL_END_DATE_FIELD))
    in_supervisor = "✓" if person in supervisor_names else "✗"
    in_range = "✓" if start and end and start <= check_date <= end else "✗"
    status_ok = "✓" if status == config.TRAVEL_STATUS_APPROVED else "✗"
    print(f"\n  发起人: {person} (被监督: {in_supervisor})")
    print(f"  申请状态: {status} (已通过: {status_ok})")
    print(f"  开始日期: {start} | 结束日期: {end}")
    print(f"  日期判断: {start} <= {check_date} <= {end} ? → {in_range}")
    print(f"  原始字段: {json.dumps(rec, ensure_ascii=False, default=str)[:300]}")

# 读日报记录 - 只看李星云和昨天的
print("\n" + "=" * 70)
print("【海外出差日报】昨日记录（仅展示李星云相关）：")
print("=" * 70)
report_records = client.get_all_records(report_tid)
found = False
for rec in report_records:
    person = _extract_text(rec.get(config.REPORT_PERSON_FIELD, "")).strip()
    report_date = _parse_date(rec.get(config.REPORT_DATE_FIELD))
    content = _extract_text(rec.get(config.REPORT_CONTENT_FIELD, "")).strip()
    if person == "李星云" and report_date == check_date:
        found = True
        print(f"\n  填报人: {person}")
        print(f"  填报日期: {report_date}")
        print(f"  今日工作内容: {content[:200]}")
if not found:
    print(f"\n  李星云在 {check_date} 无日报记录")
