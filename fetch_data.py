"""YouTube 인기 음악 차트를 받아 data.json으로 저장해요.

GitHub Actions에서 하루 1회 실행돼요. API 키는 환경 변수 YOUTUBE_API_KEY로 받아요.
videos.list 호출 1회 = 1 unit이라, 나라 13곳을 받아도 하루 13 unit이에요(한도 10,000).

- 전세계: YouTube에는 전세계 차트가 없어서, 여러 나라의 인기 음악을 받아 합산해요.
  나라마다 1위 50점, 2위 49점 … 50위 1점을 주고 더한 점수로 순위를 매겨요.
- 한국: KR 인기 음악을 YouTube 순서 그대로 써요.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API_URL = "https://www.googleapis.com/youtube/v3/videos"
KST = timezone(timedelta(hours=9))
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
MAX_RESULTS = 50
VIEWER_REGION = "KR"  # 보는 사람이 대부분 한국이라, 한국에서 막힌 영상은 빼요.
WORLD_REGIONS = ["US", "GB", "JP", "BR", "MX", "IN", "ID", "DE", "FR", "ES", "PH", "AU", "KR"]
WORLD_SIZE = 50
REGION_NAMES = {
    "US": "미국", "GB": "영국", "JP": "일본", "BR": "브라질", "MX": "멕시코", "IN": "인도",
    "ID": "인도네시아", "DE": "독일", "FR": "프랑스", "ES": "스페인", "PH": "필리핀",
    "AU": "호주", "KR": "한국",
}


def fetch_youtube_chart(api_key, region):
    """한 나라의 음악 카테고리(10) 인기 영상 목록을 받아요."""
    params = {
        "part": "snippet,contentDetails,status",
        "chart": "mostPopular",
        "regionCode": region,
        "videoCategoryId": "10",
        "maxResults": str(MAX_RESULTS),
        "key": api_key,
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as res:
        return json.load(res).get("items", [])


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


def playable(video):
    """퍼가기가 허용되고 한국에서 볼 수 있는 영상인지 봐요."""
    if not video.get("status", {}).get("embeddable"):
        return False
    rr = video.get("contentDetails", {}).get("regionRestriction", {})
    if "allowed" in rr and VIEWER_REGION not in rr["allowed"]:
        return False
    if VIEWER_REGION in rr.get("blocked", []):
        return False
    return True


def to_item(video, rank, **extra):
    sn = video["snippet"]
    return {
        "rank": rank,
        "videoId": video["id"],
        "title": sn.get("title", ""),
        "artist": artist_name(sn.get("channelTitle", "")),
        "thumbnail": best_thumbnail(sn.get("thumbnails", {})),
        "duration": parse_duration(video.get("contentDetails", {}).get("duration")),
        **extra,
    }


def to_items(videos):
    """한 나라 목록을 YouTube 순서대로 화면용 곡 목록으로 바꿔요."""
    items = []
    for v in videos:
        if playable(v):
            items.append(to_item(v, len(items) + 1))
    return items


def merge_world(by_region, size=WORLD_SIZE):
    """나라별 목록을 점수로 합산해 전세계 순위를 만들어요.

    점수가 같으면 오른 나라 수가 많은 쪽, 그다음 가장 높은 순위가 높은 쪽이 앞이에요.
    재생할 수 없는 영상도 순위 계산에는 넣고, 목록에 넣을 때만 빼요.
    """
    stats = {}
    for region, videos in by_region.items():
        for pos, v in enumerate(videos):
            s = stats.setdefault(v["id"], {"video": v, "score": 0, "regions": [], "best": pos})
            s["score"] += MAX_RESULTS - pos
            s["regions"].append(region)
            s["best"] = min(s["best"], pos)
    ranked = sorted(stats.values(), key=lambda s: (-s["score"], -len(s["regions"]), s["best"]))
    items = []
    for s in ranked:
        if not playable(s["video"]):
            continue
        items.append(to_item(s["video"], len(items) + 1, countries=len(s["regions"])))
        if len(items) == size:
            break
    return items


def world_note(by_region):
    names = "·".join(REGION_NAMES.get(r, r) for r in by_region)
    return (f"{len(by_region)}개국({names})의 YouTube 인기 음악 순위를 합산했어요. "
            f"나라마다 1위 {MAX_RESULTS}점, 2위 {MAX_RESULTS - 1}점 … {MAX_RESULTS}위 1점을 주고 더한 점수 순이에요. "
            "'N개국'은 그 곡이 순위에 오른 나라 수예요.")


def main():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        sys.exit("YOUTUBE_API_KEY 환경 변수가 없어요.")

    by_region = {}
    for region in WORLD_REGIONS:
        try:
            by_region[region] = fetch_youtube_chart(api_key, region)
            print(f"{region}: {len(by_region[region])}개")
        except urllib.error.HTTPError as e:
            # 음악 차트가 없는 나라는 400이 나요. 그 나라만 건너뛰어요.
            print(f"{region}: 건너뜀 (HTTP {e.code})")

    world = merge_world(by_region)
    korea = to_items(by_region.get("KR", []))
    if not world or not korea:
        # 빈 목록으로 기존 data.json을 덮어쓰지 않도록 실패로 끝내요.
        sys.exit("받은 곡이 없어요.")

    data = {
        "updated": datetime.now(KST).isoformat(timespec="minutes"),
        "charts": [
            {"id": "world", "title": "전세계 인기 음악",
             "note": world_note(by_region), "items": world},
            {"id": "youtube", "title": "한국 인기 음악",
             "note": "YouTube가 매기는 한국 인기 음악 영상 순서 그대로예요. "
                     "최근 조회가 빠르게 느는 영상이 위로 와요.",
             "items": korea},
        ],
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"전세계 {len(world)}곡, 한국 {len(korea)}곡 저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
