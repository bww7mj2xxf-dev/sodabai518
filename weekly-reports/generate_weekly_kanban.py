#!/usr/bin/env python3
"""海外增长业务中心 - 周工作看板生成器"""

import sys
import os
import re
import json
sys.path.insert(0, '/Users/zhongqiongwei/Documents/trae_projects/1/weekly-reports/daily-reminder')

from datetime import date, datetime, timezone, timedelta
from collections import defaultdict
import config
from feishu_client import FeishuClient
from reminder import _parse_date, _extract_text

BEIJING_TZ = timezone(timedelta(hours=8))

# 姓名别名映射
NAME_ALIAS = {"肖霞": "小白"}

# 地理位置坐标映射（用于地图展示）
LOCATION_COORDS = {
    'din daeng': (13.7666, 100.5527),
    'bangkok': (13.7563, 100.5018),
    'thailand': (13.7563, 100.5018),
    '泰国': (13.7563, 100.5018),
    'ratchada': (13.7563, 100.5657),
    'amanta': (13.7563, 100.5657),
    '拉查达': (13.7563, 100.5657),
    'bang kapi': (13.7667, 100.6333),
    'huai khwang': (13.7768, 100.5737),
    'chaturathit': (13.7712, 100.6228),
    'manila': (14.5995, 120.9842),
    'philippines': (14.5995, 120.9842),
    '菲律宾': (14.5995, 120.9842),
    'post proper': (14.5842, 121.0417),
    'highway hills': (14.5778, 121.0472),
    'kabayanan': (14.5833, 121.0333),
    'addition hills': (14.5944, 121.0417),
    'mandaluyong': (14.5833, 121.0333),
    'makati': (14.5547, 121.0244),
    'jakarta': (-6.2088, 106.8456),
    'indonesia': (-6.2088, 106.8456),
    '印尼': (-6.2088, 106.8456),
    'kuala lumpur': (3.1390, 101.6870),
    'malaysia': (3.1390, 101.6870),
    '马来西亚': (3.1390, 101.6870),
    '马来': (3.1390, 101.6870),
    'brazil': (-23.5505, -46.6333),
    '巴西': (-23.5505, -46.6333),
    'sao paulo': (-23.5505, -46.6333),
    'russia': (55.7558, 37.6173),
    '俄罗斯': (55.7558, 37.6173),
    'moscow': (55.7558, 37.6173),
    'vietnam': (10.8231, 106.6297),
    '越南': (10.8231, 106.6297),
    'ho chi minh': (10.8231, 106.6297),
    'korea': (37.5665, 126.9780),
    '韩国': (37.5665, 126.9780),
    'seoul': (37.5665, 126.9780),
}

# 国家/地区关键词（用于区域业务进度提取）
REGION_KEYWORDS = [
    '泰国', '菲律宾', '印尼', '印度尼西亚', '马来西亚', '马来',
    '巴西', '俄罗斯', '哥伦比亚', '越南', '韩国',
    '阿塞拜疆', '委内瑞拉', '阿根廷', '智利', '秘鲁',
    '希腊', '葡萄牙', '以色列', '南非', '丹麦',
    '欧洲', '中东非', '南美', '东南亚', '北美',
    '哈萨克斯坦', '厄瓜多尔', '墨西哥', '巴拿马', '乌拉圭',
    '阿联酋', '沙特', '土耳其', '埃及', '尼日利亚',
    '日本', '印度', '澳大利亚', '英国', '法国', '德国', '意大利', '西班牙',
]

REGION_ALIAS = {
    '印度尼西亚': '印尼',
    '马来': '马来西亚',
    '中东非': '中东/非洲',
}


def apply_alias(name):
    return NAME_ALIAS.get(name, name)


def geocode(location_text):
    """将地理位置文本解析为经纬度坐标"""
    if not location_text:
        return None
    text_lower = location_text.lower().strip()
    for key, coords in LOCATION_COORDS.items():
        if key in text_lower:
            return coords
    return None


def extract_regions(text):
    """从文本中提取国家/地区名称"""
    found = set()
    if not text:
        return found
    for kw in REGION_KEYWORDS:
        if kw in text:
            name = REGION_ALIAS.get(kw, kw)
            found.add(name)
    return found


def get_week_range(target_date=None):
    """获取指定日期所在周的周一至周五日期范围"""
    if target_date is None:
        target_date = datetime.now(BEIJING_TZ).date()

    weekday = target_date.weekday()
    monday = target_date - timedelta(days=weekday)
    friday = monday + timedelta(days=4)

    wk1_monday = date(2026, 1, 5)
    delta = monday - wk1_monday
    week_num = f"WK{delta.days // 7 + 1}"
    return monday, friday, week_num


