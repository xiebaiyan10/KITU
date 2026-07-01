# -*- coding: utf-8 -*-
"""
KITU v3 - 多数据源+强力反爬+完整导出
数据源：国家统计局 > 东方财富 > 百度/搜狗网页解析 > 内置备用数据
"""

import sys, os, re, json, threading, time, io
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QCheckBox, QSpinBox,
    QFileDialog, QMessageBox, QSplitter, QGroupBox, QGridLayout,
    QProgressBar, QStatusBar, QTextEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor

import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ============================================================
# 强力网络请求工具
# ============================================================
class NetClient:
    """带重试和反反爬的网络客户端"""

    _session = None

    @classmethod
    def get_session(cls):
        if cls._session is None:
            cls._session = requests.Session()
            cls._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Cache-Control': 'max-age=0',
            })
        return cls._session

    @classmethod
    def get(cls, url, params=None, timeout=15, retry=2):
        """带重试的GET请求"""
        for attempt in range(retry + 1):
            try:
                resp = cls.get_session().get(url, params=params, timeout=timeout, verify=False)
                if resp.status_code == 200:
                    resp.encoding = resp.apparent_encoding or 'utf-8'
                    return resp
                elif resp.status_code == 502:
                    time.sleep(1)
                    continue
            except Exception:
                if attempt < retry:
                    time.sleep(1)
                continue
        return None

    @classmethod
    def get_json(cls, url, params=None, timeout=15, retry=2):
        """获取JSON数据"""
        for attempt in range(retry + 1):
            try:
                resp = cls.get_session().get(url, params=params, timeout=timeout, verify=False)
                if resp and resp.status_code == 200:
                    return resp.json()
            except Exception:
                if attempt < retry:
                    time.sleep(1)
        return None


# 禁用SSL警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================
# 数据源1: 国家统计局 (国内可用)
# ============================================================
class NBSData:
    """国家统计局公开数据"""

    # 常用指标代码映射
    INDICATORS = {
        "GDP": "A0201",
        "gdp": "A0201",
        "国内生产总值": "A0201",
        "人口": "A0301",
        "总人口": "A0301",
        "出生率": "A0302",
        "死亡率": "A0303",
        "就业": "A0401",
        "失业": "A0402",
        "cpi": "A0901",
        "CPI": "A0901",
        "物价": "A0901",
        "房价": "A0H01",
        "进出口": "A0601",
        "出口": "A0602",
        "进口": "A0603",
        "工业": "A0B01",
        "消费": "A0701",
    }

    @staticmethod
    def query(indicator_code, years=15):
        """查询国家统计局数据"""
        try:
            end_year = 2024
            start_year = end_year - years

            # 国家统计局公开查询接口
            url = "https://data.stats.gov.cn/easyquery.htm"
            params = {
                "m": "QueryData",
                "dbcode": "fsnd",
                "rowcode": "sj",
                "colcode": "zb",
                "wds": "[]",
                "dfwds": json.dumps([
                    {"wdcode": "zb", "valuecode": indicator_code},
                    {"wdcode": "sj", "valuecode": str(end_year)}
                ]),
            }

            resp = NetClient.get(url, params=params, timeout=10)
            if resp and resp.status_code == 200:
                data = resp.json()
                return NBSData._parse_response(data)

            # 备用接口
            url2 = "https://data.stats.gov.cn/easyquery.htm"
            params2 = {
                "m": "QueryData",
                "dbcode": "hgnd",
                "rowcode": "sj",
                "colcode": "zb",
                "wds": "[]",
                "dfwds": json.dumps([{"wdcode": "zb", "valuecode": indicator_code}]),
            }
            resp2 = NetClient.get(url2, params=params2, timeout=10)
            if resp2 and resp2.status_code == 200:
                data2 = resp2.json()
                return NBSData._parse_response(data2)

        except Exception:
            pass
        return None

    @staticmethod
    def _parse_response(data):
        """解析国家统计局返回数据"""
        try:
            datanodes = data.get('returndata', {}).get('datanodes', [])
            if not datanodes:
                return None

            year_vals = {}
            for node in datanodes:
                code = node.get('code', '')
                val = node.get('data', {}).get('data')
                if val and val != '0':
                    # 提取年份
                    year_match = re.search(r'(\d{4})', code)
                    if year_match:
                        year = year_match.group(1)
                        try:
                            year_vals[year] = float(val)
                        except ValueError:
                            pass

            if len(year_vals) >= 3:
                sorted_years = sorted(year_vals.keys())
                values = [year_vals[y] for y in sorted_years]
                return {"年份": sorted_years, "数值": values}
        except Exception:
            pass
        return None

    @staticmethod
    def search(keyword):
        """根据关键词搜索"""
        for name, code in NBSData.INDICATORS.items():
            if keyword in name or name in keyword:
                result = NBSData.query(code)
                if result:
                    display_name = [k for k, v in NBSData.INDICATORS.items() if v == code][0]
                    return {
                        "标题": f"中国{display_name}数据",
                        "来源": "国家统计局 (data.stats.gov.cn)",
                        "数据": {display_name: result["数值"]},
                        "年份": result["年份"],
                    }
        return None


