"""YouTube 인기 음악 차트를 받아 data.json으로 저장해요.

GitHub Actions에서 하루 1회 실행돼요. API 키는 환경 변수 YOUTUBE_API_KEY로 받아요.
videos.list 호출 1회 = 1 unit이라 하루 한도(10,000 unit)에 거의 영향이 없어요.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API_URL = "https://www.googleapis.com/youtube/v3/videos"
KST = timezone(timedelta(hours=9))
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")


def fetch_youtube_chart(api_key):
    """KR 지역 음악 카테고리(10) 인기 영상 목록을 받아요."""
    params = {
        "part": "snippet,contentDetails,status",
        "chart": "mostPopular",
        "regionCode": "KR",
        "videoCategoryId": "10",
        "maxResults": "50",
        "key": api_key,
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as res:
        return json.load(res)


def parse_duration(iso):
    """ISO 8601 재생시간(PT3M25S)을 초로 바꿔요."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def artist_name(channel_title):
    """자동생성 음원 채널('가수 - Topic')이면 끝의 ' - Topic'을 떼요."""
    return re.sub(r"\s*-\s*Topic$", "", channel_title or "").strip()


def best_thumbnail(thumbnails):
    for key in ("medium", "high", "default"):
        if key in thumbnails:
            return thumbnails[key]["url"]
    return ""


def to_items(response):
    """API 응답을 화면용 곡 목록으로 바꿔요. 퍼가기 금지 영상은 빼요."""
    items = []
    for v in response.get("items", []):
        if not v.get("status", {}).get("embeddable"):
            continue
        sn = v["snippet"]
        items.append({
            "rank": len(items) + 1,
            "videoId": v["id"],
            "title": sn.get("title", ""),
            "artist": artist_name(sn.get("channelTitle", "")),
            "thumbnail": best_thumbnail(sn.get("thumbnails", {})),
            "duration": parse_duration(v.get("contentDetails", {}).get("duration")),
        })
    return items


def main():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        sys.exit("YOUTUBE_API_KEY 환경 변수가 없어요.")

    items = to_items(fetch_youtube_chart(api_key))
    if not items:
        # 빈 목록으로 기존 data.json을 덮어쓰지 않도록 실패로 끝내요.
        sys.exit("받은 곡이 없어요.")

    data = {
        "updated": datetime.now(KST).isoformat(timespec="minutes"),
        "charts": [
            {"id": "youtube", "title": "YouTube 인기 음악", "items": items},
        ],
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{len(items)}곡 저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
