import os
import sys
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

    def __init__(self, app_name: str = "CollectorApp", filename: str = "request_info.json"):
        # 최초 1회만 초기화
        if self._initialized:
            return
        self._initialized = True
        if sys.platform == 'win32':
            self.root_path = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
        else:
            self.root_path = os.path.join(os.path.expanduser("~"), ".config")
        self.app_dir   = os.path.join(self.root_path, app_name)
        self.file_path = os.path.join(self.app_dir, filename)
        self.default_source = os.path.join(utility.resource_path(), filename)

        # 파일 시스템 초기화
        self._initialize_storage()

        # 수집 정보 로드
        self._blueprint = self._load()

    # ── 파일 시스템 초기화 ──────────────────────────────
    def _initialize_storage(self) -> None:
        try:
            os.makedirs(self.app_dir, exist_ok=True)
            if not os.path.exists(self.file_path) and os.path.exists(self.default_source):
                shutil.copy2(self.default_source, self.file_path)
        except Exception as e:
            logger.error("[BlueprintStorage] 초기화 오류: %s", e)

    # ── 로드 ──────────────────────────────────────────
    def _load(self) -> dict:
        """
        JSON 파일을 로드하여 blueprint dict를 반환합니다.

        [수정 사항]
        1. list / dict 타입을 명시적으로 분기하여 len() 오동작 방지.
           - 루트가 list이고 요소가 1개인 경우에만 unwrap.
           - 루트가 dict인 경우 그대로 반환.
        2. fallback 반환값의 구조 검증 추가.
        """
        target = self.file_path if os.path.exists(self.file_path) else self.default_source

        if not os.path.exists(target):
            logger.warning("[BlueprintStorage] JSON 파일 없음, 기본값 사용: %s", target)
            return self._safe_fallback()

        try:
            with open(target, "r", encoding="utf-8") as f:
                raw = json.load(f)

            # [수정] 타입 분기로 len() 오동작 방지
            if isinstance(raw, list):
                if len(raw) == 0:
                    logger.warning("[BlueprintStorage] JSON 배열이 비어 있음, 기본값 사용")
                    return self._safe_fallback()
                # 요소가 1개인 경우에만 unwrap
                result = raw[0] if len(raw) == 1 else raw
            elif isinstance(raw, dict):
                result = raw
            else:
                logger.error("[BlueprintStorage] 지원하지 않는 JSON 루트 타입: %s", type(raw))
                return self._safe_fallback()

            # [수정] 로드된 구조 최소 검증
            if not self._validate(result):
                logger.error("[BlueprintStorage] 구조 검증 실패, 기본값 사용")
                return self._safe_fallback()

            return result

        except json.JSONDecodeError as e:
            logger.error("[BlueprintStorage] JSON 파싱 실패 (%s): %s", target, e)
            return self._safe_fallback()
        except Exception as e:
            logger.error("[BlueprintStorage] 로드 실패: %s", e)
            return self._safe_fallback()

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

    # ── Public API ────────────────────────────────────
    def read(self) -> dict:
        """
        내부 _blueprint dict의 참조(reference)를 반환합니다.

        [주의] 반환값은 복사본이 아닌 내부 객체 자체입니다.
        외부에서 키를 재할당하거나 .clear()를 호출하면 전역 상태가 오염됩니다.

        읽기 전용으로 사용하거나, in-place 수정(값 업데이트)만 허용하세요.
        완전히 독립된 사본이 필요한 경우 read_copy()를 사용하세요.
        """
        return self._blueprint

    def read_copy(self) -> dict:
        """
        내부 _blueprint의 깊은 복사본을 반환합니다.
        반환된 dict를 수정해도 원본 _blueprint에 영향을 주지 않습니다.
        """
        return deepcopy(self._blueprint)

    def reload(self) -> dict:
        """
        파일에서 blueprint를 다시 로드하고 내부 상태를 갱신합니다.
        반환값은 갱신된 _blueprint의 참조입니다.
        """
        self._blueprint = self._load()
        return self._blueprint


