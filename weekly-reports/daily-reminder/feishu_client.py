"""飞书开放平台 API 客户端。"""

import json
import os
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

    # ---- 群信息 ----

    def get_chat_info(self, chat_id):
        """获取群聊信息，返回名称等。"""
        url = f"{config.FEISHU_API_BASE}/im/v1/chats/{chat_id}"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取群信息失败: {data}")
        return data.get("data", {})

    # ---- 多维表格写入 ----

    def create_record(self, table_id, fields):
        """在指定数据表中创建一条记录。fields 为 {字段名: 值} 字典。"""
        url = f"{config.FEISHU_API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/records"
        body = {"fields": fields}
        resp = requests.post(url, headers=self._headers(), json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"创建记录失败: {data}")
        return data

    # ---- 文件上传与私聊 ----

    def upload_file_to_im(self, file_path):
        """上传文件到飞书 IM，返回 file_key。"""
        url = f"{config.FEISHU_API_BASE}/im/v1/files"
        headers = {"Authorization": self._headers()["Authorization"]}
        file_name = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            resp = requests.post(
                url,
                headers=headers,
                files={"file": (file_name, f, "application/octet-stream")},
                data={
                    "file_type": "stream",
                    "file_name": file_name,
                },
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"上传文件到IM失败: {data}")
        return data["data"]["file_key"]

    def send_file_to_user(self, open_id, file_key):
        """私发文件消息给指定用户。
        open_id: 用户的 open_id
        file_key: upload_file_to_im 返回的 file_key
        """
        url = f"{config.FEISHU_API_BASE}/im/v1/messages?receive_id_type=open_id"
        body = {
            "receive_id": open_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}),
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"发送文件消息失败: {data}")
        return data

    def send_file_to_chat(self, chat_id, file_key):
        """发文件消息到群聊。
        chat_id: 群聊 ID
        file_key: upload_file_to_im 返回的 file_key
        """
        url = f"{config.FEISHU_API_BASE}/im/v1/messages?receive_id_type=chat_id"
        body = {
            "receive_id": chat_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}),
        }
        resp = requests.post(url, headers=self._headers(), json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"发送文件到群聊失败: {data}")
        return data

    # ---- 云盘 ----

    def upload_to_drive(self, file_path, folder_token, title=None):
        """上传文件到飞书云盘指定文件夹。"""
        if title is None:
            title = os.path.basename(file_path)
        url = f"{config.FEISHU_API_BASE}/drive/v1/files/upload_all"
        headers = {"Authorization": self._headers()["Authorization"]}
        with open(file_path, "rb") as f:
            resp = requests.post(
                url,
                headers=headers,
                files={"file": (title, f, "application/octet-stream")},
                data={
                    "file_name": title,
                    "parent_type": "explorer",
                    "parent_node": folder_token,
                },
                timeout=60,
            )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"上传云盘失败: {data}")
        return data.get("data", {}).get("file_token", "")

    def get_user_open_id(self, email=None, mobile=None):
        """通过邮箱或手机号查询用户 open_id。"""
        url = f"{config.FEISHU_API_BASE}/contact/v3/users/batch_get_id"
        body = {}
        if email:
            body["emails"] = [email]
        elif mobile:
            body["mobiles"] = [mobile]
        else:
            raise ValueError("需要提供 email 或 mobile")
        resp = requests.post(url, headers=self._headers(), json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"查询用户ID失败: {data}")
        user_list = data.get("data", {}).get("user_list", [])
        if user_list:
            return user_list[0].get("user_id", "")
        return ""

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
