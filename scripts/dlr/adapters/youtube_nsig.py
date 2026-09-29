"""Solve the YouTube HLS URL n challenge with yt-dlp's EJS provider.

Input and output are JSON/URL over pipes so signed URLs never enter logs.
Requires yt-dlp-ejs and Node 22+, as documented by yt-dlp's EJS guide.
"""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import urljoin, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.extractor.youtube._video import YoutubeIE
from yt_dlp.extractor.youtube.jsc.provider import (
    JsChallengeRequest,
    JsChallengeType,
    NChallengeInput,
)


def main() -> int:
    data = json.load(sys.stdin)
    source = str(data["source"])
    player = urljoin("https://www.youtube.com", str(data["player"]))
    video_id = str(data["video_id"])
    if urlparse(player).hostname not in {"www.youtube.com", "youtube.com"}:
        return 1
    match = re.search(r"/n/([^/]+)/", urlparse(source).path)
    if not match:
        print(source)
        return 0

    challenge = match.group(1)
    with YoutubeDL({
        "js_runtimes": {"node": {"path": None}},
        "quiet": True,
        "no_warnings": True,
    }) as ydl:
        extractor = YoutubeIE(ydl)
        extractor.initialize()
        request = JsChallengeRequest(
            type=JsChallengeType.N,
            video_id=video_id,
            input=NChallengeInput(challenges=[challenge], player_url=player),
        )
        responses = extractor._jsc_director.bulk_solve([request])
        solved = responses[0][1].output.results.get(challenge) if responses else None
    if not solved or solved == challenge:
        return 1
    print(source.replace(f"/n/{challenge}/", f"/n/{solved}/", 1))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(1)