def fetch_data(client, target_week_num=None):
    """从飞书多维表格获取所有数据"""
    tables = client.list_tables()
    print(f"[INFO] 多维表格中的表单: {list(tables.keys())}")

    supervisor_tid = tables.get(config.SUPERVISOR_TABLE_NAME)
    travel_tid = tables.get(config.TRAVEL_TABLE_NAME)
    report_tid = tables.get(config.DAILY_REPORT_TABLE_NAME)

    weekly_report_tid = None
    for name, tid in tables.items():
        if '周报' in name or 'weekly' in name.lower():
            weekly_report_tid = tid
            break

    # 读取人员名单
    supervisor_records = client.get_all_records(supervisor_tid) if supervisor_tid else []
    staff = {}
    raw_to_display = {}
    for rec in supervisor_records:
        raw_name = _extract_text(rec.get(config.SUPERVISOR_NAME_FIELD, "")).strip()
        if raw_name:
            display_name = apply_alias(raw_name)
            raw_to_display[raw_name] = display_name
            staff[display_name] = {
                'name': display_name,
                'role': _extract_text(rec.get('姓名.职务', '')).strip() or '未知角色',
                'department': _extract_text(rec.get('姓名.部门', '')).strip() or ''
            }

    def resolve_person(name):
        name = name.strip()
        if name in raw_to_display:
            return raw_to_display[name]
        for raw, disp in raw_to_display.items():
            if raw in name or name in raw:
                return disp
        return None

    # 读取出差记录
    travel_records = client.get_all_records(travel_tid) if travel_tid else []
    traveling = defaultdict(list)
    for rec in travel_records:
        raw_person = _extract_text(rec.get(config.TRAVEL_PERSON_FIELD, "")).strip()
        person = resolve_person(raw_person)
        if not person or person not in staff:
            continue
        status = _extract_text(rec.get(config.TRAVEL_STATUS_FIELD, "")).strip()
        if status != config.TRAVEL_STATUS_APPROVED:
            continue
        start = _parse_date(rec.get(config.TRAVEL_START_DATE_FIELD))
        end = _parse_date(rec.get(config.TRAVEL_END_DATE_FIELD))
        if start and end:
            traveling[person].append((start, end))

    # 读取日报记录（含地理位置）
    report_records = client.get_all_records(report_tid) if report_tid else []
    daily_reports = defaultdict(dict)
    daily_geo = defaultdict(dict)  # person -> {date: (geo_text, lat, lng)}
    for rec in report_records:
        raw_person = _extract_text(rec.get(config.REPORT_PERSON_FIELD, "")).strip()
        person = resolve_person(raw_person)
        if not person or person not in staff:
            continue
        report_date = _parse_date(rec.get(config.REPORT_DATE_FIELD))
        content = _extract_text(rec.get(config.REPORT_CONTENT_FIELD, "")).strip()
        geo_text = _extract_text(rec.get('地理位置', '')).strip()
        if report_date and content:
            daily_reports[person][report_date] = content
            if geo_text:
                coords = geocode(geo_text)
                daily_geo[person][report_date] = {'text': geo_text, 'coords': coords}

    # 读取周报记录
    weekly_reports = {}
    if weekly_report_tid:
        weekly_records = client.get_all_records(weekly_report_tid)
        for rec in weekly_records:
            raw_person = _extract_text(rec.get('填写人', '')).strip()
            person = resolve_person(raw_person)
            if not person or person not in staff:
                continue
            week_label = _extract_text(rec.get('周数', '')).strip()
            if not week_label:
                continue
            if target_week_num and week_label != target_week_num:
                continue
            content = _extract_text(rec.get('本周工作总结', '')).strip()
            if content:
                if person in weekly_reports:
                    weekly_reports[person]['content'] += '\n' + content
                else:
                    weekly_reports[person] = {
                        'week_label': week_label,
                        'content': content
                    }

    return staff, traveling, daily_reports, weekly_reports, daily_geo


