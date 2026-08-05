#!/usr/bin/env python3
"""
playwright_capture_v2.py — Playwright 拦截 TikTok API 响应并提取流地址

捕获的关键 API：
  - webcast.room.enter      → 进入房间，返回流地址
  - api-live/user/room      → 用户直播房间信息
  - webcast.room.info       → 房间信息

用法同上。
"""

import sys
import asyncio
import json

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)


async def main():
    username = sys.argv[1]
    headless = "--headless" in sys.argv or "-h" in sys.argv
    live_url = f"https://www.tiktok.com/@{username}/live"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        captured = {"streams": [], "api_responses": []}

        async def on_response(response):
            url = response.url
            if not any(k in url for k in [
                "webcast.room", "webcast/room", "api-live", "stream",
                "flv", "m3u8", "tiktokcdn", "room/info",
            ]):
                return

            try:
                body = await response.text()
            except:
                body = ""

            if not body or len(body) < 5:
                return

            # Print API response
            print(f"\n[RESP] {url[:130]}", file=sys.stderr)
            print(f"  body: {body[:500]}", file=sys.stderr)

            try:
                data = json.loads(body)

                # Check for stream URL at various paths
                stream_matches = []
                for path in [
                    "data.stream_url", "data.liveUrl", "data.rtmp_pull_url",
                    "data.hls_pull_url", "data.streamUrl",
                    "stream_url", "liveUrl",
                ]:
                    parts = path.split(".")
                    val = data
                    for p in parts:
                        if isinstance(val, dict):
                            val = val.get(p)
                        else:
                            val = None
                            break
                    if val and isinstance(val, str) and len(val) > 20:
                        stream_matches.append(val)

                for sm in stream_matches:
                    if sm not in captured["streams"]:
                        captured["streams"].append(sm)
                        print(f"  → STREAM FOUND: {sm[:120]}", file=sys.stderr)

                # Also check the whole JSON for any stream-like strings
                body_str = json.dumps(data)
                for keyword in ["pull", "stream", "flv", "m3u8", "rtmp", "url"]:
                    if keyword in body_str.lower():
                        pass  # already checking above

            except:
                pass

            # Also check raw body for stream URLs
            for kw in ["pull", "flv", "m3u8"]:
                if kw in body.lower():
                    import re
                    urls = re.findall(r'(https?://[^"\'<>,\s]+(?:flv|m3u8)[^"\'<>,\s]*)', body)
                    for u in urls:
                        if u not in captured["streams"]:
                            captured["streams"].append(u)
                            print(f"  → RAW STREAM: {u[:120]}", file=sys.stderr)

        page.on("response", on_response)

        try:
            print(f"[v2] loading @{username}/live ...", file=sys.stderr)
            await page.goto(live_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(15)  # Wait longer for API calls

            print(f"\n\n=== 最终结果 ===", file=sys.stderr)
            print(f"捕获的流 URL: {len(captured['streams'])}", file=sys.stderr)
            for s in captured["streams"]:
                print(f"  {s[:150]}", file=sys.stderr)

            if captured["streams"]:
                print(captured["streams"][0])
                await browser.close()
                return

            print("未发现直播流", file=sys.stderr)
            await browser.close()
            sys.exit(1)

        except Exception as e:
            import traceback
            print(f"错误: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            await browser.close()
            sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <TikTok 用户名> [--headless]", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main())
