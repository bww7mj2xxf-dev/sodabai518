# 飞书群出差日报自动提醒

每天早上9:00自动检查：指定人员是否在出差中但未提交日报，并在飞书群内发送提醒。

## 工作流程

```
定时触发（9:00）
    → 读取多维表格"日报填写监督"（人员名单）
    → 读取"出差申请流程"（今日出差中的人员）
    → 读取"海外出差日报"（今日已提交日报的人员）
    → 对比出差人员 VS 已报人员
    → 在飞书群发送未报人员提醒
```

## 前置准备

### 1. 飞书开放平台应用

确保已在[飞书开放平台](https://open.feishu.cn/)创建自建应用，并：

- **添加"机器人"能力**（应用功能 → 机器人）
- **配置权限**（权限管理）：
  - `bitable:app` — 多维表格读取
  - `im:message:send_by_bot` — 发送群消息
  - `im:resource` — 获取群信息
- **发布应用**（版本管理与发布 → 创建版本并发布，管理员审核通过）
- 将机器人添加到目标飞书群

### 2. 获取 chat_id（目标群 ID）

运行以下命令列出机器人所在的群：

```bash
export FEISHU_APP_ID=cli_a969c16373385cce
export FEISHU_APP_SECRET=CBjRAvbipEGxEDCrctNV7Xd1vWXPs8wO
export BITABLE_APP_TOKEN=HTVFwp6hoignhIkPPegc36itnHh
export FEISHU_CHAT_ID=placeholder

cd weekly-reports/daily-reminder
pip install -r requirements.txt
python main.py --list-chats
```

从输出中找到目标群的 `chat_id`。

### 3. 确认表单名称

运行以下命令确认多维表格中的表单名称是否匹配：

```bash
python main.py --list-tables
```

如实际名称与代码中不一致，通过环境变量覆盖：
- `SUPERVISOR_TABLE_NAME`（默认："日报填写监督"）
- `TRAVEL_TABLE_NAME`（默认："出差申请流程"）
- `DAILY_REPORT_TABLE_NAME`（默认："海外出差日报"）

## 本地测试

```bash
# 试运行（只检查，不发消息）
python main.py --dry-run

# 正常执行（检查并发送群消息）
python main.py
```

## 定时部署（GitHub Actions）

### 1. 推送代码到 GitHub

将项目推送到 GitHub 仓库。

### 2. 配置 Secrets

在 GitHub 仓库 → Settings → Secrets and variables → Actions → New repository secret 中添加：

| Secret 名称 | 值 |
|---|---|
| `FEISHU_APP_ID` | `cli_a969c16373385cce` |
| `FEISHU_APP_SECRET` | `CBjRAvbipEGxEDCrctNV7Xd1vWXPs8wO` |
| `BITABLE_APP_TOKEN` | `HTVFwp6hoignhIkPPegc36itnHh` |
| `FEISHU_CHAT_ID` | （你获取到的 chat_id） |

### 3. 触发方式

- **自动**：工作日每天早上 9:00（北京时间）自动执行
- **手动**：在 GitHub Actions → Daily Report Reminder → Run workflow

## 配置项说明

所有配置通过环境变量管理，以下是完整列表：

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `FEISHU_APP_ID` | 应用 App ID | 必填 |
| `FEISHU_APP_SECRET` | 应用 App Secret | 必填 |
| `BITABLE_APP_TOKEN` | 多维表格 ID（URL 中提取） | 必填 |
| `FEISHU_CHAT_ID` | 目标群 chat_id | 必填 |
| `SUPERVISOR_TABLE_NAME` | 人员名单表单名 | 日报填写监督 |
| `TRAVEL_TABLE_NAME` | 出差记录表单名 | 出差申请流程 |
| `DAILY_REPORT_TABLE_NAME` | 日报记录表单名 | 海外出差日报 |
| `SUPERVISOR_NAME_FIELD` | 姓名字段名 | 姓名 |
| `TRAVEL_PERSON_FIELD` | 出差人员字段名 | 发起人 |
| `TRAVEL_START_DATE_FIELD` | 开始日期字段名 | 开始日期 |
| `TRAVEL_END_DATE_FIELD` | 结束日期字段名 | 结束日期 |
| `REPORT_PERSON_FIELD` | 填报人字段名 | 填报人 |
| `REPORT_CONTENT_FIELD` | 工作内容字段名 | 今日工作内容 |
| `REPORT_DATE_FIELD` | 填报日期字段名 | 填报日期 |
