# 金价与汇率追踪网页

一个基于公开行情数据的静态网页，追踪：

- 国际金价：伦敦金（现货黄金）
- 上海金价：上金所延时行情 Au99.99
- 欧元兑人民币
- 美元兑人民币
- BTC 价格

## 数据来源

- 新浪财经：国际金价、欧元兑人民币、美元兑人民币
- 上海黄金交易所：Au99.99 延时行情
- CoinGecko：BTC 现货价格

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
python -m unittest tests.test_e2e -v
```

## 自动更新

仓库中已包含 GitHub Actions 工作流：

- 每 5 分钟抓取一次最新行情
- 若数据变化则自动提交 `data/latest.json` 与 `data/history.json`
- 自动部署到 GitHub Pages