def analyze_week_data(staff, traveling, daily_reports, weekly_reports, monday, friday):
    """分析指定周的数据"""
    week_dates = [monday + timedelta(days=i) for i in range(5)]

    result = []
    total_weekly = 0
    total_daily = 0
    total_daily_expected = 0
    traveling_count = 0

    for name, info in staff.items():
        person_data = {
            'name': name,
            'role': info['role'],
            'department': info['department'],
            'has_weekly': name in weekly_reports,
            'weekly_content': weekly_reports.get(name, {}).get('content', ''),
            'is_traveling': False,
            'travel_periods': [],
            'daily_status': {},
            'daily_contents': {},
            'daily_count': 0,
            'traveling_days': 0,
            'daily_geo': {}
        }

        if name in traveling:
            for start, end in traveling[name]:
                if start <= friday and end >= monday:
                    person_data['is_traveling'] = True
                    person_data['travel_periods'].append((start, end))
                    if start <= monday and end >= friday:
                        traveling_count += 1

        if person_data['is_traveling']:
            travel_days = 0
            for d in week_dates:
                for start, end in person_data['travel_periods']:
                    if start <= d <= end:
                        travel_days += 1
                        break
            person_data['traveling_days'] = travel_days
        else:
            person_data['traveling_days'] = 0

        for d in week_dates:
            is_travel_day = False
            if person_data['is_traveling']:
                for start, end in person_data['travel_periods']:
                    if start <= d <= end:
                        is_travel_day = True
                        break

            if d in daily_reports.get(name, {}):
                person_data['daily_status'][d] = 'done'
                person_data['daily_contents'][d] = daily_reports[name][d]
                person_data['daily_count'] += 1
                total_daily += 1
            elif is_travel_day:
                person_data['daily_status'][d] = 'miss'
            else:
                person_data['daily_status'][d] = 'na'

        if person_data['is_traveling']:
            total_daily_expected += person_data['traveling_days']

        if person_data['has_weekly']:
            total_weekly += 1

        result.append(person_data)

    return result, {
        'total_staff': len(staff),
        'total_weekly': total_weekly,
        'total_daily': total_daily,
        'total_daily_expected': total_daily_expected,
        'traveling_count': traveling_count
    }


def build_travel_routes_html(person_data_list, daily_geo_data, week_dates):
    """生成出差路线时间矩阵表"""
    colors = ['#F2D25E', '#5CAB7E', '#E05555', '#6CB4EE', '#FF9F43', '#A29BFE', '#FD79A8']
    person_colors = {}
    for i, p in enumerate(person_data_list):
        if p['is_traveling']:
            person_colors[p['name']] = colors[i % len(colors)]

    day_labels = ['周一', '周二', '周三', '周四', '周五']

    travelers = [p for p in person_data_list if p['is_traveling']]
    if not travelers:
        return '<div class="section-title">本周出差路线</div><div style="color:#8A813C;font-size:13px;padding:12px;">本周无出差人员或缺少地理位置数据</div>'

    matrix_rows = []
    for p in travelers:
        name = p['name']
        color = person_colors[name]
        cells = []
        prev_city = None
        for i, d in enumerate(week_dates):
            geo = daily_geo_data.get(name, {}).get(d)
            if geo and geo.get('coords'):
                city = _short_city(geo['text'])
                if city == prev_city:
                    cells.append(f'<td class="tm-same">同左</td>')
                else:
                    cells.append(f'<td class="tm-city">{city}</td>')
                prev_city = city
            else:
                cells.append('<td class="tm-na">-</td>')
                prev_city = None

        name_safe = name.replace('&', '&amp;').replace('<', '&lt;')
        matrix_rows.append(f'''
        <tr>
            <td><span class="tm-dot" style="background:{color};"></span>{name_safe}</td>
            {''.join(cells)}
        </tr>''')

    header_cells = ''.join([f'<th>{day_labels[i]}<br><span style="font-size:10px;color:#8A813C;">{d.strftime("%m/%d")}</span></th>' for i, d in enumerate(week_dates)])

    return f'''
    <div class="section-title">本周出差路线</div>
    <div style="overflow-x:auto;margin:8px 0;">
    <table class="time-matrix">
    <thead><tr><th style="width:80px;"></th>{header_cells}</tr></thead>
    <tbody>{''.join(matrix_rows)}</tbody>
    </table>
    </div>
    <style>
    .time-matrix {{ width:100%; border-collapse:collapse; font-size:12px; }}
    .time-matrix th {{ background:#3B5042; color:#F2D25E; padding:8px 10px; border:1px solid #486C55; text-align:center; font-size:13px; }}
    .time-matrix td {{ padding:8px 10px; border:1px solid #486C55; text-align:center; background:#3B5042; color:#FDFAEC; font-size:12px; white-space:nowrap; }}
    .tm-dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:6px; }}
    .tm-na {{ color:#8A813C; }}
    .tm-city {{ font-weight:600; }}
    .tm-same {{ color:#8A813C; font-style:italic; }}
    @media (max-width:768px) {{ .time-matrix {{ font-size:11px; }} .time-matrix td,.time-matrix th {{ padding:6px; }} }}
    </style>'''


