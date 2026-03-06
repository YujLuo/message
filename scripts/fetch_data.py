from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LATEST_PATH = DATA_DIR / "latest.json"
HISTORY_PATH = DATA_DIR / "history.json"
PARIS = ZoneInfo("Europe/Paris")
USER_AGENT = "Mozilla/5.0 (Codex Market Tracker)"
HISTORY_LIMIT = 72

SINA_HQ_URL = "https://hq.sinajs.cn/?list=hf_XAU,fx_susdcny,fx_seurcny"
SINA_SOURCE_PAGE = "https://finance.sina.com.cn"
SGE_DELAYED_URL = "https://www.sge.com.cn/sjzx/yshqbg"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd,cny&include_24hr_change=true"
COINGECKO_SOURCE_PAGE = "https://www.coingecko.com/en/coins/bitcoin"
GOLD_API_URL = "https://api.gold-api.com/price/XAU"
GOLD_API_SOURCE_PAGE = "https://gold-api.com/"


def fetch_text(url: str, *, encoding: str = "utf-8") -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": SINA_SOURCE_PAGE,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode(encoding, "ignore")


def fetch_json(url: str) -> Any:
    return json.loads(fetch_text(url))


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_sina_hq(text: str) -> dict[str, list[str]]:
    payload: dict[str, list[str]] = {}
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        match = re.match(r'var hq_str_([^=]+)="(.*)";$', line)
        if not match:
            continue
        payload[match.group(1)] = match.group(2).split(",")
    return payload


def parse_sina_gold(fields: list[str]) -> dict[str, Any]:
    return {
        "label": fields[13] or "伦敦金（现货黄金）",
        "value": float(fields[0]),
        "high": float(fields[4]),
        "low": float(fields[5]),
        "market_time": f"{fields[12]} {fields[6]}",
    }


def parse_sina_fx(fields: list[str], *, label: str) -> dict[str, Any]:
    return {
        "label": label,
        "value": float(fields[1]),
        "high": float(fields[5]),
        "low": float(fields[7]),
        "market_time": f"{fields[17]} {fields[0]}",
        "source_label": fields[9],
    }


def parse_sge_delayed(html_text: str) -> dict[str, Any]:
    row_match = re.search(
        r"<tr class=\"[^\"]*\">\s*<td[^>]*>Au99\.99</td>\s*<td[^>]*><span[^>]*>([0-9.]+)</span></td>\s*<td[^>]*[^>]*>([0-9.]+)</td>\s*<td[^>]*[^>]*>([0-9.]+)</td>\s*<td[^>]*[^>]*>([0-9.]+)</td>",
        html_text,
        re.S,
    )
    if not row_match:
        raise ValueError("Failed to parse SGE delayed Au99.99 row")

    return {
        "label": "Au99.99",
        "value": float(row_match.group(1)),
        "high": float(row_match.group(2)),
        "low": float(row_match.group(3)),
        "open": float(row_match.group(4)),
    }


def parse_coingecko(payload: dict[str, Any]) -> dict[str, Any]:
    btc = payload["bitcoin"]
    return {
        "label": "Bitcoin",
        "usd": float(btc["usd"]),
        "cny": float(btc["cny"]),
        "change_pct_24h": float(btc.get("cny_24h_change") or 0.0),
    }


def merge_series(existing: list[dict[str, Any]], incoming: dict[str, Any], *, limit: int = HISTORY_LIMIT) -> list[dict[str, Any]]:
    merged = [item for item in existing if "timestamp" in item and "value" in item and item.get("timestamp") != incoming["timestamp"]]
    merged.append(incoming)
    merged.sort(key=lambda item: item["timestamp"])
    return merged[-limit:]


def previous_value(series: list[dict[str, Any]], latest_timestamp: str) -> float | None:
    prior = [item["value"] for item in series if item["timestamp"] < latest_timestamp]
    return prior[-1] if prior else None


def build_metric(
    *,
    label: str,
    value: float,
    unit: str,
    category: str,
    timestamp: str,
    market_time: str,
    source_name: str,
    source_url: str,
    source_note: str,
    series: list[dict[str, Any]],
    precision: int,
    secondary_value: str | None = None,
) -> dict[str, Any]:
    previous = previous_value(series, timestamp)
    change_abs = None if previous is None else value - previous
    change_pct = None if previous in (None, 0) else (change_abs / previous) * 100
    return {
        "label": label,
        "value": round(value, precision),
        "unit": unit,
        "category": category,
        "timestamp": timestamp,
        "market_time": market_time,
        "change_abs": None if change_abs is None else round(change_abs, 6),
        "change_pct": None if change_pct is None else round(change_pct, 4),
        "change_basis": "较上次抓取",
        "source_name": source_name,
        "source_url": source_url,
        "source_note": source_note,
        "secondary_value": secondary_value,
    }


