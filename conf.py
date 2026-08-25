import os
import ast
import json
import shutil
import logging
import importlib.util
from copy import deepcopy
import customized_settings
import utility

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════
#  SHARED DATA STORE  (크롤 결과 / 스케줄 공유)
# ══════════════════════════════════════════════════════
class DataStore:
    """
    앱 전체에서 수집 결과·스케줄을 공유하는 싱글턴.

    [주의] 이 싱글턴은 메인 프로세스(UI) 내에서만 유효합니다.
    multiprocessing.Process로 생성된 자식 프로세스는 별도의 메모리 공간을
    가지므로 DataStore 인스턴스를 공유하지 않습니다.
    자식 프로세스와의 데이터 교환은 반드시 multiprocessing.Queue를 통해
    수행하고, DataStore 갱신은 메인 프로세스에서만 처리해야 합니다.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._rows        = []  # list[dict]
            cls._instance._url_map_list = []  # list[dict]
            cls._instance._schedules   = []  # list[dict]
            cls._instance._sessions    = []  # list[dict] — 완료된 세션 요약
        return cls._instance

    # ── url maps ──────────────────────────────────────
    def add_url_map(self, url_map: dict) -> None:
        if not isinstance(url_map, dict):
            logger.warning("[DataStore] add_url_map: dict가 아닌 값 무시 (%s)", type(url_map))
            return
        self._url_map_list.append(url_map)

    def get_url_maps(self) -> list:
        return list(self._url_map_list)

    def clear_url_maps(self) -> None:
        self._url_map_list.clear()

    # ── rows ( 수집 데이터 ) ──────────────────────────────────────────
    def add_row(self, row: dict) -> None:
        if not isinstance(row, dict):
            logger.warning("[DataStore] add_row: dict가 아닌 값 무시 (%s)", type(row))
            return
        self._rows.append(row)

    def get_rows(self) -> list:
        return list(self._rows)

    def clear_rows(self) -> None:
        self._rows.clear()

    # ── schedules ─────────────────────────────────────
    def add_schedule(self, s: dict) -> None:
        if not isinstance(s, dict):
            logger.warning("[DataStore] add_schedule: dict가 아닌 값 무시 (%s)", type(s))
            return
        self._schedules.append(s)

    def get_schedules(self) -> list:
        return list(self._schedules)

    def remove_schedule(self, idx: int) -> None:
        if not isinstance(idx, int):
            logger.warning("[DataStore] remove_schedule: 유효하지 않은 인덱스 타입 (%s)", type(idx))
            return
        if 0 <= idx < len(self._schedules):
            self._schedules.pop(idx)
        else:
            logger.warning("[DataStore] remove_schedule: 범위를 벗어난 인덱스 (%d / %d)", idx, len(self._schedules))

    def update_schedule_status(self, idx: int, status: str) -> None:
        if not isinstance(idx, int):
            logger.warning("[DataStore] update_schedule_status: 유효하지 않은 인덱스 타입 (%s)", type(idx))
            return
        if 0 <= idx < len(self._schedules):
            self._schedules[idx]["status"] = status
        else:
            logger.warning("[DataStore] update_schedule_status: 범위를 벗어난 인덱스 (%d / %d)", idx, len(self._schedules))

    # ── sessions ──────────────────────────────────────
    def add_session(self, s: dict) -> None:
        if not isinstance(s, dict):
            logger.warning("[DataStore] add_session: dict가 아닌 값 무시 (%s)", type(s))
            return
        self._sessions.append(s)

    def get_sessions(self) -> list:
        return list(self._sessions)


# ══════════════════════════════════════════════════════
#  BLUEPRINT STORAGE
# ══════════════════════════════════════════════════════
class BlueprintStorage:
    """
    request_info.json을 로드해 수집 청사진(blueprint)을 관리하는 싱글턴.

    싱글턴 초기화는 최초 1회만 수행됩니다.
    이후 BlueprintStorage()를 다시 호출해도 __init__이 재실행되지 않습니다.
    """
    _instance = None

    # ── 싱글턴 ────────────────────────────────────────
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, app_name: str = utility.get_app_name(), filename: str = "request_info.json"):
        # 최초 1회만 초기화
        if self._initialized:
            return
        self._initialized = True
        self.app_dir   = utility.data_dir(app_name)
        self.file_path = os.path.join(self.app_dir, filename)
        self.default_source = os.path.join(utility.resource_path(), filename)

        # 파일 시스템 초기화
        self._initialize_storage()

        # 수집 정보 로드 — 항상 list[dict]로 정규화하고, 그중 하나를
        # "활성 블루프린트"로 가리킨다. read()는 기존 계약(단일 dict 반환)을
        # 유지하되 활성 블루프린트를 반환한다.
        self._blueprints = self._load()
        self._active_seq_no = self._blueprints[0].get("seq_no")

    # ── 파일 시스템 초기화 ──────────────────────────────
    def _initialize_storage(self) -> None:
        try:
            os.makedirs(self.app_dir, exist_ok=True)
            # 개발(.py) 환경에선 file_path == default_source(둘 다 저장소)라 시딩 불필요 —
            # 같은 경로 복사(SameFileError) 방지 겸, 저장소 파일을 그대로 사용.
            if (self.file_path != self.default_source
                    and not os.path.exists(self.file_path)
                    and os.path.exists(self.default_source)):
                shutil.copy2(self.default_source, self.file_path)
        except Exception as e:
            logger.error("[BlueprintStorage] 초기화 오류: %s", e)

    # ── 로드 ──────────────────────────────────────────
    def _load(self) -> list:
        """
        JSON 파일을 로드하여 blueprint 리스트(list[dict])를 반환합니다.

        - 루트가 dict(구버전 단일 포맷)이면 원소 1개짜리 리스트로 감쌉니다.
        - 루트가 list이면 길이와 무관하게 원소 단위로 검증합니다 —
          일부 원소가 깨져도 나머지 정상 블루프린트는 살아남습니다.
        - 검증을 통과한 원소가 하나도 없으면 fallback 1개짜리 리스트를 반환합니다
          (반환 리스트는 항상 최소 1개 원소를 보장).
        """
        target = self.file_path if os.path.exists(self.file_path) else self.default_source

        if not os.path.exists(target):
            logger.warning("[BlueprintStorage] JSON 파일 없음, 기본값 사용: %s", target)
            return [self._ensure_seq_no(self._safe_fallback(), 0, [])]

        try:
            with open(target, "r", encoding="utf-8") as f:
                raw = json.load(f)

            if isinstance(raw, dict):
                candidates = [raw]
            elif isinstance(raw, list):
                candidates = raw
            else:
                logger.error("[BlueprintStorage] 지원하지 않는 JSON 루트 타입: %s", type(raw))
                return [self._ensure_seq_no(self._safe_fallback(), 0, [])]

            validated = []
            for i, item in enumerate(candidates):
                if not isinstance(item, dict) or not self._validate(item):
                    logger.warning("[BlueprintStorage] 블루프린트 #%d 검증 실패, 건너뜀", i)
                    continue
                validated.append(self._ensure_seq_no(item, i, validated))

            if not validated:
                logger.error("[BlueprintStorage] 유효한 블루프린트 없음, 기본값 사용")
                return [self._ensure_seq_no(self._safe_fallback(), 0, [])]
            return validated

        except json.JSONDecodeError as e:
            logger.error("[BlueprintStorage] JSON 파싱 실패 (%s): %s", target, e)
            return [self._ensure_seq_no(self._safe_fallback(), 0, [])]
        except Exception as e:
            logger.error("[BlueprintStorage] 로드 실패: %s", e)
            return [self._ensure_seq_no(self._safe_fallback(), 0, [])]

    @staticmethod
    def _ensure_seq_no(item: dict, index: int, accepted: list) -> dict:
        """
        seq_no 고유성 불변식을 보장합니다 — 사이드바 목록·페이지 번들 캐시·
        워커 라우팅이 모두 seq_no를 키로 쓰므로, 없거나 중복이면 위치 기반
        식별자로 보정합니다.
        """
        seq_no = item.get("seq_no")
        if not seq_no or any(b.get("seq_no") == seq_no for b in accepted):
            item = dict(item)
            item["seq_no"] = f"__unnamed_{index}"
            logger.warning(
                "[BlueprintStorage] 블루프린트 #%d의 seq_no 누락/중복 — '%s'로 보정",
                index, item["seq_no"]
            )
        return item

    def _safe_fallback(self) -> dict:
        """
        customized_settings.get_request_settings() 호출 후
        반환값 타입을 검증하여 안전한 dict를 보장합니다.
        """
        try:
            fallback = customized_settings.get_request_settings()
            if isinstance(fallback, dict):
                return fallback
            logger.error(
                "[BlueprintStorage] get_request_settings()가 dict를 반환하지 않음: %s",
                type(fallback)
            )
        except Exception as e:
            logger.error("[BlueprintStorage] get_request_settings() 호출 실패: %s", e)
        # 최후 수단: 앱이 최소한 기동될 수 있도록 빈 구조 반환
        return {}

    def _validate(self, data: dict) -> bool:
        """
        blueprint dict가 최소 필수 키를 포함하는지 검증합니다.
        필수 키가 누락된 경우 경고 로그를 남기고 False를 반환합니다.
        """
        REQUIRED_KEYS = ("url", "conditions")
        missing = [k for k in REQUIRED_KEYS if k not in data]
        if missing:
            logger.warning("[BlueprintStorage] 필수 키 누락: %s", missing)
            return False
        return True

    # ── Public API (단일 블루프린트 — 기존 계약 유지) ──
    def read(self) -> dict:
        """
        현재 활성 블루프린트 dict의 참조(reference)를 반환합니다.

        [주의] 반환값은 복사본이 아닌 내부 객체 자체입니다.
        외부에서 키를 재할당하거나 .clear()를 호출하면 전역 상태가 오염됩니다.
        읽기 전용으로 사용하거나, in-place 수정(값 업데이트)만 허용하세요.

        블루프린트가 1개뿐이던 구버전에서는 "유일한 블루프린트"를 반환했으며,
        다중 블루프린트 도입 후에는 set_active()로 지정된 활성 블루프린트를
        반환합니다(기본값: 첫 번째). 기존 호출부는 수정 없이 동작합니다.
        """
        return self._active()

    # ── Public API (다중 블루프린트) ───────────────────
    def list_blueprints(self) -> list:
        """전체 블루프린트의 깊은 복사본 리스트를 반환합니다 (사이드바 목록용)."""
        return deepcopy(self._blueprints)

    def list_seq_nos(self) -> list:
        """파일 순서를 보존한 seq_no 목록을 반환합니다."""
        return [b.get("seq_no") for b in self._blueprints]

    def get(self, seq_no):
        """seq_no에 해당하는 블루프린트의 깊은 복사본을 반환합니다. 없으면 None."""
        found = self._find(seq_no)
        return deepcopy(found) if found is not None else None

    @property
    def active_seq_no(self):
        return self._active_seq_no

    def set_active(self, seq_no) -> dict:
        """
        활성 블루프린트를 변경합니다. 존재하지 않는 seq_no면 ValueError.

        [주의] 싱글턴의 전역 상태를 바꾸므로 반드시 Qt 메인 스레드
        (시그널/슬롯 경로)에서만 호출해야 합니다. 크롤링 자식 프로세스는
        별도 메모리 공간이라 영향을 받지 않습니다.
        """
        if self._find(seq_no) is None:
            raise ValueError(f"존재하지 않는 블루프린트 seq_no: {seq_no}")
        self._active_seq_no = seq_no
        return self._active()

    def _find(self, seq_no):
        """seq_no에 해당하는 내부 dict 참조(deepcopy 아님)를 반환. 없으면 None."""
        for b in self._blueprints:
            if b.get("seq_no") == seq_no:
                return b
        return None

    def _active(self) -> dict:
        """활성 seq_no가 가리키는 내부 dict 참조. _load()가 최소 1개를 보장."""
        return self._find(self._active_seq_no) or self._blueprints[0]


# ══════════════════════════════════════════════════════
#  CUSTOM MODULE STORAGE
# ══════════════════════════════════════════════════════
class CustomModuleStorage:
    """
    seq_no별 커스텀 모듈(`{kind}/{seq_no}.py`)을 로드하는 싱글턴.

    수집 단계와 정제 단계는 실행 컨텍스트가 서로 다르므로(수집: 크롤링 자식
    프로세스 + Selenium 의존, 정제: 메인 GUI 프로세스 + 순수 데이터 처리)
    같은 seq_no라도 kind별로 물리적으로 다른 파일에 둡니다. exec 단위(=장애
    단위)도 함께 분리되어, 한쪽 파일의 버그나 무거운 import가 다른 kind의
    로드에 영향을 주지 않습니다.
      - kind="render" → render/{seq_no}.py:
            render(driver, selectors, items: dict) -> list[dict]
      - kind="login" → login/{seq_no}.py:
            login(driver, login_info: dict) -> None
      - kind="refine" → refine/{seq_no}.py:
            refine(data: list[dict]) -> list[dict]
            refine_row(row: dict) -> dict

    앱 데이터 폴더(app_dir)는 BlueprintStorage와 동일하게 kind별 서브폴더
    구성이며, seed-on-first-run 정책도 동일합니다. 번들 리소스 경로
    (default_source)는 실제 소스가 프로젝트 루트의 `{kind}/` 폴더에 있으므로
    그 하위를 가리킵니다. 파일이 seq_no마다 다르므로 BlueprintStorage처럼
    단일 값을 메모리에 캐싱하지 않고, 매 호출마다 해당 파일을 새로 읽습니다 —
    앱 데이터 폴더의 파일을 직접 수정하면 재시작 없이 바로 다음 호출에
    반영됩니다.
    """
    _instance = None
    _KINDS = ("render", "login", "refine")

    # ── 싱글턴 ────────────────────────────────────────
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, app_name: str = utility.get_app_name()):
        # 최초 1회만 초기화
        if self._initialized:
            return
        self._initialized = True
        self.app_dir = utility.data_dir(app_name)

    # ── 경로 해석 ──────────────────────────────────────
    def resolve_path(self, seq_no, kind: str) -> str:
        """
        `{kind}/{seq_no}.py`의 실제 경로를 결정합니다 (BlueprintStorage._initialize_storage()와
        동일한 seed-on-first-run 정책):

        - 앱 데이터 폴더에 파일이 없고 번들 리소스 경로에 기본값이 있으면 최초
          1회 복사해 심습니다(고객별로 패키징에 포함한 기본 규칙).
        - 이후에는 앱 데이터 폴더의 파일을 우선 사용하고, 없으면 번들 리소스
          경로로 폴백합니다.
        """
        if kind not in self._KINDS:
            raise ValueError(f"지원하지 않는 kind 값입니다: {kind!r} ({self._KINDS}만 지원)")

        filename       = f"{seq_no}.py"
        file_path      = os.path.join(self.app_dir, kind, filename)
        default_source = os.path.join(utility.resource_path(), kind, filename)

        # 개발(.py) 환경에선 file_path == default_source(둘 다 저장소)라 시딩 불필요 —
        # 같은 경로 복사(SameFileError) 방지 겸, 저장소 파일을 그대로 사용.
        if (file_path != default_source
                and not os.path.exists(file_path) and os.path.exists(default_source)):
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                shutil.copy2(default_source, file_path)
            except Exception as e:
                logger.error("[CustomModuleStorage] 시딩 실패 (seq_no=%s, kind=%s): %s", seq_no, kind, e)

        return file_path if os.path.exists(file_path) else default_source

    # ── 존재 확인 (exec 없이, AST 기반) ─────────────────
    def _defines(self, seq_no, kind: str, *names) -> bool:
        """
        `{kind}/{seq_no}.py`가 최상위에 `names` 중 하나라도 함수로 정의하고
        있는지 확인합니다. 파일을 실행(exec)하지 않고 AST만 파싱하므로, 파일에
        문법 오류가 있거나 무거운 최상위 코드가 있어도 안전하게 False로
        처리됩니다(UI에서 경고 팝업 여부를 판단하는 등 가벼운 조회 용도).
        """
        path = self.resolve_path(seq_no, kind)
        if not os.path.isfile(path):
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)
        except (SyntaxError, OSError) as e:
            logger.error("[CustomModuleStorage] 파일 파싱 실패 (seq_no=%s, kind=%s): %s", seq_no, kind, e)
            return False

        defined = {
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        return any(name in defined for name in names)

    def has_refine(self, seq_no) -> bool:
        """`refine/{seq_no}.py`에 refine() 또는 refine_row()가 정의돼 있는지 확인합니다."""
        return self._defines(seq_no, "refine", "refine", "refine_row")

    def has_render(self, seq_no) -> bool:
        """`render/{seq_no}.py`에 render()가 정의돼 있는지 확인합니다."""
        return self._defines(seq_no, "render", "render")

    def has_login(self, seq_no) -> bool:
        """`login/{seq_no}.py`에 login()이 정의돼 있는지 확인합니다."""
        return self._defines(seq_no, "login", "login")

    # ── 로드 (exec 실행) ────────────────────────────────
    def _load_module(self, seq_no, kind: str):
        """
        `{kind}/{seq_no}.py`를 실제로 import하여 module 객체를 반환합니다.

        Returns:
            module | None — 파일이 없으면 None.

        Raises:
            파일 실행 중 발생한 예외(SyntaxError 등)는 그대로 전파합니다 —
            "규칙 없음"(None)과 "규칙이 있는데 깨져 있음"(예외)을 호출 측이
            구분해 다르게 안내할 수 있도록 의도한 동작입니다.
        """
        path = self.resolve_path(seq_no, kind)
        if not os.path.isfile(path):
            return None

        spec   = importlib.util.spec_from_file_location(f"custom_module_{kind}_{seq_no}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def load_refine(self, seq_no):
        """
        `refine/{seq_no}.py`를 로드하여 사용자 정의 정제 함수를 반환합니다.

        파일에 refine(data: list[dict]) -> list[dict]가 있으면 그대로 반환하고,
        refine_row(row: dict) -> dict만 있으면 각 행에 적용하는 함수로 감싸서
        list[dict] -> list[dict] 형태의 콜러블로 반환합니다.

        Returns:
            callable | None — 파일이 없거나 두 함수 모두 없으면 None.
        """
        module = self._load_module(seq_no, "refine")
        if module is None:
            return None

        if hasattr(module, "refine"):
            return module.refine
        if hasattr(module, "refine_row"):
            row_fn = module.refine_row
            return lambda data: [row_fn(row) for row in data]
        return None

    def load_render(self, seq_no):
        """
        `render/{seq_no}.py`를 로드하여 사용자 정의 렌더링 결과 추출 함수를 반환합니다.

        Returns:
            callable(driver, selectors, items) -> list[dict] | None — 파일이
            없거나 render()가 없으면 None.
        """
        module = self._load_module(seq_no, "render")
        if module is None:
            return None
        return getattr(module, "render", None)

    def load_login(self, seq_no):
        """
        `login/{seq_no}.py`를 로드하여 사용자 정의 로그인 함수를 반환합니다.

        Returns:
            callable(driver, login_info) -> None | None — 파일이 없거나
            login()이 없으면 None.
        """
        module = self._load_module(seq_no, "login")
        if module is None:
            return None
        return getattr(module, "login", None)