def _short_city(geo_text):
    """从地理位置文本提取城市简称"""
    if not geo_text:
        return '未知'
    text = geo_text.strip()
    # 常见地点简写
    mapping = {
        'din daeng': '曼谷·Din Daeng',
        'bangkok': '曼谷',
        'bang kapi': '曼谷·Bang Kapi',
        'huai khwang': '曼谷·Huai Khwang',
        'chaturathit': '曼谷·Chaturathit',
        'ratchada': '曼谷·Ratchada',
        'amanta': '曼谷·Ratchada',
        '拉查达': '曼谷·Ratchada',
        'thailand': '曼谷',
        'post proper': '马尼拉·Post Proper',
        'highway hills': '马尼拉·Highway Hills',
        'kabayanan': '马尼拉·Kabayanan',
        'addition hills': '马尼拉·Addition Hills',
        'manila': '马尼拉',
        'philippines': '马尼拉',
        'jakarta': '雅加达',
        'indonesia': '雅加达',
        'kuala lumpur': '吉隆坡',
        'malaysia': '吉隆坡',
        'saigon': '胡志明市',
        'ho chi minh': '胡志明市',
        'vietnam': '胡志明市',
        'sao paulo': '圣保罗',
        'brazil': '圣保罗',
        'moscow': '莫斯科',
        'russia': '莫斯科',
        'seoul': '首尔',
        'korea': '首尔',
    }
    text_lower = text.lower()
    for key, short in mapping.items():
        if key in text_lower:
            return short
    # 截取前20个字符作为显示
    return text[:20] + ('…' if len(text) > 20 else '')


def build_region_summary_html(person_data_list, week_dates):
    """生成区域业务进度 HTML"""
    # 按地区汇总：{region: {summary_parts: [], persons: set()}}
    region_data = defaultdict(lambda: {'items': [], 'persons': set()})

    for p in person_data_list:
        name = p['name']

        # 从日报中提取
        for d in week_dates:
            content = p['daily_contents'].get(d, '')
            regions = extract_regions(content)
            for region in regions:
                # 提取包含该地区关键词的句子
                sentences = re.split(r'[；;。\n]', content)
                relevant = [s.strip() for s in sentences if region in s and len(s.strip()) > 5]
                for s in relevant[:3]:  # 每条最多取3句
                    region_data[region]['items'].append(f'{name} {d.strftime("%m/%d")}：{s}')
                    region_data[region]['persons'].add(name)

        # 从周报中提取
        weekly_content = p.get('weekly_content', '')
        if weekly_content:
            regions = extract_regions(weekly_content)
            for region in regions:
                sentences = re.split(r'[；;。\n]', weekly_content)
                relevant = [s.strip() for s in sentences if region in s and len(s.strip()) > 5]
                for s in relevant[:3]:
                    entry = f'{name} 周报：{s}'
                    if entry not in region_data[region]['items']:
                        region_data[region]['items'].append(entry)
                        region_data[region]['persons'].add(name)

    if not region_data:
        return '<div class="section-title">🌏 区域业务进度</div><div style="color:#8A813C;font-size:13px;padding:12px;">本周暂无区域业务数据</div>'

    # 按涉及人数排序
    sorted_regions = sorted(region_data.items(), key=lambda x: -len(x[1]['persons']))

    region_cards = []
    for region, data in sorted_regions:
        items_html = ''.join([f'<div class="region-item">• {item}</div>' for item in data['items'][:10]])
        region_cards.append(f'''
        <div class="region-card">
            <div class="region-name">{region} <span style="font-size:11px;color:#8A813C;">({len(data["persons"])}人 · {len(data["items"])}条)</span></div>
            <div class="region-items">{items_html}</div>
        </div>
        ''')

    return f'''
    <div class="section-title">区域业务进度</div>
    <div class="region-grid">{"".join(region_cards)}</div>
    <style>
    .region-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 12px; margin-top: 8px; }}
    .region-card {{ background: #3B5042; border: 1px solid #486C55; border-radius: 8px; padding: 12px 14px; }}
    .region-name {{ font-size: 14px; font-weight: 700; color: #F2D25E; margin-bottom: 8px; }}
    .region-items {{ font-size: 12px; color: #C1CEC4; line-height: 1.7; }}
    .region-item {{ padding: 2px 0; border-bottom: 1px dotted rgba(72,108,85,0.3); }}
    .region-item:last-child {{ border-bottom: none; }}
    @media (max-width: 768px) {{ .region-grid {{ grid-template-columns: 1fr; }} }}
    </style>'''


