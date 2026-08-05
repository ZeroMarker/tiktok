#!/usr/bin/env python3
"""
playwright_live_check.py — 用 Playwright 浏览器检测 TikTok 直播

当所有 API 检测均未发现直播时使用。
浏览器会真实渲染页面、执行 JavaScript，可能拿到 API 检测不到的流。

用法：
  python3 playwright_live_check.py <username>
  python3 playwright_live_check.py <username> --headless

成功 → 输出 FLV 流 URL（一行）
失败 → exit 1
"""

import sys
import asyncio
import json
import re

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("缺少 playwright：pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)


async def main():
    username = sys.argv[1]
    headless = "--headless" in sys.argv or "-h" in sys.argv
    live_url = f"https://www.tiktok.com/@{username}/live"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
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
            extra_http_headers={
                "X-Forwarded-For": "203.104.209.1",
                "X-Real-IP": "203.104.209.1",
            },
        )

        page = await context.new_page()

        # 监听网络请求，捕获 stream URL
        captured_urls = []

        def on_response(response):
            # 检查是否有 stream URL 在响应中
            if "stream" in response.url.lower() or "flv" in response.url.lower() or "m3u8" in response.url.lower():
                if "tiktokcdn" in response.url:
                    captured_urls.append(response.url)

        page.on("response", on_response)

        try:
            print(f"[playwright] 正在加载 @{username}/live ...", file=sys.stderr)
            await page.goto(live_url, wait_until="domcontentloaded", timeout=30000)
            # 等待页面渲染
            await asyncio.sleep(8)

            # 尝试从页面提取 SIGI_STATE（渲染后的版本）
            sigi_text = await page.evaluate("""
                () => {
                    const el = document.getElementById('SIGI_STATE');
                    return el ? el.textContent : null;
                }
            """)

            if sigi_text:
                sigi = json.loads(sigi_text)
                lr = sigi.get("LiveRoom", {}) or {}
                lr_user_info = lr.get("liveRoomUserInfo", {}) or {}
                lr_data = lr_user_info.get("liveRoom", {}) or {}
                status = lr_data.get("status")
                room_id = lr_data.get("roomId")
                cr_info = sigi.get("CurrentRoom", {}).get("roomInfo") or {}
                cr_room = cr_info.get("roomId") if cr_info else None
                print(f"[playwright] SIGI_STATE: status={status}, liveRoom.roomId={room_id}, CurrentRoom.roomId={cr_room}", file=sys.stderr)

            # 检查视频元素
            has_video = await page.evaluate("""
                () => {
                    const videos = document.querySelectorAll('video');
                    return videos.length > 0 && videos[0].src ? videos[0].src : null;
                }
            """)

            if has_video:
                print(f"[playwright] video src: {has_video[:100]}", file=sys.stderr)
                captured_urls.append(has_video)

            # 检查网络请求捕获
            stream_urls = []
            for u in captured_urls:
                if any(ext in u.lower() for ext in ['.flv', '.m3u8', '.ts']):
                    stream_urls.append(u)

            if stream_urls:
                print(stream_urls[0])
                await browser.close()
                return

            # 如果还没有发现，检查 prerender 数据
            prerender = await page.evaluate("""
                () => {
                    try {
                        const data = window.__PRERENDER_DATA__;
                        return data ? JSON.stringify(data).substring(0, 1000) : null;
                    } catch(e) { return null; }
                }
            """)
            if prerender:
                print(f"[playwright] prerender data found (len={len(prerender)})", file=sys.stderr)

            # 获取页面 html 中的 stream URL
            html = await page.content()
            flv_matches = re.findall(r'(https?://[^"\'<>]+?\.flv[^"\'<>]*)', html)
            for m in flv_matches:
                if 'tiktokcdn' in m:
                    print(m)
                    await browser.close()
                    return

            print(f"[playwright] 未发现直播流", file=sys.stderr)
            await browser.close()
            sys.exit(1)

        except Exception as e:
            print(f"[playwright] 错误: {e}", file=sys.stderr)
            await browser.close()
            sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法：{sys.argv[0]} <TikTok 用户名> [--headless]", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main())