# ══════════════════════════════════════════════════════
#  CUSTOM MODULE STORAGE
# ══════════════════════════════════════════════════════
class CustomModuleStorage:
    """
    seq_no별 커스텀 모듈(`{seq_no}.py`)을 로드하는 싱글턴.

    한 파일에 서로 독립적인 두 종류의 훅을 선택적으로 정의할 수 있습니다:
      - 수집 단계 (html_render 스파이더, conditions.rendering=True 일 때만 참조):
            login(driver, login_info: dict) -> None
            render(driver, selectors, items: dict) -> list[dict]
      - 정제 단계 (needs_cleaning=True 일 때만 참조, 기존과 동일):
            refine(data: list[dict]) -> list[dict]
            refine_row(row: dict) -> dict

    앱 데이터 폴더(app_dir)는 BlueprintStorage와 동일하게 평탄한 구성이며,
    seed-on-first-run 정책도 동일합니다. 번들 리소스 경로(default_source)는
    실제 소스가 `custom_rules/` 서브폴더에 있으므로 그 하위를 가리킵니다
    (폴더명은 기존 파일·git 이력과의 호환을 위해 그대로 유지).
    파일이 seq_no마다 다르므로 BlueprintStorage처럼 단일 값을 메모리에
    캐싱하지 않고, 매 호출마다 해당 seq_no의 파일을 새로 읽습니다 —
    앱 데이터 폴더의 파일을 직접 수정하면 재시작 없이 바로 다음 호출에
    반영됩니다.
    """
    _instance = None

    # ── 싱글턴 ────────────────────────────────────────
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, app_name: str = "CollectorApp"):
        # 최초 1회만 초기화
        if self._initialized:
            return
        self._initialized = True
        if sys.platform == 'win32':
            self.root_path = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
        else:
            self.root_path = os.path.join(os.path.expanduser("~"), ".config")
        self.app_dir = os.path.join(self.root_path, app_name)

        try:
            os.makedirs(self.app_dir, exist_ok=True)
        except Exception as e:
            logger.error("[CustomModuleStorage] 초기화 오류: %s", e)

    # ── 경로 해석 ──────────────────────────────────────
    def resolve_path(self, seq_no) -> str:
        """
        `{seq_no}.py`의 실제 경로를 결정합니다 (BlueprintStorage._initialize_storage()와
        동일한 seed-on-first-run 정책):

        - 앱 데이터 폴더에 파일이 없고 번들 리소스 경로에 기본값이 있으면 최초
          1회 복사해 심습니다(고객별로 패키징에 포함한 기본 규칙).
        - 이후에는 앱 데이터 폴더의 파일을 우선 사용하고, 없으면 번들 리소스
          경로로 폴백합니다.
        """
        filename       = f"{seq_no}.py"
        file_path      = os.path.join(self.app_dir, filename)
        default_source = os.path.join(utility.resource_path(), "custom_rules", filename)

        if not os.path.exists(file_path) and os.path.exists(default_source):
            try:
                shutil.copy2(default_source, file_path)
            except Exception as e:
                logger.error("[CustomModuleStorage] 시딩 실패 (seq_no=%s): %s", seq_no, e)

        return file_path if os.path.exists(file_path) else default_source

    # ── 존재 확인 (exec 없이, AST 기반) ─────────────────
    def _defines(self, seq_no, *names) -> bool:
        """
        `{seq_no}.py`가 최상위에 `names` 중 하나라도 함수로 정의하고 있는지
        확인합니다. 파일을 실행(exec)하지 않고 AST만 파싱하므로, 파일에
        문법 오류가 있거나 무거운 최상위 코드가 있어도 안전하게 False로
        처리됩니다(UI에서 경고 팝업 여부를 판단하는 등 가벼운 조회 용도).
        """
        path = self.resolve_path(seq_no)
        if not os.path.isfile(path):
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)
        except (SyntaxError, OSError) as e:
            logger.error("[CustomModuleStorage] 파일 파싱 실패 (seq_no=%s): %s", seq_no, e)
            return False

        defined = {
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        return any(name in defined for name in names)

    def has_refine(self, seq_no) -> bool:
        """`{seq_no}.py`에 refine() 또는 refine_row()가 정의돼 있는지 확인합니다."""
        return self._defines(seq_no, "refine", "refine_row")

    def has_render(self, seq_no) -> bool:
        """`{seq_no}.py`에 render()가 정의돼 있는지 확인합니다."""
        return self._defines(seq_no, "render")

    def has_login(self, seq_no) -> bool:
        """`{seq_no}.py`에 login()이 정의돼 있는지 확인합니다."""
        return self._defines(seq_no, "login")

    # ── 로드 (exec 실행) ────────────────────────────────
    def _load_module(self, seq_no):
        """
        `{seq_no}.py`를 실제로 import하여 module 객체를 반환합니다.

        Returns:
            module | None — 파일이 없으면 None.

        Raises:
            파일 실행 중 발생한 예외(SyntaxError 등)는 그대로 전파합니다 —
            "규칙 없음"(None)과 "규칙이 있는데 깨져 있음"(예외)을 호출 측이
            구분해 다르게 안내할 수 있도록 의도한 동작입니다.
        """
        path = self.resolve_path(seq_no)
        if not os.path.isfile(path):
            return None

        spec   = importlib.util.spec_from_file_location(f"custom_module_{seq_no}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def load_refine(self, seq_no):
        """
        `{seq_no}.py`를 로드하여 사용자 정의 정제 함수를 반환합니다.

        파일에 refine(data: list[dict]) -> list[dict]가 있으면 그대로 반환하고,
        refine_row(row: dict) -> dict만 있으면 각 행에 적용하는 함수로 감싸서
        list[dict] -> list[dict] 형태의 콜러블로 반환합니다.

        Returns:
            callable | None — 파일이 없거나 두 함수 모두 없으면 None.
        """
        module = self._load_module(seq_no)
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
        `{seq_no}.py`를 로드하여 사용자 정의 렌더링 결과 추출 함수를 반환합니다.

        Returns:
            callable(driver, selectors, items) -> list[dict] | None — 파일이
            없거나 render()가 없으면 None.
        """
        module = self._load_module(seq_no)
        if module is None:
            return None
        return getattr(module, "render", None)

    def load_login(self, seq_no):
        """
        `{seq_no}.py`를 로드하여 사용자 정의 로그인 함수를 반환합니다.

        Returns:
            callable(driver, login_info) -> None | None — 파일이 없거나
            login()이 없으면 None.
        """
        module = self._load_module(seq_no)
        if module is None:
            return None
        return getattr(module, "login", None)
