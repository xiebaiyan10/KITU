# KITU - 智能图表生成器

输入关键词 → 联网搜索真实数据 → 一键生成精美图表

<p align="center">
  <img src="kitu.ico" width="128" alt="KITU Logo">
</p>

## ✨ 特点

- 🔍 **真实联网搜索** — 不是假数据！接入国家统计局、东方财富、搜狗/Bing等真实数据源
- 🎯 **傻瓜式操作** — 输入关键词就完事，小学生也能用
- 📊 **5种图表** — 折线图（看趋势）、柱状图（比大小）、饼图（看占比）、面积图、散点图
- 💾 **6种导出** — PNG / JPG / PDF / SVG / CSV / Excel
- 🪟 **桌面应用** — 双击exe直接打开，不用装Python

## 📸 截图

<!-- 可以在这里放截图 -->

## 🚀 使用

### 双击 `KITU.exe` 直接运行

或者从源码运行：
```bash
pip install -r requirements.txt
python main.py
```

然后输入你想查的关键词，比如：

| 输入 | 生成 |
|------|------|
| `中国GDP` | 中国GDP及增长率趋势图 |
| `CPI` | 居民消费价格指数走势 |
| `人口` | 中国人口与出生率变化 |
| `房价` | 北上广深房价对比 |
| `互联网用户` | 网民数量与普及率 |
| `新能源车` | 新能源汽车销量趋势 |

## 🛠 技术栈

Python 3 / PyQt5 / Matplotlib / Pandas / Requests / BeautifulSoup4

## 📄 License

MIT — 随便用
