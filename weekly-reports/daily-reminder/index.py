"""FC3 HTTP 触发器入口 —— 飞书事件回调处理。"""

import json
import base64
import sys
import threading
import traceback

# 将 deps 目录加入 Python 路径（存放 requests 等第三方包）
sys.path.insert(0, "/code/deps")

import config
from feishu_client import FeishuClient
from bot_handler import handle_record_message


def handler(event, context):
    """FC3 HTTP 触发器标准 handler。event 为 bytes，返回响应 dict。"""
    try:
        event_json = json.loads(event)
    except (json.JSONDecodeError, TypeError):
        return _resp(400, {"error": "invalid json"})

    path = event_json.get("rawPath", "/")
    method = event_json.get("requestContext", {}).get("http", {}).get("method", "GET")
    body = _get_body(event_json)

    if path == "/health":
        return _resp(200, {"status": "ok"})

    if path == "/feishu/callback" and method == "POST":
        return _handle_callback(body)

    return _resp(404, {"error": "not found"})


def _get_body(event_json: dict) -> str:
    body = event_json.get("body", "") or ""
    if event_json.get("isBase64Encoded", False):
        body = base64.b64decode(body).decode("utf-8")
    return body


def _resp(status_code: int, data: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(data, ensure_ascii=False),
    }


def _handle_callback(body: str) -> dict:
    try:
        body_json = json.loads(body)
    except json.JSONDecodeError:
        return _resp(400, {"error": "invalid json"})

    # URL 验证
    if "challenge" in body_json:
        return _resp(200, {"challenge": body_json["challenge"]})

    # 兼容 Schema 2.0 和旧版事件格式
    schema = body_json.get("schema", "")
    if schema == "2.0":
        header = body_json.get("header", {})
        event_type = header.get("event_type", "")
        token = header.get("token", "")
    else:
        event_type = body_json.get("event_type", "")
        token = body_json.get("token", "")

    # 验证 token
    if token and token != config.FEISHU_VERIFICATION_TOKEN:
        return _resp(403, {"code": -1, "msg": "invalid token"})

    # 仅处理消息接收事件
    if event_type != "im.message.receive_v1":
        return _resp(200, {"code": 0, "msg": "ok"})

    # 后台线程处理业务逻辑，立即返回 200（满足飞书 3 秒 SLA）
    thread = threading.Thread(
        target=_process_event_thread,
        args=(body_json,),
        daemon=True,
    )
    thread.start()

    return _resp(200, {"code": 0, "msg": "ok"})


def _process_event_thread(event_data: dict):
    try:
        client = FeishuClient()
        handle_record_message(client, event_data)
    except Exception:
        print(f"[ERROR] 后台处理失败:\n{traceback.format_exc()}")