def generate_html(person_data_list, stats, monday, friday, week_num, daily_geo_data):
    """生成周报看板HTML"""

    def format_date(d):
        return d.strftime('%m/%d')

    def format_period(start, end):
        return f"{start}～{end}"

    def escape_html(text):
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    def split_work_items(content):
        items = []
        lines = content.split('\n')
        current_item = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.', '•', '-', '*')):
                if current_item:
                    items.append('\n'.join(current_item))
                current_item = [line.lstrip('1234567890.•-* ').strip()]
            else:
                current_item.append(line)
        if current_item:
            items.append('\n'.join(current_item))
        return items

    week_dates = [monday + timedelta(days=i) for i in range(5)]
    day_labels = ['一', '二', '三', '四', '五']

    # 每日日报统计条
    daily_bar_items = []
    for i, d in enumerate(week_dates):
        count = sum(1 for p in person_data_list if p['daily_status'].get(d) == 'done')
        daily_bar_items.append(f'<div class="daily-bar-item"><div class="daily-bar-num">{count}</div><div class="daily-bar-label">周{day_labels[i]} {format_date(d)}</div></div>')

    # 生成人员卡片
    person_cards = []
    anomalies = []

    for p in person_data_list:
        work_items = []
        if p['weekly_content']:
            items = split_work_items(p['weekly_content'])
            for i, item in enumerate(items[:10], 1):
                work_items.append(f'<div class="work-item"><span class="wi-idx">{i}.</span> <span class="wi-text">{escape_html(item)}</span></div>')

        travel_badges = []
        if p['travel_periods']:
            periods = ', '.join([format_period(s, e) for s, e in p['travel_periods']])
            travel_badges.append(f'<span class="badge badge-travel">✈ 出差中 ({periods})</span>')

        if p['has_weekly']:
            weekly_badge = '<span class="badge badge-green">周报 ✓</span>'
        else:
            weekly_badge = '<span class="badge badge-red">周报 ✗</span>'

        daily_section = ''
        if p['is_traveling']:
            day_cells = []
            daily_items = []
            for i, d in enumerate(week_dates):
                status = p['daily_status'].get(d, 'na')
                title = f'{day_labels[i]} {format_date(d)}'
                if status == 'done':
                    day_cells.append(f'<span class="day-cell day-done" title="{title}">✓</span>')
                    daily_items.append(f'<div class="daily-item"><span class="daily-date">{format_date(d)}</span> {escape_html(p["daily_contents"].get(d, ""))}</div>')
                elif status == 'miss':
                    day_cells.append(f'<span class="day-cell day-miss" title="{title}">✗</span>')
                else:
                    day_cells.append(f'<span class="day-cell day-na" title="{title}">-</span>')

            daily_section = f'''
                <div class="section-title">日报（{p["daily_count"]}/{p["traveling_days"]}天）</div>
                <div class="day-row">{"".join(day_cells)}</div>
                <div class="daily-detail">{"".join(daily_items)}</div>'''

        for d, content in p['daily_contents'].items():
            if len(content.strip()) < 30:
                anomalies.append({
                    'type': 'short',
                    'name': p['name'],
                    'date': d,
                    'content': content
                })

        if p['is_traveling'] and p['daily_count'] < p['traveling_days']:
            missing_days = []
            for i, d in enumerate(week_dates):
                if p['daily_status'].get(d) == 'miss':
                    missing_days.append(day_labels[i])
            anomalies.append({
                'type': 'inconsistent',
                'name': p['name'],
                'details': f'出差{p["traveling_days"]}天中仅完成{p["daily_count"]}天日报（缺{"、".join(missing_days)}）'
            })

        person_cards.append(f'''
        <div class="person-card">
            <div class="card-header">
                <div class="person-name">{escape_html(p["name"])}</div>
                <div class="person-role">{escape_html(p["role"])}</div>
                <div class="badges">
                    {weekly_badge}
                    {" ".join(travel_badges)}
                </div>
            </div>
            <div class="card-body">
                <div class="section-title">周报（{week_num}）</div>
                <div class="work-items">{"".join(work_items) if work_items else '<div style="color:#8A813C;font-size:12px;">本周未提交周报</div>'}</div>
                <div class="meta-row">
                    <span>共 {len(work_items)} 项工作</span>
                </div>
                {daily_section}
            </div>
        </div>
        ''')

    # 异常分析
    anomaly_html = ''
    short_anomalies = [a for a in anomalies if a['type'] == 'short']
    if short_anomalies:
        anomaly_html += f'''
        <div class="anomaly-box">
            <div class="anomaly-title">日报内容过短（<30字）</div>
            {''.join([f'<div class="anomaly-item anomaly-info">• {a["name"]} {format_date(a["date"])}：仅{len(a["content"])}字 —— {escape_html(a["content"])[:50]}</div>' for a in short_anomalies])}
        </div>
        '''

    inconsistent_anomalies = [a for a in anomalies if a['type'] == 'inconsistent']
    if inconsistent_anomalies:
        anomaly_html += f'''
        <div class="anomaly-box">
            <div class="anomaly-title">周报日报不一致</div>
            {''.join([f'<div class="anomaly-item anomaly-warn">• {a["name"]}：{a["details"]}</div>' for a in inconsistent_anomalies])}
        </div>
        '''

    # 提交情况总表
    summary_rows = []
    for p in person_data_list:
        day_cells = []
        for d in week_dates:
            status = p['daily_status'].get(d, 'na')
            if status == 'done':
                day_cells.append('<td class="td-done">✓</td>')
            elif status == 'miss':
                day_cells.append('<td class="td-miss">✗</td>')
            else:
                day_cells.append('<td class="td-na">-</td>')

        travel_mark = '✓' if p['is_traveling'] else '-'
        weekly_mark = '<span class="td-done">✓</span>' if p['has_weekly'] else '<span class="td-miss">✗</span>'

        summary_rows.append(f'''
        <tr>
            <td>{escape_html(p["name"])}</td>
            <td>{travel_mark}</td>
            <td>{weekly_mark}</td>
            {''.join(day_cells)}
        </tr>''')

    # 结论摘要
    conclusion_parts = []
    missing_weekly = [p for p in person_data_list if not p['has_weekly']]
    if missing_weekly:
        names = '、'.join([p['name'] for p in missing_weekly])
        conclusion_parts.append(f'<span class="conclusion-tag tag-red">{names} 未提交周报</span>')

    for a in inconsistent_anomalies:
        conclusion_parts.append(f'<span class="conclusion-tag tag-orange">{a["name"]} {a["details"]}</span>')

    conclusion = ''
    if conclusion_parts:
        conclusion = f'<div class="conclusion conclusion-warn">⚠ {" ".join(conclusion_parts)}</div>'
    elif stats['total_daily_expected'] > 0 and stats['total_daily'] == stats['total_daily_expected']:
        conclusion = '<div class="conclusion conclusion-ok">✅ 本周出差人员日报全部提交，无异常。</div>'

    weekly_rate = round(stats['total_weekly'] / stats['total_staff'] * 100) if stats['total_staff'] else 0
    daily_expected = stats['total_daily_expected'] if stats['total_daily_expected'] > 0 else 0
    daily_rate = round(stats['total_daily'] / daily_expected * 100) if daily_expected else 0

    # 出差路线地图
    travel_routes_html = build_travel_routes_html(person_data_list, daily_geo_data, week_dates)

    # 区域业务进度
    region_summary_html = build_region_summary_html(person_data_list, week_dates)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>海外增长业务中心 周工作看板 {week_num}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #2D3E33; color: #FDFAEC; min-height: 100vh; padding: 24px;
}}
.container {{ max-width: 1440px; margin: 0 auto; }}

