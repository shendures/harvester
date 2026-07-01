import os, sys, json, shutil, logging
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
