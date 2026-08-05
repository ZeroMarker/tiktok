#!/usr/bin/env python3
"""
playwright_capture.py — Playwright 浏览器抓取 TikTok 直播流

与 simple 版不同，此脚本拦截所有 XHR/API 响应，
并从 webcast API 响应中提取流 URL。

用法：
  python3 playwright_capture.py <username> [--headless]
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

        captured = {"api": [], "streams": []}

        async def on_response(response):
            url = response.url
            try:
                body = await response.text()
            except:
                body = ""

            # 捕获 webcast API
            if "webcast" in url or "room/info" in url:
                captured["api"].append(url)
                print(f"[API] {url[:120]} → {body[:300]}", file=sys.stderr)
                try:
                    data = json.loads(body)
                    stream_url = (
                        data.get("data", {}).get("stream_url")
                        or data.get("data", {}).get("liveUrl")
                        or data.get("data", {}).get("rtmp_pull_url")
                        or data.get("data", {}).get("hls_pull_url")
                    )
                    if stream_url:
                        captured["streams"].append(stream_url)
                        print("  → stream_url found!", file=sys.stderr)
                except:
                    pass

            # 捕获流 URL
            if "tiktokcdn" in url and ("flv" in url or "m3u8" in url):
                captured["streams"].append(url)
                print(f"[STREAM] {url[:150]}", file=sys.stderr)

            # 捕获 /api/live/ 或类似端点
            if "/api/live/" in url or "live/detail" in url or "live/room" in url:
                if "room_id" in url or "live" in url:
                    captured["api"].append(url)
                    print(f"[LIVE_API] {url[:120]}", file=sys.stderr)

        page.on("response", on_response)

        try:
            print(f"[playwright_capture] loading @{username}/live ...", file=sys.stderr)
            await page.goto(live_url, wait_until="domcontentloaded", timeout=30000)
            # Wait for JS to execute and API calls
            await asyncio.sleep(10)

            # Check for video element
            video_src = await page.evaluate("""
                () => {
                    const v = document.querySelector('video');
                    return v ? (v.src || v.currentSrc || null) : null;
                }
            """)

            # Also check page source for pre-loaded data
            sigi = await page.evaluate("""
                () => {
                    const el = document.getElementById('SIGI_STATE');
                    return el ? el.textContent : null;
                }
            """)
            if sigi:
                s = json.loads(sigi)
                lr = s.get("LiveRoom", {}) or {}
                lru = lr.get("liveRoomUserInfo", {}) or {}
                lro = lru.get("liveRoom", {}) or {}
                cr = s.get("CurrentRoom", {}) or {}
                print(f"[SIGI] status={lro.get('status')} roomId={lro.get('roomId')} CurrentRoom={list(cr.keys())}", file=sys.stderr)

            print(f"\n--- 结果汇总 ---", file=sys.stderr)
            print(f"已捕获 API 请求: {len(captured['api'])}", file=sys.stderr)
            print(f"已捕获流 URL: {len(captured['streams'])}", file=sys.stderr)
            print(f"Video element src: {video_src}", file=sys.stderr)

            if captured["streams"]:
                print(captured["streams"][0])
                await browser.close()
                return

            if video_src and ("flv" in video_src or "m3u8" in video_src or "tiktokcdn" in video_src):
                print(video_src)
                await browser.close()
                return

            print(f"未发现直播流", file=sys.stderr)
            await browser.close()
            sys.exit(1)

        except Exception as e:
            print(f"错误: {e}", file=sys.stderr)
            await browser.close()
            sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <TikTok 用户名> [--headless]", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main())