# ============================================================
# 数据源2: 东方财富/金融数据 (国内可用)
# ============================================================
class EastMoneyData:
    """东方财富公开数据接口"""

    @staticmethod
    def get_gdp():
        """获取中国GDP数据"""
        try:
            # 东方财富宏观经济API
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "sortColumns": "REPORT_DATE",
                "sortTypes": "1",
                "pageSize": "20",
                "pageNumber": "1",
                "reportName": "RPT_ECONOMY_CN_GDP",
                "columns": "REPORT_DATE,TIME,INDICATOR_NAME,VALUE",
                "source": "WEB",
                "client": "WEB",
            }
            data = NetClient.get_json(url, params=params, timeout=10)
            if data and data.get('result'):
                items = data['result'].get('data', [])
                years = []
                values = []
                for item in items:
                    date_str = item.get('REPORT_DATE', '')[:4]
                    val = item.get('VALUE')
                    if date_str and val:
                        years.append(date_str)
                        values.append(float(val))
                if len(years) >= 3:
                    years.reverse()
                    values.reverse()
                    return {"年份": years, "数值": values}
        except Exception:
            pass
        return None

    @staticmethod
    def get_cpi():
        """获取CPI数据"""
        try:
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "sortColumns": "REPORT_DATE",
                "sortTypes": "-1",
                "pageSize": "20",
                "pageNumber": "1",
                "reportName": "RPT_ECONOMY_CN_CPI",
                "columns": "REPORT_DATE,TIME,NATIONAL_SAME,NATIONAL_BASE",
                "source": "WEB",
                "client": "WEB",
            }
            data = NetClient.get_json(url, params=params, timeout=10)
            if data and data.get('result'):
                items = data['result'].get('data', [])
                years = []
                values = []
                for item in items:
                    date_str = item.get('REPORT_DATE', '')[:4]
                    val = item.get('NATIONAL_SAME') or item.get('NATIONAL_BASE')
                    if date_str and val:
                        years.append(date_str)
                        values.append(float(val))
                if len(years) >= 3:
                    years.reverse()
                    values.reverse()
                    return {"年份": years, "数值": values}
        except Exception:
            pass
        return None

    @staticmethod
    def get_population():
        """获取人口数据"""
        try:
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "sortColumns": "REPORT_DATE",
                "sortTypes": "-1",
                "pageSize": "20",
                "pageNumber": "1",
                "reportName": "RPT_ECONOMY_CN_POP",
                "columns": "REPORT_DATE,TIME,VALUE",
                "source": "WEB",
                "client": "WEB",
            }
            data = NetClient.get_json(url, params=params, timeout=10)
            if data and data.get('result'):
                items = data['result'].get('data', [])
                years = []
                values = []
                for item in items:
                    date_str = item.get('REPORT_DATE', '')[:4]
                    val = item.get('VALUE')
                    if date_str and val:
                        years.append(date_str)
                        values.append(float(val))
                if len(years) >= 3:
                    years.reverse()
                    values.reverse()
                    return {"年份": years, "数值": values}
        except Exception:
            pass
        return None

    @staticmethod
    def search(keyword):
        """根据关键词搜索东方财富数据"""
        kw = keyword.lower()
        result = None

        if any(w in kw for w in ['gdp', '国内生产', '生产总值']):
            result = EastMoneyData.get_gdp()
            name = "GDP"
        elif any(w in kw for w in ['cpi', '物价', '通胀', '通货膨胀']):
            result = EastMoneyData.get_cpi()
            name = "CPI"
        elif any(w in kw for w in ['人口']):
            result = EastMoneyData.get_population()
            name = "人口"

        if result:
            return {
                "标题": f"中国{name}数据",
                "来源": "东方财富数据中心",
                "数据": {name: result["数值"]},
                "年份": result["年份"],
            }
        return None


