"""
飞书日报提醒系统配置。
所有敏感信息和可变参数通过环境变量注入，不写入代码。
"""

import os

# --- 飞书应用凭证 ---
FEISHU_APP_ID = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]

# --- 多维表格 ---
BITABLE_APP_TOKEN = os.environ["BITABLE_APP_TOKEN"]

# 三个表单的名称（用于在表格中按名称匹配）
SUPERVISOR_TABLE_NAME = os.environ.get("SUPERVISOR_TABLE_NAME", "日报填写监督")
TRAVEL_TABLE_NAME = os.environ.get("TRAVEL_TABLE_NAME", "出差申请流程")
DAILY_REPORT_TABLE_NAME = os.environ.get("DAILY_REPORT_TABLE_NAME", "海外出差日报")

# --- 字段名（按实际表格字段名配置） ---
# 人员名单表单字段
SUPERVISOR_NAME_FIELD = os.environ.get("SUPERVISOR_NAME_FIELD", "姓名")

# 出差记录表单字段
TRAVEL_PERSON_FIELD = os.environ.get("TRAVEL_PERSON_FIELD", "发起人")
TRAVEL_START_DATE_FIELD = os.environ.get("TRAVEL_START_DATE_FIELD", "开始日期")
TRAVEL_END_DATE_FIELD = os.environ.get("TRAVEL_END_DATE_FIELD", "结束日期")
TRAVEL_STATUS_FIELD = os.environ.get("TRAVEL_STATUS_FIELD", "申请状态")
TRAVEL_STATUS_APPROVED = os.environ.get("TRAVEL_STATUS_APPROVED", "已通过")

# 日报记录表单字段
REPORT_PERSON_FIELD = os.environ.get("REPORT_PERSON_FIELD", "填报人")
REPORT_CONTENT_FIELD = os.environ.get("REPORT_CONTENT_FIELD", "今日工作内容")
REPORT_DATE_FIELD = os.environ.get("REPORT_DATE_FIELD", "填报日期")

# --- 目标群聊 ---
FEISHU_CHAT_ID = os.environ.get("FEISHU_CHAT_ID", "")

# --- 回调机器人配置 ---
FEISHU_VERIFICATION_TOKEN = os.environ.get("FEISHU_VERIFICATION_TOKEN", "yHuzpy9V6ZZGwqAOavE3gfhJGlz88lnH")
RECORD_TABLE_NAME = os.environ.get("RECORD_TABLE_NAME", "任务登记表")
WEEKLY_REPORT_TABLE_NAME = os.environ.get("WEEKLY_REPORT_TABLE_NAME", "2026周报")
FEISHU_USER_OPEN_ID = os.environ.get("FEISHU_USER_OPEN_ID", "")
RECORD_KEYWORDS = os.environ.get("RECORD_KEYWORDS", "记录,记录任务").split(",")

# --- API 地址 ---
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
