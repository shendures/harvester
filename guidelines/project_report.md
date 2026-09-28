# DataCrawler v2.0 (Harvest) — 프로젝트 리포트

> 신규 개발자가 프로젝트에 처음 합류했을 때 가장 먼저 읽는 온보딩 개요 문서입니다. 이
> 프로젝트가 무엇을 하는지, 코드가 어떻게 나뉘어 있는지, 더 깊이 알고 싶을 때 어느 문서를
> 봐야 하는지를 다룹니다. 프로세스 경계·실행/데이터 흐름 등 전체 아키텍처는
> `architecture.md`, 모듈(.py) 단위 상세 책임·의존관계는 `../MODULE_SPEC.md`에서 별도
> 관리됩니다. 함께 관리되는 문서: 이슈·백로그 `issues.md` · 진행 이력 `history.md` ·
> exe/설치 프로그램 빌드 절차 `build_guide.md`

- **최신 갱신**: 2026-09-28

---

## 1. 프로젝트 개요

**DataCrawler**는 Scrapy 크롤링 엔진과 PyQt6 GUI를 결합한 데스크톱 웹 데이터 수집
애플리케이션입니다. 비개발자도 GUI에서 코드 한 줄 없이 수집 조건을 설정하고, 실시간
진행 상황을 모니터링하며, 결과를 CSV 또는 DB로 내보낼 수 있습니다.

**핵심 기능**:
- 정적 HTML · JS 렌더링(Selenium) · JSON API · XML · 목록→상세 2단계, 5가지 수집 방식
- 수집 후 7단계 규칙 기반 데이터 정제(결측 행 제거·중복 제거·타입 변환 등)
- 스케줄 등록으로 무인(unattended) 자동 수집·정제·저장
- 사이트별(seq_no) 커스텀 로그인·렌더링·정제 로직을 코드 수정 없이 플러그인으로 확장
- 수집 대상(블루프린트) 1개는 단일 레이아웃, 2개 이상은 다중 블루프린트 레이아웃
- 수집 상태 평가 대시보드 — KPI별(HTTP 오류율·빈 응답률·지연 응답 비율·유효 데이터
  비율) 신뢰구간·회차 패턴 기반 정상/주의/문제 판정과 종합 평가 팝업

- **엔진**: Scrapy 2.14 · **UI**: PyQt6 · **수집 형식**: HTML(정적/Selenium 렌더링), JSON, XML
- **출력**: CSV, MongoDB, MySQL, PostgreSQL

| 영역 | 파일 | 규모 |
|---|---|---|
| GUI 레이아웃 | `layout/` 패키지 | 3,920줄 (26개 파일) |
| 이벤트 핸들러 (Mixin, 단일+다중 공용) | `trigger/` 패키지 | 6,547줄 (11개 파일) |
| 테마·공용 위젯·정제 규칙 UI | `style.py` | 1,848줄 |
| 수집 워커 (QThread+multiprocessing) | `worker.py` | 583줄 |
| 요청 생성·데이터 추출 | `engine.py` | 481줄 |
| Spider 5종 | `scraper/spiders/` | html/html_render/json/xml/detail |
| 데이터 정제 | `preprocess.py` | 340줄 |
| 설정·상태 공유 (싱글턴 3종) | `conf.py` | 618줄 |

---

## 2. 문서 지도

더 깊이 알고 싶은 주제별로 아래 문서를 참고하세요.

| 알고 싶은 것 | 참고 문서 |
|---|---|
| 프로세스 경계·계층 구조·실행/데이터 흐름·핵심 설계 원칙 | `architecture.md` |
| 특정 모듈(.py)의 책임·의존관계 상세 (뭘 고치면 뭐가 영향받는지) | `../MODULE_SPEC.md` |
| 정제 규칙(remove_null_row 등) 서브시스템 심화 | `preprocess.md` |
| Windows exe/설치 프로그램 빌드 절차 | `build_guide.md` |
| 완료된 작업 이력 | `history.md` |
| 알려진 이슈·백로그 | `issues.md` |

