# CLAUDE.md

이 저장소는 **Claude Code 웹(claude.ai/code)** 에서 작업하는 프로젝트입니다. 답변·커밋 메시지·코드 주석은 한국어로 씁니다.

## 만들려는 것

신곡·인기곡 목록을 API로 받아 화면에 보여주고, 곡을 누르면 그 곡의 유튜브 영상이 페이지 안에서 바로 재생되는 웹페이지예요. GitHub Pages로 공개해요.

- 배포 주소: https://zeloso21.github.io/music-chart/ (저장소 root의 `index.html`)
- 구성: `fetch_data.py`(차트 수집) → `.github/workflows/update.yml`(매일 06:07 KST, 수동 실행, `main`에 스크립트 바뀌면 실행) → `data.json` → `index.html`(목록 + IFrame 플레이어).
- `data.json` 형식: `{updated, charts: [{id, title, note, items: [{rank, videoId, title, artist, thumbnail, duration(초), genres}]}]}`. 탭은 `charts` 항목마다 하나씩 생기고, `note`는 탭 아래 순위 설명이에요.
- 탭: 한국·일본·미국·영국. 나라마다 `mostPopular` 음악 차트를 YouTube 순서 그대로 써요. 한국에서 막힌 영상(`regionRestriction`)과 퍼가기 금지 영상은 빼요. 하루 4 unit. 나라별 30곡 유지로 정했어요(더 늘리려면 Apple Music 차트 등 다른 출처가 필요한데, 사용자가 지금처럼 유지하기로 함).
- 장르: `videos.list`의 `topicDetails.topicCategories`(위키백과 주소)를 `fetch_data.py`의 `GENRES`로 한국어 장르 이름에 대응시켜 곡마다 `genres`로 저장해요(추가 unit 없음). 화면에서는 나라 탭 아래 목록 상자로 '장르 전체'/장르별을 고르고, 순위 번호는 원래 나라 순위 그대로예요.
- 여러 나라 점수를 합산한 '전세계'·'종합' 탭은 써 봤다가 사용자 요청으로 뺐어요. 나라별 탭만 둬요.

## 정해진 것 (지켜야 할 규칙)

1. **API 키는 화면에 넣지 말 것.** 공개 저장소라 `index.html`이나 JS에서 API를 직접 부르면 키가 노출돼요.
   - 키는 GitHub Secrets에 `YOUTUBE_API_KEY`로 등록돼 있어요(YouTube Data API v3, 읽기 전용).
   - **GitHub Actions**가 하루 1회 API를 불러 `data.json`을 만들어 커밋하고, 화면은 `data.json`만 읽어요.
   - 워크플로 파일에 `permissions: contents: write`를 꼭 넣어야 `data.json`을 커밋할 수 있어요(저장소 기본 권한은 읽기 전용).
   - 같은 사용자의 `zeloso21/kodex200-dashboard`가 이 방식(Actions cron → data.json 자동 커밋)으로 운영 중이에요.
2. **재생은 YouTube IFrame Player API**로 해요. 공식 플레이어 임베드라 저작권 문제가 없어요.
3. **퍼가기 금지 영상은 거를 것.** 일부 공식 뮤직비디오는 외부 사이트에서 재생이 막혀 있어요. `videos.list`의 `status.embeddable`이 true인 것만 목록에 넣어요.
4. **YouTube API 하루 한도는 10,000 unit**이에요. `videos.list`는 호출 1회에 1 unit, `search.list`는 100 unit이라 검색을 많이 쓰면 금방 차요.
5. **키 없는 공개 API를 우선** 써요. 새 키가 필요하면 사용자에게 먼저 물어봐요.

## 데이터 출처 후보

| 출처 | 내용 | 비고 |
|---|---|---|
| YouTube 인기 음악 차트 | `videos.list?chart=mostPopular&regionCode=KR&videoCategoryId=10` | **2026-10-10 실측: 차트 길이는 나라마다 30곡이 끝이에요**(KR·JP·US·GB 모두 `pageInfo.totalResults`=30, `nextPageToken` 없음. `maxResults=50`으로 요청해도 30곡). KR은 30곡 모두 embeddable. 상당수가 자동생성 음원 채널(`가수 - Topic`)이라 채널명 끝의 ` - Topic`을 떼면 가수명이 돼요. 1 unit |
| Apple Music 차트 RSS | `rss.applemarketingtools.com` 한국 인기곡·신곡 JSON | 키 없음. 영상 ID가 없어서 곡마다 YouTube `search.list`(100 unit)로 찾아 붙여야 해요(100곡이면 하루 한도의 절반). 아직 확인 안 함 |
| Last.fm | 세계·장르별 인기곡 | 무료 키 발급이 필요해요(아직 없음) |

멜론·지니는 공식 API가 없어서 쓰지 않아요.

## 처음 계획 (사용자와 대화하며 바꿔도 됨)

1. `fetch_data.py` + `.github/workflows/update.yml`(매일 cron + 수동 실행 `workflow_dispatch`) → `data.json`
2. `index.html`: 곡 목록(썸네일·제목·가수·재생시간) + 위쪽 플레이어, 누르면 재생, 끝나면 다음 곡 자동 재생
3. 탭: 'YouTube 인기 음악' 먼저, 'Apple Music 한국 TOP100·신곡'은 나중에
4. 휴대폰에서도 보기 좋게(가로 스크롤 없이)

## 배포

- GitHub Pages: `main` 브랜치 `/`(root)에서 서비스해요. 푸시하면 1~2분 뒤 반영돼요.
- 로컬 실행 환경은 따로 없어요. 화면 확인은 Pages 주소나 웹 세션의 미리보기로 해요.
