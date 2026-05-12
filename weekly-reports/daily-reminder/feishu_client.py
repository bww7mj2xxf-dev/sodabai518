"""飞书开放平台 API 客户端。"""

import time
import requests
import config


class FeishuClient:
    def __init__(self):
        self._token = None
        self._token_expire_at = 0

    # ---- token ----

    def _ensure_token(self):
        """获取或刷新 tenant_access_token，自动缓存到过期前 5 分钟。"""
        if self._token and time.time() < self._token_expire_at - 300:
            return

        resp = requests.post(
            f"{config.FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": config.FEISHU_APP_ID,
                "app_secret": config.FEISHU_APP_SECRET,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 token 失败: {data}")

        self._token = data["tenant_access_token"]
        self._token_expire_at = time.time() + data.get("expire", 7200)

    def _headers(self):
        self._ensure_token()
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    # ---- 多维表格 ----

    def list_tables(self):
        """列出多维表格下所有数据表，返回 {表名: table_id} 映射。"""
        url = f"{config.FEISHU_API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"列出数据表失败: {data}")

        result = {}
        for item in data.get("data", {}).get("items", []):
            result[item["name"]] = item["table_id"]
        return result

    def get_all_records(self, table_id):
        """读取某个数据表的全部记录，返回字段值列表（自动翻页）。"""
        records = []
        page_token = None

        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token

            url = f"{config.FEISHU_API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/records"
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"读取表格记录失败: {data}")

            for item in data.get("data", {}).get("items", []):
                fields = item.get("fields", {})
                records.append(fields)

            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"].get("page_token")

        return records

    # ---- 消息 ----

    def send_chat_message(self, chat_id, content):
        """向指定群聊发送文本消息。"""
        url = f"{config.FEISHU_API_BASE}/im/v1/messages?receive_id_type=chat_id"
        body = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": content,
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"发送消息失败: {data}")
        return data

    # ---- 辅助：获取群列表（用于查找 chat_id） ----

    def list_chats(self):
        """列出机器人所在的群聊，用于查找目标群的 chat_id。"""
        url = f"{config.FEISHU_API_BASE}/im/v1/chats"
        chats = []
        page_token = None

        while True:
            params = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token

            resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"获取群列表失败: {data}")

            for item in data.get("data", {}).get("items", []):
                chats.append({
                    "chat_id": item["chat_id"],
                    "name": item.get("name", ""),
                })

            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"].get("page_token")

        return chats
