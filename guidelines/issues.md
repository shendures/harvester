# DataCrawler v2.0 (Harvest) — 이슈 및 백로그

> `project_report.md`에서 분리된 이슈 관리 문서입니다.
> 프로젝트 구조는 `project_report.md`, 완료된 작업 이력은 `history.md` 참고.
> 이 문서는 아키텍처·릴리즈·보안·심각 버그(대량/전체 데이터 유실, 영구적 상태 손상·서비스
> 정지, 공통 경로 크래시)급 항목만 남긴 엄격 기준 정리본입니다(2026-09-28). 경미한 이슈의
> 전체 이력은 git 이력(`guidelines/issues.md` 이전 커밋)으로 복구 가능합니다.

- **최초 감사 일자**: 2026-07-03 ~ 2026-07-04
- **최신 갱신**: 2026-09-28
- **현황**: 해결 14건 · 미해결 0건 · 보류 1건

> **작성 규칙**: 해결된 이슈(✅)는 §1 표(`# | 이슈 | 위치 | 원인 | 해결 | PR/커밋`)에 한 행으로 추가합니다.
> 미해결(❌)·보류(⏸) 이슈는 표에 넣지 않고 §2에 `### 항목명 — 상태 (날짜)` 헤딩과 `위치/상세/사유·필요 조치` 불릿 리스트로 작성합니다 — 표 셀에는 진행 중인 원인 분석·대안 검토 같은 긴 서술이 담기지 않기 때문입니다.
> 이슈가 해결되면 §2 항목을 삭제하고 §1 표로 옮깁니다.

---

## 1. 해결된 이슈 (14건)

