from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LATEST_PATH = DATA_DIR / "latest.json"
HISTORY_PATH = DATA_DIR / "history.json"
PARIS = ZoneInfo("Europe/Paris")

ECB_HISTORY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
ECB_SOURCE_PAGE = "https://www.ecb.europa.eu/stats/eurofxref/html/index.en.html"
LBMA_TODAY_URL = "https://prices.lbma.org.uk/json/today.json"
LBMA_SOURCE_PAGE = "https://www.lbma.org.uk/prices-and-data/lbma-gold-price"
SGE_HOME_URL = "https://www.sge.com.cn/"
SGE_HISTORY_URL = "https://www.sge.com.cn/graph/DayilyJzj"
USER_AGENT = "Mozilla/5.0 (Codex Market Tracker)"


def fetch_text(url: str, *, data: bytes | None = None) -> str:
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "ignore")


def fetch_json(url: str, *, data: bytes | None = None) -> Any:
    return json.loads(fetch_text(url, data=data))


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_ecb_history(xml_text: str) -> list[dict[str, Any]]:
    namespace = {"ecb": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
    root = ET.fromstring(xml_text)
    series = []

    for cube in root.findall(".//ecb:Cube[@time]", namespace):
        rates = {node.attrib["currency"]: float(node.attrib["rate"]) for node in cube.findall("ecb:Cube", namespace)}
        cny_rate = rates.get("CNY")
        usd_rate = rates.get("USD")
        if not cny_rate or not usd_rate:
            continue
        series.append(
            {
                "date": cube.attrib["time"],
                "eur_cny": cny_rate,
                "usd_cny": cny_rate / usd_rate,
            }
        )

    return sorted(series, key=lambda item: item["date"])


def infer_lbma_date(label: str, today_local: date) -> str:
    day, month = map(int, label.split("/"))
    candidate = date(today_local.year, month, day)
    if candidate > today_local + timedelta(days=7):
        candidate = date(today_local.year - 1, month, day)
    return candidate.isoformat()


def pick_lbma_fix(gold_data: dict[str, Any]) -> tuple[str, float, str]:
    pm = gold_data.get("pm") or {}
    am = gold_data.get("am") or {}

    if pm.get("usd"):
        return "PM", float(pm["usd"]), pm.get("date") or am.get("date")
    if am.get("usd"):
        return "AM", float(am["usd"]), am.get("date")
    raise ValueError("LBMA gold data missing both AM and PM values")


def parse_lbma_today(payload: dict[str, Any], today_local: date) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    gold = payload.get("gold") or {}
    fix_label, latest_value, fix_date_label = pick_lbma_fix(gold)
    if not fix_date_label:
        raise ValueError("LBMA fix date missing")

    latest = {
        "as_of": infer_lbma_date(fix_date_label, today_local),
        "value": latest_value,
        "source_note": f"LBMA Gold Price {fix_label}",
    }

    history = []
    week_values = gold.get("week") or []
    week_labels = gold.get("weekLabel") or []
    for label, raw_value in zip(week_labels, week_values, strict=False):
        value = raw_value.get("y") if isinstance(raw_value, dict) else raw_value
        if value is None:
            continue
        history.append(
            {
                "date": infer_lbma_date(label, today_local),
                "value": float(value),
            }
        )

    return latest, history


def parse_sge_home(html_text: str) -> dict[str, Any]:
    date_match = re.search(r"行情日期：(\d{4}-\d{2}-\d{2})", html_text)
    am_match = re.search(r"上海金早盘价（元/克）</p><span[^>]*>([0-9.]+)</span>", html_text)
    pm_match = re.search(r"上海金午盘价（元/克）</p><span[^>]*>([0-9.]+)</span>", html_text)

    if not date_match or not am_match:
        raise ValueError("Failed to parse SGE homepage quote block")

    return {
        "as_of": date_match.group(1),
        "am": float(am_match.group(1)),
        "pm": float(pm_match.group(1)) if pm_match else None,
    }


def parse_sge_history(payload: dict[str, Any]) -> list[dict[str, Any]]:
    am_map = {datetime.fromtimestamp(item[0] / 1000, tz=UTC).date().isoformat(): float(item[1]) for item in payload.get("zp", [])}
    pm_map = {datetime.fromtimestamp(item[0] / 1000, tz=UTC).date().isoformat(): float(item[1]) for item in payload.get("wp", [])}
    dates = sorted(set(am_map) | set(pm_map))
    history = []

    for day in dates:
        value = pm_map.get(day, am_map.get(day))
        if value is None:
            continue
        history.append({"date": day, "value": value})

    return history


def merge_series(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], *, limit: int = 30) -> list[dict[str, Any]]:
    merged = {item["date"]: item for item in existing if "date" in item and "value" in item}
    for item in incoming:
        merged[item["date"]] = {"date": item["date"], "value": float(item["value"])}
    return sorted(merged.values(), key=lambda item: item["date"])[-limit:]


def find_previous_value(series: list[dict[str, Any]], latest_date: str) -> float | None:
    prior = [item["value"] for item in series if item["date"] < latest_date]
    return prior[-1] if prior else None


def build_metric(
    *,
    series: list[dict[str, Any]],
    latest_date: str,
    latest_value: float,
    label: str,
    unit: str,
    category: str,
    source_name: str,
    source_url: str,
    source_note: str,
    today_local: date,
) -> dict[str, Any]:
    previous = find_previous_value(series, latest_date)
    change_abs = None if previous is None else latest_value - previous
    change_pct = None if previous in (None, 0) else (change_abs / previous) * 100

    return {
        "label": label,
        "value": round(latest_value, 4 if category == "fx" else 2),
        "unit": unit,
        "category": category,
        "as_of": latest_date,
        "stale": latest_date < today_local.isoformat(),
        "change_abs": None if change_abs is None else round(change_abs, 6),
        "change_pct": None if change_pct is None else round(change_pct, 4),
        "source_name": source_name,
        "source_url": source_url,
        "source_note": source_note,
    }


