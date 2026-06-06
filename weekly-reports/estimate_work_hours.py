#!/usr/bin/env python3
"""工时评估脚本：根据工作项概述和本周工作总结，使用 LLM 评估工作耗时。"""

import sys
import os
import json
import argparse
import requests
from datetime import date, datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily-reminder"))

import config
from feishu_client import FeishuClient
from reminder import _extract_text


BEIJING_TZ = timezone(timedelta(hours=8))
WK1_MONDAY = date(2026, 1, 5)


def get_last_week_num(today=None):
    """计算上周的 WK 编号（WK1=2026年1月5日起算）。"""
    if today is None:
        today = datetime.now(BEIJING_TZ).date()
    # 上周一
    last_monday = today - timedelta(days=today.weekday() + 7)
    delta = last_monday - WK1_MONDAY
    return f"WK{delta.days // 7 + 1}"


def build_prompt(items):
    """构建批量评估 prompt。items 为 [{"index": i, "概述": ..., "总结": ...}, ...]"""
    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    return f"""你是一个工时评估助手。请根据每个工作项的"工作项概述"和"本周工作总结"，估算该工作本周耗费的工时数（单位：小时）。

评估规则：
- 描述中明确提到天数或小时数的，以描述中声明的时间为准
- 日常例行、维护性工作：0.5-2 小时
- 跨部门协作、多方沟通、会议推进：2-4 小时
- 方案设计、需求分析、深度调研：3-8 小时
- 出差外勤、客户现场拜访、展会支持：按整天 8 小时估算
- 信息不足或两项都为空：返回 0

以下是要评估的工作项列表：
{items_json}

请严格按以下 JSON 数组格式返回评估结果，每个元素包含 index 和 hours：
[{{"index": 0, "hours": 4.5}}, {{"index": 1, "hours": 2.0}}, ...]

只返回 JSON 数组，不要包含其他任何文字、解释或 markdown 格式。"""


# ---- LLM Provider 默认配置 ----
PROVIDER_DEFAULTS = {
    "anthropic": {
        "api_base": "https://api.anthropic.com/v1/messages",
        "model": "claude-sonnet-4-6",
    },
    "openai": {
        "api_base": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o",
    },
    "deepseek": {
        "api_base": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-chat",
    },
}


def _get_llm_config():
    """根据 LLM_PROVIDER 环境变量返回 (api_base, api_key, model)。"""
    provider = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
    api_key = os.environ["LLM_API_KEY"]
    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["deepseek"])
    api_base = os.environ.get("LLM_API_BASE", defaults["api_base"])
    model = os.environ.get("LLM_MODEL", defaults["model"])
    return provider, api_base, api_key, model


