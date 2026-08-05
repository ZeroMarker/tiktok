#!/usr/bin/env python3
"""Try to enter the TikTok room and get stream URL."""
import re, json, sys
from curl_cffi import requests

session = requests.Session()
session.get("https://www.tiktok.com", impersonate="chrome131")
r = session.get("https://www.tiktok.com/@emma_kusunoki/live", impersonate="chrome131", timeout=20)

match = re.search(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', r.text, re.DOTALL)
sigi = json.loads(match.group(1))

# Get the user's permanent room id from LiveRoom.user
user_room_id = sigi.get("LiveRoom", {}).get("liveRoomUserInfo", {}).get("user", {}).get("roomId", "")
print(f"User roomId: {user_room_id}")

# Try room/enter API - this is what the frontend does
# The POST body needs specific parameters
room_id = str(user_room_id)

# Get cookies from the session
cookies = session.cookies.get_dict()
print(f"Cookies: {list(cookies.keys())}")

# Try room/enter via curl_cffi POST
r_enter = session.post(
    "https://webcast.tiktok.com/webcast/room/enter/",
    data={
        "room_id": room_id,
        "aid": "1988",
        "live_id": "1",
        "resp_content_type": "protobuf",
    },
    impersonate="chrome131",
    timeout=15,
)
print(f"\nroom/enter POST status: {r_enter.status_code}")
print(f"room/enter body: {r_enter.text[:500]}")

# Also try with get (as the page does via SSR)
r_enter_get = session.get(
    "https://webcast.tiktok.com/webcast/room/enter/",
    params={"room_id": room_id, "aid": "1988"},
    impersonate="chrome131",
    timeout=15,
)
print(f"\nroom/enter GET status: {r_enter_get.status_code}")
print(f"room/enter GET body: {r_enter_get.text[:500]}")

# Try room/data endpoint
r_data = session.get(
    "https://webcast.tiktok.com/webcast/room/data/",
    params={"room_id": room_id, "aid": "1988"},
    impersonate="chrome131",
    timeout=15,
)
print(f"\nroom/data status: {r_data.status_code}")
print(f"room/data body: {r_data.text[:300]}")
