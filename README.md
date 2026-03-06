# 金价与汇率追踪网页

一个基于官方公开数据的静态网页，追踪：

- 国际金价：LBMA Gold Price
- 上海金价：上海黄金交易所上海金基准价
- 欧元兑人民币
- 美元兑人民币

## 数据来源

- ECB: `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml`
- LBMA: `https://prices.lbma.org.uk/json/today.json`
- SGE 首页: `https://www.sge.com.cn/`
- SGE 上海金基准价历史: `https://www.sge.com.cn/graph/DayilyJzj`

## 本地运行

```bash
python scripts/fetch_data.py
python -m http.server 8000
```

打开 `http://127.0.0.1:8000`。

## 测试

解析测试：

```bash
python -m unittest scripts.test_fetchers -v
```

浏览器烟雾测试：

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
python -m unittest tests.test_e2e -v
```

## 自动更新

仓库中已包含 GitHub Actions 工作流：

- 每天 `18:15 Europe/Paris` 抓取并更新数据
- 若数据变化则自动提交 `data/latest.json` 与 `data/history.json`
- 自动部署到 GitHub Pages