.header {{ text-align: center; padding: 32px 0 24px; }}
.header h1 {{ font-size: 26px; color: #F2D25E; margin-bottom: 8px; }}
.header .week-info {{ font-size: 14px; color: #C1CEC4; }}
.stats {{ display: flex; justify-content: center; gap: 40px; padding: 20px 0; flex-wrap: wrap; }}
.stat-item {{ text-align: center; }}
.stat-num {{ font-size: 30px; font-weight: 700; color: #F2D25E; }}
.stat-label {{ font-size: 12px; color: #C1CEC4; margin-top: 2px; }}
.stat-sub {{ font-size: 11px; color: #8A813C; }}

.section-title {{ color: #5CAB7E; font-size: 14px; font-weight: 600; margin: 14px 0 8px; padding-bottom: 4px; border-bottom: 1px solid #486C55; }}

.summary-table {{ width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }}
.summary-table th {{ background: #3B5042; color: #F2D25E; padding: 10px 8px; text-align: center; border: 1px solid #486C55; }}
.summary-table td {{ padding: 8px; text-align: center; border: 1px solid #486C55; background: #3B5042; }}
.td-done {{ color: #5CAB7E; font-weight: 700; }}
.td-miss {{ color: #E05555; font-weight: 700; }}
.td-na {{ color: #8A813C; }}

.person-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 16px; margin-top: 16px; }}
.person-card {{ background: #3B5042; border: 1px solid #486C55; border-radius: 10px; overflow: hidden; }}
.person-card:hover {{ box-shadow: 0 2px 16px rgba(0,0,0,0.3); }}
.card-header {{ padding: 14px 16px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; border-bottom: 1px solid #486C55; }}
.person-name {{ font-size: 16px; font-weight: 700; color: #FDFAEC; }}
.badges {{ display: flex; gap: 6px; flex-wrap: wrap; }}
.badge {{ font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 600; }}
.badge-green {{ background: rgba(92,171,126,0.25); color: #5CAB7E; }}
.badge-red {{ background: rgba(224,85,85,0.25); color: #E05555; }}
.badge-travel {{ background: rgba(242,210,94,0.20); color: #F2D25E; }}
.card-body {{ padding: 12px 16px 16px; }}
.person-role {{ font-size: 12px; color: #F2D25E; background: rgba(242,210,94,0.12); padding: 1px 8px; border-radius: 4px; }}
.work-items {{ margin-bottom: 4px; }}
.work-item {{ font-size: 12px; color: #C1CEC4; line-height: 1.7; padding: 3px 0; border-bottom: 1px dotted rgba(72,108,85,0.4); }}
.work-item:last-child {{ border-bottom: none; }}
.wi-idx {{ color: #8A813C; font-weight: 700; margin-right: 4px; }}
.wi-text {{ color: #C1CEC4; }}
.meta-row {{ display: flex; gap: 16px; font-size: 12px; color: #8A813C; flex-wrap: wrap; }}

.day-row {{ display: flex; gap: 8px; margin: 6px 0; }}
.day-cell {{ width: 36px; height: 28px; display: flex; align-items: center; justify-content: center; border-radius: 4px; font-size: 13px; font-weight: 700; }}
.day-done {{ background: rgba(92,171,126,0.25); color: #5CAB7E; }}
.day-miss {{ background: rgba(224,85,85,0.25); color: #E05555; }}
.day-na {{ background: rgba(138,129,60,0.10); color: #8A813C; }}

.daily-detail {{ margin-top: 8px; }}
.daily-item {{ font-size: 12px; color: #C1CEC4; padding: 3px 0; }}
.daily-date {{ color: #8A813C; margin-right: 6px; font-weight: 600; }}

.daily-bar {{ display: flex; gap: 12px; margin: 8px 0; flex-wrap: wrap; justify-content: center; }}
.daily-bar-item {{ text-align: center; background: #3B5042; border: 1px solid #486C55; border-radius: 8px; padding: 10px 16px; min-width: 60px; }}
.daily-bar-num {{ font-size: 22px; font-weight: 700; color: #F2D25E; }}
.daily-bar-label {{ font-size: 11px; color: #C1CEC4; }}

.conclusion {{ padding: 16px 20px; border-radius: 10px; margin: 16px 0; font-size: 14px; line-height: 1.8; }}
.conclusion-ok {{ background: rgba(92,171,126,0.15); border: 1px solid #5CAB7E; color: #5CAB7E; }}
.conclusion-warn {{ background: rgba(242,210,94,0.10); border: 1px solid #F2D25E; color: #FDFAEC; }}
.conclusion-tag {{ display: inline-block; padding: 2px 10px; border-radius: 4px; margin: 2px 4px; font-size: 13px; font-weight: 600; }}
.tag-red {{ background: rgba(224,85,85,0.25); color: #E05555; }}
.tag-orange {{ background: rgba(242,210,94,0.20); color: #F2D25E; }}

.anomaly-box {{ background: #3B5042; border: 1px solid #486C55; border-radius: 10px; padding: 16px; margin: 16px 0; }}
.anomaly-title {{ font-size: 14px; font-weight: 600; color: #F2D25E; margin-bottom: 10px; }}
.anomaly-item {{ font-size: 12px; padding: 4px 0; }}
.anomaly-info {{ color: #8A813C; }}
.anomaly-warn {{ color: #F2D25E; }}

@media (max-width: 768px) {{
    .person-grid {{ grid-template-columns: 1fr; }}
    .stats {{ gap: 20px; }}
}}
</style>
</head>
<body>
<div class="container">

<div class="header">
    <h1>海外增长业务中心 周工作看板</h1>
    <div class="week-info">{week_num} · {monday.strftime('%Y年%m月%d日')} — {friday.strftime('%Y年%m月%d日')} · 生成于 {datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M')}</div>
</div>

<div class="stats">
    <div class="stat-item"><div class="stat-num">{stats["total_staff"]}</div><div class="stat-label">团队人数</div></div>
    <div class="stat-item"><div class="stat-num">{stats["traveling_count"]}</div><div class="stat-label">本周出差中</div></div>
    <div class="stat-item"><div class="stat-num">{stats["total_weekly"]}/{stats["total_staff"]}</div><div class="stat-label">周报完成</div><div class="stat-sub">{weekly_rate}%</div></div>
    <div class="stat-item"><div class="stat-num">{stats["total_daily"]}/{daily_expected}</div><div class="stat-label">日报完成</div><div class="stat-sub">{daily_rate}%</div></div>
</div>

<div class="daily-bar">
    {"".join(daily_bar_items)}
</div>

{conclusion}

<div class="section-title">本周提交情况</div>
<div style="overflow-x: auto;">
<table class="summary-table">
<thead>
<tr><th>姓名</th><th>出差</th><th>周报</th><th>周一</th><th>周二</th><th>周三</th><th>周四</th><th>周五</th></tr>
</thead>
<tbody>
{''.join(summary_rows)}
</tbody>
</table>
</div>

{travel_routes_html}

{region_summary_html}

<div class="section-title">人员详情（{week_num}）</div>
<div class="person-grid">
{''.join(person_cards)}
</div>

{anomaly_html}

</div><!-- .container -->

</body>
</html>'''

    return html


def main():
    args = sys.argv[1:]
    auto_mode = '--auto' in args
    send_mode = '--send' in args

    # 解析目标周
    target_date = None
    for arg in args:
        arg_upper = arg.upper().replace('WK', '').strip()
        try:
            week_num = int(arg_upper)
            wk1_monday = date(2026, 1, 5)
            target_date = wk1_monday + timedelta(weeks=week_num - 1)
            break
        except ValueError:
            continue

    # --auto 模式：周一自动生成上周报告
    if auto_mode and target_date is None:
        today = datetime.now(BEIJING_TZ).date()
        if today.weekday() == 0:  # 周一
            target_date = today - timedelta(days=7)
            print(f"[INFO] 自动模式：周一出具上周报告（{target_date}）")
        else:
            target_date = today
            print(f"[INFO] 自动模式：非周一，生成当前周报告（{target_date}）")

    monday, friday, week_num = get_week_range(target_date)
    print(f"[INFO] 目标周: {week_num}（{monday} ~ {friday}）")

    client = FeishuClient()
    staff, traveling, daily_reports, weekly_reports, daily_geo = fetch_data(client, target_week_num=week_num)
    print(f"[INFO] 获取到 {len(staff)} 名人员")

    person_data_list, stats = analyze_week_data(staff, traveling, daily_reports, weekly_reports, monday, friday)

    html = generate_html(person_data_list, stats, monday, friday, week_num, daily_geo)

    # 输出到本地（兼容 GitHub Actions 环境）
    import tempfile
    output_dir = os.environ.get('RUNNER_TEMP', tempfile.gettempdir())
    html_path = os.path.join(output_dir, f'海外增长周工作看板{week_num}.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    # 本地调试时也保存到项目目录
    local_output = '/Users/zhongqiongwei/Documents/trae_projects/1/weekly-reports/海外增长周工作看板.html'
    local_archive = f'/Users/zhongqiongwei/Documents/trae_projects/1/weekly-reports/海外增长周工作看板{week_num}.html'
    try:
        os.makedirs(os.path.dirname(local_output), exist_ok=True)
        with open(local_output, 'w', encoding='utf-8') as f:
            f.write(html)
        with open(local_archive, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"[INFO] 本地文件已保存: {local_output}")
    except (OSError, FileNotFoundError):
        print(f"[INFO] 本地目录不可写，跳过本地保存（CI 环境正常）")

    file_size_kb = len(html.encode('utf-8')) / 1024
    print(f"[INFO] 文件大小: {file_size_kb:.1f} KB")
    print(f"[INFO] 统计: 团队{stats['total_staff']}人 | 出差{stats['traveling_count']}人 | 周报{stats['total_weekly']}/{stats['total_staff']} | 日报{stats['total_daily']}/{stats['total_daily_expected']}")

    # --send 模式：发送到飞书私聊 + 云盘
    if send_mode:
        open_id = os.environ.get('FEISHU_USER_OPEN_ID', '')
        folder_token = os.environ.get('FEISHU_DRIVE_FOLDER_TOKEN', '')

        if open_id:
            try:
                print("[INFO] 上传文件到飞书 IM...")
                file_key = client.upload_file_to_im(html_path)
                print(f"[INFO] 发送私聊消息到用户 {open_id}...")
                client.send_file_to_user(open_id, file_key)
                print("[INFO] 私聊发送成功")
            except Exception as e:
                print(f"[WARN] 私聊发送失败: {e}")
        else:
            # 回退：发送到群聊
            chat_id = os.environ.get('FEISHU_CHAT_ID', '')
            if chat_id:
                try:
                    print("[INFO] 未设置 FEISHU_USER_OPEN_ID，发送到群聊...")
                    file_key = client.upload_file_to_im(html_path)
                    client.send_file_to_chat(chat_id, file_key)
                    print("[INFO] 群聊发送成功")
                except Exception as e:
                    print(f"[WARN] 群聊发送也失败: {e}")
            else:
                print("[WARN] 未设置 FEISHU_USER_OPEN_ID 和 FEISHU_CHAT_ID，跳过发送")

        if folder_token:
            try:
                print(f"[INFO] 上传到飞书云盘文件夹 {folder_token}...")
                file_title = f'海外增长周工作看板{week_num}.html'
                client.upload_to_drive(html_path, folder_token, file_title)
                print("[INFO] 云盘上传成功")
            except Exception as e:
                print(f"[WARN] 云盘上传失败: {e}")
        else:
            print("[WARN] 未设置 FEISHU_DRIVE_FOLDER_TOKEN，跳过云盘上传")


if __name__ == "__main__":
    main()