| # | 이슈 | 위치 | 원인 | 해결 | PR/커밋 |
|---|---|---|---|---|---|
| ① | 리다이렉트 시 수집 결과 전량 skip → total=0 | `worker.py` / `engine.py` | `worker._handle_line()`이 응답의 최종 URL로 url_list를 대조 — 리다이렉트 사이트는 최종 URL≠요청 URL이라 전량 skip | `engine.get_response_status()`에 `req_url` 추가, 대조 기준을 `req_url`로 변경 | `d469277` |
| ⑥ | `get_response_status()` None 필드 접근·비표준 상태코드 예외 | `engine.py:161,165` | `ip_address`가 None(Selenium 응답 등)이면 AttributeError로 결과 조용히 유실, 비표준 상태코드는 `HTTPStatus()` ValueError | None 방어, ValueError를 try/except로 처리 | PR #19 |
| ⑧ | `/text()` XPath 추출 깨짐(빈 값/ValueError) | `engine.py:299` | `extract_data_from_root()`가 텍스트 노드에도 `node.xpath(".")` 호출 — 문자열 텍스트는 빈 값 조용히 유실, JSON 파싱 가능 텍스트는 parsel 1.11이 json 타입 판정해 ValueError로 전체 실패(`@attr`도 동일 버그) | `node.root`가 문자열이면 그대로 사용하도록 분기 | PR #13 |
| ⑪ | 월간 스케줄 등록 시 QTimer OverflowError | `trigger.py:2013-2015` | 남은 시간을 ms로 환산해 `QTimer.start()`에 그대로 전달 — 30일치가 C int32 최댓값 초과 | 7일 단위로 타이머를 재등록하는 방식으로 청크 분할 | - |
| ⑫ | 스케줄 저장 위치 오류(소스/설치 디렉터리, PyInstaller 시 유실) | `trigger.py:2085, 2090-2091`, `layout.py:1357-1358` | `self.default_source`(소스/설치 디렉터리)에 저장 — PyInstaller 빌드 시 `resource_path()`가 임시 폴더(`_MEIPASS`)라 실행마다 유실 | 저장은 `self.file_path`(LOCALAPPDATA)로, 로드는 `file_path` 우선·없으면 `default_source` 폴백 | - |
| ⑭ | spirenderer 드라이버 누수(`driver.quit()` finally 미사용) | `spiders/spirenderer.py:64-101` | `driver.quit()`이 try 블록 마지막에 있어 예외 발생 시 Chrome 프로세스 누적 | 드라이버 생성 이후 코드를 try/finally로 감싸 `driver.quit()`을 finally로 이동 | - |
| ⑮ | POST URL에 `?` 없으면 크래시, 미지원 분기 시 암묵적 None 반환 | `engine.py:36-37, 83-133` | `get_json_form()`의 `None[0]` TypeError + 잘못된 정규식 이스케이프, `get_scrapy_request()`가 미지원 조합에서 암묵적 None 반환 → `yield None` | `?` 부재 시 명시적 ValueError, 정규식 raw string 전환, 미지원 조합도 명시적 ValueError | - |
| ⑯ | `request_info.json` 루트 리스트에 블루프린트 2개 이상 시 빈 설정으로 기동, 워커 조용히 사망 | `conf.py:165-183`, `worker.py:92` | 루트 리스트를 unwrap 없이 그대로 `_validate()`에 전달 — `"url" in list`가 항상 False라 검증 실패 → 빈 dict 폴백, 이후 `worker.run()`의 `self.task["callback_url"]`(try 밖)에서 KeyError → QThread가 조용히 죽고 UI는 "실행 중"에 고착 | 다중 블루프린트 지원 도입과 함께 `BlueprintStorage`가 루트 리스트를 항목별로 unwrap해 개별 검증하도록 재설계 | `d6b0d90` |
| ⑱ | 스케줄+정제 자동 저장 조합에서 빈 데이터 시 블로킹 모달 노출 가능 | `layout.py:preprocess()`, `trigger.py:_run_refine()`/`_extract_result_table()` | 세 함수 모두 "무인 실행"을 고려하지 않고 데이터가 비면 항상 `QMessageBox.warning()` 호출 — 재조사 결과 `worker.py`의 `_done`(=summary total)은 URL 매칭 응답 수만 세고 실제 추출된 `data`(items) 존재 여부는 반영하지 않아, `summary.total>0`이라 `_on_finished()`의 `total==0` 조기 return을 통과하면서도 `_collected_data`가 완전히 비는 경우(셀렉터 불일치 등)가 가능함을 확인 — 원래 문서가 지목했던 `_run_refine()` 외에 `preprocess()`(job 종류 무관 매번 호출)·`_extract_result_table()`의 raw 분기(`auto_save_source` 기본값이라 오히려 더 자주 노출)까지 총 3곳 모두 도달 가능했음 | 3곳 모두에 무인 실행 신호(`task.get("job")=="스케줄 실행"`/`skip_ui_update`/`silent`)로 분기 추가 — 모달 대신 `log_manager.append_log("warn", ...)`로 대체. `_extract_result_table("refined", silent=True)`는 호출부가 이미 `SCHEDULED_REFINE_RULES`로 정제를 실행한 뒤이므로 화면 상태 기반 `_run_refine()` 폴백 호출도 차단 | `6ae108f` |
| ⑲ | "②정제 규칙 설정" 탭 [정제 실행] 클릭 시 TypeError로 프로세스 abort | `layout.py:763`, `trigger.py:1069` | `clicked.connect(self._run_refine)`가 시그널의 `bool checked` 인자를 `rules_override`로 그대로 전달 — `dict(False)` 호출로 `TypeError`, try/except 범위 밖이라 PyQt6가 프로세스 abort | `clicked.connect(lambda: self._run_refine())`으로 감싸 bool 인자 차단 | PR #59 |
| ㉑ | `spirenderer.py`의 `conditions["login"]` 직접 접근이 신규 request_info.json과 스키마 불일치 | `spiders/spirenderer.py:73`, `generator_conditions.html:1490` | "로그인 없는 사이트도 `login: null` 명시" 암묵적 스키마 전제인데, 생성기의 delete-if-null 목록에 `login`도 포함돼 로그인 미사용 시 키 자체가 삭제됨 → `KeyError` | 코드(`.get()` 방어) 대신 기존 관례 유지 — 생성기 delete-if-null 목록에서 `login` 제외 | - |
| ㉕ | PyInstaller 배포 파이프라인 부재로 커스텀 규칙 번들 여부 보장 불가 | `guidelines/preprocess.md`, (부재였던) 빌드 스크립트 | `.spec`·빌드 스크립트가 저장소에 전무해 `--add-data` 구성이 수동·비문서화, `preprocess.md` 안내도 구경로 기준이라 실제 조회 경로와 불일치 | `build-exe.ps1` 신설(seq_no 일치 검증, 스테이징 후 번들), `preprocess.md` 경로 안내 갱신 | - |
| ㉗ | `build-exe.ps1`이 pyinstaller의 정상 INFO 로그를 오류로 오인해 빌드 첫 줄에서 강제 중단 | `build-exe.ps1:28,109` | 스크립트 최상단 `$ErrorActionPreference = "Stop"` 상태에서 `pyinstaller`(native 명령)가 진행 상황을 stderr에 INFO로 기록 — PowerShell 5.1이 stderr 첫 줄을 즉시 종료 오류로 승격시켜 실제로는 정상 진행 중인 빌드를 매번 시작 직후 중단시킴(Windows 실 빌드로 재현 — PR #64 도입 이후 이 스크립트로 완주된 적이 실제로 없었음, 기존 dist 산출물은 스크립트를 거치지 않은 수동 pyinstaller 실행 결과였음) | `pyinstaller` 호출 앞뒤로만 `$ErrorActionPreference`를 `"Continue"`↔`"Stop"`으로 일시 전환하고, 실패 여부는 `$LASTEXITCODE`로 직접 판별해 0이 아니면 명시적으로 중단 | Windows 실 빌드로 수정 전(첫 INFO 줄에서 `NativeCommandError`로 즉시 중단, exe 미생성) → 수정 후(정상 완주, `dist\DataCrawler.exe` 생성, `EXITCODE=0`) 확인. 이어서 `build-installer.ps1`도 검토 — Inno Setup(ISCC.exe) 자체가 이 머신에 미설치라 실행 검증은 보류 |
| ㉘ | `build-installer.ps1`의 ISCC.exe 탐색 경로에 사용자별 설치 위치 누락 | `build-installer.ps1:33-36` | winget으로 Inno Setup을 설치(관리자 권한 없이 실행하면 기본이 사용자별 설치)하니 `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`에 설치됐는데, 탐색 후보 목록은 시스템 전체 설치 경로(`Program Files`/`Program Files (x86)`)만 확인 — 사용자별 설치 시 항상 "찾을 수 없음"으로 실패 | 탐색 후보 목록에 `$Env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe`를 추가 | Windows 실 빌드 — winget으로 실제 Inno Setup 6.7.3 설치(사용자별 경로 확인) → 수정 전 탐색 실패 재현 → 수정 후 정상 탐색+컴파일, `dist\DataCrawler-Setup.exe`(PE32 GUI, 약 73MB) 생성 확인. `build-exe.ps1`(이슈㉗)→`build-installer.ps1` 전 과정이 실제 Windows 환경에서 처음부터 끝까지 완주됨을 최초로 확인 |

---

## 2. 미해결·보류 이슈 (1건)

### ㉙ 로그인 인증 수집의 스케줄러 연동 미구현 — ⏸ 보류 (2026-07-23)

- **위치**: `trigger/toolbar.py`의 `GlobalToolbarTriggers._actual_start()`(반영됨, `a0be22f`) vs
  `trigger/scheduler.py`의 `SchedulerPageTriggers._apply_schedule()`/`_run_now()`(미반영)
- **상세**: 매뉴얼 "시작" 흐름은 인증 관리 페이지(`AuthManagerPage`)에 입력된 로그인 정보
  (`loginUrl`/`id`/`password`)를 `_actual_start()`가 `task["conditions"]["login"]`에 실시간
  반영하도록 구현됨(`request_info.json` 파일에는 쓰지 않고 이번 실행 task에만 반영). 반면
  스케줄 실행(`_run_now()`)은 `self.sched_task.update(deepcopy(BlueprintStorage().read())); self.sched_task.update(s)`로
  별도 구성되는데, `s`(등록 시점에 저장된 스케줄 dict)에는 로그인 정보가 전혀 없어 결국
  `BlueprintStorage().read()`의 `conditions.login`(대개 `id`/`password`가 `null`)만 그대로
  쓰임 — 로그인 인증이 필요한 수집을 스케줄로 등록해도 실제 자격증명 없이 실행되어 로그인
  실패로 수집이 중단될 수 있음.
- **보류 사유·필요 조치**: 스케줄은 무인 실행(이슈 ⑱ 참고)이라 매뉴얼 흐름처럼 "실행 시점의
  위젯 값"을 읽는 방식은 부적합 — 이미 같은 이유로 정제 규칙(`refine_rules`)이 스케줄 등록
  시점(`_apply_schedule()`)에 체크박스 상태를 스냅샷해 스케줄 dict에 저장하는 방식을 쓰고
  있으므로, 로그인 정보도 동일 패턴(등록 시점 스냅샷 → `_save_schedules_to_json()`으로 영속화
  → `_run_now()`에서 `sched_task["conditions"]["login"]`에 명시적 병합)을 적용하는 방향으로
  검토됨. DB 저장 자격증명(`db_pw`)도 이미 평문으로 스케줄 JSON에 저장되고 있어 새로운 보안
  리스크는 아님. 사용자와 우선순위 논의 후 착수 예정이라 별도 조치 없이 보류.

---

## 3. 보안·운영 관찰

- **`env/database.ini`에 실제 API 키 4개 평문 존재** (공공데이터포털, 한국은행,
  OpenDART, IROS). git 미추적 상태이지만, 그 이유가 Python 템플릿 `.gitignore`의
  `env/` 규칙(가상환경용)에 **우연히** 걸렸기 때문 → `.gitignore`에 명시적 등록
  또는 `.env` 이관 권장 (2026-07-09 재확인: 여전히 명시적 등록 안 됨)
- `ROBOTSTXT_OBEY=True`인 반면 봇 UA 행세·랜덤 쿠키·프록시 로테이션 미들웨어가
  공존 — 사용 정책 정리 필요
- **테스트 코드 0개** — 검증용으로 작성했던 미들웨어 테스트 8건은 검증 완료 후
  정책에 따라 저장소에서 제거됨 (PR #6). `preprocess.DataRefiner`,
  `utility.generate_combined_urls`가 테스트 도입 최적 지점
- Scrapy 2.16으로 올리면 sync `start_requests()`가 **에러 없이 무시되어 0건 수집**
  (검증 중 실측) — 업그레이드 시 async `start()` 마이그레이션 필수
