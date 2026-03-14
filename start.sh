uv venv

uv tool install yt-dlp[default,curl-cffi]

yt-dlp "https://www.tiktok.com/@kobiritukii/live" --get-url

ffmpeg -i "https://pull-hls-f16-sg01.tiktokcdn.com/stage/stream-2136630083463938117_or4/index.m3u8?expire=1774717953&sign=ebafddf3772c571b72f2ea208af19688" \
-t 10 -c copy -bsf:a aac_adtstoasc \
-movflags +faststart \
tiktok_10s_test.mp4

ffmpeg -i "https://pull-hls-tiktok.xx.com/xx.m3u8" -c:v copy -c:a aac -f flv "rtmp://live-push.bilivideo.com/live-bvc/?streamname=xxx&key=yyy"

ffmpeg \
  -headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36\r\nReferer: https://www.tiktok.com/\r\n" \
  -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 -timeout 30000000 \
  -i "https://pull-hls-f16-sg01.tiktokcdn.com/stage/stream-2136630083463938117_or4/index.m3u8?expire=1774717953&sign=ebafddf3772c571b72f2ea208af19688" \
  -c copy -bsf:a aac_adtstoasc \
  -map 0 -reset_timestamps 1 \
  -f segment \
  -segment_time 10 \
  -segment_format mp4 \
  -strftime 1 \
  "tiktok_live_%Y%m%d_%H%M%S.mp4"