# ============================================================
# 数据源3: 网页搜索 + 表格提取 (增强反反爬)
# ============================================================
class WebScraper:
    """网页爬虫 - 多搜索引擎 + 表格提取"""

    @staticmethod
    def search_sogou(keyword, pages=2):
        """搜狗搜索（国内反爬较弱）"""
        texts = []
        try:
            for p in range(pages):
                url = f"https://www.sogou.com/web?query={keyword}&page={p+1}"
                resp = NetClient.get(url, timeout=10)
                if resp:
                    soup = BeautifulSoup(resp.text, 'lxml')
                    # 提取搜索结果摘要
                    for tag in soup.find_all(['p', 'div']):
                        txt = tag.get_text(strip=True)
                        if len(txt) > 30 and len(txt) < 500:
                            texts.append(txt)
                    # 提取表格
                    for table in soup.find_all('table'):
                        rows = table.find_all('tr')
                        for row in rows:
                            cols = row.find_all(['td', 'th'])
                            row_txt = ' | '.join(c.get_text(strip=True) for c in cols if c.get_text(strip=True))
                            if row_txt:
                                texts.append(row_txt)
                time.sleep(0.5)
        except Exception:
            pass
        return texts

    @staticmethod
    def search_bing(keyword, pages=2):
        """Bing搜索"""
        texts = []
        try:
            for p in range(pages):
                url = f"https://cn.bing.com/search?q={keyword}&first={p*10+1}"
                resp = NetClient.get(url, timeout=10)
                if resp:
                    soup = BeautifulSoup(resp.text, 'lxml')
                    for tag in soup.find_all(['p', 'li', 'span']):
                        txt = tag.get_text(strip=True)
                        if len(txt) > 30 and len(txt) < 500:
                            texts.append(txt)
                time.sleep(0.5)
        except Exception:
            pass
        return texts

    @staticmethod
    def extract_table_from_url(url):
        """从指定URL提取表格"""
        try:
            resp = NetClient.get(url, timeout=15)
            if resp:
                soup = BeautifulSoup(resp.text, 'lxml')
                tables = soup.find_all('table')
                all_tables = []
                for table in tables:
                    rows = table.find_all('tr')
                    table_data = []
                    for row in rows:
                        cols = row.find_all(['td', 'th'])
                        row_data = [c.get_text(strip=True) for c in cols if c.get_text(strip=True)]
                        if row_data:
                            table_data.append(row_data)
                    if len(table_data) >= 2:
                        all_tables.append(table_data)
                return all_tables
        except Exception:
            pass
        return []

    @staticmethod
    def extract_numbers(texts):
        """从文本中智能提取年份-数字对"""
        patterns = [
            r'(\d{4})\s*年?\s*[：:]*\s*([\d,.]+\s*(?:亿|万|%|美元|元)?)',
            r'(\d{4})[^\d]*?([\d,.]+)',
        ]

        results = []
        seen = set()
        for text in texts:
            for pat in patterns:
                for match in re.finditer(pat, text):
                    year = match.group(1)
                    val_str = match.group(2).replace(',', '').strip()

                    # 处理单位
                    multiplier = 1
                    if '亿' in val_str:
                        multiplier = 100000000
                        val_str = val_str.replace('亿', '')
                    elif '万' in val_str:
                        multiplier = 10000
                        val_str = val_str.replace('万', '')
                    val_str = val_str.replace('%', '').replace('美元', '').replace('元', '')

                    try:
                        val = float(val_str) * multiplier
                        key = (int(year), round(val, 2))
                        if key not in seen and 1990 <= int(year) <= 2030 and val > 0:
                            seen.add(key)
                            results.append(key)
                    except ValueError:
                        pass

        return results


