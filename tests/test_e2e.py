import http.server
import os
import socketserver
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


class E2ESmokeTest(unittest.TestCase):
    @unittest.skipIf(sync_playwright is None, "playwright is not installed")
    def test_homepage_renders_market_cards(self) -> None:
        os.chdir(ROOT)
        with socketserver.TCPServer(("127.0.0.1", 0), QuietHandler) as httpd:
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()

            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    page = browser.new_page(viewport={"width": 1440, "height": 1200})
                    page.goto(f"http://127.0.0.1:{port}", wait_until="networkidle")
                    self.assertEqual(page.locator(".metric-card").count(), 6)
                    self.assertTrue(page.get_by_role("heading", name="国际金价").is_visible())
                    self.assertTrue(page.get_by_role("heading", name="上海金价").is_visible())
                    self.assertTrue(page.get_by_role("heading", name="欧元兑人民币").is_visible())
                    self.assertTrue(page.get_by_role("heading", name="美元兑人民币").is_visible())
                    self.assertTrue(page.get_by_role("heading", name="BTC 人民币价格").is_visible())
                    self.assertTrue(page.get_by_role("heading", name="BTC 美元价格").is_visible())
                    output_dir = ROOT / "output" / "playwright"
                    output_dir.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(output_dir / "homepage.png"), full_page=True)
                    browser.close()
            finally:
                httpd.shutdown()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
