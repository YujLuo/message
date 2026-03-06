import json
import unittest
from pathlib import Path

from scripts.fetch_data import parse_coingecko, parse_sge_delayed, parse_sina_fx, parse_sina_gold, parse_sina_hq

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


class FetcherParsingTests(unittest.TestCase):
    def test_parse_sina_hq(self) -> None:
        text = (FIXTURES / "sina_hq.txt").read_text(encoding="utf-8")
        payload = parse_sina_hq(text)
        self.assertIn("hf_XAU", payload)
        self.assertIn("fx_susdcny", payload)
        self.assertIn("fx_seurcny", payload)

    def test_parse_sina_gold(self) -> None:
        text = (FIXTURES / "sina_hq.txt").read_text(encoding="utf-8")
        payload = parse_sina_hq(text)
        gold = parse_sina_gold(payload["hf_XAU"])
        self.assertEqual(gold["label"], "伦敦金（现货黄金）")
        self.assertAlmostEqual(gold["value"], 5096.18)
        self.assertEqual(gold["market_time"], "2026-03-06 17:45:00")

    def test_parse_sina_fx(self) -> None:
        text = (FIXTURES / "sina_hq.txt").read_text(encoding="utf-8")
        payload = parse_sina_hq(text)
        usd = parse_sina_fx(payload["fx_susdcny"], label="美元兑人民币")
        eur = parse_sina_fx(payload["fx_seurcny"], label="欧元兑人民币")
        self.assertAlmostEqual(usd["value"], 6.906)
        self.assertAlmostEqual(eur["value"], 7.9937)

    def test_parse_sge_delayed(self) -> None:
        html_text = (FIXTURES / "sge_yshqbg.html").read_text(encoding="utf-8")
        payload = parse_sge_delayed(html_text)
        self.assertAlmostEqual(payload["value"], 1139.9)
        self.assertAlmostEqual(payload["high"], 1151.0)
        self.assertAlmostEqual(payload["low"], 1132.0)

    def test_parse_coingecko(self) -> None:
        payload = json.loads((FIXTURES / "coingecko_btc.json").read_text(encoding="utf-8-sig"))
        btc = parse_coingecko(payload)
        self.assertAlmostEqual(btc["usd"], 70470)
        self.assertAlmostEqual(btc["cny"], 486576)


if __name__ == "__main__":
    unittest.main()
