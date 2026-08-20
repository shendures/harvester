# BUILD_GUIDE — Windows exe 빌드 및 배포 가이드

> DataCrawler(Harvest)를 고객 배포용 `.exe` / 설치 프로그램(`Setup.exe`)으로 빌드하는
> 절차를 다룹니다. 함께 관리되는 문서:
> - **빌드 스크립트 도입·수정 이력**: `HISTORY.md` (PR #64·#65·#66, 이슈㉗·㉘ 등)
> - **알려진 이슈**: `ISSUES.md` (이슈㉕·㉗·㉘)
> - **아키텍처 개요**: `PROJECT_REPORT.md` §6 의존성 요약

- **최신 갱신**: 2026-07-30

---

## 0. 전제 조건

- **반드시 Windows 환경(PowerShell)에서 실행**해야 합니다. `build-exe.ps1`/`build-installer.ps1`
  모두 Windows 전용 스크립트이며, PyInstaller가 만드는 `.exe`도 Windows 바이너리입니다
  (WSL/Linux에서는 빌드할 수 없습니다).
- Python 3.12 이상 + `requirements.txt`의 패키지가 설치되어 있어야 합니다(`pyinstaller`,
  `pyinstaller-hooks-contrib` 포함). 가상환경을 쓰는 경우:
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```
- 설치 프로그램(`Setup.exe`)까지 만들려면 [Inno Setup](https://jrsoftware.org/isinfo.php)이
  추가로 필요합니다(무료, Windows 전용 외부 도구 — Python 패키지 아님).

---

## 1. 배포할 고객의 청사진(blueprint) 준비

레포 루트에 다음을 준비합니다.

1. **`request_info.json`** — 배포할 고객의 수집 설정. `.gitignore` 대상이라 각자 로컬에
   준비해야 합니다. `seq_no` 필드가 이번에 빌드할 고객 번호와 일치해야 합니다.
2. **(필요 시) 커스텀 규칙** — `render/{seq_no}.py`(렌더링), `login/{seq_no}.py`(로그인),
   `refine/{seq_no}.py`(정제) 중 해당 고객에게 필요한 파일. 규칙 작성법은
   `PREPROCESS.md` §3.1a 참고.

> `render/`·`login/`·`refine/`은 여러 고객의 규칙 파일을 함께 보관하는 개발자용 폴더입니다.
> 다음 단계의 빌드 스크립트가 **지정한 `seq_no` 파일만** 골라 담기 때문에, 이 폴더에 다른
> 고객 파일이 섞여 있어도 이번 빌드에는 포함되지 않습니다.

---

## 2. exe 빌드 — `build-exe.ps1`

```powershell
.\build-exe.ps1 -SeqNo 000001 -AppName DataCrawler
```

| 파라미터 | 필수 | 설명 |
|---|---|---|
| `-SeqNo` | 필수 | 배포할 고객의 seq_no. `request_info.json`의 실제 `seq_no`와 다르면 즉시 중단됩니다(고객 파일 오혼입 방지). |
| `-AppName` | 선택 (기본값 `CollectorApp`) | exe 파일명이자, 실행 시 데이터가 저장되는 `%LOCALAPPDATA%\<AppName>\` 폴더명도 함께 결정합니다. |

**스크립트가 하는 일 (요약)**
1. `request_info.json` 존재 및 `seq_no` 일치 검증
2. 해당 `seq_no`의 `{render,login,refine}/{SeqNo}.py`만 임시 스테이징 폴더로 격리
3. PyInstaller `--onefile --windowed`로 `main.py`를 빌드하면서, 동적 import라 자동 탐지되지
   않는 `scrapy.cfg`/`settings.py`/`pipelines.py`/`middlewares.py`/`spiders/`/아이콘 파일,
   그리고 Scrapy/Twisted 계열이 필요로 하는 패키지 메타데이터(`--copy-metadata`)를 함께 번들
4. 스테이징 폴더 정리

**결과물**: `dist\<AppName>.exe`

---

## 3. (선택) 설치 프로그램으로 감싸기 — `build-installer.ps1`

exe 파일을 그대로 전달하는 대신 설치/제거·바로가기 생성을 지원하는 설치 프로그램을 만들고
싶다면, 2단계 완료 후 실행합니다.

```powershell
.\build-installer.ps1 -AppName DataCrawler -AppVersion 1.0.0
```

| 파라미터 | 필수 | 설명 |
|---|---|---|
| `-AppName` | 선택 (기본값 `CollectorApp`) | 2단계와 **동일한 값**을 사용해야 합니다(`dist\<AppName>.exe`를 찾아 감쌈). |
| `-AppVersion` | 선택 (기본값 `1.0.0`) | 설치 프로그램에 표시될 버전. |
| `-AppPublisher` | 선택 (기본값 `-AppName`과 동일) | 설치 프로그램에 표시될 배포자명. |

Inno Setup의 커맨드라인 컴파일러 `ISCC.exe`를 PATH → `Program Files\Inno Setup 6` →
`Program Files (x86)\Inno Setup 6` → `%LOCALAPPDATA%\Programs\Inno Setup 6`(winget 사용자별
설치 경로) 순으로 탐색합니다.

**결과물**: `dist\<AppName>-Setup.exe`

---

## 4. 실행 후 확인

- 최초 실행 시 `request_info.json`/`render`/`login`/`refine`이 `%LOCALAPPDATA%\<AppName>\`로
  자동 복사(시딩)됩니다. 이후 실행부터는 그 위치의 파일을 읽습니다.
- exe 파일명을 빌드 후 **직접 바꾸지 마세요** — `utility.get_app_name()`이 실행 파일명으로
  데이터 폴더명을 결정하므로, 이름을 바꾸면 다음 실행부터 새 이름의 빈 데이터 폴더를 찾아
  기존 `request_info.json`/`render`/`login`/`refine`을 못 찾는 것처럼 보일 수 있습니다.

---

## 5. 트러블슈팅

| 증상 | 원인 / 대처 |
|---|---|
| `pyinstaller`가 첫 로그 줄에서 바로 멈추고 `NativeCommandError` | PowerShell 5.1이 pyinstaller의 정상 진행 로그(stderr에 쓰는 INFO 로그)를 오류로 오인하는 실측 버그. `build-exe.ps1`이 pyinstaller 호출 구간에서만 `$ErrorActionPreference`를 `Continue`로 낮추고 `$LASTEXITCODE`로 직접 판정하도록 이미 조치되어 있습니다(이슈㉗) — 만약 이 동작이 안 보이면 스크립트가 최신 버전인지 확인하세요. |
| 빌드는 성공했는데 실행한 exe에서 `ModuleNotFoundError` | `--copy-metadata` 목록(`cryptography`, `lxml`, `twisted` 등) 밖의 의존성(Selenium/SQLAlchemy 등)일 수 있습니다. 오류 메시지의 모듈명을 `build-exe.ps1`의 pyinstaller 호출에 `--hidden-import <모듈명>` 또는 `--collect-all <모듈명>`으로 추가한 뒤 재시도하세요. |
| exe 실행 시 Scrapy가 정상 동작하지 않음(엔진/스파이더 설정 관련 오류) | `scrapy.cfg`/`settings.py`/`pipelines.py`/`middlewares.py`가 문자열 경로로 동적 import되어 PyInstaller 자동 분석에 안 잡히는 케이스(PR #66에서 해결) — `build-exe.ps1`이 최신 버전인지 확인하세요. |
| `build-installer.ps1`에서 "Inno Setup(ISCC.exe)을 찾을 수 없습니다" | Inno Setup 미설치이거나, winget으로 사용자별 권한 없이 설치해 `%LOCALAPPDATA%\Programs\Inno Setup 6\`에 들어간 경우입니다(이슈㉘, 최신 스크립트는 이 경로도 탐색합니다). 여전히 안 잡히면 실제 설치 경로를 확인해 스크립트의 탐색 후보에 추가하세요. |
| `request_info.json`의 한글이 깨지거나 `seq_no` 검증에서 파싱 실패 | Windows PowerShell의 `Get-Content` 기본 인코딩(CP949) 문제였으나, `-Encoding UTF8` 명시로 이미 수정되어 있습니다(PR #65) — 스크립트가 최신 버전인지 확인하세요. |

---

## 관련 문서

- 커스텀 규칙(정제/렌더링) 작성 및 배포 절차 상세: `PREPROCESS.md` §3.1a, §5
- 빌드 파이프라인 도입·수정 이력: `HISTORY.md` (2026-07-13, 2026-07-21 항목)
- 알려진 이슈: `ISSUES.md` 이슈㉕·㉗·㉘
