import json
import unittest
from datetime import date
from pathlib import Path

from scripts.fetch_data import parse_ecb_history, parse_lbma_today, parse_sge_history, parse_sge_home

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


class FetcherParsingTests(unittest.TestCase):
    def test_parse_ecb_history(self) -> None:
        xml_text = (FIXTURES / "ecb_hist_90d.xml").read_text(encoding="utf-8")
        data = parse_ecb_history(xml_text)
        self.assertEqual(data[-1]["date"], "2026-03-05")
        self.assertAlmostEqual(data[-1]["eur_cny"], 8.3381)
        self.assertAlmostEqual(data[-1]["usd_cny"], 7.1768807024)

    def test_parse_lbma_today_prefers_pm(self) -> None:
        payload = json.loads((FIXTURES / "lbma_today.json").read_text(encoding="utf-8-sig"))
        latest, history = parse_lbma_today(payload, today_local=date(2026, 3, 6))
        self.assertEqual(latest["as_of"], "2026-03-05")
        self.assertEqual(latest["source_note"], "LBMA Gold Price PM")
        self.assertGreaterEqual(len(history), 3)

    def test_parse_sge_home(self) -> None:
        html_text = (FIXTURES / "sge_home.html").read_text(encoding="utf-8")
        payload = parse_sge_home(html_text)
        self.assertEqual(payload["as_of"], "2026-03-06")
        self.assertAlmostEqual(payload["am"], 1143.07)
        self.assertAlmostEqual(payload["pm"], 1139.95)

    def test_parse_sge_history_uses_pm_when_present(self) -> None:
        payload = json.loads((FIXTURES / "sge_dayily_jzj.json").read_text(encoding="utf-8-sig"))
        series = parse_sge_history(payload)
        self.assertEqual(series[0]["date"], "2026-03-03")
        self.assertAlmostEqual(series[0]["value"], 1136.48)


if __name__ == "__main__":
    unittest.main()
