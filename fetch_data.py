"""YouTube 나라별 인기 음악 차트를 받아 data.json으로 저장해요.

GitHub Actions에서 하루 1회 실행돼요. API 키는 환경 변수 YOUTUBE_API_KEY로 받아요.
videos.list 호출 1회 = 1 unit이라, 4개국을 받아도 하루 4 unit이에요(한도 10,000).
나라마다 YouTube가 매기는 인기 음악 순서를 그대로 탭 하나로 만들어요.
곡마다 YouTube 주제 정보(topicDetails)로 장르를 붙여, 화면에서 장르별로 골라 볼 수 있어요.

인기 차트에는 클래식이 거의 없어서, '클래식' 탭은 search.list(100 unit)로 따로 만들어요.
최근 30일 동안 올라온 클래식 주제 영상(4~20분) 중 조회수 순이에요.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API_URL = "https://www.googleapis.com/youtube/v3/videos"
SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
KST = timezone(timedelta(hours=9))
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
MAX_RESULTS = 50
VIEWER_REGION = "KR"  # 보는 사람이 대부분 한국이라, 한국에서 막힌 영상은 빼요.
# 탭 순서대로 (나라 코드, 탭 이름)
COUNTRIES = [("KR", "한국"), ("JP", "일본"), ("US", "미국"), ("GB", "영국")]
CLASSICAL_TOPIC = "/m/0ggq0m"  # YouTube(Freebase) 주제 ID: Classical music
CLASSICAL_DAYS = 30
CLASSICAL_SIZE = 30
# YouTube 주제(위키백과 문서 이름) → 화면에 보일 장르 이름. 이 순서가 곡의 장르 표시 순서예요.
GENRES = {
    "Pop_music": "팝",
    "Hip_hop_music": "힙합",
    "Rhythm_and_blues": "R&B·소울",
    "Soul_music": "R&B·소울",
    "Rock_music": "록",
    "Electronic_music": "일렉트로닉",
    "Independent_music": "인디",
    "Music_of_Latin_America": "라틴",
    "Country_music": "컨트리",
    "Jazz": "재즈",
    "Classical_music": "클래식",
    "Reggae": "레게",
}


def fetch_youtube_chart(api_key, region, limit=MAX_RESULTS):
    """한 나라의 음악 카테고리(10) 인기 영상 목록을 최대 limit개 받아요.

    다음 페이지(nextPageToken)가 있으면 이어서 받아요. 페이지마다 1 unit이에요.
    """
    items, token = [], None
    while len(items) < limit:
        params = {
            "part": "snippet,contentDetails,status,topicDetails",
            "chart": "mostPopular",
            "regionCode": region,
            "videoCategoryId": "10",
            "maxResults": str(min(50, limit - len(items))),
            "key": api_key,
        }
        if token:
            params["pageToken"] = token
        url = API_URL + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=30) as res:
            page = json.load(res)
        items += page.get("items", [])
        # YouTube가 알려 주는 차트 전체 길이를 남겨 둬요(30곡만 오는 이유 확인용).
        print(f"  {region}: {len(page.get('items', []))}개 받음, 전체 {page.get('pageInfo', {}).get('totalResults')}개")
        token = page.get("nextPageToken")
        if not token:
            break
    return items[:limit]


def get_json(url, params):
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=30) as res:
        return json.load(res)


def fetch_classical(api_key):
    """최근 30일 동안 올라온 클래식 영상(4~20분)을 조회수 순으로 찾아요.

    search.list 1회(100 unit)로 후보 50개를 찾고, videos.list 1회(1 unit)로 상세 정보를 받아요.
    검색 결과에 다른 장르가 섞일 수 있어서, 주제 정보에 클래식이 붙은 영상만 남겨요.
    """
    since = datetime.now(timezone.utc) - timedelta(days=CLASSICAL_DAYS)
    found = get_json(SEARCH_URL, {
        "part": "id",
        "type": "video",
        "videoCategoryId": "10",
        "topicId": CLASSICAL_TOPIC,
        "order": "viewCount",
        "publishedAfter": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "videoDuration": "medium",      # 4~20분
        "videoEmbeddable": "true",
        "regionCode": VIEWER_REGION,
        "maxResults": "50",
        "key": api_key,
    })
    ids = [it["id"]["videoId"] for it in found.get("items", []) if it.get("id", {}).get("videoId")]
    if not ids:
        return []
    details = get_json(API_URL, {
        "part": "snippet,contentDetails,status,topicDetails",
        "id": ",".join(ids),
        "maxResults": "50",
        "key": api_key,
    })
    by_id = {v["id"]: v for v in details.get("items", [])}
    videos = [by_id[i] for i in ids if i in by_id]  # 검색(조회수) 순서 유지
    classical = [v for v in videos if "클래식" in genres_of(v)]
    print(f"  클래식: 검색 {len(ids)}개, 클래식 주제 {len(classical)}개")
    return to_items(classical)[:CLASSICAL_SIZE]


def previous_chart(chart_id):
    """기존 data.json에서 같은 탭을 꺼내요(오늘 못 받았을 때 어제 것을 쓰려고)."""
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            return next((c for c in json.load(f).get("charts", []) if c.get("id") == chart_id), None)
    except (OSError, ValueError):
        return None


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


def genres_of(video):
    """topicCategories(위키백과 주소 목록)에서 장르 이름을 뽑아요."""
    topics = {url.rsplit("/", 1)[-1] for url in video.get("topicDetails", {}).get("topicCategories", [])}
    names = []
    for topic, name in GENRES.items():
        if topic in topics and name not in names:
            names.append(name)
    return names


def to_item(video, rank, **extra):
    sn = video["snippet"]
    return {
        "rank": rank,
        "videoId": video["id"],
        "title": sn.get("title", ""),
        "artist": artist_name(sn.get("channelTitle", "")),
        "thumbnail": best_thumbnail(sn.get("thumbnails", {})),
        "duration": parse_duration(video.get("contentDetails", {}).get("duration")),
        "genres": genres_of(video),
        **extra,
    }


def to_items(videos):
    """한 나라 목록을 YouTube 순서대로 화면용 곡 목록으로 바꿔요."""
    items = []
    for v in videos:
        if playable(v):
            items.append(to_item(v, len(items) + 1))
    return items


def main():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        sys.exit("YOUTUBE_API_KEY 환경 변수가 없어요.")

    charts = []
    for code, name in COUNTRIES:
        items = to_items(fetch_youtube_chart(api_key, code))
        print(f"{name}: {len(items)}곡")
        if not items:
            # 한 나라라도 비면 탭이 사라지지 않도록, 기존 data.json을 그대로 두고 실패로 끝내요.
            sys.exit(f"{name} 곡이 없어요.")
        charts.append({
            "id": code.lower(),
            "title": name,
            "note": f"YouTube가 매기는 {name} 인기 음악 영상 순서 그대로예요. "
                    "최근 조회가 빠르게 느는 영상이 위로 와요.",
            "items": items,
        })

    # 클래식은 검색이라 실패해도 나라별 차트 갱신은 막지 않아요. 못 받으면 어제 것을 그대로 써요.
    try:
        classical = fetch_classical(api_key)
    except Exception as e:  # noqa: BLE001 - 할당량 초과 등 무엇이든 어제 것으로 대신해요
        print(f"클래식: 받기 실패 ({e})")
        classical = []
    print(f"클래식: {len(classical)}곡")
    if classical:
        charts.append({
            "id": "classical",
            "title": "클래식",
            "note": f"최근 {CLASSICAL_DAYS}일 동안 올라온 클래식 영상(4~20분) 중 조회수 순이에요. "
                    "YouTube 공식 차트가 아니라 검색 결과라서 순위 번호는 조회수 순서예요.",
            "items": classical,
        })
    elif prev := previous_chart("classical"):
        print("클래식: 어제 목록을 그대로 써요.")
        charts.append(prev)

    data = {
        "updated": datetime.now(KST).isoformat(timespec="minutes"),
        "charts": charts,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
