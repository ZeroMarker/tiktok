#!/usr/bin/env python3
"""Check TikTok live detection details."""
import re, json, sys
sys.path.insert(0, "/root/tiktok/tk")
from curl_cffi import requests

session = requests.Session()
session.get("https://www.tiktok.com", impersonate="chrome131")

r = session.get("https://www.tiktok.com/@emma_kusunoki/live", impersonate="chrome131", timeout=20)
match = re.search(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', r.text, re.DOTALL)
sigi = json.loads(match.group(1))

cr = sigi.get("CurrentRoom", {})
print("CurrentRoom keys:", list(cr.keys()))
for k in ["roomId", "anchorId", "anchorUniqueId", "loadingState", "enterRoomWithSSR", "playMode"]:
    print(f"  {k}: {cr.get(k)}")
ri = cr.get("roomInfo")
print(f"roomInfo: {type(ri).__name__} = {ri}")
print(f"loadingState: {cr.get('loadingState')}")

# Check user profile in LiveRoom
lr = sigi.get("LiveRoom", {})
lru = lr.get("liveRoomUserInfo", {})
user = lru.get("user", {})
print(f"\nUser roomId: {user.get('roomId')}")
print(f"User isLive: {user.get('isLive')}")
print(f"User uniqueId: {user.get('uniqueId')}")

# The room from user details
print(f"\nroom_id used: {user.get('roomId')}")
print(f"liveRoom.status: {lru.get('liveRoom', {}).get('status')}")
print(f"liveRoom.roomId: {lru.get('liveRoom', {}).get('roomId')}")
print(f"liveRoom.title: {lru.get('liveRoom', {}).get('title')}")
print(f"liveRoom.startTime: {lru.get('liveRoom', {}).get('startTime')}")
