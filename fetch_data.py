"""음악 차트를 받아 data.json으로 저장해요. 탭은 한국 · 클래식 · 올드팝이에요.

GitHub Actions에서 하루 1회 실행돼요. API 키는 환경 변수 YOUTUBE_API_KEY로 받아요.

- 한국: YouTube가 매기는 한국 인기 음악 순서 그대로(videos.list, 1 unit).
  곡마다 YouTube 주제 정보(topicDetails)로 장르를 붙여, 화면에서 장르별로 골라 볼 수 있어요.
- 클래식: 인기 차트에는 클래식이 거의 없어서 search.list(100 unit)로 따로 찾아요.
  최근 30일 동안 올라온 클래식 영상(4~20분) 중 조회수 순이에요.
- 올드팝: 정해 둔 60~80년대 가수(OLDIES_ARTISTS)의 영상을 search.list로 역대 조회수 순으로 찾아요.
하루 약 203 unit이에요(한도 10,000).
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
COUNTRIES = [("KR", "한국")]
# YouTube 주제 정보의 '클래식'은 팝·인도 영화음악에도 붙어 있어서 믿을 수 없어요(2026-10-12 실측).
# 'classical'·'orchestra' 같은 넓은 낱말로 찾으면 리액션·커버 영상이 섞여서(같은 날 실측),
# 작곡가 이름으로 검색하고, 제목·채널명에 작곡가나 곡 형식 이름이 있는 영상만 남겨요. 검색어의 |는 '또는'이에요.
CLASSICAL_COMPOSERS = [
    "Mozart", "Beethoven", "Bach", "Chopin", "Tchaikovsky", "Vivaldi", "Debussy", "Liszt",
    "Rachmaninoff", "Brahms", "Schubert", "Handel", "Haydn", "Mahler", "Dvorak", "Ravel",
    "Satie", "Mendelssohn", "Schumann", "Paganini", "Grieg", "Elgar",
    "모차르트", "베토벤", "바흐", "쇼팽", "차이콥스키", "비발디", "드뷔시", "라흐마니노프", "브람스", "슈베르트",
]
CLASSICAL_QUERY = "|".join(CLASSICAL_COMPOSERS)
CLASSICAL_WORDS = re.compile(
    r"symphon|concerto|sonata|nocturne|[eé]tude|pr[eé]lude|fugue|requiem|overture|"
    r"philharmoni|string quartet|mozart|beethoven|\bbach\b|chopin|tchaikovsky|vivaldi|debussy|"
    r"\bliszt\b|rachmanino|brahms|schubert|handel|haydn|mahler|dvo[rř][aá]k|\bravel\b|satie|"
    r"mendelssohn|schumann|paganini|grieg|elgar|"
    r"교향곡|협주곡|소나타|녹턴|모차르트|베토벤|바흐|쇼팽|차이콥스키|비발디|드뷔시|라흐마니노프|브람스|슈베르트|"
    r"交響曲|協奏曲",
    re.IGNORECASE,
)
# 클래식 탭에서 빼는 영상: 리액션·커버·속도 바꾼 편집 등
CLASSICAL_EXCLUDE = re.compile(r"reaction|react|first time|hears|tested|cover|slowed|reverb|sped up|"
                               r"remix|lofi|lo-fi|반응|커버", re.IGNORECASE)
CLASSICAL_DAYS = 30
CLASSICAL_SIZE = 30
# 올드팝 가수 목록. 검색어와 '이 가수 영상인지' 확인에 같이 써요. 더하거나 빼도 돼요.
OLDIES_ARTISTS = [
    "The Beatles", "Queen", "ABBA", "Elvis Presley", "Bee Gees", "Carpenters",
    "Simon & Garfunkel", "Eagles", "Elton John", "The Rolling Stones", "Michael Jackson",
    "Whitney Houston", "Stevie Wonder", "Bon Jovi", "Cyndi Lauper", "Wham!", "a-ha",
    "Boney M.", "Fleetwood Mac", "Lionel Richie", "Madonna", "The Police",
]
OLDIES_SIZE = 30
OLDIES_PER_ARTIST = 3   # 한 가수가 목록을 다 차지하지 않도록 가수당 최대 곡 수
OLDIES_EXCLUDE = re.compile(r"cover|karaoke|reaction|tutorial|lesson|instrumental|remix|tribute|"
                            r"커버|노래방|반응", re.IGNORECASE)
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


def search_videos(api_key, **params):
    """search.list 1회(100 unit)로 후보 50개를 찾고, videos.list 1회(1 unit)로 상세 정보를 받아요.

    검색 순서(조회수 순)를 그대로 유지해서 돌려줘요.
    """
    found = get_json(SEARCH_URL, {
        "part": "id",
        "type": "video",
        "videoCategoryId": "10",
        "order": "viewCount",
        "videoEmbeddable": "true",
        "regionCode": VIEWER_REGION,
        "maxResults": "50",
        "key": api_key,
        **params,
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
    return [by_id[i] for i in ids if i in by_id]


def fetch_classical(api_key):
    """최근 30일 동안 올라온 클래식 영상(4~20분)을 조회수 순으로 찾아요.

    작곡가 이름으로 검색하고, 제목·채널명에 클래식 낱말(CLASSICAL_WORDS)이 있고
    리액션·커버(CLASSICAL_EXCLUDE)가 아닌 영상만 남겨요.
    """
    since = datetime.now(timezone.utc) - timedelta(days=CLASSICAL_DAYS)
    videos = search_videos(
        api_key,
        q=CLASSICAL_QUERY,
        publishedAfter=since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        videoDuration="medium",  # 4~20분
    )
    classical = [v for v in videos
                 if CLASSICAL_WORDS.search(v["snippet"].get("title", "") + " " + v["snippet"].get("channelTitle", ""))
                 and not CLASSICAL_EXCLUDE.search(v["snippet"].get("title", ""))]
    print(f"  클래식: 검색 {len(videos)}개, 클래식 낱말 있음 {len(classical)}개")
    items = to_items(classical)[:CLASSICAL_SIZE]
    for it in items:
        it["genres"] = ["클래식"]  # 탭 전체가 클래식이라 장르 표시를 맞춰요
    return items


def oldies_artist(video):
    """영상이 목록의 어느 가수 것인지 찾아요. 없으면 None.

    채널명(끝의 VEVO·Topic은 떼고)을 먼저 보고, 없으면 제목 맨 앞의 가수를 봐요.
    ('ABBA - Dancing Queen'처럼 제목 뒤쪽에 다른 가수 이름이 섞일 수 있어서요.)
    """
    def find(text, at_start):
        hits = []
        for name in OLDIES_ARTISTS:
            bare = name.lower().removeprefix("the ")
            m = re.search(r"(?<![a-z])" + re.escape(bare) + r"(?![a-z])", text)
            if m and (not at_start or text[:m.start()].strip() in ("", "the")):
                hits.append((m.start(), name))
        return min(hits)[1] if hits else None

    channel = re.sub(r"\s*(-\s*topic|vevo)$", "", video["snippet"].get("channelTitle", "").lower())
    # 제목에서는 맨 앞에 가수 이름이 올 때만 인정해요('Fetty Wap - Trap Queen'이 Queen으로 잡히지 않게).
    return find(channel, at_start=False) or find(video["snippet"].get("title", "").lower(), at_start=True)


def fetch_oldies(api_key):
    """목록의 가수 영상을 역대 조회수 순으로 찾아요.

    커버·노래방·리액션 영상과 1분 30초~10분 밖의 영상(모음·짧은 클립)은 빼고,
    가수당 최대 OLDIES_PER_ARTIST곡까지만 넣어요. 가수 이름은 채널명 대신 목록의 이름을 써요.
    """
    videos = search_videos(api_key, q="|".join(f'"{a}"' for a in OLDIES_ARTISTS))
    per_artist, picked = {}, []
    for v in videos:
        artist = oldies_artist(v)
        dur = parse_duration(v.get("contentDetails", {}).get("duration"))
        if not artist or OLDIES_EXCLUDE.search(v["snippet"].get("title", "")) or not 90 <= dur <= 600:
            continue
        if per_artist.get(artist, 0) >= OLDIES_PER_ARTIST:
            continue
        per_artist[artist] = per_artist.get(artist, 0) + 1
        picked.append((v, artist))
    print(f"  올드팝: 검색 {len(videos)}개, 남은 곡 {len(picked)}개")
    items = to_items([v for v, _ in picked])
    artists = {v["id"]: a for v, a in picked}
    for it in items:
        it["artist"] = artists[it["videoId"]]
    return items[:OLDIES_SIZE]


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


def add_search_chart(charts, chart_id, title, fetch, api_key, note):
    """검색으로 만드는 탭을 붙여요. 실패하거나 비면 기존 data.json의 같은 탭을 그대로 써요."""
    try:
        items = fetch(api_key)
    except Exception as e:  # noqa: BLE001 - 할당량 초과 등 무엇이든 어제 것으로 대신해요
        print(f"{title}: 받기 실패 ({e})")
        items = []
    print(f"{title}: {len(items)}곡")
    for it in items:  # 검색 탭은 결과가 들쭉날쭉할 수 있어서, 무엇이 들어갔는지 실행 기록에 남겨요
        print(f"  {it['rank']:>2}. {it['artist']} | {it['title']}")
    if items:
        charts.append({"id": chart_id, "title": title, "note": note, "items": items})
    elif prev := previous_chart(chart_id):
        print(f"{title}: 어제 목록을 그대로 써요.")
        charts.append(prev)


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

    # 검색 탭은 실패해도(할당량 초과 등) 한국 차트 갱신은 막지 않아요. 못 받으면 어제 것을 그대로 써요.
    add_search_chart(charts, "classical", "클래식", fetch_classical, api_key,
                     f"최근 {CLASSICAL_DAYS}일 동안 올라온 클래식 영상(4~20분) 중 조회수 순이에요. "
                     "YouTube 공식 차트가 아니라 검색 결과라서 순위 번호는 조회수 순서예요.")
    add_search_chart(charts, "oldies", "올드팝", fetch_oldies, api_key,
                     "비틀즈·퀸·아바·엘비스 등 60~80년대 가수 영상을 역대 조회수 순으로 모았어요. "
                     f"한 가수는 {OLDIES_PER_ARTIST}곡까지, 커버·노래방 영상은 빼요.")

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