def main() -> None:
    generated_at = datetime.now(PARIS)
    snapshot_time = generated_at.isoformat(timespec="seconds")
    history_payload = load_json_file(HISTORY_PATH, {"series": {}})
    series_store: dict[str, list[dict[str, Any]]] = history_payload.get("series", {})

    sina_payload = parse_sina_hq(fetch_text(SINA_HQ_URL, encoding="gb18030"))
    gold_quote = parse_sina_gold(sina_payload["hf_XAU"])
    usd_cny_quote = parse_sina_fx(sina_payload["fx_susdcny"], label="美元兑人民币")
    eur_cny_quote = parse_sina_fx(sina_payload["fx_seurcny"], label="欧元兑人民币")
    sge_quote = parse_sge_delayed(fetch_text(SGE_DELAYED_URL))
    btc_quote = parse_coingecko(fetch_json(COINGECKO_URL))

    series_updates = {
        "international_gold": {"timestamp": snapshot_time, "value": gold_quote["value"]},
        "shanghai_gold": {"timestamp": snapshot_time, "value": sge_quote["value"]},
        "eur_cny": {"timestamp": snapshot_time, "value": eur_cny_quote["value"]},
        "usd_cny": {"timestamp": snapshot_time, "value": usd_cny_quote["value"]},
        "btc_cny": {"timestamp": snapshot_time, "value": btc_quote["cny"]},
    }

    merged_series = {
        key: merge_series(series_store.get(key, []), value)
        for key, value in series_updates.items()
    }

    latest_payload = {
        "as_of": generated_at.date().isoformat(),
        "published_at": generated_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "mode": "near_realtime",
        "refresh_interval_seconds": 300,
        "ui_poll_interval_seconds": 60,
        "gold": {
            "international": build_metric(
                label="国际金价",
                value=gold_quote["value"],
                unit="USD/oz",
                category="gold",
                timestamp=snapshot_time,
                market_time=gold_quote["market_time"],
                source_name="新浪财经",
                source_url="https://finance.sina.com.cn/money/future/hf.html",
                source_note="伦敦金（现货黄金）",
                series=merged_series["international_gold"],
                precision=2,
            ),
            "shanghai": build_metric(
                label="上海金价",
                value=sge_quote["value"],
                unit="CNY/g",
                category="gold",
                timestamp=snapshot_time,
                market_time=generated_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
                source_name="上海黄金交易所",
                source_url=SGE_DELAYED_URL,
                source_note="延时行情 Au99.99",
                series=merged_series["shanghai_gold"],
                precision=2,
            ),
        },
        "fx": {
            "eur_cny": build_metric(
                label="欧元兑人民币",
                value=eur_cny_quote["value"],
                unit="CNY",
                category="fx",
                timestamp=snapshot_time,
                market_time=eur_cny_quote["market_time"],
                source_name="新浪财经",
                source_url="https://finance.sina.com.cn/money/forex/hq/EURCNY.shtml",
                source_note="欧元兑人民币即期汇率",
                series=merged_series["eur_cny"],
                precision=4,
            ),
            "usd_cny": build_metric(
                label="美元兑人民币",
                value=usd_cny_quote["value"],
                unit="CNY",
                category="fx",
                timestamp=snapshot_time,
                market_time=usd_cny_quote["market_time"],
                source_name="新浪财经",
                source_url="https://finance.sina.com.cn/money/forex/hq/USDCNY.shtml",
                source_note="美元兑人民币即期汇率",
                series=merged_series["usd_cny"],
                precision=4,
            ),
        },
        "crypto": {
            "btc": build_metric(
                label="BTC 价格",
                value=btc_quote["cny"],
                unit="CNY",
                category="crypto",
                timestamp=snapshot_time,
                market_time=generated_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
                source_name="CoinGecko",
                source_url=COINGECKO_SOURCE_PAGE,
                source_note="Bitcoin spot price",
                series=merged_series["btc_cny"],
                precision=2,
                secondary_value=f"≈ {btc_quote['usd']:.2f} USD",
            ),
        },
        "sources": [
            {"id": "sina_gold", "label": "新浪财经 伦敦金", "url": "https://finance.sina.com.cn/money/future/hf.html"},
            {"id": "sge", "label": "上海黄金交易所 延时行情 Au99.99", "url": SGE_DELAYED_URL},
            {"id": "sina_fx", "label": "新浪财经 外汇即期汇率", "url": "https://finance.sina.com.cn/money/forex/hq.shtml"},
            {"id": "coingecko", "label": "CoinGecko Bitcoin Spot", "url": COINGECKO_SOURCE_PAGE},
        ],
    }

    history_output = {
        "generated_at": latest_payload["published_at"],
        "series": merged_series,
    }

    write_json_file(LATEST_PATH, latest_payload)
    write_json_file(HISTORY_PATH, history_output)


if __name__ == "__main__":
    main()