**처음 합류했다면**: 이 문서(개요) → `architecture.md`(전체 실행 흐름) → 수정하려는
기능에 해당하는 `../MODULE_SPEC.md` 절 순으로 읽는 것을 권장합니다.

---

## 3. 코드 둘러보기

무엇이 어디 있는지만 안내합니다. 프로세스 경계·실행 흐름 등 각 조각이 어떻게 연결되는지는
`architecture.md`, 파일별 클래스·함수 단위 책임과 모듈 간 의존 관계는 `../MODULE_SPEC.md`를
참고하세요.

- **`main.py`**: 진입점
- **`layout/`** (3,920줄, 26개 파일): GUI 위젯 트리
- **`trigger/`** (6,547줄, 11개 파일): 이벤트 핸들러 Mixin
- **`style.py`** (1,848줄): 테마·공용 위젯·정제 규칙 UI
- **`worker.py`** (583줄): 크롤링 실행 브리지
- **`engine.py`** (481줄): 요청 생성·데이터 추출
- **`scraper/spiders/`**: Spider 5종(html/html_render/json/xml/detail)
- **`scraper/{settings,items,middlewares,pipelines}.py`**: Scrapy 자체 설정(미들웨어·
  파이프라인 등)
- **`preprocess.py`** (340줄): 데이터 정제 파이프라인
- **`conf.py`** (618줄): 설정·상태 싱글턴
- **`render/`·`login/`·`refine/{seq_no}.py`**: 사이트별 커스텀 로직 플러그인
- **`utility.py`·`glean.py`·`db_conn.py`**: 경로/URL 처리, URL 목록 생성, DB 연결 유틸리티

---

## 4. 핵심 설정 파일: request_info.json

수집 작업의 청사진(blueprint) 목록입니다. 최상위는 배열이며, 원소 개수로 Single/Multi
레이아웃이 갈립니다. `BlueprintStorage`가 로드해 `DataStore`와 각 Spider에 전달합니다.
`callback_url`은 페이지네이션(`${page:시작:증가:끝}`)·키워드 확장(`${keywords:...}`)
템플릿을 지원하고, `spiders`(수집 방식)와 `conditions`(데이터 형식·XPath/경로 기반
추출 규칙 `items` 등)가 각각 수집 동작을 정의합니다.

```json
[
  {
    "seq_no": "000001",
    "title": "작업명",
    "url": "https://example.com/list",
    "callback_url": "https://example.com/list?page=${page:1:1:10}",
    "conditions": {
      "dataFormat": "html",
      "method": "GET",
      "rendering": false,
      "items": { "root": "//div[@class='list']/li", "title": ".//h2/text()" }
    },
    "spiders": "html",
    "needs_cleaning": true
  }
]
```

전체 필드 스키마와 `spiders` 값별 Spider 매핑은 `generator_conditions.html`(블루프린트
저작 도구), `../MODULE_SPEC.md`의 블루프린트 저작 도구 절(2.12), `architecture.md`의
블루프린트 저작 흐름(§6)을 참고하세요.

---

## 5. 의존성 요약

| 라이브러리 | 용도 |
|---|---|
| `Scrapy` / `PyQt6` | 크롤링 엔진 / 데스크톱 GUI 프레임워크 |
| `selenium` / `webdriver-manager` | JS 렌더링 수집 / Chrome 드라이버 자동 설치 |
| `lxml` / `parsel` | HTML/XML 파싱 |
| `pymongo` / `mysqlclient`·`PyMySQL` / `psycopg2` | MongoDB / MySQL / PostgreSQL 연결 |
| `SQLAlchemy` | ORM (DB 추상화) |
| `furl` / `python-dotenv` | URL 파싱/조작 / 환경 변수 로드 |
| `pyinstaller` | exe 빌드 |
| Inno Setup | (Windows 전용 외부 도구) 설치 프로그램 패키징 |

> exe/설치 프로그램 빌드 절차 전체(사전 준비물, 단계별 명령, 트러블슈팅)는 `build_guide.md` 참고.