# ============================================================
# 数据源4: 内置备用数据 (最后兜底)
# ============================================================
BACKUP_DATA = {
    "中国GDP": {
        "标题": "中国GDP数据",
        "来源": "内置参考数据（联网获取失败时的备用）",
        "数据": {
            "GDP(万亿元)": [41.2,48.8,53.9,59.6,64.4,68.9,74.6,83.2,91.9,98.7,101.4,114.9,121.0,126.1,134.9],
            "增长率(%)": [10.6,9.6,9.2,7.9,7.8,7.4,7.0,6.8,6.9,6.7,6.0,8.4,3.0,5.2,5.0],
        },
        "年份": ["2010","2011","2012","2013","2014","2015","2016","2017","2018","2019","2020","2021","2022","2023","2024"],
    },
    "CPI": {
        "标题": "中国CPI数据",
        "来源": "内置参考数据",
        "数据": {
            "CPI同比(%)": [3.3,5.4,2.6,2.6,2.0,1.4,2.0,1.6,2.1,2.9,2.5,0.9,2.0,0.2,0.2],
        },
        "年份": ["2010","2011","2012","2013","2014","2015","2016","2017","2018","2019","2020","2021","2022","2023","2024"],
    },
    "人口": {
        "标题": "中国人口数据",
        "来源": "内置参考数据",
        "数据": {
            "总人口(亿)": [13.41,13.47,13.54,13.61,13.68,13.75,13.83,13.90,13.95,14.00,14.12,14.12,14.11,14.09,14.07],
            "出生率(‰)": [11.9,11.9,12.1,12.1,12.4,12.1,13.0,12.4,10.9,10.5,8.5,7.5,6.8,6.4,6.4],
        },
        "年份": ["2010","2011","2012","2013","2014","2015","2016","2017","2018","2019","2020","2021","2022","2023","2024"],
    },
    "房价": {
        "标题": "中国房价走势",
        "来源": "内置参考数据",
        "数据": {
            "北京(万元/㎡)": [2.0,2.2,2.5,3.1,3.3,3.5,3.8,4.1,4.3,4.5,4.8,5.0,5.2,5.5,5.3],
            "上海(万元/㎡)": [1.8,2.0,2.2,2.8,3.0,3.2,3.6,3.9,4.2,4.5,4.8,5.1,5.4,5.6,5.5],
            "深圳(万元/㎡)": [1.5,1.8,2.0,2.5,2.8,3.2,3.8,4.5,5.0,5.4,5.8,6.2,6.5,6.8,6.5],
        },
        "年份": ["2010","2011","2012","2013","2014","2015","2016","2017","2018","2019","2020","2021","2022","2023","2024"],
    },
    "互联网用户": {
        "标题": "中国互联网用户",
        "来源": "内置参考数据",
        "数据": {
            "网民(亿)": [4.57,5.13,5.64,6.18,6.49,6.88,7.31,7.72,8.29,9.04,9.89,10.32,10.67,10.92,11.03],
            "普及率(%)": [34.3,38.3,42.1,45.8,47.9,50.3,53.2,55.8,59.6,64.5,70.4,73.0,75.6,77.5,78.0],
        },
        "年份": ["2010","2011","2012","2013","2014","2015","2016","2017","2018","2019","2020","2021","2022","2023","2024"],
    },
    "新能源车": {
        "标题": "中国新能源汽车销量",
        "来源": "内置参考数据",
        "数据": {
            "销量(万辆)": [0.8,1.3,1.8,3.5,7.5,33.1,50.7,77.7,125.6,120.6,136.7,352.1,688.7,949.5,1286.0],
        },
        "年份": ["2010","2011","2012","2013","2014","2015","2016","2017","2018","2019","2020","2021","2022","2023","2024"],
    },
}


# ============================================================
# 统一搜索引擎
# ============================================================
class SearchEngine:
    """统一搜索入口 - 多源并行搜索"""

    @staticmethod
    def search(keyword):
        """搜索数据，按优先级尝试多个数据源"""
        results = []

        # 1. 先查内置关键词映射（最快）
        for key, data in BACKUP_DATA.items():
            if keyword in key or key in keyword:
                results.append(("内置", data))
                break

        # 2. 尝试东方财富（国内可用）
        em = EastMoneyData.search(keyword)
        if em:
            results.append(("东方财富", em))

        # 3. 尝试国家统计局
        nbs = NBSData.search(keyword)
        if nbs:
            results.append(("国家统计局", nbs))

        # 4. 网页搜索提取（搜狗+Bing）
        all_texts = []
        all_texts.extend(WebScraper.search_sogou(keyword, pages=1))
        all_texts.extend(WebScraper.search_bing(keyword, pages=1))

        numbers = WebScraper.extract_numbers(all_texts)
        if len(numbers) >= 4:
            sorted_nums = sorted(set(numbers))
            years = [str(y) for y, v in sorted_nums]
            values = [v for y, v in sorted_nums]
            results.append(("网页搜索", {
                "标题": f"{keyword} 数据",
                "来源": "搜狗/Bing搜索结果提取",
                "数据": {keyword: values},
                "年份": years,
            }))

        return results


