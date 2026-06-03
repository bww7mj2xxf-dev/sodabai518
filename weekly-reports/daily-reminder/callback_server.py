"""飞书事件回调 HTTP 服务。部署在阿里云 FC3，通过 gunicorn 运行。"""

import json
import threading
import time
import traceback

from flask import Flask, request, jsonify

import config
from feishu_client import FeishuClient
from bot_handler import handle_record_message

app = Flask(__name__)


@app.route("/feishu/callback", methods=["POST"])
def feishu_callback():
    """飞书事件订阅回调入口。"""

    body = request.get_data(as_text=True)
    try:
        body_json = json.loads(body)
    except json.JSONDecodeError:
        return jsonify({"code": -1, "msg": "invalid json"}), 400

    # URL 验证（challenge 响应）
    if "challenge" in body_json:
        return jsonify({"challenge": body_json["challenge"]})

    # 兼容 Schema 2.0 和旧版事件格式
    schema = body_json.get("schema", "")
    if schema == "2.0":
        header = body_json.get("header", {})
        event_type = header.get("event_type", "")
        token = header.get("token", "")
    else:
        event_type = body_json.get("event_type", "")
        token = body_json.get("token", "")

    # 验证 verification token
    if token and token != config.FEISHU_VERIFICATION_TOKEN:
        return jsonify({"code": -1, "msg": "invalid token"}), 403

    # 仅处理消息接收事件
    if event_type != "im.message.receive_v1":
        return jsonify({"code": 0, "msg": "ok"})

    # 后台线程异步处理业务逻辑，立即返回 200
    thread = threading.Thread(
        target=_process_event_thread,
        args=(body_json,),
        daemon=True,
    )
    thread.start()

    return jsonify({"code": 0, "msg": "ok"})


def _process_event_thread(event_data: dict):
    try:
        client = FeishuClient()
        handle_record_message(client, event_data)
    except Exception:
        print(f"[ERROR] 后台处理失败:\n{traceback.format_exc()}")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": int(time.time())})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000, debug=True)