def call_llm_anthropic(api_base, api_key, model, prompt):
    """调用 Anthropic Claude API。"""
    resp = requests.post(
        api_base,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"]


def call_llm_openai_compatible(api_base, api_key, model, prompt):
    """调用 OpenAI 兼容 API（含 DeepSeek 等）。"""
    resp = requests.post(
        api_base,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def parse_hours_response(text):
    """从 LLM 返回文本中提取 JSON 数组。"""
    text = text.strip()
    # 尝试去掉可能的 markdown 代码块标记
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if len(lines) > 1 else text
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()
    return json.loads(text)


def chunk_list(lst, n):
    """将列表切分为每块最多 n 个元素的块。"""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def main():
    parser = argparse.ArgumentParser(description="根据工作项概述和总结，用 LLM 评估工时数")
    parser.add_argument("--week", default=None, help="目标周数，如 WK22（与 --auto 二选一）")
    parser.add_argument("--auto", action="store_true", help="自动处理上周（用于定时任务）")
    parser.add_argument("--dry-run", action="store_true", help="只预览评估结果，不实际写入")
    parser.add_argument("--batch-size", type=int, default=10, help="每批评估的记录数（默认 10）")
    args = parser.parse_args()

    if args.auto:
        target_week = get_last_week_num()
        print(f"[INFO] 自动模式：上周={target_week}")
    elif args.week:
        target_week = args.week
    else:
        parser.error("请指定 --week 或 --auto")
        sys.exit(1)

    if "LLM_API_KEY" not in os.environ:
        print("[ERROR] 请设置环境变量 LLM_API_KEY")
        sys.exit(1)

    provider, api_base, api_key, model = _get_llm_config()
    print(f"[INFO] LLM: provider={provider}, model={model}")

    client = FeishuClient()
    tables = client.list_tables()
    print(f"[INFO] 多维表格中的表单: {list(tables.keys())}")

    # 查找"2026周报"表
    weekly_tid = tables.get(config.WEEKLY_REPORT_TABLE_NAME)
    if not weekly_tid:
        for name, tid in tables.items():
            if "周报" in name or "weekly" in name.lower():
                weekly_tid = tid
                print(f"[INFO] 使用匹配到的表单: {name}")
                break
    if not weekly_tid:
        print(f"[ERROR] 未找到包含'周报'的表单，可用表单: {list(tables.keys())}")
        sys.exit(1)

    records = client.get_all_records_with_ids(weekly_tid)
    print(f"[INFO] 共读取 {len(records)} 条记录")

    # 筛选：匹配周数 + 工作耗时为空 + 有内容
    target = []
    for rec in records:
        f = rec["fields"]
        week_label = _extract_text(f.get("周数", "")).strip()
        if week_label != target_week:
            continue
        hours = f.get("工作耗时(小时)")
        if hours is not None and hours != "" and hours != 0:
            continue
        overview = _extract_text(f.get("工作项概述", "")).strip()
        summary = _extract_text(f.get("本周工作总结", "")).strip()
        if not overview and not summary:
            continue
        target.append(rec)

    if not target:
        print(f"[INFO] 没有需要评估工时的记录（周数={args.week}）")
        return

    print(f"[INFO] 找到 {len(target)} 条需评估的记录")

    # 分批处理
    total_estimated = 0
    for batch in chunk_list(target, args.batch_size):
        items = []
        for i, rec in enumerate(batch):
            f = rec["fields"]
            items.append({
                "index": i,
                "概述": _extract_text(f.get("工作项概述", "")).strip(),
                "总结": _extract_text(f.get("本周工作总结", "")).strip(),
            })

        prompt = build_prompt(items)
        print(f"\n[INFO] 评估第 {total_estimated + 1}-{total_estimated + len(batch)} 条...")
        print(f"[DEBUG] Prompt 长度: {len(prompt)} 字符")

        try:
            if provider == "anthropic":
                response_text = call_llm_anthropic(api_base, api_key, model, prompt)
            else:
                response_text = call_llm_openai_compatible(api_base, api_key, model, prompt)
            print(f"[DEBUG] LLM 返回: {response_text[:300]}...")
            results = parse_hours_response(response_text)
        except Exception as e:
            print(f"[ERROR] LLM 调用或解析失败: {e}")
            print(f"[ERROR] 原始返回: {response_text[:500] if 'response_text' in dir() else 'N/A'}")
            continue

        for item in results:
            idx = item["index"]
            hours = float(item["hours"])
            rec = batch[idx]
            f = rec["fields"]
            person = _extract_text(f.get("填写人", "")).strip()
            overview = _extract_text(f.get("工作项概述", "")).strip()
            summary = _extract_text(f.get("本周工作总结", "")).strip()
            print(f"  [{person}] {overview[:40]}... -> {hours}h")

            if not args.dry_run:
                client.update_record(weekly_tid, rec["record_id"], {"工作耗时(小时)": hours})
                print(f"    ✓ 已写入")

        total_estimated += len(batch)

    print(f"\n[DONE] 共评估 {total_estimated} 条记录")

    # 发送飞书单聊通知
    open_id = config.FEISHU_USER_OPEN_ID
    if open_id and not args.dry_run:
        try:
            msg = f"周报工时写入已完成-{target_week}"
            client.send_text_to_user(open_id, msg)
            print(f"[INFO] 已发送飞书通知: {msg}")
        except Exception as e:
            print(f"[WARN] 飞书通知发送失败: {e}")
    elif not open_id:
        print("[WARN] 未配置 FEISHU_USER_OPEN_ID，跳过通知")


if __name__ == "__main__":
    main()