def build_latest_payload(
    *,
    intl_gold: dict[str, Any],
    sh_gold: dict[str, Any],
    eur_cny: dict[str, Any],
    usd_cny: dict[str, Any],
    generated_at: datetime,
) -> dict[str, Any]:
    stale = any(metric["stale"] for metric in (intl_gold, sh_gold, eur_cny, usd_cny))
    return {
        "as_of": generated_at.date().isoformat(),
        "published_at": generated_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "stale": stale,
        "gold": {
            "international": intl_gold,
            "shanghai": sh_gold,
        },
        "fx": {
            "eur_cny": eur_cny,
            "usd_cny": usd_cny,
        },
        "sources": [
            {"id": "lbma", "label": "LBMA Gold Price", "url": LBMA_SOURCE_PAGE},
            {"id": "sge", "label": "上海黄金交易所 上海金基准价", "url": "https://www.sge.com.cn/sjzx/jzj"},
            {"id": "ecb", "label": "ECB 欧元外汇参考汇率", "url": ECB_SOURCE_PAGE},
        ],
    }


def main() -> None:
    today_local = datetime.now(PARIS).date()
    generated_at = datetime.now(PARIS)
    existing_history = load_json_file(HISTORY_PATH, {"series": {}})
    series_store: dict[str, list[dict[str, Any]]] = existing_history.get("series", {})

    ecb_xml = fetch_text(ECB_HISTORY_URL)
    ecb_history = parse_ecb_history(ecb_xml)
    eur_cny_series = [{"date": item["date"], "value": item["eur_cny"]} for item in ecb_history][-30:]
    usd_cny_series = [{"date": item["date"], "value": item["usd_cny"]} for item in ecb_history][-30:]
    latest_fx = ecb_history[-1]

    lbma_payload = fetch_json(LBMA_TODAY_URL)
    lbma_latest, lbma_week = parse_lbma_today(lbma_payload, today_local)
    intl_gold_series = merge_series(series_store.get("international_gold", []), lbma_week, limit=30)
    if not any(item["date"] == lbma_latest["as_of"] for item in intl_gold_series):
        intl_gold_series = merge_series(
            intl_gold_series,
            [{"date": lbma_latest["as_of"], "value": lbma_latest["value"]}],
            limit=30,
        )

    sge_home = parse_sge_home(fetch_text(SGE_HOME_URL))
    sge_history_payload = fetch_json(
        SGE_HISTORY_URL,
        data=urllib.parse.urlencode({"start": (today_local - timedelta(days=120)).isoformat(), "end": today_local.isoformat()}).encode(),
    )
    sge_history = parse_sge_history(sge_history_payload)[-30:]
    shanghai_latest_value = sge_home["pm"] if sge_home["pm"] is not None else sge_home["am"]
    if not any(item["date"] == sge_home["as_of"] for item in sge_history):
        sge_history = merge_series(sge_history, [{"date": sge_home["as_of"], "value": shanghai_latest_value}], limit=30)

    intl_gold_metric = build_metric(
        series=intl_gold_series,
        latest_date=lbma_latest["as_of"],
        latest_value=lbma_latest["value"],
        label="国际金价",
        unit="USD/oz",
        category="gold",
        source_name="LBMA",
        source_url=LBMA_SOURCE_PAGE,
        source_note=lbma_latest["source_note"],
        today_local=today_local,
    )

    shanghai_gold_metric = build_metric(
        series=sge_history,
        latest_date=sge_home["as_of"],
        latest_value=shanghai_latest_value,
        label="上海金价",
        unit="CNY/g",
        category="gold",
        source_name="SGE",
        source_url="https://www.sge.com.cn/sjzx/jzj",
        source_note="上海金基准价 PM" if sge_home["pm"] is not None else "上海金基准价 AM",
        today_local=today_local,
    )

    eur_cny_metric = build_metric(
        series=eur_cny_series,
        latest_date=latest_fx["date"],
        latest_value=latest_fx["eur_cny"],
        label="欧元兑人民币",
        unit="CNY",
        category="fx",
        source_name="ECB",
        source_url=ECB_SOURCE_PAGE,
        source_note="ECB 官方参考汇率",
        today_local=today_local,
    )

    usd_cny_metric = build_metric(
        series=usd_cny_series,
        latest_date=latest_fx["date"],
        latest_value=latest_fx["usd_cny"],
        label="美元兑人民币",
        unit="CNY",
        category="fx",
        source_name="ECB",
        source_url=ECB_SOURCE_PAGE,
        source_note="ECB 官方参考汇率",
        today_local=today_local,
    )

    latest_payload = build_latest_payload(
        intl_gold=intl_gold_metric,
        sh_gold=shanghai_gold_metric,
        eur_cny=eur_cny_metric,
        usd_cny=usd_cny_metric,
        generated_at=generated_at,
    )
    history_payload = {
        "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "series": {
            "international_gold": intl_gold_series,
            "shanghai_gold": sge_history,
            "eur_cny": eur_cny_series,
            "usd_cny": usd_cny_series,
        },
    }

    write_json_file(LATEST_PATH, latest_payload)
    write_json_file(HISTORY_PATH, history_payload)


if __name__ == "__main__":
    main()
