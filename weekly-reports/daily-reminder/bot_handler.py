"""消息解析、去重、记录创建核心逻辑。"""

import json
import re
import time
import traceback
from collections import OrderedDict

import config
from feishu_client import FeishuClient

# ---- 缓存 ----

_table_id_cache: str | None = None

# ---- 去重：防止飞书重试导致重复记录 ----

_processed_message_ids: OrderedDict[str, float] = OrderedDict()
_MAX_DEDUP_SIZE = 1000
_DEDUP_TTL_SECONDS = 300


def _cleanup_expired():
    now = time.time()
    expired = [mid for mid, ts in _processed_message_ids.items() if now - ts > _DEDUP_TTL_SECONDS]
    for mid in expired:
        del _processed_message_ids[mid]


def is_duplicate(message_id: str) -> bool:
    _cleanup_expired()
    if message_id in _processed_message_ids:
        return True
    _processed_message_ids[message_id] = time.time()
    while len(_processed_message_ids) > _MAX_DEDUP_SIZE:
        _processed_message_ids.popitem(last=False)
    return False


# ---- 消息解析 ----

def parse_record_content(text: str) -> str | None:
    """从消息文本中提取"记录"关键词后的内容，清理前导标点。"""
    for kw in config.RECORD_KEYWORDS:
        idx = text.find(kw)
        if idx == -1:
            continue
        after = text[idx + len(kw):]
        cleaned = re.sub(r'^[\s,，:：]+', '', after).strip()
        if cleaned:
            return cleaned
    return None


# ---- 主处理逻辑 ----

def handle_record_message(client: FeishuClient, event_data: dict) -> None:
    """处理消息事件：解析、去重、写入表格、回复确认。"""
    try:
        event = event_data.get("event", {})
        message = event.get("message", {})
        message_id = message.get("message_id", "")
        chat_id = message.get("chat_id", "")

        if not message_id or not chat_id:
            print("[WARN] 消息缺少 message_id 或 chat_id，跳过")
            return

        # 去重
        if is_duplicate(message_id):
            print(f"[INFO] 重复消息 {message_id}，跳过")
            return

        # 解析消息文本
        content_str = message.get("content", "{}")
        try:
            content_obj = json.loads(content_str)
            text = content_obj.get("text", "")
        except json.JSONDecodeError:
            print(f"[WARN] 无法解析消息内容: {content_str}")
            return

        if not text:
            return

        # 提取"记录"内容
        record_content = parse_record_content(text)
        if not record_content:
            return

        print(f"[INFO] 识别到记录请求: {record_content}")

        # 获取群名称
        chat_name = _get_chat_name(client, chat_id)

        # 查找目标表格（使用缓存减少 API 调用）
        global _table_id_cache
        if _table_id_cache is None:
            tables = client.list_tables()
            _table_id_cache = tables.get(config.RECORD_TABLE_NAME)
        table_id = _table_id_cache
        if not table_id:
            error_msg = f"未找到表格「{config.RECORD_TABLE_NAME}」，请检查表格是否存在。"
            print(f"[ERROR] {error_msg}")
            client.send_chat_message(
                chat_id,
                json.dumps({"text": error_msg}),
            )
            return

        # 写入记录
        now_ms = int(time.time() * 1000)
        fields = {
            "飞书任务内容": record_content,
            "记录时间": now_ms,
            "来源群": chat_name,
        }
        client.create_record(table_id, fields)
        print(f"[INFO] 已写入表格: {record_content}")

        # 回复确认
        client.send_chat_message(
            chat_id,
            json.dumps({"text": f"已记录任务：{record_content}"}),
        )

    except Exception:
        print(f"[ERROR] 处理记录消息失败:\n{traceback.format_exc()}")
        try:
            chat_id = event_data.get("event", {}).get("message", {}).get("chat_id")
            if chat_id:
                client = FeishuClient()
                client.send_chat_message(
                    chat_id,
                    json.dumps({"text": "记录任务时出错，请稍后重试。"}),
                )
        except Exception:
            pass


def _get_chat_name(client: FeishuClient, chat_id: str) -> str:
    try:
        info = client.get_chat_info(chat_id)
        return info.get("name", chat_id)
    except Exception:
        print(f"[WARN] 获取群名称失败: {traceback.format_exc()}")
        return chat_id