# ============================================================
# 搜索线程
# ============================================================
class SearchThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword

    def run(self):
        try:
            self.progress_signal.emit("🔍 正在多源并行搜索...")

            # 先检查内置
            for key, data in BACKUP_DATA.items():
                if self.keyword in key or key in self.keyword:
                    self.progress_signal.emit(f"📋 匹配到内置数据: {key}")
                    time.sleep(0.3)
                    self.finished_signal.emit(data)
                    return

            # 尝试东方财富
            self.progress_signal.emit("📊 查询东方财富数据中心...")
            em = EastMoneyData.search(self.keyword)
            if em:
                self.progress_signal.emit("✅ 东方财富返回数据")
                self.finished_signal.emit(em)
                return

            # 尝试国家统计局
            self.progress_signal.emit("🏛 查询国家统计局...")
            nbs = NBSData.search(self.keyword)
            if nbs:
                self.progress_signal.emit("✅ 国家统计局返回数据")
                self.finished_signal.emit(nbs)
                return

            # 网页搜索
            self.progress_signal.emit("🌐 搜狗搜索网页数据...")
            texts1 = WebScraper.search_sogou(self.keyword, pages=1)

            self.progress_signal.emit("🌐 Bing搜索网页数据...")
            texts2 = WebScraper.search_bing(self.keyword, pages=1)

            all_texts = texts1 + texts2
            self.progress_signal.emit(f"📝 获取到 {len(all_texts)} 条网页文本，正在提取数字...")

            numbers = WebScraper.extract_numbers(all_texts)

            if len(numbers) >= 4:
                sorted_nums = sorted(set(numbers))
                years = [str(y) for y, v in sorted_nums]
                values = [v for y, v in sorted_nums]
                self.progress_signal.emit(f"✅ 提取到 {len(years)} 个年份的数据点")
                result = {
                    "标题": f"{self.keyword} 数据",
                    "来源": "搜狗/Bing搜索结果智能提取",
                    "数据": {self.keyword: values},
                    "年份": years,
                }
                self.finished_signal.emit(result)
                return

            # 智能匹配内置数据
            self.progress_signal.emit("💡 网页未提取到足够数据，智能匹配内置数据...")
            matched = None
            kw_lower = self.keyword.lower()
            for key, data in BACKUP_DATA.items():
                key_lower = key.lower()
                if any(w in kw_lower for w in key_lower.split()) or any(w in key_lower for w in kw_lower.split()):
                    matched = data
                    break

            if matched:
                self.progress_signal.emit(f"📋 智能匹配到: {matched['标题']}")
                self.finished_signal.emit(matched)
            else:
                # 返回GDP作为兜底
                self.progress_signal.emit("⚠ 未能精确匹配，返回中国GDP数据作为参考")
                self.finished_signal.emit(BACKUP_DATA["中国GDP"])

        except Exception as e:
            # 最终兜底
            self.error_signal.emit(f"搜索出错: {str(e)}")


# ============================================================
# 图表画布
# ============================================================
class ChartCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(9, 5.5), dpi=100, facecolor='white')
        super().__init__(self.fig)
        self.setParent(parent)


# ============================================================
# 主界面
# ============================================================
class KITUApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📊 KITU")
        self.setMinimumSize(1150, 780)
        self.current_data = None
        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)
        main.setContentsMargins(12, 10, 12, 10)
        main.setSpacing(6)

        # 标题
        title = QLabel("🌐 KITU")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2c3e50;")
        main.addWidget(title)

        sub = QLabel("输入关键词 → 自动联网搜索 → 智能提取数据 → 生成图表 → 导出")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        main.addWidget(sub)

        # 搜索区
        sg = QGroupBox()
        sg.setStyleSheet("""
            QGroupBox { border: 2px solid #3498db; border-radius: 10px; 
                       margin-top: 6px; padding: 15px; background: #eaf2f8; }
        """)
        sl = QVBoxLayout(sg)

        row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词：中国GDP、CPI、人口、房价、互联网用户、新能源车...")
        self.search_input.setFont(QFont("Microsoft YaHei", 12))
        self.search_input.setMinimumHeight(42)
        self.search_input.setStyleSheet("""
            QLineEdit { border: 2px solid #bdc3c7; border-radius: 8px; padding: 5px 15px; background: white; }
            QLineEdit:focus { border-color: #2980b9; }
        """)
        self.search_input.returnPressed.connect(self.start_search)
        row.addWidget(self.search_input)

        self.search_btn = QPushButton("🔍 联网搜索")
        self.search_btn.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        self.search_btn.setMinimumHeight(42)
        self.search_btn.setMinimumWidth(120)
        self.search_btn.setStyleSheet("""
            QPushButton { background: #2980b9; color: white; border: none; border-radius: 8px; }
            QPushButton:hover { background: #2471a3; }
            QPushButton:disabled { background: #95a5a6; }
        """)
        self.search_btn.clicked.connect(self.start_search)
        row.addWidget(self.search_btn)
        sl.addLayout(row)

        # 快捷标签
        qr = QHBoxLayout()
        qr.addWidget(QLabel("💡"))
        for kw in ["中国GDP", "CPI", "人口", "房价", "互联网用户", "新能源车"]:
            btn = QPushButton(kw)
            btn.setStyleSheet("""
                QPushButton { background: white; border: 1px solid #3498db; border-radius: 12px;
                             padding: 3px 12px; font-size: 11px; color: #2980b9; }
                QPushButton:hover { background: #3498db; color: white; }
            """)
            btn.clicked.connect(lambda _, k=kw: self._quick(k))
            qr.addWidget(btn)
        qr.addStretch()
        sl.addLayout(qr)
        main.addWidget(sg)

        # 状态
        self.status_label = QLabel("👆 输入关键词，点击搜索")
        self.status_label.setStyleSheet("color: #7f8c8d; padding: 2px;")
        main.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setMaximum(0)
        self.progress.setFixedHeight(4)
        main.addWidget(self.progress)

        # 主分割器
        splitter = QSplitter(Qt.Horizontal)

        # 左侧
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 4, 0)
        ll.setSpacing(5)

        ps = """
            QGroupBox { font-weight: bold; border: 1px solid #ddd; border-radius: 7px;
                       margin-top: 6px; padding: 10px; background: white; }
        """

        # 日志
        lg = QGroupBox("📋 搜索过程")
        lg.setStyleSheet(ps)
        lgl = QVBoxLayout(lg)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(90)
        self.log.setStyleSheet("font-size: 10px; background: #fafafa;")
        lgl.addWidget(self.log)
        ll.addWidget(lg)

        # 数据选择
        dg = QGroupBox("📊 数据项")
        dg.setStyleSheet(ps)
        dl = QVBoxLayout(dg)
        self.cb_layout = QVBoxLayout()
        dl.addLayout(self.cb_layout)
        self.cb_all = QCheckBox("全选")
        self.cb_all.setChecked(True)
        self.cb_all.stateChanged.connect(self._toggle_all)
        dl.addWidget(self.cb_all)
        ll.addWidget(dg)

        # 图表设置
        cg = QGroupBox("📈 图表设置")
        cg.setStyleSheet(ps)
        cl = QVBoxLayout(cg)
        cl.addWidget(QLabel("类型:"))
        self.chart_type = QComboBox()
        self.chart_type.addItems(["📈 折线图", "📊 柱状图", "🥧 饼图", "📉 面积图", "📌 散点图"])
        cl.addWidget(self.chart_type)
        self.show_labels_cb = QCheckBox("显示数值标签")
        self.show_labels_cb.setChecked(True)
        cl.addWidget(self.show_labels_cb)
        ll.addWidget(cg)

        # 年份
        yg = QGroupBox("📅 年份范围")
        yg.setStyleSheet(ps)
        yl = QGridLayout(yg)
        yl.addWidget(QLabel("起:"), 0, 0)
        self.ys = QComboBox()
        yl.addWidget(self.ys, 0, 1)
        yl.addWidget(QLabel("止:"), 0, 2)
        self.ye = QComboBox()
        yl.addWidget(self.ye, 0, 3)
        self.auto_year = QCheckBox("自动全部年份")
        self.auto_year.setChecked(True)
        yl.addWidget(self.auto_year, 1, 0, 1, 4)
        ll.addWidget(yg)

        # 生成按钮
        self.gen_btn = QPushButton("🎨 生成图表")
        self.gen_btn.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        self.gen_btn.setMinimumHeight(45)
        self.gen_btn.setStyleSheet("""
            QPushButton { background: #27ae60; color: white; border: none; border-radius: 8px; }
            QPushButton:hover { background: #229954; }
            QPushButton:disabled { background: #bdc3c7; }
        """)
        self.gen_btn.clicked.connect(self.generate_chart)
        self.gen_btn.setEnabled(False)
        ll.addWidget(self.gen_btn)

        # 导出区
        eg = QGroupBox("💾 导出")
        eg.setStyleSheet(ps)
        el = QGridLayout(eg)
        formats = [
            ("PNG图片", "png", self.save_png),
            ("JPG图片", "jpg", self.save_jpg),
            ("PDF文档", "pdf", self.save_pdf),
            ("SVG矢量", "svg", self.save_svg),
            ("CSV数据", "csv", self.export_csv),
            ("Excel数据", "xlsx", self.export_excel),
        ]
        for i, (label, ext, func) in enumerate(formats):
            btn = QPushButton(f"📥 {label}")
            btn.setStyleSheet("padding: 5px; border: 1px solid #ccc; border-radius: 4px; background: white; font-size: 11px;")
            btn.clicked.connect(lambda _, f=func, e=ext: f(e))
            btn.setEnabled(False)
            el.addWidget(btn, i // 3, i % 3)
            setattr(self, f'export_btn_{ext}', btn)
        ll.addWidget(eg)

        ll.addStretch()

        # 右侧图表
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        self.canvas = ChartCanvas()
        self._placeholder()
        rl.addWidget(self.canvas)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([320, 790])
        main.addWidget(splitter)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")

    def _quick(self, kw):
        self.search_input.setText(kw)
        self.start_search()

    def _toggle_all(self, state):
        for cb in getattr(self, 'data_cbs', []):
            cb.setChecked(state == Qt.Checked)

    def _placeholder(self):
        ax = self.canvas.fig.add_subplot(111)
        ax.text(0.5, 0.5, '🌐 输入关键词 → 联网搜索 → 生成图表',
               ha='center', va='center', fontsize=16, color='#bdc3c7',
               transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
        self.canvas.draw()

    # ===== 搜索 =====
    def start_search(self):
        kw = self.search_input.text().strip()
        if not kw:
            return QMessageBox.information(self, "提示", "请输入关键词")

        self.status_label.setText(f"🔍 搜索中: {kw}")
        self.status_label.setStyleSheet("color: #2980b9; font-weight: bold;")
        self.progress.setVisible(True)
        self.search_btn.setEnabled(False)
        self.gen_btn.setEnabled(False)
        self.log.clear()

        self.st = SearchThread(kw)
        self.st.progress_signal.connect(self._on_progress)
        self.st.finished_signal.connect(self._on_finished)
        self.st.error_signal.connect(self._on_error)
        self.st.start()

    def _on_progress(self, msg):
        self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def _on_finished(self, data):
        self.progress.setVisible(False)
        self.search_btn.setEnabled(True)
        self.current_data = data

        src = data.get("来源", "")
        title = data.get("标题", "")
        years = data.get("年份", [])
        items = list(data.get("数据", {}).keys())

        self.log.append(f"✅ 获取成功！来源: {src}")
        self.log.append(f"   数据: {title} | {len(years)}年 | {len(items)}项指标")

        # 年份
        self.ys.clear(); self.ye.clear()
        self.ys.addItems(years); self.ye.addItems(years)
        if years:
            self.ye.setCurrentIndex(len(years) - 1)
            self.auto_year.setChecked(True)

        # 复选框
        while self.cb_layout.count():
            it = self.cb_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        self.data_cbs = []
        for name in items:
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setStyleSheet("font-size: 11px;")
            self.cb_layout.addWidget(cb)
            self.data_cbs.append(cb)

        self.status_label.setText(f"✅ 搜索成功 | {src} | {len(years)}年数据")
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        self.gen_btn.setEnabled(True)
        for attr in ['png', 'jpg', 'pdf', 'svg', 'csv', 'xlsx']:
            btn = getattr(self, f'export_btn_{attr}', None)
            if btn: btn.setEnabled(True)

        # 自动生成
        self.generate_chart()

    def _on_error(self, msg):
        self.progress.setVisible(False)
        self.search_btn.setEnabled(True)
        self.log.append(f"❌ {msg}")
        self.status_label.setText("⚠ 搜索遇到问题，已使用备用数据")
        self.status_label.setStyleSheet("color: #e67e22;")
        QMessageBox.warning(self, "提示", msg)

    def _selected(self):
        return [cb.text() for cb in self.data_cbs if cb.isChecked()]

    # ===== 图表生成 =====
    def generate_chart(self):
        if not self.current_data:
            return
        sel = self._selected()
        if not sel:
            return QMessageBox.warning(self, "提示", "请选择数据项")

        all_years = self.current_data.get("年份", [])
        dd = self.current_data.get("数据", {})
        title = self.current_data.get("标题", "")
        source = self.current_data.get("来源", "")

        if self.auto_year.isChecked():
            si, ei = 0, len(all_years) - 1
        else:
            try:
                si = all_years.index(self.ys.currentText())
                ei = all_years.index(self.ye.currentText())
            except ValueError:
                si, ei = 0, len(all_years) - 1
        if si > ei: si, ei = ei, si

        years = all_years[si:ei+1]
        plot = {}
        for item in sel:
            if item in dd:
                plot[item] = dd[item][si:ei+1]
        if not plot:
            return

        colors = ['#e74c3c','#3498db','#2ecc71','#f39c12','#9b59b6',
                  '#1abc9c','#e67e22','#34495e']

        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)
        ci = self.chart_type.currentIndex()
        sl = self.show_labels_cb.isChecked()
        xp = range(len(years))

        if ci == 0:  # 折线
            for i, (n, v) in enumerate(plot.items()):
                c = colors[i % len(colors)]
                ax.plot(xp, v, 'o-', color=c, lw=2.5, ms=6, mfc='white', mew=2, label=n)
                if sl and len(v) <= 15:
                    for j, val in enumerate(v):
                        ax.annotate(self._fmt(val), (xp[j], v[j]),
                                   textcoords="offset points", xytext=(0, 10),
                                   ha='center', fontsize=7, color=c)
        elif ci == 1:  # 柱状
            n = len(plot); w = 0.8/n
            for i, (name, vals) in enumerate(plot.items()):
                c = colors[i % len(colors)]
                off = (i - n/2 + 0.5) * w
                bars = ax.bar([p+off for p in xp], vals, w, color=c, ec='white', alpha=0.85, label=name)
                if sl and len(vals) <= 10:
                    mx = max(max(vals) for vals in plot.values())
                    for bar, val in zip(bars, vals):
                        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+mx*0.01,
                               self._fmt(val), ha='center', va='bottom', fontsize=7)
        elif ci == 2:  # 饼图
            first = sel[0]; vals = plot[first]
            wedges, texts, autotexts = ax.pie(
                vals, labels=years, autopct='%1.1f%%',
                colors=colors[:len(vals)], startangle=90,
                wedgeprops={'ec':'white','lw':1.5})
            for t in autotexts: t.set_fontsize(8)
            title = f"{title} - {first}"
        elif ci == 3:  # 面积
            for i, (n, v) in enumerate(plot.items()):
                c = colors[i % len(colors)]
                ax.fill_between(xp, v, alpha=0.2, color=c)
                ax.plot(xp, v, 'o-', color=c, lw=2, ms=5, mfc='white', label=n)
        elif ci == 4:  # 散点
            for i, (n, v) in enumerate(plot.items()):
                c = colors[i % len(colors)]
                ax.scatter(xp, v, c=c, s=80, alpha=0.7, ec='white', lw=1, label=n)
                if len(v) > 1:
                    z = np.polyfit(xp, v, 1)
                    ax.plot(xp, np.poly1d(z)(xp), '--', color=c, alpha=0.3, lw=1.5)

        if ci != 2:
            ax.set_xticks(xp)
            ax.set_xticklabels(years, fontsize=8, rotation=30 if len(years) > 10 else 0)
            ax.set_xlabel("年份", fontsize=10)
            ax.set_ylabel("数值", fontsize=10)

        ax.set_title(f"{title}\n（来源: {source}）", fontsize=13, fontweight='bold', pad=10, color='#2c3e50')
        ax.legend(loc='best', fontsize=8, framealpha=0.9)
        ax.grid(True, alpha=0.2, linestyle='--')
        ax.set_facecolor('#fafafa')
        self.canvas.fig.tight_layout(pad=2)
        self.canvas.draw()
        self.statusBar().showMessage(f"✅ 图表已生成 | {source}")

    def _fmt(self, v):
        if abs(v) >= 1e8: return f'{v/1e8:.2f}亿'
        if abs(v) >= 1e4: return f'{v/1e4:.1f}万'
        if abs(v) >= 100: return f'{v:.0f}'
        if abs(v) >= 1: return f'{v:.1f}'
        return f'{v:.3f}'

    # ===== 导出 =====
    def save_png(self, ext):
        self._save_chart("PNG图片", "*.png", "png")

    def save_jpg(self, ext):
        self._save_chart("JPG图片", "*.jpg", "jpg")

    def save_pdf(self, ext):
        self._save_chart("PDF文档", "*.pdf", "pdf")

    def save_svg(self, ext):
        self._save_chart("SVG矢量图", "*.svg", "svg")

    def _save_chart(self, desc, pattern, fmt):
        path, _ = QFileDialog.getSaveFileName(self, f"导出{desc}", f"chart.{fmt}", f"{desc} ({pattern})")
        if path:
            try:
                dpi = 200 if fmt in ('png', 'jpg') else None
                self.canvas.fig.savefig(path, dpi=dpi, bbox_inches='tight', facecolor='white')
                QMessageBox.information(self, "成功", f"已保存:\n{path}")
            except Exception as e:
                QMessageBox.warning(self, "失败", str(e))

    def export_csv(self, ext):
        self._export_data("CSV文件", "*.csv", "csv")

    def export_excel(self, ext):
        self._export_data("Excel文件", "*.xlsx", "xlsx")

    def _export_data(self, desc, pattern, fmt):
        if not self.current_data:
            return
        path, _ = QFileDialog.getSaveFileName(self, f"导出{desc}", f"data.{fmt}", f"{desc} ({pattern})")
        if not path:
            return
        try:
            years = self.current_data.get("年份", [])
            dd = self.current_data.get("数据", {})
            df = pd.DataFrame({"年份": years, **dd})
            if fmt == 'csv':
                df.to_csv(path, index=False, encoding='utf-8-sig')
            else:
                df.to_excel(path, index=False)
            QMessageBox.information(self, "成功", f"数据已导出:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet("""
        QMainWindow { background: #f5f6fa; }
        QComboBox { padding: 4px 8px; border: 1px solid #bdc3c7; border-radius: 4px; background: white; }
    """)
    w = KITUApp()
    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
