"""
DataCrawler v2.0  —  PyQt6
대시보드 / 스케줄러 / 모니터링 / 통계 분석 완성본
"""

import os, re, sys, csv, json, socket, ctypes, shutil, time, multiprocessing
import utility
from copy import deepcopy
from datetime import datetime, timedelta
from collections import defaultdict
from datetime import datetime as dt
import customized_settings
import db_conn
import worker

from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QTableWidget,
    QTableWidgetItem, QSplitter, QFrame, QProgressBar, QTextEdit,
    QScrollArea, QGridLayout, QHeaderView, QStackedWidget,
    QSpinBox, QDoubleSpinBox, QFileDialog, QMessageBox,
    QTimeEdit, QCheckBox, QSizePolicy, QAbstractItemView, QDateEdit, QSystemTrayIcon,
    QStyledItemDelegate, QStyleOptionViewItem, QDialog, QTabWidget, QMenu
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QTimer, QPoint, QDate, QObject, QThread, pyqtSignal, QStandardPaths
)
from PyQt6.QtGui import (
    QColor, QFont, QPalette, QPainter, QPen, QBrush,
    QLinearGradient, QFontMetrics, QIcon, QAction
)

# Windows 작업 표시줄 아이콘 해결을 위한 코드
myappid = 'my.scrapy.collector.v0_8'
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

# ══════════════════════════════════════════════════════
#  THEME
# ══════════════════════════════════════════════════════
BG_PRIMARY = "#0f1117"
BG_SECONDARY = "#161820"
BG_HOVER = "#1e2030"

ACCENT = "#4f46e5"
ACCENT_LIGHT = "#818cf8"
ACCENT_HOVER = "#4338ca"

TEXT_PRIMARY = "#e5e7eb"
TEXT_SECONDARY = "#9ca3af"
TEXT_MUTED = "#6b7280"

BORDER = "#2a2d3a"
BORDER_LIGHT = "#374151"

GREEN = "#10b981"
AMBER = "#fbbf24"
RED = "#f87171"
BLUE = "#60a5fa"
PURPLE = "#a78bfa"

GLOBAL_QSS = f"""
QMainWindow, QWidget {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    font-family: 'Consolas', 'JetBrains Mono', 'Courier New', monospace;
    font-size: 13px;
}}
QScrollBar:vertical {{
    background: {BG_SECONDARY}; width: 6px; border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_LIGHT}; border-radius: 3px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {BG_SECONDARY}; height: 6px; border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_LIGHT}; border-radius: 3px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QToolTip {{
    background-color: {BG_SECONDARY}; color: {TEXT_PRIMARY};
    border: 1px solid {BORDER}; padding: 4px 8px;
    border-radius: 4px; font-size: 12px;
}}
QHeaderView::section {{
    background: {BG_PRIMARY}; color: {TEXT_MUTED};
    border: none; border-bottom: 1px solid {BORDER};
    padding: 6px 10px; font-size: 10px; letter-spacing: 1px;
}}
QTableWidget {{
    background: {BG_PRIMARY}; color: {TEXT_PRIMARY};
    border: none; gridline-color: {BG_HOVER}; font-size: 12px;
}}
QTableWidget::item {{ padding: 6px 10px; }}
QTableWidget::item:selected {{
    background: {BG_HOVER}; color: {TEXT_PRIMARY};
}}
QComboBox {{
    background: {BG_PRIMARY}; color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_LIGHT}; border-radius: 4px;
    padding: 4px 8px; font-size: 12px;
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {BG_SECONDARY}; color: {TEXT_PRIMARY};
    border: 1px solid {BORDER}; selection-background-color: {BG_HOVER};
}}
QLineEdit {{
    background: {BG_PRIMARY}; color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_LIGHT}; border-radius: 6px;
    padding: 6px 10px; font-size: 12px;
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QSpinBox, QDoubleSpinBox, QTimeEdit {{
    background: {BG_PRIMARY}; color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_LIGHT}; border-radius: 4px;
    padding: 3px 6px; font-size: 12px;
}}
QCheckBox {{ color: {TEXT_SECONDARY}; spacing: 6px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border-radius: 3px;
    border: 1px solid {BORDER_LIGHT}; background: {BG_PRIMARY};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
}}
"""


# ══════════════════════════════════════════════════════
#  SHARED DATA STORE  (크롤 결과 / 스케줄 공유)
# ══════════════════════════════════════════════════════
class DataStore:
    """앱 전체에서 수집 결과·스케줄을 공유하는 싱글턴"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._rows = []  # list[dict]
            cls._instance._url_map_list = []  # list[dict]
            cls._instance._schedules = []  # list[dict]
            cls._instance._sessions = []  # list[dict] — 완료된 세션 요약
        return cls._instance

    # urls
    def add_url_map(self, url_map: dict):
        self._url_map_list.append(url_map)

    def get_url_maps(self):
        return self._url_map_list

    def clear_url_maps(self):
        self._url_map_list.clear()

    # rows
    def add_row(self, row: dict):
        self._rows.append(row)

    def get_rows(self):
        return list(self._rows)

    def clear_rows(self):
        self._rows.clear()

    # schedules
    def add_schedule(self, s: dict):
        self._schedules.append(s)

    def get_schedules(self):
        return list(self._schedules)

    def remove_schedule(self, idx: int):
        if 0 <= idx < len(self._schedules):
            self._schedules.pop(idx)

    def update_schedule_status(self, idx: int, status: str):
        if 0 <= idx < len(self._schedules):
            self._schedules[idx]["status"] = status

    # sessions
    def add_session(self, s: dict):
        self._sessions.append(s)

    def get_sessions(self):
        return list(self._sessions)

store = DataStore()

class BlueprintStorage:
    _instance = None

    # ── 싱글턴 ────────────────────────────────────────────────────────────────
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, app_name: str = "CollectorApp", filename: str = "request_info.json"):

        self.root_path = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
        self.app_dir = os.path.join(self.root_path, app_name)
        self.file_path = os.path.join(self.app_dir, filename)

        try:
            self.default_source = os.path.join(utility.resource_path(), filename)
        except Exception as e:
            self.default_source = filename

        # 수집 정보 초기화
        self._initialize_storage()

        # LOAD 수집 정보
        self._blueprint = self.load()

    # ── 파일 시스템 초기화 ───────────────────────────────────────────────────
    def _initialize_storage(self) -> None:
        try:
            os.makedirs(self.app_dir, exist_ok=True)
            if not os.path.exists(self.file_path) and os.path.exists(self.default_source):
                shutil.copy2(self.default_source, self.file_path)
        except Exception as e:
            print(f"[BlueprintStorage] 초기화 오류: {e}")

    # ── 로드 ─────────────────────────────────────────────────────────────────
    def load(self):
        target = self.file_path if os.path.exists(self.file_path) else self.default_source
        if not os.path.exists(target):
            return customized_settings.get_request_settings()
        try:
            with open(target, "r", encoding="utf-8") as f:
                request_info = json.load(f)

                # 수집 대상이 하나일 경우
                if len(request_info) == 1:
                    request_info = request_info[0]

                return request_info

        except Exception as e:
            print(f"[BlueprintStorage] 로드 실패: {e}")
            return customized_settings.get_request_settings()

    # ── 업데이트 ─────────────────────────────────────────────────────────────────
    def update(
            self,
            request_info: dict,
            dashboard_page=None,
            monitor_page=None,
            session_page=None,
            auth_page=None
    ) -> None:
        new_settings = request_info.copy()

        if dashboard_page is not None:
            new_settings = self._sync_dashboard(new_settings, dashboard_page)
        # if monitor_page is not None:
        #     new_settings = self._sync_monitor_page(new_settings, monitor_page)
        if session_page is not None:
            new_settings = self._sync_session_page(new_settings, session_page)
        if auth_page is not None:
            new_settings = self._sync_auth_page(new_settings, auth_page)

        request_info.update(new_settings)

    # ── 저장 ─────────────────────────────────────────────────────────────────
    def save(self, request_info) -> None:
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(request_info, f, ensure_ascii=False, indent=4)            
        except Exception as e:
            print(f"[BlueprintStorage] 저장 실패: {e}")

    # =========================================================================
    # PUBLIC API
    # =========================================================================
    def read(self) -> dict:
        """
        내부 _blueprint dict 의 참조(reference)를 반환합니다.

        [중요] 반환값은 복사본이 아닌 내부 객체 자체입니다.
        모듈 최상단에서

            _blueprint = BlueprintStorage().read()

        로 할당하면, 이후 consolidate_from_pages() 가 _blueprint 를
        in-place 로 수정할 때 외부 변수에도 즉시 반영됩니다.
        재할당이 필요 없습니다.
        """
        return self._blueprint


    # ── 개별 Page 동기화 헬퍼 ────────────────────────────────────────────────
    @staticmethod
    def _sync_dashboard(new_settings: dict, page) -> None:
        try:
            new_settings["tasks"]["main"]["delay"] = page.delay_spin.value()
            new_settings["tasks"]["main"]["threads"] = page.thread_spin.value()
            new_settings["tasks"]["main"]["timeout"] = page.timeout_spin.value()
            new_settings["tasks"]["main"]["retry"] = page.retry_spin.value()
            new_settings["tasks"]["main"]["session"]["ua_ra"] = page.ua_check.isChecked()
            new_settings["tasks"]["main"]["session"]["cookie_ra"] = page.cookie_check.isChecked()

            out_mode = getattr(page, "_out_mode", "FILE")
            new_settings["tasks"]["main"]["extract"]["file"]["enabled"] = (out_mode == "FILE")
            new_settings["tasks"]["main"]["extract"]["db"]["enabled"] = (out_mode == "DB")
            new_settings["tasks"]["main"]["extract"]["file"]["auto_save"] = getattr(page, "_auto_save", False)

            return new_settings
        except AttributeError as e:
            print(f"[BlueprintStorage] DashboardPage 동기화 오류: {e}")

    @staticmethod
    def _sync_monitor_page(new_settings: dict, page) -> None:
        try:
            return
        except AttributeError as e:
            print(f"[BlueprintStorage] MonitorPage 동기화 오류: {e}")

    @staticmethod
    def _sync_schedule_page(new_settings: dict, page) -> None:
        try:
            return
        except AttributeError as e:
            print(f"[BlueprintStorage] SchedulerPage 동기화 오류: {e}")

    def _sync_session_page(self, new_settings: dict, page) -> None:
        try:
            new_settings["tasks"]["main"]["net_rotate"]["enabled"] = page._global_cb.isChecked()
            new_settings["tasks"]["main"]["net_rotate"]["rotate"] = page._rotate_cb.isChecked()
            new_settings["tasks"]["main"]["net_rotate"]["allow_ip_cnts"] = page._allow_ip_cnts.value()
            new_settings["tasks"]["main"]["net_rotate"]["ip_list"] = deepcopy(getattr(page, "_proxy_rows", []))
            return new_settings
        except AttributeError as e:
            print(f"[BlueprintStorage] SessionSettingsPage 동기화 오류: {e}")

    def _sync_auth_page(self, new_settings: dict, page) -> None:
        try:
            new_settings["tasks"]["main"]["auth"]["tls_verify"] = page._tls_cb.isChecked()
            new_settings["tasks"]["main"]["auth"]["encrypt_store"] = page._store_cb.isChecked()
            new_settings["tasks"]["main"]["auth"]["session_auto_rotate"] = page._rotate_cb.isChecked()
            new_settings["tasks"]["main"]["auth"]["credentials"] = deepcopy(getattr(page, "_auth_rows", []))

            # Login Info 탭 위젯 (실제 위젯명: _login_url, _login_id, _login_pw 등)
            login = new_settings["tasks"]["main"]["auth"].setdefault("login", {})

            def _text(attr):
                w = getattr(page, attr, None)
                return w.text().strip() if w is not None else None

            login["user_id"] = _text("_login_id") or None
            login["pwd"] = _text("_login_pw") or None

        except AttributeError as e:
            print(f"[BlueprintStorage] AuthManagerPage 동기화 오류: {e}")


    def find_task_by_schedule(self, name: str, url: str) -> dict | None:
        """name + callback_urls 로 태스크를 검색합니다."""
        for t in self._blueprint.get("tasks", []):
            if t.get("name") == name and t.get("callback_url") == url:
                return t
        return None

    # =========================================================================
    # dict-like 인터페이스 (하위 호환)
    # =========================================================================
    def __getitem__(self, key):
        if key in self._blueprint:
            return self._blueprint[key]
        task = self.get_active_task()
        if task and key in task:
            return task[key]
        return None

    def __setitem__(self, key, value):
        if key in ("version", "global", "tasks"):
            self._blueprint[key] = value
        else:
            task = self.get_active_task()
            if task is not None:
                task[key] = value
            else:
                self._blueprint[key] = value

    def get(self, key, default=None):
        val = self[key]
        return val if val is not None else default

blueprint = BlueprintStorage()  # 수집 정보 클래스
request_info = blueprint.read()  # 수집 정보

# ══════════════════════════════════════════════════════
#  CRAWLER WORKER THREAD
# ══════════════════════════════════════════════════════
class MultiprocessWorker(QThread):
    """
    별도의 서브 프로세스를 실행하고 모니터링하여 Scrapy를 구동하는 작업 스레드.
    수집 목록 목록은 임시 파일로 전달하여 명령어 길이 제한을 회피합니다.
    """
    progress = pyqtSignal(int, int)
    new_row = pyqtSignal(dict)
    log_message = pyqtSignal(str, str)
    stats_update = pyqtSignal(dict)
    finished = pyqtSignal(dict, dict)  # session summary dict
    no_urls = pyqtSignal()             # URL 리스트 생성 실패 시 즉시 emit

    LOG_TEMPLATES = {
        "ok": ["수집 성공 ({url}) — {time}s", "파싱 완료: {title}", "데이터 저장 완료 #{idx}"],
        "warn": ["응답 지연 감지 ({time}s), 딜레이 조정 중", "Rate limit 감지 — 재시도 대기"],
        "err": ["연결 타임아웃: {url}", "파싱 오류: 셀렉터 매칭 실패 ({url})"],
        "info": ["페이지 {page} 진입 중", "셀렉터 재적용 완료", "프록시 전환 ({proxy})"],
    }

    def __init__(self, task, job_name="수동 실행"):
        super().__init__()
        self.task = task
        self.process = None  # 프로세스 객체 저장을 위한 변수 추가
        self.queue = multiprocessing.Queue()  # 프로세스 간 통신을 위한 큐 생성
        self.job_name = job_name
        self._running = True
        self._errors = 0
        self._done = 0
        self._resp_times = []
        self.total = None
        self._started_at = None

    def stop(self):
        """
        수집 중단 요청.
        _running 플래그만 False 로 세팅하면 run() 루프가 다음
        queue.get(timeout=0.5) 만료 시점에 중단 분기로 진입합니다.
        큐를 이곳에서 비우지 않습니다 — empty()+get_nowait() 조합은
        멀티프로세스 환경에서 race condition을 일으킬 수 있습니다.
        """
        self._running = False

    def run(self):

        self._started_at = datetime.now()

        callback_url = self.task["callback_url"]
        threads = self.task["threads"]
        delay = self.task["delay"]

        # 전체 대상 URL 리스트 생성 및 세트 변환 (조회 성능 최적화)
        try:
            generated_urls = utility.generate_combined_urls(self.task['callback_url'])
            url_list = set(generated_urls)  # 조회를 위해 set으로 변환
            total = len(url_list)
        except:
            url_list = set()
            total = 0

        # [방법 A] URL 리스트 생성 단계에서 즉시 감지
        # — URL 패턴 오류 / callback_url 미설정 등으로 수집 대상이 0건인 경우
        #   타이머 없이 이 시점에 no_urls 시그널을 emit하고 종료한다.
        if total == 0:
            self.log_message.emit("err", "수집 대상 URL이 없습니다. URL 또는 수집 설정을 확인하세요.")
            self.no_urls.emit()
            return

        self.log_message.emit("info", "크롤러 초기화 완료")
        self.log_message.emit("info", f"대상: {self.task["callback_url"]}")
        self.log_message.emit("info", f"스레드 {threads}개 / 딜레이 {delay}s")

        processed_urls = set()
        
        try:

            # 수집 객체 선언
            self.process = multiprocessing.Process(target=worker.run_spider, args=(self.task, self.queue))

            # 수집 프로세스 실행
            self.process.start()

            self.log_message.emit("info", "SCRAPY START")

            # 실시간 로그 및 데이터 수신 루프
            while self.process.is_alive() or not self.queue.empty():

                # 수집 종료 시
                if not self._running:
                    if self.process and self.process.is_alive():
                        self.process.terminate()          # 1. SIGTERM
                        self.process.join(timeout=0.5)   # 2. 워ό어 스레드 안에서 실행 — UI 블로킹 없으만 무콘 타임아웃 단축
                        if self.process.is_alive():       # 3. SIGKILL
                            self.process.kill()
                            self.process.join(timeout=0.3)
                    try:
                        self.process.close()              # 4. 자원 해제
                    except Exception:
                        pass
                    try:                                  # 5. 남은 큐 카주인자 — 프로세스 종료 후라 race condition 없으먹
                        while True:
                            self.queue.get_nowait()
                    except Exception:
                        pass
                    self.log_message.emit("warn", "사용자에 의해 중단됨")
                    break

                try:

                    # 큐에서 한 줄 읽기 (timeout을 주어 중단 체크가 가능하게 함)
                    line = self.queue.get(timeout=0.5)

                    clean_line = line.strip()

                    if clean_line.startswith("RESULT_INFO:"):

                        result_info = json.loads(clean_line.replace("RESULT_INFO:", "").strip())
                        result_info["resp_info"]["timestamp"] = datetime.now()
                        result_info["job_name"] = self.job_name

                        res_url = result_info["resp_info"]["url"]
                        status_code = result_info["resp_info"]["status"]
                        resp_time = result_info["resp_info"]["pure_latency"]
                        reason = result_info["resp_info"]["reason"]

                        # 1. 대상 리스트에 있고 2. 이전에 카운팅한 적이 없는 경우만 진행
                        if res_url in url_list and res_url not in processed_urls:
                            processed_urls.add(res_url)
                            url_map = {"req_url": res_url, "status_code": status_code,"pure_latency": resp_time,
                                       "session": len([callback_url]),
                                       "timestamp": result_info["resp_info"]["timestamp"]}
                            store.add_url_map(url_map)
                            # 카운팅 이력에 추가
                            self._done += 1

                        # 상태 코드 ( status_code )
                        if status_code == 404 or status_code == 500:
                            self._errors += 1
                            level, tmpl = "err", reason
                        elif status_code == 429:
                            level, tmpl = "warn", reason
                        elif status_code == 301:
                            level, tmpl = "info", reason
                        elif status_code == 200:
                            level, tmpl = "ok", reason
                        else:
                            level, tmpl = "unclear", reason

                        self.log_message.emit(level, tmpl)

                        store.add_row(result_info)
                        self.new_row.emit(result_info)

                        self._resp_times.append(resp_time)
                        avg = sum(self._resp_times) / len(self._resp_times)

                        # 대시보드 - 상태바
                        self.progress.emit(self._done, total)

                        # 대시보드 - 세션 통계
                        self.stats_update.emit({
                            "total": self._done,
                            "errors": self._errors,
                            "pages": total,
                            "avg_time": f"{avg:.2f}s",
                        })

                        time.sleep(max(0.05, delay / threads))

                    else:
                        pass

                except Exception as e:  # Queue.Empty 예외 발생 시 무시하고 루프 계속
                    continue


        except Exception as e:
            self.log_message.emit("err", e)

        finally:
            elapsed = (datetime.now() - self._started_at).total_seconds()
            avg_t = sum(self._resp_times) / len(self._resp_times) if self._resp_times else 0

            summary = {
                "job": self.job_name,
                "url": callback_url,
                "total": self._done,
                "errors": self._errors,
                "success": self._done - self._errors,
                "avg_time": round(avg_t, 3),
                "elapsed": round(elapsed, 1),
                "started": self._started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "interrupted": not self._running,  # True if stopped by user
                "finished": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            store.add_session(summary)
            self.finished.emit(self.task, summary)


# ──────────────────────────────────────────────────────
#  EqualSpacingTable
#  — Initial Equal distribution · Free resize + H-scroll · Double-click auto-fit
# ──────────────────────────────────────────────────────
class EqualSpacingTable(QTableWidget):
    """
    초기 Equal 분배 + 자유 리사이즈 + 가로 스크롤 테이블

    ─────────────────────────────────────────────────────
    동작 원칙
    ─────────
    • 초기(컬럼 수 확정 / 창 최초 표시): viewport 너비를 균등 분배
    • 컬럼 드래그: 해당 컬럼 너비만 변경, 나머지 컬럼은 Fixed 유지
      → 전체 컬럼 합산이 viewport 초과 시 가로 스크롤바 자동 활성화
    • 창 리사이즈: 컬럼들이 이미 사용자 지정된 경우 그대로 유지
      (초기 equal 분배 상태인 경우에만 재분배)
    • 헤더 구분선 더블클릭: 해당 컬럼의 모든 셀 + 헤더 텍스트 중
      가장 긴 것에 맞춰 Auto-fit

    Public API
    ──────────
    set_column_spacing(px)   셀 좌우 padding 변경 (시각적 간격)
    set_hscroll_handle(px)   가로 스크롤바 핸들 최소 너비
    set_row_height(px)       모든 행 높이 변경
    reset_equal()            현재 viewport 기준으로 Equal 너비 재초기화
    fit_column(logical)      지정 컬럼 Auto-fit (더블클릭과 동일)
    """

    MIN_COL_W = 30  # 컬럼 최소 너비 (px)
    H_PADDING = 20  # auto-fit 시 텍스트 양쪽 여유 패딩 (px, 한쪽 10)

    def __init__(
            self,
            parent=None,
            row_height: int = 28,
            col_padding: int = 10,
            hscroll_handle: int = 24,
    ):
        super().__init__(parent)

        self._row_height = row_height
        self._col_padding = col_padding
        self._hscroll_handle = hscroll_handle

        # True: 아직 사용자가 드래그한 적 없음 → 창 리사이즈 시 재분배
        self._is_equal_state = True
        # sectionResized 재진입 방지
        self._resizing = False

        self._init_table()
        self._apply_style()

    # ── 초기 설정 ─────────────────────────────────────
    def _init_table(self):
        self.verticalHeader().setVisible(False)
        self.setWordWrap(False)
        self.setShowGrid(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(True)
        self.verticalHeader().setDefaultSectionSize(self._row_height)

        # 가로 스크롤바: 컬럼 합산이 viewport 초과 시 자동 표시
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(False)
        hdr.setMinimumSectionSize(self.MIN_COL_W)

        # 드래그 리사이즈 — 해당 컬럼만 변경 (다른 컬럼 고정)
        hdr.sectionResized.connect(self._on_section_resized)

        # 헤더 구분선 더블클릭 → Auto-fit
        hdr.sectionHandleDoubleClicked.connect(self.fit_column)

    # ── viewport 총 너비 계산 ─────────────────────────
    def _viewport_total(self) -> int:
        vscroll = self.verticalScrollBar()
        sb_w = vscroll.width() if vscroll.isVisible() else 0
        return max(1, self.viewport().width() - sb_w)

    # ── Equal width 초기 분배 ─────────────────────────
    def _redistribute(self):
        """
        viewport 너비를 컬럼 수로 균등 분할합니다.
        나머지 픽셀은 마지막 컬럼에 흡수합니다.
        """
        n = self.columnCount()
        if n <= 0:
            return

        total = self._viewport_total()
        base_w = max(self.MIN_COL_W, total // n)
        rem = total - base_w * n

        self._resizing = True
        try:
            for c in range(n):
                self.setColumnWidth(c, base_w + (rem if c == n - 1 else 0))
        finally:
            self._resizing = False

        self._is_equal_state = True

    # ── 드래그 핸들러 — 해당 컬럼만 변경 ──────────────
    def _on_section_resized(self, logical: int, old_w: int, new_w: int):
        """
        드래그된 컬럼의 너비만 변경합니다.
        다른 컬럼은 Fixed 유지 → 전체 합산 증가 시 H-scrollbar 활성화.
        MIN_COL_W 미만으로는 줄일 수 없습니다.
        """
        if self._resizing:
            return

        # MIN_COL_W 클램프
        if new_w < self.MIN_COL_W:
            self._resizing = True
            try:
                self.setColumnWidth(logical, self.MIN_COL_W)
            finally:
                self._resizing = False

        # 사용자가 직접 조작 → equal 상태 해제 (창 리사이즈 시 재분배 안 함)
        self._is_equal_state = False

    # ── Auto-fit (더블클릭 / 공개 API) ────────────────
    def fit_column(self, logical: int):
        """
        지정 컬럼의 너비를 해당 컬럼 내 가장 긴 텍스트에 맞춥니다.

        측정 대상
        ─────────
        • 헤더 텍스트
        • 모든 행의 셀 텍스트 (QTableWidgetItem)
        • CellWidget이 있는 경우 위젯의 sizeHint().width()

        폰트
        ────
        • 헤더: horizontalHeader().font()
        • 셀:   self.font()
        """
        hdr = self.horizontalHeader()
        hdr_font = hdr.font()
        cell_font = self.font()

        hdr_fm = QFontMetrics(hdr_font)
        cell_fm = QFontMetrics(cell_font)

        # 헤더 텍스트 너비
        hdr_text = self.horizontalHeaderItem(logical)
        max_w = hdr_fm.horizontalAdvance(hdr_text.text() if hdr_text else "") + self.H_PADDING

        # 셀 텍스트 / 위젯 너비
        for row in range(self.rowCount()):
            widget = self.cellWidget(row, logical)
            if widget:
                max_w = max(max_w, widget.sizeHint().width() + self.H_PADDING)
            else:
                item = self.item(row, logical)
                if item and item.text():
                    tw = cell_fm.horizontalAdvance(item.text()) + self._col_padding * 2 + self.H_PADDING
                    max_w = max(max_w, tw)

        target_w = max(self.MIN_COL_W, max_w)

        self._resizing = True
        try:
            self.setColumnWidth(logical, target_w)
        finally:
            self._resizing = False

        # auto-fit 도 사용자 조작으로 간주 → equal 상태 해제
        self._is_equal_state = False

    # ── Qt 이벤트 오버라이드 ──────────────────────────
    def resizeEvent(self, event):
        """
        창 크기 변경 시:
          - equal 상태이면 재분배 (초기 상태 유지)
          - 사용자가 이미 드래그한 경우 컬럼 너비 그대로 유지
        """
        super().resizeEvent(event)
        if self._is_equal_state and self.columnCount() > 0:
            self._redistribute()

    def setColumnCount(self, count: int):
        """컬럼 수 확정 직후 Equal 재분배 예약."""
        super().setColumnCount(count)
        if count > 0:
            self._is_equal_state = True
            QTimer.singleShot(0, self._redistribute)

    # ── StyleSheet ────────────────────────────────────
    def _apply_style(self):
        p = self._col_padding
        self.setShowGrid(False)
        self.setStyleSheet(f"""
            QTableWidget::item {{
                padding-left:  {p}px;
                padding-right: {p}px;
                border-right: 1px solid {BORDER};
            }}
            QTableWidget::item:last-child {{
                border-right: none;
            }}
            QHeaderView::section {{
                background: {BG_PRIMARY}; color: {TEXT_MUTED};
                border: none;
                border-right: 1px solid {BORDER};
                border-bottom: 1px solid {BORDER};
                padding: 6px {p}px;
                font-size: 10px; letter-spacing: 1px;
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
            QScrollBar:vertical {{
                background: {BG_SECONDARY}; width: 4px; border-radius: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER_LIGHT}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: {BG_SECONDARY}; height: 6px; border-radius: 3px;
            }}
            QScrollBar::handle:horizontal {{
                background: {BORDER_LIGHT}; border-radius: 3px;
                min-width: {self._hscroll_handle}px;
                max-width: {self._hscroll_handle}px;
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{ width: 0; }}
        """)

    # ── Public API ────────────────────────────────────
    def set_column_spacing(self, padding_px: int):
        """셀 좌우 padding 변경 (시각적 간격)."""
        self._col_padding = padding_px
        self._apply_style()

    def set_hscroll_handle(self, width_px: int):
        """가로 스크롤바 핸들 최소 너비 변경."""
        self._hscroll_handle = width_px
        self._apply_style()

    def set_row_height(self, height_px: int):
        """모든 행의 기본 높이 변경."""
        self._row_height = height_px
        self.verticalHeader().setDefaultSectionSize(height_px)
        for r in range(self.rowCount()):
            self.setRowHeight(r, height_px)

    def reset_equal(self):
        """현재 viewport 기준으로 Equal 너비를 재초기화합니다."""
        self._redistribute()


class Divider(QFrame):
    def __init__(self, orientation="h", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine if orientation == "h" else QFrame.Shape.VLine)
        self.setStyleSheet(f"color:{BORDER}; background:{BORDER};")
        if orientation == "h":
            self.setFixedHeight(1)
        else:
            self.setFixedWidth(1)


def make_label(text, color=TEXT_SECONDARY, size=13, bold=False):
    lbl = QLabel(text)
    lbl.setContentsMargins(0, 0, 5, 0)
    weight = "bold" if bold else "normal"
    lbl.setStyleSheet(f"color:{color}; font-size:{size}px; font-weight:{weight}; background:transparent; border:none;")
    return lbl

def card_widget(title="", parent=None):
    """어두운 테두리 카드. (widget, inner_layout) 반환"""
    w = QWidget(parent)
    w.setStyleSheet(f"""
        QWidget {{
            background:{BG_SECONDARY};
            border:1px solid {BORDER};
            border-radius:8px;
        }}
    """)
    outer = QVBoxLayout(w)
    outer.setContentsMargins(14, 12, 14, 12)
    outer.setSpacing(8)
    if title:
        lbl = make_label(title.upper(), TEXT_MUTED, 10)
        lbl.setStyleSheet(lbl.styleSheet() + " letter-spacing:1px;")
        outer.addWidget(lbl)
        outer.addWidget(Divider())
    return w, outer


def action_btn(text, color=ACCENT, hover=ACCENT_HOVER, text_color="white", parent=None):
    btn = QPushButton(text, parent)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background:{color}; color:{text_color};
            border:none; border-radius:6px;
            padding:6px 14px; font-size:12px; font-weight:bold;
        }}
        QPushButton:hover {{ background:{hover}; }}
        QPushButton:disabled {{
            background:{BG_HOVER};
            color:{TEXT_MUTED};
            border:1px solid {BORDER};
        }}
    """)
    return btn


def outline_btn(text, parent=None):
    btn = QPushButton(text, parent)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background:transparent; color:{TEXT_SECONDARY};
            border:1px solid {BORDER_LIGHT}; border-radius:6px;
            padding:5px 12px; font-size:12px;
        }}
        QPushButton:hover {{ color:{TEXT_PRIMARY}; border-color:{TEXT_MUTED}; }}
        QPushButton:disabled {{
            background:{BG_HOVER};
            color:{TEXT_MUTED};
            border:1px solid {BORDER};
        }}
    """)
    return btn


class NavItem(QPushButton):
    def __init__(self, icon_char, label):
        super().__init__()
        self.setText(f"  {icon_char}   {label}")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(38)
        self.setStyleSheet(f"""
            QPushButton {{
                background:transparent; color:{TEXT_SECONDARY};
                text-align:left; padding-left:12px;
                border:none; border-left:2px solid transparent; font-size:13px;
            }}
            QPushButton:hover {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}
            QPushButton:checked {{
                background:{BG_HOVER}; color:{ACCENT_LIGHT};
                border-left:2px solid {ACCENT_LIGHT};
            }}
        """)



class TagButton(QPushButton):
    def __init__(self, text):
        super().__init__(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background:#1a1040; color:#a78bfa;
                border:1px solid #312e81; border-radius:4px;
                padding:3px 10px; font-size:11px;
            }}
            QPushButton:hover {{ background:#312e81; }}
            QPushButton:checked {{ background:{ACCENT}; color:white; border-color:{ACCENT}; }}
        """)


class StatCard(QWidget):
    def __init__(self, label, value, color=TEXT_PRIMARY):
        super().__init__()
        self.setStyleSheet(f"background:{BG_PRIMARY}; border-radius:6px; border:1px solid {BORDER};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        self._val = QLabel(value)
        self._val.setStyleSheet(
            f"color:{color}; font-size:20px; font-weight:bold; border:none; background:transparent;")
        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px; border:none; background:transparent;")
        lay.addWidget(self._val)
        lay.addWidget(self._lbl)

    def update_value(self, v):
        self._val.setText(str(v))


class LogView(QTextEdit):
    COLORS = {"ok": GREEN, "err": RED, "warn": AMBER, "info": ACCENT_LIGHT}

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setStyleSheet(f"""
            QTextEdit {{
                background:{BG_PRIMARY}; color:{TEXT_SECONDARY};
                border:none; font-size:11px;
                font-family:'Consolas', monospace; padding:4px;
            }}
        """)

    def append_log(self, level: str, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        color = self.COLORS.get(level, TEXT_SECONDARY)
        tag = f"[{level.upper():4s}]"
        self.append(
            f'<span style="color:{TEXT_MUTED};">{ts}</span> '
            f'<span style="color:{color}; font-weight:bold;">{tag}</span> '
            f'<span style="color:{TEXT_SECONDARY};">{message}</span>'
        )
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())


# ══════════════════════════════════════════════════════
#  GLOBAL TOOLBAR  (모든 페이지 공통 상단 툴바)
# ══════════════════════════════════════════════════════
class GlobalToolbar(QWidget):
    """
    Sidebar 오른쪽 콘텐츠 영역 최상단에 고정 표시되는 공통 툴바.
    - URL 라벨 / URL 입력창 / URL 복사 버튼 / 시작·중지 버튼
    - start_requested : 시작 버튼 클릭 시 emit (request_info dict)
    - stop_requested  : 중지 버튼 클릭 시 emit
    - reset_requested : 수집 시작 직전 UI 초기화 요청 emit
    """
    start_requested = pyqtSignal(dict)
    stop_requested = pyqtSignal()
    reset_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._start_cancelled = False   # 중지 시 QTimer 예약 콜백을 막는 플래그
        self.step_circles = []
        self.step_labels = []
        # 실제 페이지 인스턴스는 MainWindow._build()에서 set_pages()로 주입됩니다.
        self.dashboard = None
        self.monitor_page = None
        self.session_page = None
        self.auth_page = None
        self.log_view = None  # DashboardPage 생성 후 set_log_view()로 주입
        self._build()
        self.task = {}

    # ── UI 구성 ───────────────────────────────────────
    def _build(self):
        self.setFixedHeight(49)
        self.setStyleSheet(
            f"background:{BG_SECONDARY}; border-bottom:1px solid {BORDER};"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(10)

        # 수집 방식 라벨
        lay.addWidget(make_label(request_info["conditions"]["method"], ACCENT_LIGHT, 12, True))

        # URL 입력창
        self.url_input = QLineEdit(request_info["url"] if request_info else "")
        self.url_input.setCursorPosition(0)
        lay.addWidget(self.url_input, 1)

        # URL 복사 버튼
        self._copy_btn = outline_btn("URL 복사")
        self._copy_btn.clicked.connect(self._copy_url)
        lay.addWidget(self._copy_btn)

        # 시작 / 중지 버튼
        self.run_btn = QPushButton("▶  시작")
        self.run_btn.setFixedWidth(90)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(self._toggle_run)
        self._style_run_btn(False)
        lay.addWidget(self.run_btn)

    # ── 내부 메서드 ───────────────────────────────────
    def _copy_url(self):
        """URL을 클립보드에 복사하고 입력창의 텍스트를 전체 선택합니다."""
        QApplication.clipboard().setText(self.url_input.text())
        self.url_input.setFocus()
        self.url_input.selectAll()

    # 단계 사이 (선)
    def _update_step_ui(self, step_idx):
        """
        현재 인덱스에 해당하는 단계만 주인공으로 만들고,
        나머지는 과거/미래 상관없이 모두 배경으로 보냅니다.
        """
        for i in range(len(self.step_circles)):
            # 현재 활성화된 단계 (Accent Color)
            if i == step_idx:
                circle_style = f"""
                    background: {ACCENT};
                    border: 2px solid {ACCENT_LIGHT};
                    color: white;
                """
                label_style = f"color: {TEXT_PRIMARY}; font-weight: bold;"

            # 그 외 모든 단계 (Muted Color)
            else:
                label_style = f"color: {TEXT_MUTED}; font-weight: normal;"
                circle_style = f"""
                    background: {BG_SECONDARY};
                    border: 2px solid {BORDER};
                    color: {TEXT_MUTED};
                """

            # 스타일 적용
            self.step_circles[i].setStyleSheet(circle_style + "border-radius: 14px; font-weight: bold;")
            self.step_labels[i].setStyleSheet(label_style + "font-size: 11px;")

    def _style_run_btn(self, running: bool):
        if running:
            self.run_btn.setText("⬛  중지")
            self.run_btn.setStyleSheet(f"""
                QPushButton{{background:#7f1d1d;color:{RED};border:none;border-radius:6px;
                padding:6px 14px;font-size:13px;font-weight:bold;}}
                QPushButton:hover{{background:#991b1b;}}""")
        else:
            self.run_btn.setText("▶  시작")
            self.run_btn.setStyleSheet(f"""
                QPushButton{{background:{ACCENT};color:white;border:none;border-radius:6px;
                padding:6px 14px;font-size:13px;font-weight:bold;}}
                QPushButton:hover{{background:{ACCENT_HOVER};}}""")

    # 시작 버튼 클릭 시 호출
    def _toggle_run(self):
        """시작/중지 버튼 클릭 시 호출"""
        if not self._running:

            # ── 0. 이전 중지로 인한 취소 플래그 해제 ──
            self._start_cancelled = False

            # ── 1. 작업 진행 상태를 즉시 "수집 대기(step 0)"로 표시 ──
            mw = self._main_window()
            if mw is not None:
                mw.dashboard._update_step_ui(0)

            # ── 2. MainWindow의 실제 dashboard/monitor_page 초기화 요청 ──
            self.reset_requested.emit()

            # ── 3. GlobalToolbar 내부의 로컬 페이지도 동일하게 초기화 ──
            self.dashboard._reset_dashboard()
            self.monitor_page._reset_monitor_page()

            self.set_running(True)

            self._log("info", "수집을 시작합니다.")

            # UI 업데이트가 즉시 반영되도록 강제 허용
            QApplication.processEvents()

            # 사용자 경험을 위해 아주 짧은 지연 후 다음 로직 실행
            QTimer.singleShot(1000, self._step_to_setting)
        else:
            # 중지 버튼 클릭 시 즉시 [수집 대기]로 복귀
            # ── 1. QTimer 예약 콜백(_step_to_setting / _actual_start) 취소 ──
            self._start_cancelled = True

            # ── 2. 워커 프로세스 중지 시그널 ──
            self.stop_requested.emit()

            # ── 3. 버튼 / step UI 즉시 초기화 ──
            self.set_running(False)
            self._update_step_ui(0)
            mw = self._main_window()
            if mw is not None:
                mw.dashboard._update_step_ui(0)

            # ── 4. 모든 페이지 UI 및 DataStore 완전 초기화 ──
            self._full_reset()

            self._log("warn", "수집이 중단되었습니다. 수집 대기 상태로 초기화합니다.")

    def _step_to_setting(self):
        """[단계 1: 수집 세팅] 처리"""
        # 중지 버튼이 눌렸으면 콜백 취소
        if self._start_cancelled:
            return

        # GlobalToolbar 자체 step UI 업데이트
        self._update_step_ui(1)

        # ── MainWindow.dashboard의 step UI도 함께 "수집 세팅(1)" 으로 전환 ──
        mw = self._main_window()
        if mw is not None: mw.dashboard._update_step_ui(1)

        # UI 업데이트가 즉시 반영되도록 강제 허용
        QApplication.processEvents()

        self._log("info", "환경 설정을 로드합니다. (수집 세팅 중...)")

        # 실제 설정 로드 작업
        try:
            # 세팅 단계가 사용자 눈에 충분히 보이도록 1초 유지 후 다음 단계로 이동
            QTimer.singleShot(1000, self._actual_start)

        except Exception as e:
            self._log("err", f"설정 로드 실패: {e}")
            self._update_step_ui(0)
            if mw is not None:
                mw.dashboard._update_step_ui(0)

    def _actual_start(self):
        """[단계 2: 데이터 수집] 실제 시작"""
        # 중지 버튼이 눌렸으면 콜백 취소
        if self._start_cancelled:
            return

        try:
            # 메인 윈도우에 시작 신호 전달 (MainWindow의 _launch_worker 실행)
            # _launch_worker 내부에서 dashboard._update_step_ui(2) 를 호출하므로
            # 여기서는 별도로 step UI를 올릴 필요 없음

            dashboard_page = self.dashboard
            session_page = self.session_page
            auth_page = self.auth_page
            self.task.update(request_info)
            self.task["delay"] = dashboard_page.delay_spin.value()
            self.task["threads"] = dashboard_page.thread_spin.value()
            self.task["timeout"] = dashboard_page.timeout_spin.value()
            self.task["retry"] = dashboard_page.retry_spin.value()
            self.task["user_agent"] = session_page.ua_check.isChecked()
            self.task["cookie"] = session_page.cookie_check.isChecked()
            self.task["proxy"] = {
                                "enabled": session_page._global_cb.isChecked(),
                                "rotate": session_page._rotate_cb.isChecked(),
                                "allow_ip_cnts": session_page._allow_ip_cnts.value(),
                                "ip_list": deepcopy(getattr(session_page, "_proxy_rows", []))
                             }
            self.task["extract"] = dashboard_page.output_info["extract"]
            self.start_requested.emit(self.task)

        except Exception as e:
            self._log("err", f"설정 로드 실패: {e}")
            self._update_step_ui(0)  # 에러 시 대기 상태로 복귀
            mw = self._main_window()
            if mw is not None:
                mw.dashboard._update_step_ui(0)

    def _main_window(self):
        """부모 위젯을 순회하여 MainWindow 인스턴스를 반환합니다. 없으면 None."""
        w = self.parent()
        while w is not None:
            if isinstance(w, QMainWindow):
                return w
            w = w.parent()
        return None

    def _full_reset(self):
        """
        중지 버튼 클릭 시 호출 — DataStore 및 모든 페이지 UI를 완전히 초기화합니다.
        · DataStore: rows / url_maps 클리어 (sessions는 이력 유지)
        · DashboardPage: 실시간 결과 테이블, 요약 카드, step UI → 수집 대기
        · MonitorPage: 수집 모니터링 테이블, 세션 통계 카드 클리어
        · GlobalToolbar + MainWindow: step UI / 프로그레스바 → 수집 대기
        """
        # DataStore 초기화 (수집 결과 행 + URL 맵; sessions는 이력이므로 유지)
        store.clear_rows()
        store.clear_url_maps()

        # DashboardPage 초기화 (테이블, 요약 카드, step UI)
        if self.dashboard is not None:
            self.dashboard._reset_dashboard()

        # MonitorPage 완전 초기화 (테이블 + 세션 통계 카드)
        if self.monitor_page is not None:
            self.monitor_page._reset_monitor_page()

        # GlobalToolbar 자체 step UI → 수집 대기
        self._update_step_ui(0)

        # MainWindow 프로그레스바 초기화
        mw = self._main_window()
        if mw is not None:
            mw.reset_progress()

    def set_running(self, v: bool):
        self._running = v
        self._style_run_btn(v)

    def set_pages(self, dashboard=None, monitor_page=None, session_page=None, auth_page=None) -> None:
        """MainWindow 초기화 후 실제 페이지 인스턴스를 주입합니다."""
        if dashboard is not None:
            self.dashboard = dashboard
        if monitor_page is not None:
            self.monitor_page = monitor_page
        if session_page is not None:
            self.session_page = session_page
        if auth_page is not None:
            self.auth_page = auth_page

    def set_log_view(self, log_view) -> None:
        """MainWindow 초기화 후 DashboardPage.log_view 를 주입합니다."""
        self.log_view = log_view

    def get_url(self) -> str:
        return self.url_input.text().strip()

    def _log(self, level: str, message: str) -> None:
        """log_view 가 주입된 경우에만 로그를 출력합니다."""
        if self.log_view is not None:
            self.log_view.append_log(level, message)


# ══════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════
class Sidebar(QWidget):
    page_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self._build()

    def _build(self):

        self.setFixedWidth(190)
        self.setStyleSheet(f"background:{BG_SECONDARY}; border-right:1px solid {BORDER};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 16)
        lay.setSpacing(2)

        logo = make_label("DataCrawler", ACCENT_LIGHT, 15, True)
        logo.setStyleSheet(logo.styleSheet() + " padding:0 16px 12px;")
        lay.addWidget(logo)
        lay.addWidget(Divider())

        nav_lbl = make_label("NAVIGATOR", TEXT_MUTED, 9)
        nav_lbl.setStyleSheet(nav_lbl.styleSheet() + " letter-spacing:2px; padding:12px 16px 4px;")
        lay.addWidget(nav_lbl)

        PAGES = [("⬡", "대시보드"), ("≡", "모니터링"), ("◷", "스케줄러"), ("▲", "통계 분석")]

        # 첫번째 수집 정보 기준으로 SETTINGS 빌드
        SETTINGS = [("◎", "세션 설정"), ("⬡", "인증 관리")] if request_info["auth"] else [("◎", "세션 설정")]

        self._btns = []
        for i, (icon, label) in enumerate(PAGES):
            btn = NavItem(icon, label)
            btn.clicked.connect(lambda _, idx=i: self._on_nav(idx))
            lay.addWidget(btn)
            self._btns.append(btn)

        lay.addSpacing(8)
        lay.addWidget(Divider())

        set_lbl = make_label("SETTINGS", TEXT_MUTED, 9)
        set_lbl.setStyleSheet(set_lbl.styleSheet() + " letter-spacing:2px; padding:12px 16px 4px;")
        lay.addWidget(set_lbl)

        for j, (icon, label) in enumerate(SETTINGS):
            btn = NavItem(icon, label)
            page_idx = len(PAGES) + j  # 4, 5
            btn.clicked.connect(lambda _, idx=page_idx: self._on_nav(idx))
            lay.addWidget(btn)
            self._btns.append(btn)

        lay.addStretch()
        lay.addWidget(Divider())

        status_row = QHBoxLayout();
        status_row.setContentsMargins(16, 8, 16, 0)
        dot = make_label("●", GREEN, 10)
        st = make_label("연결됨", GREEN, 12)
        status_row.addWidget(dot)
        status_row.addWidget(st)
        status_row.addStretch()
        lay.addLayout(status_row)

        self._btns[0].setChecked(True)

    def _on_nav(self, idx):
        for i, b in enumerate(self._btns):
            b.setChecked(i == idx)
        self.page_changed.emit(idx)


# ══════════════════════════════════════════════════════
#  DASHBOARD PAGE
# ══════════════════════════════════════════════════════
class DashboardPage(QWidget):

    def __init__(self):
        super().__init__()
        self.step_circles = []
        self.step_labels = []
        self.step_arrow_groups = []
        self._index = 0
        self._out_mode = None
        self.output_info = customized_settings.get_output_settings()
        self._running = False
        self._all_rows = []
        self._collected_data = []   # 수집된 원본 데이터를 메모리에 보관 (추출 시 사용)
        self._build()

    def _build(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea();
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body);
        bl.setContentsMargins(14, 14, 14, 14);
        bl.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # Config row
        cfg = QHBoxLayout();
        cfg.setSpacing(10)

        # STEP TRACKER
        stw, stl = card_widget("작업 진행 상태")
        step_container = QWidget()
        step_layout = QHBoxLayout(step_container)
        step_layout.setContentsMargins(60, 20, 60, 20)  # 좌우 마진 조정

        steps = ["수집 대기", "수집 세팅", "데이터 수집", "결과물 추출"]

        for i, text in enumerate(steps):
            # 1. 단계 숫자 원형 레이블
            circle = QLabel(str(i + 1))
            circle.setFixedSize(34, 34)  # 원 크기
            circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # 초기 스타일 (대기 상태)
            circle.setStyleSheet(f"""
                        background: {BG_SECONDARY}; border: 2px solid {BORDER}; 
                        border-radius: 14px; color: {TEXT_MUTED}; font-weight: bold;
                    """)
            self.step_circles.append(circle)

            # 2. 단계 텍스트 레이블
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; font-weight: bold;")
            self.step_labels.append(lbl)

            # 레이아웃에 추가
            step_unit = QVBoxLayout()
            step_unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            step_unit.addWidget(circle, 0, Qt.AlignmentFlag.AlignCenter)
            step_unit.addWidget(lbl, 0, Qt.AlignmentFlag.AlignCenter)
            step_layout.addLayout(step_unit)

            # 단계 사이 연결 선 (마지막 단계 제외)
            if i < len(steps) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFixedHeight(2)
                line.setStyleSheet(f"background: {BORDER}; margin-bottom: 25px;")
                step_layout.addWidget(line, 1)  # 라인이 공간을 채우도록 가중치 1 부여

        stl.addWidget(step_container)
        cfg.addWidget(stw, 1)  # 상태창이 조금 더 넓게 배치 (비율 3)

        self._update_step_ui(0)  # 초기 실행 시 "수집 대기" 상태로 불이 들어오게 설정

        # card 1
        c1w, c1 = card_widget("수집 설정")

        # Row 1 — 딜레이 / 스레드
        r1 = QHBoxLayout(); r1.setSpacing(8)
        r1.addWidget(make_label("Delay(s)", TEXT_SECONDARY, 12))
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.5, 10.0);
        self.delay_spin.setValue(0.5);
        self.delay_spin.setSingleStep(0.5);
        self.delay_spin.setDecimals(1);  # setDecimals : 소수점 자리 수 self.delay_spin.setSuffix("s")
        self.delay_spin.setToolTip("요청 간 대기 시간 (기본 1.5s)")
        r1.addWidget(self.delay_spin)
        r1.addSpacing(6)
        r1.addWidget(make_label(" Threads", TEXT_SECONDARY, 12))
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(1, 16);
        self.thread_spin.setValue(4)
        self.thread_spin.setToolTip("병렬 수집 스레드 수")
        r1.addWidget(self.thread_spin)
        r1.addSpacing(6)
        r1.addStretch();
        c1.addLayout(r1)

        # Row 2 — 타임 아웃 / 재시도
        r2 = QHBoxLayout();
        r2.setSpacing(8)
        r2.addWidget(make_label("Timeout(s)", TEXT_SECONDARY, 12))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60);
        self.timeout_spin.setValue(10)
        self.timeout_spin.setToolTip("요청 최대 대기 시간")
        r2.addWidget(self.timeout_spin)
        r2.addWidget(make_label("   Retry", TEXT_SECONDARY, 12))
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 5);
        self.retry_spin.setValue(2)
        self.retry_spin.setToolTip("실패 시 재시도 횟수 (기본 2회)")
        r2.addWidget(self.retry_spin)
        r2.addSpacing(6)
        r2.addStretch();
        c1.addLayout(r2)

        c1w.setFixedWidth(320)
        cfg.addWidget(c1w, 1)
        bl.addLayout(cfg)

        # ── 실시간 수집 결과 (결과 페이지에서 이동) ────────────────
        mon_row = QHBoxLayout();
        mon_row.setSpacing(10)
        tcw, tc = card_widget("실시간 수집 결과")
        tbl_ctrl = QHBoxLayout()

        # 좌: 검색창 + rows 배지
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 검색")
        self.search_box.setFixedWidth(220)
        self.search_box.textChanged.connect(self._apply_filter)
        tbl_ctrl.addWidget(self.search_box)

        self.count_lbl = QLabel("0 rows")
        self.count_lbl.setStyleSheet(
            f"color:{ACCENT_LIGHT}; background:{BG_HOVER}; padding:2px 8px; border-radius:10px; font-size:11px;")
        tbl_ctrl.addWidget(self.count_lbl)

        tbl_ctrl.addStretch()

        # 우: EXTRACT / 추출 설정
        exp_btn = action_btn("EXTRACT");
        exp_btn.clicked.connect(self._extract_result_table)
        tbl_ctrl.addWidget(exp_btn)
        out_cfg_btn = QPushButton("⚙  추출 설정")
        out_cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        out_cfg_btn.setStyleSheet(f"""
            QPushButton {{
                background:{BG_SECONDARY}; color:{TEXT_SECONDARY};
                border:1px solid {BORDER_LIGHT}; border-radius:6px;
                padding:5px 12px; font-size:12px;
            }}
            QPushButton:hover {{ background:{BG_HOVER}; color:{ACCENT_LIGHT}; border-color:{ACCENT_LIGHT}; }}
        """)
        out_cfg_btn.clicked.connect(self._open_output_settings_dialog)
        tbl_ctrl.addWidget(out_cfg_btn)
        tc.addLayout(tbl_ctrl)

        self.result_table = EqualSpacingTable(parent=self, row_height=28, col_padding=10, hscroll_handle=50)
        self.result_table.setColumnCount(len(self._get_result_columns()) + 1)
        self.result_table.setHorizontalHeaderLabels(["NO"] + self._get_result_columns())
        self.result_table.itemClicked.connect(self._show_detail)
        tc.addWidget(self.result_table)
        mon_row.addWidget(tcw, 1)

        # ── 우측 고정 패널 (수집 결과 요약 + 콘솔 로그) ──
        rw = QWidget();
        rw.setFixedWidth(320)
        rl = QVBoxLayout(rw);
        rl.setContentsMargins(0, 0, 0, 0);
        rl.setSpacing(10)

        summary_card_w, summary_card_l = card_widget("수집 결과 요약")
        summary_inner_lay = QGridLayout();
        summary_inner_lay.setSpacing(8)
        self.sum_total = StatCard("전체 항목", "0")
        self.sum_ok = StatCard("200 성공", "0", GREEN)
        self.sum_err = StatCard("오류 합계", "0", RED)
        self.sum_warn = StatCard("Rate Limit", "0", AMBER)
        summary_inner_lay.addWidget(self.sum_total, 0, 0);
        summary_inner_lay.addWidget(self.sum_ok, 0, 1)
        summary_inner_lay.addWidget(self.sum_err, 1, 0);
        summary_inner_lay.addWidget(self.sum_warn, 1, 1)
        summary_card_l.addLayout(summary_inner_lay)
        rl.addWidget(summary_card_w)

        lw, ll = card_widget("콘솔 로그")
        self.log_view = LogView();
        self.log_view.setMinimumHeight(200)
        clr = outline_btn("지우기");
        clr.clicked.connect(self.log_view.clear)

        clrr = QHBoxLayout();
        clrr.addStretch();
        clrr.addWidget(clr)
        ll.addLayout(clrr)
        ll.addWidget(self.log_view)
        rl.addWidget(lw, 1)

        mon_row.addWidget(rw)
        bl.addLayout(mon_row, 1)

        # ── 선택 항목 상세 (결과 페이지에서 이동) ──────────────────
        dw, dl = card_widget("선택 항목 상세")
        self.detail_lbl = make_label("테이블에서 행을 클릭하세요.", TEXT_MUTED, 12)
        dl.addWidget(self.detail_lbl)
        bl.addWidget(dw)

    # 단계 사이 (선)
    def _update_step_ui(self, step_idx):
        """
        현재 인덱스에 해당하는 단계만 주인공으로 만들고,
        나머지는 과거/미래 상관없이 모두 배경으로 보냅니다.
        """
        for i in range(len(self.step_circles)):
            # 현재 활성화된 단계 (Accent Color)
            if i == step_idx:
                circle_style = f"""
                    background: {ACCENT};
                    border: 2px solid {ACCENT_LIGHT};
                    color: white;
                """
                label_style = f"color: {TEXT_PRIMARY}; font-weight: bold;"

            # 그 외 모든 단계 (Muted Color)
            else:
                circle_style = f"""
                    background: {BG_SECONDARY};
                    border: 2px solid {BORDER};
                    color: {TEXT_MUTED};
                """
                label_style = f"color: {TEXT_MUTED}; font-weight: normal;"

            # 스타일 적용
            self.step_circles[i].setStyleSheet(circle_style + "border-radius: 14px; font-weight: bold;")
            self.step_labels[i].setStyleSheet(label_style + "font-size: 11px;")

    def _make_table(self, headers):
        """
        EqualSpacingTable 을 사용해 생성:
          - 모든 컬럼 Equal width (Stretch 고정)
          - col_padding=10 으로 셀 간격 기본 설정
          - hscroll_handle=50 으로 가로 스크롤 핸들 짧게 고정
        """
        t = EqualSpacingTable(
            parent=self,
            row_height=28,
            col_padding=10,
            hscroll_handle=50,
        )
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        return t

    def _reset_dashboard(self):
        self.result_table.setSortingEnabled(False)
        self.result_table.setRowCount(0)
        self._all_rows = []
        self._collected_data = []   # 메모리 데이터 초기화
        self.count_lbl.setText("0 rows")

        # 수집 결과 요약 초기화
        self.sum_total.update_value(0)
        self.sum_ok.update_value(0)
        self.sum_err.update_value(0)
        self.sum_warn.update_value(0)

        self.detail_lbl.setText("테이블에서 행을 클릭하세요.")
        self.result_table.setSortingEnabled(True)
        self._update_step_ui(0)

    def set_running(self, v: bool):
        """GlobalToolbar 에서 상태를 받아 내부 플래그만 동기화합니다."""
        self._running = v

    def _get_result_columns(self):
        """MonitorPage 에서 이동: 동적 컬럼 목록"""
        items = list(request_info["conditions"]["items"].keys())
        return [c for c in items if c not in ("root", "detail_root", "main_root", "detail")]

    # ── 실시간 수집 결과 테이블 ──────────────────────
    def add_row(self, row: dict):
        """워커 new_row 시그널 → 수집 모니터링(세션 통계 우측 패널) 용 더미 유지"""
        pass  # 세션 통계는 update_stats 로만 갱신; 결과 테이블은 _add_realtime_row 사용

    def _add_realtime_row(self, row: dict):
        """워커 new_row 시그널 → 실시간 수집 결과 테이블에 행 추가 + 메모리 데이터 적재"""
        self._all_rows.append(row)

        resp = row.get("resp_info", {})
        data = resp.get("data", [])
        if not isinstance(data, list) or not data:
            return

        # ── 테이블 표출 직전: 작업 진행 상태를 "결과물 추출(step 3)"으로 전환 ──
        self._update_step_ui(3)

        columns = self._get_result_columns()
        self.result_table.setSortingEnabled(False)

        for entry in data:
            if not isinstance(entry, dict):
                continue

            # ── 메모리에 원본 데이터 적재 (추출 시 사용) ──
            self._collected_data.append(entry)

            current_row = self.result_table.rowCount()
            self.result_table.insertRow(current_row)

            no_item = QTableWidgetItem()
            no_item.setData(Qt.ItemDataRole.DisplayRole, current_row)
            no_item.setForeground(QColor(TEXT_MUTED))
            self.result_table.setItem(current_row, 0, no_item)

            for col_idx, col_name in enumerate(columns, start=1):
                val = entry.get(col_name, "—")
                item = QTableWidgetItem()
                if isinstance(val, (int, float)):
                    item.setData(Qt.ItemDataRole.DisplayRole, val)
                else:
                    item.setText(str(val) if val is not None else "—")
                item.setForeground(QColor(TEXT_PRIMARY))
                self.result_table.setItem(current_row, col_idx, item)

        self.result_table.setSortingEnabled(True)
        self.count_lbl.setText(f"{self.result_table.rowCount()} rows")
        self._update_summary_cards()

    def _update_summary_cards(self):
        """수집 결과 요약 카드 갱신"""
        total = self.result_table.rowCount()
        ok = err = 0
        for r in range(total):
            values = []
            for c in range(1, self.result_table.columnCount()):
                item = self.result_table.item(r, c)
                values.append(item.text().strip() if item else "")
            empty = [v for v in values if v in ("", "—") or v.lower() in ("none", "null")]
            if len(empty) == len(values):
                err += 1
            else:
                ok += 1
        ok_rate = f"{ok / total * 100:.1f}%" if total else "0%"
        err_rate = f"{err / total * 100:.1f}%" if total else "0%"
        self.sum_total.update_value(total)
        self.sum_ok.update_value(ok)
        self.sum_err.update_value(err)
        self.sum_warn.update_value(ok_rate)
        # self.sum_warn.update_value(f"성공 {ok_rate} / 오류 {err_rate}")

    def _apply_filter(self):
        keyword = self.search_box.text().lower().strip()
        if not keyword:
            for r in range(self.result_table.rowCount()):
                self.result_table.setRowHidden(r, False)
            self.count_lbl.setText(f"{self.result_table.rowCount()} rows")
            return
        visible = 0
        for r in range(self.result_table.rowCount()):
            matched = any(
                self.result_table.item(r, c) and
                keyword in self.result_table.item(r, c).text().lower()
                for c in range(self.result_table.columnCount())
            )
            self.result_table.setRowHidden(r, not matched)
            if matched:
                visible += 1
        self.count_lbl.setText(f"{visible} rows")

    def _show_detail(self, item):
        row = item.row()
        columns = self._get_result_columns()
        parts = []
        VALUE_COLORS = {0: ACCENT_LIGHT, 1: TEXT_PRIMARY, 2: GREEN, 3: RED}
        for col_idx, col_name in enumerate(columns):
            cell = self.result_table.item(row, col_idx + 1)
            val = cell.text() if cell else "—"
            parts.append(
                f"<b style='color:{ACCENT_LIGHT};'>{col_name}:</b> "
                f"<span style='color:{VALUE_COLORS.get(col_idx, TEXT_MUTED)};'>{val}</span>"
            )
        self.detail_lbl.setText("<br>".join(parts))
        self.detail_lbl.setTextFormat(Qt.TextFormat.RichText)

    def update_stats(self, stats):
        """세션 통계 시그널 수신 — MonitorPage가 테이블 직접 집계로 처리하므로 pass."""
        pass

    def _open_output_settings_dialog(self):
        """출력 대상 / 상세 설정(인라인) / AUTO SAVE Dialog"""
        dlg = QDialog(self)
        dlg.setWindowTitle("추출 설정")
        dlg.setFixedWidth(500)

        dlg.setStyleSheet(f"""
            QDialog {{
                background:{BG_SECONDARY};
                border:1px solid {BORDER};
                border-radius:10px;
            }}
        """)

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(22, 18, 22, 18)
        vl.setSpacing(0)

        # ── 타이틀 ──────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.addWidget(make_label("추출 설정", TEXT_PRIMARY, 14, True))
        title_row.addStretch()
        vl.addLayout(title_row)
        vl.addSpacing(10)
        vl.addWidget(Divider())
        vl.addSpacing(14)

        # ── 출력 대상 ──────────────────────────────────────
        out_file_btn = TagButton("FILE");
        out_file_btn.setToolTip("로컬 파일로 저장 (CSV / JSON / Excel)")
        out_db_btn = TagButton("DB");
        out_db_btn.setToolTip("데이터베이스 서버로 전송")

        self._out_mode = "FILE" if self.output_info["extract"]["file"]["enabled"] else "DB"
        out_file_btn.setChecked(self._out_mode == "FILE")
        out_db_btn.setChecked(self._out_mode == "DB")

        is_file_mode = out_file_btn.isChecked
        out_mode_lbl = make_label(
            "로컬 파일 저장 모드" if is_file_mode else "DB 서버 전송 모드",
            TEXT_MUTED, 10
        )

        out_row = QHBoxLayout();
        out_row.setSpacing(8)
        out_row.addWidget(make_label("출력 대상", TEXT_SECONDARY, 12))
        out_row.addSpacing(6)
        out_row.addWidget(out_file_btn)
        out_row.addWidget(out_db_btn)
        out_row.addSpacing(10)
        out_row.addWidget(out_mode_lbl)
        out_row.addStretch()
        vl.addLayout(out_row)
        vl.addSpacing(12)

        # ── 자동 저장 ──────────────────────────────────────
        auto_save_chk = QCheckBox("Auto Save")
        auto_save_chk.setChecked(self.output_info["extract"]["auto_save"])
        auto_save_chk.setToolTip("수집 완료 시 선택된 출력 대상(FILE/DB)에 자동 저장")

        save_row = QHBoxLayout();
        save_row.setSpacing(8)
        save_row.addWidget(make_label("자동 저장", TEXT_SECONDARY, 12))
        save_row.addSpacing(6)
        save_row.addWidget(auto_save_chk)
        save_row.addStretch()
        vl.addLayout(save_row)
        vl.addSpacing(14)

        vl.addWidget(Divider())
        vl.addSpacing(14)

        # ── 상세 설정 인라인 패널 (QStackedWidget) ──────
        detail_title = make_label("상세 설정", TEXT_MUTED, 10)
        detail_title.setStyleSheet(detail_title.styleSheet() + " letter-spacing:1px;")
        vl.addWidget(detail_title)
        vl.addSpacing(10)


        stack = QStackedWidget()
        stack.setObjectName("extractStack")
        # 위젯에 바운더리 X
        stack.setStyleSheet(f"""
                    QStackedWidget#extractStack {{
                        background:{BG_PRIMARY};
                        border:1px solid {BORDER};
                        border-radius:6px;
                    }}
                    QStackedWidget#extractStack > QWidget {{
                        background:{BG_PRIMARY};
                        border:none;
                    }}
                """)

        # 위젯에 바운더리 O
        # stack.setStyleSheet(f"background:{BG_PRIMARY}; border:1px solid {BORDER}; border-radius:6px;")

        # 스택 위젯이 현재 페이지 크기에 맞춰 변화하도록 설정
        stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        # ── PAGE 0 : FILE 설정 ───────────────────────────
        file_page = QWidget()
        fp = QVBoxLayout(file_page)
        fp.setContentsMargins(14, 14, 14, 14)
        fp.setSpacing(10)

        # 경로
        path_lay = QHBoxLayout();
        path_lay.setSpacing(8)
        path_lay.addWidget(make_label("경로", TEXT_SECONDARY, 12))
        path_edit = QLineEdit(self.output_info["extract"]["file"]["file_path"])
        # path_edit.setPlaceholderText("저장 폴더를 선택하세요...")
        path_edit.setReadOnly(True)
        path_lay.addWidget(path_edit, 1)
        browse_btn = outline_btn("Browse")
        browse_btn.setFixedWidth(72)

        def _browse():
            folder = QFileDialog.getExistingDirectory(dlg, "저장 폴더 선택", path_edit.text() or "")
            if folder:
                path_edit.setText(folder)

        browse_btn.clicked.connect(_browse)
        path_lay.addWidget(browse_btn)
        fp.addLayout(path_lay)

        # 파일명
        file_nm_lay = QHBoxLayout();
        file_nm_lay.setSpacing(10)
        file_nm_lay.addWidget(make_label("파일명", TEXT_SECONDARY, 12))
        file_nm = QLineEdit();
        file_nm.setText(self.output_info["extract"]["file"]["file_name"])
        file_nm_lay.addWidget(file_nm)
        fp.addLayout(file_nm_lay)

        # 형식
        opt_lay = QHBoxLayout();
        opt_lay.setSpacing(10)

        opt_lay.addWidget(make_label("형식", TEXT_SECONDARY, 12))
        fmt_combo = QComboBox()
        fmt_combo.addItems(["CSV", "JSON", "Excel"]);
        fmt_combo.setCurrentText(self.output_info["extract"]["file"]["file_format"])
        opt_lay.addWidget(fmt_combo)
        opt_lay.addSpacing(10)

        # 형식에 따른 인코딩·구분자 표시/숨김
        def _on_fmt_changed(fmt_text: str):
            is_csv = (fmt_text == "CSV")
            enc_widget.setVisible(is_csv)
            delim_widget.setVisible(is_csv)
            update_dialog_size()

        # 인코딩 (CSV일 때만 표시)
        enc_widget = QWidget()
        enc_lay = QHBoxLayout(enc_widget)
        enc_lay.setContentsMargins(0, 0, 0, 0)
        enc_lay.setSpacing(10)

        enc_combo = QComboBox()
        enc_combo.addItems(["UTF-8", "UTF-8 BOM", "CP949 (EUC-KR)"]);
        enc_combo.setCurrentText(self.output_info["extract"]["file"]["file_encoding"])
        enc_lay.addWidget(make_label("인코딩", TEXT_SECONDARY, 12))
        enc_lay.addWidget(enc_combo)
        opt_lay.addWidget(enc_widget)
        opt_lay.addSpacing(10)

        # 구분자 (CSV일 때만 표시)
        delim_widget = QWidget()
        delim_lay = QHBoxLayout(delim_widget)
        delim_lay.setContentsMargins(0, 0, 0, 0)
        delim_lay.setSpacing(10)
        csv_delimeter = QLineEdit();
        csv_delimeter.setText(self.output_info["extract"]["file"]["file_delimiter"])
        delim_lay.addWidget(make_label("구분자", TEXT_SECONDARY, 12))
        delim_lay.addWidget(csv_delimeter)
        opt_lay.addWidget(delim_widget)
        opt_lay.addStretch()
        fp.addLayout(opt_lay)

        # 저장 후 폴더 열기
        open_path_chk = QCheckBox("저장 완료 후 폴더 열기")
        open_path_chk.setChecked(self.output_info["extract"]["file"]["is_open_save_path"])
        open_path_chk.setToolTip("저장 완료 시 지정 경로를 파일 탐색기로 자동으로 엽니다")
        fp.addWidget(open_path_chk)

        stack.addWidget(file_page)  # index 0

        # ── PAGE 1 : DB 설정 ────────────────────────────
        db_page = QWidget()
        dp = QVBoxLayout(db_page)
        dp.setContentsMargins(14, 14, 14, 14)
        dp.setSpacing(8)

        def _lbl(t):
            return make_label(t, TEXT_SECONDARY, 11)

        def _inp(txt="", ph=""):
            e = QLineEdit(txt);
            e.setPlaceholderText(ph);
            return e

        DB_PORTS = {"MySQL": "3306", "PostgreSQL": "5432", "MongoDB": "27017"}

        grid = QGridLayout();
        grid.setSpacing(8);
        grid.setColumnStretch(1, 1)

        _db_type = QComboBox();
        _db_type.addItems(["MySQL", "PostgreSQL", "MongoDB"]);
        _db_type.setCurrentText(self.output_info["extract"]["db"]["db_env"])
        _db_host = _inp(txt=self.output_info["extract"]["db"]["host"])
        _db_port = _inp(txt=self.output_info["extract"]["db"]["port"])
        _db_name = _inp(self.output_info["extract"]["db"]["database"])
        _db_schema = _inp(self.output_info["extract"]["db"]["schema"])
        _db_user = _inp(self.output_info["extract"]["db"]["user"])
        _db_pw = _inp(self.output_info["extract"]["db"]["password"]); _db_pw.setEchoMode(QLineEdit.EchoMode.Password)
        _db_data = _inp(self.output_info["extract"]["db"]["save_data_nm"])

        for row_i, (label, widget) in enumerate([
            ("DB Type", _db_type), ("HOST", _db_host), ("PORT", _db_port),
            ("DB Name", _db_name), ("SCHEMA", _db_schema),
            ("USER", _db_user), ("PASSWORD", _db_pw), ("DATA Name", _db_data),
        ]):
            grid.addWidget(_lbl(label), row_i, 0)
            grid.addWidget(widget, row_i, 1)

        _db_type.currentTextChanged.connect(lambda t: _db_port.setText(DB_PORTS.get(t, "")))
        dp.addLayout(grid)

        # 연결 테스트
        test_row = QHBoxLayout();
        test_row.setSpacing(10)
        test_btn = outline_btn("TEST CONNECTION")
        test_result_lbl = make_label("", TEXT_MUTED, 11)

        def _test_conn():
            host = _db_host.text().strip() or "localhost"
            try:
                port = int(_db_port.text().strip())
            except ValueError:
                test_result_lbl.setText("⚠ 포트 번호가 올바르지 않습니다")
                test_result_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;");
                return
            test_result_lbl.setText("연결 중...")
            test_result_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
            QApplication.processEvents()
            info = {
                "db_env": _db_type.currentText(), "host": host, "port": str(port),
                "database": _db_name.text().strip(),
                "schema": _db_schema.text().strip(),
                "user": _db_user.text().strip(),
                "password": _db_pw.text(),
                "save_data_nm": _db_data.text().strip()
            }
            try:
                ok = db_conn._check_db_connect_info(info)
                if ok:
                    test_result_lbl.setText(f"✅ {host}:{port} 연결 성공")
                    test_result_lbl.setStyleSheet(f"color:{GREEN}; font-size:11px;")
                else:
                    test_result_lbl.setText("❌ 연결 실패: 접속 정보를 확인하세요")
                    test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
            except ImportError:
                try:
                    with socket.create_connection((host, port), timeout=3):
                        test_result_lbl.setText(f"✅ {host}:{port} 소켓 연결 성공 (드라이버 미설치)")
                        test_result_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;")
                except OSError as e:
                    test_result_lbl.setText(f"❌ 연결 실패: {e}")
                    test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
            except Exception as e:
                test_result_lbl.setText(f"❌ 연결 실패: {e}")
                test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")

        test_btn.clicked.connect(_test_conn)
        test_row.addWidget(test_btn);
        test_row.addWidget(test_result_lbl);
        test_row.addStretch()
        dp.addLayout(test_row)

        stack.addWidget(db_page)  # index 1

        # ── 초기 페이지 선택 & 버튼 토글 연동 ──────────
        stack.setCurrentIndex(0 if is_file_mode() else 1)

        def update_dialog_size():
            """페이지 전환 후 다이얼로그 크기를 유동적으로 재조정"""
            # 1. 현재 스택 위젯의 높이를 현재 페이지에 맞춤
            current_page = stack.currentWidget()
            if current_page:
                current_page.layout().activate()  # 내부 레이아웃 즉시 갱신
                hint_height = current_page.layout().sizeHint().height()
                stack.setFixedHeight(hint_height)

            # 2. 다이얼로그 전체 크기 재계산
            # 즉시 레이아웃을 업데이트하지 않으면 이전 크기를 기억하므로 아래 과정 필요
            dlg.layout().activate()
            dlg.adjustSize()

        def _on_file_clicked():
            self._out_mode = "FILE"
            out_mode_lbl.setText("로컬 파일 저장 모드")
            out_db_btn.setChecked(False)
            stack.setCurrentIndex(0)
            stack.setMinimumHeight(0)
            stack.setMaximumHeight(16777215)
            update_dialog_size()

        def _on_db_clicked():
            self._out_mode = "DB"
            out_mode_lbl.setText("DB 서버 전송 모드")
            out_file_btn.setChecked(False)
            stack.setCurrentIndex(1)
            stack.setMinimumHeight(0)
            stack.setMaximumHeight(16777215)
            update_dialog_size()

        out_file_btn.clicked.connect(_on_file_clicked)
        out_db_btn.clicked.connect(_on_db_clicked)

        # 형식 콤보 시그널 연결 및 초기 상태 적용 (update_dialog_size 정의 이후)
        fmt_combo.currentTextChanged.connect(_on_fmt_changed)
        _on_fmt_changed(fmt_combo.currentText())

        vl.addWidget(stack)
        vl.addSpacing(16)
        vl.addWidget(Divider())
        vl.addSpacing(12)

        # ── 하단 버튼 행 ────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        def _apply_file():

            is_auto_save_chk = auto_save_chk.isChecked()
            self.output_info["extract"]["auto_save"] = is_auto_save_chk

            if self._out_mode == "FILE":
                file_path = utility.update_slash(os.path.normpath(path_edit.text()), False)
                file_name = utility.update_empty_value(file_nm.text())
                file_format = utility.update_empty_value(fmt_combo.currentText())
                file_encoding = utility.update_empty_value(enc_combo.currentText())
                file_delimeter = utility.update_empty_value(csv_delimeter.text())
                is_open_save_path = open_path_chk.isChecked()

                self.output_info["extract"]["db"] = customized_settings.get_output_settings()["extract"]["db"]
                self.output_info["extract"]["file"]["enabled"] = True
                self.output_info["extract"]["file"]["file_path"] = file_path
                self.output_info["extract"]["file"]["file_name"] = file_name
                self.output_info["extract"]["file"]["file_format"] = file_format
                self.output_info["extract"]["file"]["file_encoding"] = file_encoding
                self.output_info["extract"]["file"]["file_delimiter"] = file_delimeter
                self.output_info["extract"]["file"]["is_open_save_path"] = is_open_save_path

            elif self._out_mode == "DB":

                db_env = utility.update_empty_value(_db_type.currentText())
                db_host = utility.update_empty_value(_db_host.text())
                db_port = utility.update_empty_value(_db_port.text())
                db_schema = utility.update_empty_value(_db_schema.text())
                db_name = utility.update_empty_value(_db_name.text())
                db_user = utility.update_empty_value(_db_user.text())
                db_pass = utility.update_empty_value(_db_pw.text())
                save_data_nm = utility.update_empty_value(_db_data.text())

                self.output_info["extract"]["file"] = customized_settings.get_output_settings()["extract"]["file"]
                self.output_info["extract"]["file"]["enabled"] = False
                self.output_info["extract"]["db"]["enabled"] = True
                self.output_info["extract"]["db"]["db_env"] = db_env
                self.output_info["extract"]["db"]["host"] = db_host
                self.output_info["extract"]["db"]["port"] = db_port
                self.output_info["extract"]["db"]["schema"] = db_schema
                self.output_info["extract"]["db"]["database"] = db_name
                self.output_info["extract"]["db"]["user"] = db_user
                self.output_info["extract"]["db"]["password"] = db_pass
                self.output_info["extract"]["db"]["save_data_nm"] = save_data_nm

            dlg.accept()

        apply_btn = action_btn("적용");
        apply_btn.clicked.connect(_apply_file)
        cancel_btn = outline_btn("취소");
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(apply_btn);
        btn_row.addWidget(cancel_btn)
        vl.addLayout(btn_row)

        update_dialog_size()
        dlg.adjustSize()
        dlg.exec()

    def _extract_result_table(self, task: dict = None):
        """메모리(_collected_data)에 보관된 수집 데이터를 FILE 또는 DB로 추출"""

        # ── 메모리 데이터 유효성 검사 ──────────────────
        if not self._collected_data:
            QMessageBox.warning(self, "추출 불가", "메모리에 수집된 데이터가 없습니다.\n수집을 먼저 실행해 주세요.")
            return

        data = self._collected_data   # 메모리 데이터 참조
        headers = list(data[0].keys())

        try:

            if self.output_info["extract"]["file"]["enabled"] is True:

                file_path = self.output_info["extract"]["file"]["file_path"]
                file_name = self.output_info["extract"]["file"]["file_name"]
                file_format = self.output_info["extract"]["file"]["file_format"]

                if file_format == "CSV":

                    delimiter = self.output_info["extract"]["file"]["file_delimiter"]

                    # 최종 파일명
                    final_file_name = file_name

                    # 파일 중복 체크
                    if os.path.exists(f"{file_path}\\{file_name}.{file_format}"):

                        # 동일 파일명 존재 시, 파일명에 번호를 붙여 파일명 생성
                        count = 1
                        while True:
                            # 파일명(1).csv, 파일명(2).csv 형태로 경로 생성
                            new_file_name = f"{file_name} ({count})"
                            if not os.path.exists(f"{file_path}\\{new_file_name}.{file_format}"):
                                break
                            count += 1

                        final_file_name = new_file_name

                    with open(f"{file_path}\\{final_file_name}.csv", mode='w', encoding='utf-8-sig', newline='') as f:

                        # delimiter 인자에 원하는 구분자를 넣으세요 (예: ',', '\t', '|')
                        writer = csv.DictWriter(f, fieldnames=headers, delimiter=delimiter)

                        # 4. 헤더와 데이터 쓰기
                        writer.writeheader()
                        writer.writerows(data)

                elif file_format == "JSON":
                    # 파일 중복 체크 및 사용자 확인
                    if os.path.exists(f"{file_path}\\{file_name}.{file_format}"):
                        reply = QMessageBox.question(
                            self,
                            '덮어쓰기 확인',
                            f"'{file_name}.{file_format}' 파일이 이미 존재합니다.\n덮어쓰시겠습니까?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No
                        )

                        # '아니오'를 누르면 즉시 함수 종료 (프로세스 중단)
                        if reply == QMessageBox.StandardButton.No:
                            # self._update_log(f"⚠️ 사용자에 의해 파일 저장이 취소되었습니다.")
                            return

                    with open(f"{file_path}\\{file_name}.json", 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)

                # QMessageBox.information(self, "FILE 저장 완료", f"{len(data)}건 저장")

                # 저장 파일 폴더 열기
                is_open_save_path = self.output_info["extract"]["file"]["is_open_save_path"]
                if file_path and is_open_save_path:
                    # self._update_log(f"📂 저장 폴더를 엽니다: {file_path}")
                    os.startfile(file_path)

            elif self.output_info["extract"]["db"]["enabled"] is True:

                db_info = self.output_info["extract"]["db"]

                try:
                    is_exist = db_conn._check_db_table_exists(db_info)
                    save_mode = 'append'  # 기본값

                    if is_exist:
                        # 2. 커스텀 3버튼 메시지 박스 생성
                        msg_box = QMessageBox(self)
                        msg_box.setWindowTitle("DB 데이터 처리 선택")
                        msg_box.setText(f"'{db_info["save_data_nm"]}' 테이블이 이미 존재합니다.\n어떻게 처리하시겠습니까?")
                        msg_box.setIcon(QMessageBox.Icon.Question)

                        # 버튼 추가
                        btn_overwrite = msg_box.addButton("덮어쓰기(새로 생성)", QMessageBox.ButtonRole.DestructiveRole)
                        btn_append = msg_box.addButton("추가 적재(이어 쓰기)", QMessageBox.ButtonRole.AcceptRole)
                        btn_cancel = msg_box.addButton("취소", QMessageBox.ButtonRole.RejectRole)

                        msg_box.setDefaultButton(btn_append)
                        msg_box.exec()

                        # 3. 사용자 선택 결과 처리
                        clicked_button = msg_box.clickedButton()

                        if clicked_button == btn_overwrite:
                            save_mode = 'overwrite'
                        elif clicked_button == btn_append:
                            save_mode = 'append'
                        else:
                            self._update_log("⚠️ 사용자가 DB 저장을 취소했습니다.")
                            return  # 프로세스 종료

                    db_conn.save_db(db_info, data, mode=save_mode)
                    mode_str = "덮어쓰기" if save_mode == 'overwrite' else "추가 적재"
                    # QMessageBox.information(self, "DB 저장 완료", f"[{mode_str}] 완료: {len(data)}건 저장")

                except Exception as e:
                    # DB 에러 상세 분석 및 알림
                    QMessageBox.critical(self, "DB 저장 실패", f"DB 접속 및 로그인 정보가 올바르지 않습니다.\n\n[시스템 에러 내용]\n{str(e)}")

        except Exception as e:
            # self._update_log(f"❌ 저장 실패: {str(e)}")
            QMessageBox.critical(self, "추출 오류", str(e))

# ══════════════════════════════════════════════════════
#  MONITOR PAGE
# ══════════════════════════════════════════════════════
class MonitorPage(QWidget):
    def __init__(self):
        super().__init__()
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body);
        bl.setContentsMargins(14, 14, 14, 14);
        bl.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── 세션 통계 ────────────────
        stw, stl = card_widget("세션 통계")
        sg = QHBoxLayout();
        sg.setSpacing(10)
        self.s_total = StatCard("요청 완료", "0")
        self.s_err = StatCard("오류", "0", RED)
        self.s_pages = StatCard("총 수집 항목", "0", ACCENT_LIGHT)
        self.s_speed = StatCard("평균 응답", "—", GREEN)
        for card in [self.s_total, self.s_err, self.s_pages, self.s_speed]:
            card.setStyleSheet(f"background:{BG_PRIMARY}; border-radius:6px; border:1px solid {BORDER};")
            sg.addWidget(card, 1)
        stl.addLayout(sg)
        bl.addWidget(stw)

        # ── 수집 모니터링 테이블 (대시보드에서 이동) ───────────────
        tcw, tc = card_widget("수집 모니터링")

        tbl_ctrl = QHBoxLayout();
        tbl_ctrl.addStretch()
        self.row_count_lbl = QLabel("0 rows")
        self.row_count_lbl.setStyleSheet(
            f"color:{ACCENT_LIGHT}; background:{BG_HOVER}; padding:2px 8px; border-radius:10px; font-size:11px;")
        tbl_ctrl.addWidget(self.row_count_lbl)
        tbl_ctrl.addSpacing(10)
        exp_csv = outline_btn("내보내기");
        exp_csv.clicked.connect(self._export_csv)
        tbl_ctrl.addWidget(exp_csv)
        tc.addLayout(tbl_ctrl)

        self.table = EqualSpacingTable(parent=self, row_height=28, col_padding=10, hscroll_handle=50)
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(["NO", "URL", "STATUS", "IP_ADDRESS", "USER-AGENT", "COOKIES", "LATENCY(PURE)", "LATENCY(TOTAL)", "JOB_NAME"])
        tc.addWidget(self.table)
        bl.addWidget(tcw, 1)


    def add_row(self, row: dict):
        """워커 new_row → 수집 모니터링 테이블 행 추가 (누적)"""
        if not row or "resp_info" not in row:
            return
        resp_info = row["resp_info"]
        data = resp_info.get("data")
        if not data or isinstance(data, dict):
            return

        target_url = resp_info["url"]

        self.table.setSortingEnabled(False)
        current_row = self.table.rowCount()
        self.table.insertRow(current_row)

        STATUS_COLOR = {"200": GREEN, "404": RED, "429": AMBER, "500": RED, "301": BLUE}
        vals = [
            current_row,
            target_url,
            resp_info["status"],
            resp_info["ip_address"],
            resp_info["user_agents"],
            resp_info["cookies"],
            resp_info["pure_latency"],
            resp_info["total_latency"],
            row["job_name"],
        ]
        colors = [
            TEXT_MUTED,
            TEXT_MUTED,
            STATUS_COLOR.get(str(resp_info["status"]), TEXT_SECONDARY),
            TEXT_PRIMARY,
            TEXT_PRIMARY,
            TEXT_PRIMARY,
            TEXT_PRIMARY,
            ACCENT_LIGHT,
            TEXT_MUTED,
        ]
        for col, (val, color) in enumerate(zip(vals, colors)):
            item = QTableWidgetItem()
            if isinstance(val, (int, float)):
                item.setData(Qt.ItemDataRole.DisplayRole, val)
            else:
                item.setText(str(val))
            item.setForeground(QColor(color))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(current_row, col, item)

        self.table.setSortingEnabled(True)
        self.row_count_lbl.setText(f"{self.table.rowCount()} rows")
        self._refresh_session_stats()

    def _refresh_session_stats(self):
        """수집 모니터링 테이블에 쌓인 데이터를 직접 집계해 세션 통계 카드를 갱신합니다.
        - 총 수집 항목 : 테이블 전체 행 수
        - 요청 완료    : STATUS_COLOR 기준 RED가 아닌 행 수
        - 오류         : STATUS_COLOR 기준 RED인 행 수 (404, 500 등)
        - 평균 응답    : LATENCY(PURE) 열 값들의 평균
        """
        ERROR_STATUSES = {"404", "500", "503", "502", "429"}  # RED로 표시되는 상태 코드
        total_rows = self.table.rowCount()
        errors = 0
        latencies = []

        for r in range(total_rows):
            # col 2: STATUS
            status_item = self.table.item(r, 2)
            if status_item:
                status_val = status_item.text().strip()
                if status_val in ERROR_STATUSES:
                    errors += 1
            # col 6: LATENCY(PURE)
            lat_item = self.table.item(r, 6)
            if lat_item:
                try:
                    latencies.append(float(lat_item.text()))
                except (ValueError, TypeError):
                    pass

        completed = total_rows - errors
        avg_latency = f"{sum(latencies) / len(latencies):.2f}s" if latencies else "—"

        self.s_total.update_value(completed)
        self.s_err.update_value(errors)
        self.s_pages.update_value(total_rows)
        self.s_speed.update_value(avg_latency)

    def update_stats(self, stats):
        """워커 stats_update 시그널 수신 — 테이블 기반 집계로 대체되므로 pass."""
        pass  # 세션 통계는 _refresh_session_stats()가 테이블 직접 집계로 처리

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "CSV 저장", "crawl_monitor.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["NO", "URL", "STATUS", "IP_ADDRESS", "USER-AGENTS", "COOKIES", "LATENCY(PURE)", "LATENCY(TOTAL)", "JOB_NAME"])
            # w.writerow(["NO", "URL", "STATUS", "IP_ADDRESS", "LATENCY(PURE)", "LATENCY(TOTAL)", "JOB_NAME"])
            for r in range(self.table.rowCount()):
                w.writerow([
                    self.table.item(r, c).text() if self.table.item(r, c) else ""
                    for c in range(7)
                ])
        QMessageBox.information(self, "완료", f"저장 완료:\n{path}")



    def _reset_monitor_page(self):
        """중지 또는 수집 시작 시 호출 — 테이블과 세션 통계 카드를 모두 초기화합니다."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setSortingEnabled(True)
        self.row_count_lbl.setText("0 rows")

        # 세션 통계 카드 초기화
        self.s_total.update_value(0)
        self.s_err.update_value(0)
        self.s_pages.update_value(0)
        self.s_speed.update_value("—")


# ══════════════════════════════════════════════════════
#  MINI CHART WIDGETS
# ══════════════════════════════════════════════════════
class BarChart(QWidget):
    """레이블 + 값 배열을 받아 수직 막대 차트를 그림"""

    def __init__(self, labels=None, values=None, color=ACCENT, parent=None):
        super().__init__(parent)
        self.labels = labels or []
        self.values = values or []
        self.color = QColor(color)
        self.setMinimumHeight(160)

    def set_data(self, labels, values, color=None):
        self.labels = labels
        self.values = values
        if color: self.color = QColor(color)
        self.update()

    def paintEvent(self, e):
        if not self.values: return
        p = QPainter(self);
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 40, 10, 10, 28
        chart_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b

        max_v = max(self.values) or 1
        n = len(self.values)
        bar_w = max(4, chart_w // n - 4)

        # grid lines
        p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))
        for i in range(1, 5):
            y = pad_t + chart_h - int(chart_h * i / 4)
            p.drawLine(pad_l, y, W - pad_r, y)
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 8))
            p.drawText(0, y + 4, pad_l - 4, 14, Qt.AlignmentFlag.AlignRight,
                       str(int(max_v * i / 4)))
            p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))

        # bars + labels
        for i, (lbl, val) in enumerate(zip(self.labels, self.values)):
            x = pad_l + i * (chart_w // n) + (chart_w // n - bar_w) // 2
            bar_h = int(chart_h * val / max_v)
            y = pad_t + chart_h - bar_h

            grad = QLinearGradient(x, y, x, y + bar_h)
            grad.setColorAt(0, self.color.lighter(130))
            grad.setColorAt(1, self.color)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(x, y, bar_w, bar_h, 3, 3)

            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 8))
            p.drawText(x - 4, H - pad_b + 4, bar_w + 8, 20,
                       Qt.AlignmentFlag.AlignCenter, str(lbl))

            # value on top
            p.setPen(QColor(TEXT_SECONDARY))
            p.setFont(QFont("Consolas", 8))
            p.drawText(x - 4, max(y - 14, 0), bar_w + 8, 14,
                       Qt.AlignmentFlag.AlignCenter, str(val))

        p.end()


class LineChart(QWidget):
    """시계열 선 그래프"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.datasets = []  # list of (label, values, color)
        self.x_labels = []
        self.setMinimumHeight(160)

    def set_data(self, x_labels, datasets):
        self.x_labels = x_labels
        self.datasets = datasets
        self.update()

    def paintEvent(self, e):
        if not self.datasets: return
        p = QPainter(self);
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        pl, pr, pt, pb = 40, 10, 14, 30
        cw, ch = W - pl - pr, H - pt - pb

        all_vals = [v for _, vals, _ in self.datasets for v in vals]
        max_v = max(all_vals) if all_vals else 1

        # grid
        p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))
        for i in range(1, 5):
            y = pt + ch - int(ch * i / 4)
            p.drawLine(pl, y, W - pr, y)
            p.setPen(QColor(TEXT_MUTED))
            p.setFont(QFont("Consolas", 8))
            p.drawText(0, y - 6, pl - 4, 14, Qt.AlignmentFlag.AlignRight,
                       str(int(max_v * i / 4)))
            p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DotLine))

        n = max(len(self.x_labels), 1)
        step = cw / max(n - 1, 1)

        for label, vals, color in self.datasets:
            if not vals: continue
            qc = QColor(color)
            points = []
            for i, v in enumerate(vals):
                x = int(pl + i * step)

                if max_v == 0:
                    y = pt + ch
                else:
                    y = int(pt + ch - ch * v / max_v)
                points.append(QPoint(x, y))

            # line
            p.setPen(QPen(qc, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(len(points) - 1):
                p.drawLine(points[i], points[i + 1])

            # dots
            p.setBrush(QBrush(qc))
            p.setPen(QPen(QColor(BG_PRIMARY), 2))
            for pt2 in points:
                p.drawEllipse(pt2, 4, 4)

        # x labels
        p.setPen(QColor(TEXT_MUTED))
        p.setFont(QFont("Consolas", 8))
        for i, lbl in enumerate(self.x_labels):
            x = int(pl + i * step)
            p.drawText(x - 20, H - pb + 4, 40, 20, Qt.AlignmentFlag.AlignCenter, str(lbl))

        p.end()


class DonutChart(QWidget):
    """도넛 차트: segments = [(label, value, color)]"""

    def __init__(self, segments=None, parent=None):
        super().__init__(parent)
        self.segments = segments or []
        self.setMinimumSize(140, 140)
        self.setMaximumSize(180, 180)

    def set_data(self, segments):
        self.segments = segments
        self.update()

    def paintEvent(self, e):
        # [수정] 데이터가 없으면 아무것도 그리지 않고 리턴합니다.
        if not self.segments or sum(v for _, v, _ in self.segments) == 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        size = min(W, H) - 16
        x = (W - size) // 2
        y = (H - size) // 2

        total = sum(v for _, v, _ in self.segments)
        start = -90 * 16

        # 1. 파이 조각 그리기
        for label, val, color in self.segments:
            span = int(360 * 16 * val / total)
            p.setBrush(QBrush(QColor(color)))
            p.setPen(QPen(QColor(BG_PRIMARY), 3))
            p.drawPie(x, y, size, size, start, span)
            start += span

        # 2. 가운데 구멍 뚫기 (Donut 형태)
        hole = int(size * 0.52)
        hx = (W - hole) // 2
        hy = (H - hole) // 2
        p.setBrush(QBrush(QColor(BG_SECONDARY)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(hx, hy, hole, hole)

        # 3. 센터 텍스트 (총합) 표시
        p.setPen(QColor(TEXT_PRIMARY))
        p.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        p.drawText(0, 0, W, H, Qt.AlignmentFlag.AlignCenter, str(total))

        p.end()


# ══════════════════════════════════════════════════════
#  STATISTICS PAGE
# ══════════════════════════════════════════════════════
class StatisticsPage(QWidget):
    def __init__(self):
        super().__init__()
        self._build()
        # auto-refresh every 3 s
        self._timer = QTimer();
        self._timer.timeout.connect(self.reload)
        self._timer.start(3000)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea();
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body);
        bl.setContentsMargins(14, 14, 14, 14);
        bl.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── Row 1: KPI cards ──────────────────────
        kpi_row = QHBoxLayout();
        kpi_row.setSpacing(10)
        self.kpi_total = StatCard("총 수집 항목", "0")
        self.kpi_success = StatCard("성공률", "0%", GREEN)
        self.kpi_avg_t = StatCard("평균 응답", "—", BLUE)
        self.kpi_sessions = StatCard("완료 세션", "0", PURPLE)
        for kpi in [self.kpi_total, self.kpi_success, self.kpi_avg_t, self.kpi_sessions]:
            kpi.setStyleSheet(f"background:{BG_SECONDARY}; border-radius:6px; border:1px solid {BORDER};")
            kpi_row.addWidget(kpi, 1)
        bl.addLayout(kpi_row)

        # ── Row 2: Status pie + bar chart ─────────
        row2 = QHBoxLayout();
        row2.setSpacing(10)

        # Status donut
        sw, sl = card_widget("상태 코드 분포")
        inner = QHBoxLayout();
        inner.setSpacing(16)
        self.donut = DonutChart()
        inner.addWidget(self.donut)
        legend_w = QWidget();
        legend_w.setStyleSheet("background:transparent;")
        self.legend_lay = QVBoxLayout(legend_w);
        self.legend_lay.setSpacing(6);
        self.legend_lay.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(legend_w);
        inner.addStretch()
        sl.addLayout(inner)
        row2.addWidget(sw, 1)

        # Response time histogram (24 buckets)
        rw2, rl2 = card_widget("응답 시간 분포 (s)")
        self.resp_bar = BarChart(color=BLUE)
        rl2.addWidget(self.resp_bar)
        row2.addWidget(rw2, 2)
        bl.addLayout(row2)

        # ── Row 3: Hourly trend line ───────────────
        lw, ll = card_widget("시간대별 수집량 추이")
        self.trend_line = LineChart()
        self.trend_line.setMinimumHeight(180)
        ll.addWidget(self.trend_line)
        bl.addWidget(lw)

        # ── Row 4: Session history table ──────────
        tw, tl = card_widget("세션 이력")
        self.session_table = EqualSpacingTable(
            parent=self,
            row_height=30,
            col_padding=10,
            hscroll_handle=50,
        )
        self.session_table.setColumnCount(9)
        self.session_table.setHorizontalHeaderLabels(
            ["작업명", "URL", "총 항목", "성공", "오류", "평균 응답", "소요 시간", "시작 시각", "완료 시각"])
        tl.addWidget(self.session_table)
        bl.addWidget(tw)

    # ── data ───────────────────────────────────
    def reload(self):
        rows = store.get_url_maps()
        sessions = store.get_sessions()
        if not rows and not sessions:
            return

        total = len(rows)  # URL_LIST
        ok = sum(1 for r in rows if str(r["status_code"]) == "200")  # URL_LIST 중 RESPONSE = 200인 것
        rate = f"{ok / total * 100:.1f}%" if total else "0%"
        times = [r["pure_latency"] for r in rows if
                 isinstance(r["pure_latency"], float)]  # URL_LIST의 각각 URL의 순수 레이턴시
        avg_t = f"{sum(times) / len(times):.2f}s" if times else "—"

        self.kpi_total.update_value(total)
        self.kpi_success.update_value(rate)
        self.kpi_avg_t.update_value(avg_t)
        self.kpi_sessions.update_value(len(sessions))

        # Donut ( 통계 분석 - 상태 코드 분포 )
        status_cnt = defaultdict(int)
        for r in rows: status_cnt[str(r["status_code"])] += 1
        # ── 수정: COLOR_MAP 키를 str 로 통일하여 단일 응답 시 Gray 오류 해소 ──
        COLOR_MAP = {"200": GREEN, "301": BLUE, "404": AMBER, "429": PURPLE, "500": RED}
        segments = [(k, v, COLOR_MAP.get(str(k), ACCENT_LIGHT)) for k, v in sorted(status_cnt.items())]
        self.donut.set_data(segments)
        # rebuild legend
        for i in reversed(range(self.legend_lay.count())):
            w = self.legend_lay.itemAt(i).widget()
            if w: w.deleteLater()
        for k, v, color in segments:
            row_w = QWidget();
            row_w.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row_w);
            rl.setContentsMargins(0, 0, 0, 0);
            rl.setSpacing(6)
            dot = QLabel("●");
            dot.setStyleSheet(f"color:{color}; font-size:12px;")
            txt = make_label(f"{k}  {v}", TEXT_SECONDARY, 11)
            rl.addWidget(dot);
            rl.addWidget(txt);
            rl.addStretch()
            self.legend_lay.addWidget(row_w)
        self.legend_lay.addStretch()

        # Response bar (bucket 0.2 intervals) ( 통계 분석 - 응답 시간 분포  )
        if times:
            buckets = defaultdict(int)
            for t in times:
                b = round(round(t / 0.2) * 0.2, 1)
                buckets[b] += 1
            sorted_b = sorted(buckets.items())
            labels = [str(k) for k, _ in sorted_b]
            values = [v for _, v in sorted_b]
            self.resp_bar.set_data(labels, values, BLUE)

        # Hourly trend (last 12 hours) ( 통계분석 - 시간대별 수집량 추이 )
        hour_ok = defaultdict(int)
        hour_err = defaultdict(int)
        now = datetime.now()
        for r in rows:
            try:
                ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
                diff_h = int((now - ts).total_seconds() // 3600)
                if 0 <= diff_h < 12:
                    bucket = now.hour - diff_h
                    if str(r["status_code"]) == "200":
                        hour_ok[bucket] += 1
                    else:
                        hour_err[bucket] += 1
            except:
                pass
        hours = [(now - timedelta(hours=11 - i)).hour for i in range(12)]
        ok_vals = [hour_ok.get(h, 0) for h in hours]
        err_vals = [hour_err.get(h, 0) for h in hours]
        self.trend_line.set_data(
            [f"{h:02d}h" for h in hours],
            [("성공", ok_vals, GREEN), ("오류", err_vals, RED)]
        )

        # Session table ( 통계 분석 - 세션 이력 )
        self.session_table.setSortingEnabled(False)
        self.session_table.setRowCount(0)
        for s in reversed(sessions):
            r = self.session_table.rowCount()
            self.session_table.insertRow(r)
            vals = [s["job"], s["url"], str(s["total"]), str(s["success"]),
                    str(s["errors"]), f"{s['avg_time']}s", f"{s['elapsed']}s", s["started"], s["finished"]]
            colors = [TEXT_PRIMARY, ACCENT_LIGHT, TEXT_PRIMARY, GREEN,
                      RED, BLUE, TEXT_MUTED, TEXT_MUTED, TEXT_MUTED]
            for col, (val, color) in enumerate(zip(vals, colors)):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self.session_table.setItem(r, col, item)
        self.session_table.setSortingEnabled(True)

    def _export_json(self):
        rows = store.get_rows()
        sessions = store.get_sessions()
        if not rows and not sessions:
            QMessageBox.warning(self, "경고", "저장할 데이터가 없습니다.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "리포트 저장", "report.json", "JSON (*.json)")
        if not path: return
        report = {
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sessions": sessions,
            "rows": [{k: str(v) for k, v in r.items()} for r in rows],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, "완료", f"저장 완료:\n{path}")


# ══════════════════════════════════════════════════════
#  SCHEDULER PAGE
# ══════════════════════════════════════════════════════
class SchedulerPage(QWidget):
    schedule_run = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._timers: dict[int, QTimer] = {}
        self._build()
        self._refresh_table()
        self.task = {}
        self.session_page = SessionSettingsPage()

    # ────────────────────────────────────────────────
    def _build(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea();
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body);
        bl.setContentsMargins(14, 14, 14, 14);
        bl.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── 본문(bl) 내 상단 버튼 영역 추가 ───────────────
        btn_container = QHBoxLayout()
        btn_container.addStretch()  # 왼쪽 여백을 꽉 채워 버튼을 오른쪽으로 밀어냄
        add_btn = action_btn("+ 작업 추가")
        add_btn.clicked.connect(self._show_add_panel)
        btn_container.addWidget(add_btn)
        bl.addLayout(btn_container)  # bl 레이아웃의 가장 처음에 추가됨
        # ──────────────────────────────────────────────

        # ══ Schedule Table ════════════════════════════
        tw, tl = card_widget("등록된 작업")
        self.sched_table = EqualSpacingTable(parent=self, row_height=36, col_padding=10, hscroll_handle=50)
        self.sched_table.setColumnCount(7)
        self.sched_table.setHorizontalHeaderLabels(
            ["NO", "Task Name", "URL", "Execution Time", "Next Runtime", "Status", "Action"])
        tl.addWidget(self.sched_table)
        bl.addWidget(tw, 1)

        # ── Next Task ─────────────────────────────────
        nrw, nrl = card_widget("Next Task")
        self.next_task_lbl = make_label("등록된 스케줄 없음", TEXT_MUTED, 18, False)
        self.next_task_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        nrl.addWidget(self.next_task_lbl)
        bl.addWidget(nrw)

        self._cd_timer = QTimer();
        self._cd_timer.timeout.connect(self._update_countdown)
        self._cd_timer.start(1000)

    # ── 신규 등록 Dialog ──────────────────────────
    def _show_add_panel(self):
        """새 스케줄 등록 Dialog를 띄운다."""
        dlg = QDialog(self)
        dlg.setWindowTitle("새 스케줄 등록")
        dlg.setFixedWidth(560)
        dlg.setStyleSheet(f"background:{BG_SECONDARY}; border:1px solid {BORDER};")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(0)

        # ── 공통 헬퍼 ─────────────────────────────
        def sec_label(text):
            lbl = make_label(text.upper(), TEXT_MUTED, 9)
            lbl.setStyleSheet(lbl.styleSheet() + " letter-spacing:1.5px;")
            return lbl

        def field_row(label, widget, label_w=110):
            row = QHBoxLayout();
            row.setSpacing(8)
            lw = make_label(label, TEXT_SECONDARY, 12)
            lw.setFixedWidth(label_w)
            row.addWidget(lw);
            row.addWidget(widget, 1)
            return row

        cb_style = f"""
            QComboBox {{
                background:{BG_PRIMARY}; color:{TEXT_PRIMARY};
                border:1px solid {BORDER_LIGHT}; border-radius:4px;
                padding:4px 8px; font-size:12px;
            }}
            QComboBox::drop-down {{ border:none; width:18px; }}
            QComboBox QAbstractItemView {{
                background:{BG_SECONDARY}; color:{TEXT_PRIMARY};
                border:1px solid {BORDER}; selection-background-color:{BG_HOVER};
            }}
        """

        def hms_combos():
            h = QComboBox();
            h.addItems([f"{t:02d}" for t in range(24)])
            m = QComboBox();
            m.addItems([f"{t:02d}" for t in range(60)])
            s = QComboBox();
            s.addItems([f"{t:02d}" for t in range(60)])
            hms_style = f"""
                QComboBox {{
                    background:{BG_PRIMARY}; color:{TEXT_PRIMARY};
                    border:1px solid {BORDER_LIGHT}; border-radius:4px;
                    padding:2px 4px; font-size:12px;
                }}
                QComboBox::drop-down {{ border:none; width:14px; }}
                QComboBox QAbstractItemView {{
                    background:{BG_SECONDARY}; color:{TEXT_PRIMARY};
                    border:1px solid {BORDER}; selection-background-color:{BG_HOVER};
                }}
            """
            for cb in (h, m, s):
                cb.setFixedWidth(52);
                cb.setStyleSheet(hms_style)
            return h, m, s

        def time_sep():
            lbl = make_label(":", TEXT_MUTED, 13, True);
            lbl.setFixedWidth(8)
            return lbl

        def iv_lbl(t):
            return make_label(t, TEXT_SECONDARY, 12)

        # ── 타이틀 ────────────────────────────────
        root.addWidget(make_label("새 스케줄 등록", TEXT_PRIMARY, 14, True))
        root.addSpacing(10);
        root.addWidget(Divider());
        root.addSpacing(14)

        # ── 기본 정보 ─────────────────────────────
        root.addWidget(sec_label("기본 정보"))
        root.addSpacing(8)
        self.sched_name = QLineEdit("작업명을 입력하세요.");
        self.sched_url = QLineEdit(request_info["callback_url"]);
        self.sched_url.setCursorPosition(0)  # 커서 맨 앞으로
        root.addLayout(field_row("Task Name", self.sched_name))
        root.addSpacing(6)
        root.addLayout(field_row("Target URL", self.sched_url))
        root.addSpacing(12);
        root.addWidget(Divider());
        root.addSpacing(12)

        # ── 수집 설정 ───────────────────────
        root.addWidget(sec_label("수집 설정"))
        root.addSpacing(8)
        self.sched_delay = QDoubleSpinBox();
        self.sched_delay.setRange(0.5, 10.0);
        self.sched_delay.setValue(0.5);
        self.sched_delay.setSingleStep(0.5);
        self.sched_delay.setDecimals(1);  # setDecimals : 소수점 자리 수 self.delay_spin.setSuffix("s")
        self.sched_threads = QSpinBox();
        self.sched_threads.setRange(1, 16);
        self.sched_threads.setValue(4)
        self.sched_timeout = QSpinBox();
        self.sched_timeout.setRange(1, 60);
        self.sched_timeout.setValue(10);  # self.sched_timeout.setSuffix("s")
        self.sched_retry = QSpinBox();
        self.sched_retry.setRange(0, 5);
        self.sched_retry.setValue(3)
        cs_row = QHBoxLayout();
        cs_row.setSpacing(8)
        for lbl_txt, w in [("Delay(s)", self.sched_delay), ("Thread", self.sched_threads),
                           ("Timeout(s)", self.sched_timeout), ("Retry", self.sched_retry)]:
            cs_row.addWidget(make_label(lbl_txt, TEXT_MUTED, 11));
            cs_row.addWidget(w)
        cs_row.addStretch()
        root.addLayout(cs_row)
        root.addSpacing(12);
        root.addWidget(Divider());
        root.addSpacing(12)

        # ── Save Setting ───────────────────────────
        root.addWidget(sec_label("Save Setting"))
        root.addSpacing(8)

        output_info = customized_settings.get_output_settings()

        # 출력 대상 (FILE / DB)
        self._sched_out_mode = "FILE" if output_info["extract"]["file"]["enabled"] else "DB"
        sched_out_file_btn = TagButton("FILE")
        sched_out_file_btn.setToolTip("로컬 파일로 저장 (CSV / JSON / Excel)")
        sched_out_db_btn = TagButton("DB")
        sched_out_db_btn.setToolTip("데이터베이스 서버로 전송")
        sched_out_file_btn.setChecked(self._sched_out_mode == "FILE")
        sched_out_db_btn.setChecked(self._sched_out_mode == "DB")

        sched_out_mode_lbl = make_label(
            "로컬 파일 저장 모드" if self._sched_out_mode == "FILE" else "DB 서버 전송 모드",
            TEXT_MUTED, 10
        )
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        out_row.addWidget(make_label("출력 대상", TEXT_MUTED, 11))
        out_row.addSpacing(6)
        out_row.addWidget(sched_out_file_btn)
        out_row.addWidget(sched_out_db_btn)
        out_row.addSpacing(10)
        out_row.addWidget(sched_out_mode_lbl)
        out_row.addStretch()
        root.addLayout(out_row)
        root.addSpacing(8)

        # 상세 설정 스택 (FILE / DB)
        sched_extract_stack = QStackedWidget()
        sched_extract_stack.setObjectName("schedExtractStack")
        sched_extract_stack.setStyleSheet(f"""
            QStackedWidget#schedExtractStack {{
                background:{BG_PRIMARY};
                border:1px solid {BORDER};
                border-radius:6px;
            }}
            QStackedWidget#schedExtractStack > QWidget {{
                background:{BG_PRIMARY};
                border:none;
            }}
        """)
        sched_extract_stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        # ── PAGE 0 : FILE 설정 ──────────────────────
        sched_file_page = QWidget()
        sfp = QVBoxLayout(sched_file_page)
        sfp.setContentsMargins(14, 14, 14, 14)
        sfp.setSpacing(10)

        # 경로
        sched_path_lay = QHBoxLayout()
        sched_path_lay.setSpacing(8)
        sched_path_lay.addWidget(make_label("경로", TEXT_SECONDARY, 12))
        _fp = output_info["extract"]["file"]["file_path"]
        sched_path_edit = QLineEdit(_fp if _fp else customized_settings.set_desktop_dir())
        sched_path_edit.setReadOnly(True)
        sched_path_lay.addWidget(sched_path_edit, 1)
        sched_browse_btn = outline_btn("Browse")
        sched_browse_btn.setFixedWidth(72)

        def _sched_browse():
            folder = QFileDialog.getExistingDirectory(dlg, "저장 폴더 선택", sched_path_edit.text() or "")
            if folder:
                sched_path_edit.setText(folder)

        sched_browse_btn.clicked.connect(_sched_browse)
        sched_path_lay.addWidget(sched_browse_btn)
        sfp.addLayout(sched_path_lay)

        # 파일명
        sched_fnm_lay = QHBoxLayout()
        sched_fnm_lay.setSpacing(10)
        sched_fnm_lay.addWidget(make_label("파일명", TEXT_SECONDARY, 12))
        _fn = output_info["extract"]["file"]["file_name"]
        sched_file_nm = QLineEdit(_fn if _fn else "untitled0")
        sched_fnm_lay.addWidget(sched_file_nm)
        sfp.addLayout(sched_fnm_lay)

        # 형식 / 인코딩 / 구분자
        sched_opt_lay = QHBoxLayout()
        sched_opt_lay.setSpacing(10)
        sched_opt_lay.addWidget(make_label("형식", TEXT_SECONDARY, 12))
        sched_fmt_combo = QComboBox()
        sched_fmt_combo.addItems(["CSV", "JSON", "Excel"])
        sched_fmt_combo.setCurrentText(output_info["extract"]["file"]["file_format"])
        sched_opt_lay.addWidget(sched_fmt_combo)
        sched_opt_lay.addSpacing(10)

        sched_enc_widget = QWidget()
        sched_enc_lay = QHBoxLayout(sched_enc_widget)
        sched_enc_lay.setContentsMargins(0, 0, 0, 0)
        sched_enc_lay.setSpacing(10)
        sched_enc_combo = QComboBox()
        sched_enc_combo.addItems(["UTF-8", "UTF-8 BOM", "CP949 (EUC-KR)"])
        sched_enc_combo.setCurrentText(output_info["extract"]["file"]["file_encoding"])
        sched_enc_lay.addWidget(make_label("인코딩", TEXT_SECONDARY, 12))
        sched_enc_lay.addWidget(sched_enc_combo)
        sched_opt_lay.addWidget(sched_enc_widget)
        sched_opt_lay.addSpacing(10)

        sched_delim_widget = QWidget()
        sched_delim_lay = QHBoxLayout(sched_delim_widget)
        sched_delim_lay.setContentsMargins(0, 0, 0, 0)
        sched_delim_lay.setSpacing(10)
        sched_csv_delim = QLineEdit()
        sched_csv_delim.setText(output_info["extract"]["file"]["file_delimiter"] or ",")
        sched_delim_lay.addWidget(make_label("구분자", TEXT_SECONDARY, 12))
        sched_delim_lay.addWidget(sched_csv_delim)
        sched_opt_lay.addWidget(sched_delim_widget)
        sched_opt_lay.addStretch()
        sfp.addLayout(sched_opt_lay)

        def _sched_on_fmt_changed(fmt_text: str):
            is_csv = (fmt_text == "CSV")
            sched_enc_widget.setVisible(is_csv)
            sched_delim_widget.setVisible(is_csv)

        sched_fmt_combo.currentTextChanged.connect(_sched_on_fmt_changed)
        _sched_on_fmt_changed(sched_fmt_combo.currentText())

        sched_extract_stack.addWidget(sched_file_page)  # index 0

        # ── PAGE 1 : DB 설정 ────────────────────────
        sched_db_page = QWidget()
        sdp = QVBoxLayout(sched_db_page)
        sdp.setContentsMargins(14, 14, 14, 14)
        sdp.setSpacing(8)

        def _slbl(t):
            return make_label(t, TEXT_SECONDARY, 11)

        def _sinp(txt="", ph=""):
            e = QLineEdit(txt)
            e.setPlaceholderText(ph)
            return e

        DB_PORTS_S = {"MySQL": "3306", "PostgreSQL": "5432", "MongoDB": "27017"}
        sgrid = QGridLayout()
        sgrid.setSpacing(8)
        sgrid.setColumnStretch(1, 1)

        _sdb_type = QComboBox()
        _sdb_type.addItems(["MySQL", "PostgreSQL", "MongoDB"])
        _sdb_type.setCurrentText(output_info["extract"]["db"]["db_env"])
        _sdb_host = _sinp(txt=output_info["extract"]["db"]["host"])
        _sdb_port = _sinp(txt=output_info["extract"]["db"]["port"])
        _sdb_name = _sinp(output_info["extract"]["db"]["database"])
        _sdb_schema = _sinp(output_info["extract"]["db"]["schema"])
        _sdb_user = _sinp(output_info["extract"]["db"]["user"])
        _sdb_pw = _sinp(output_info["extract"]["db"]["password"])
        _sdb_pw.setEchoMode(QLineEdit.EchoMode.Password)
        _sdb_data = _sinp(output_info["extract"]["db"]["save_data_nm"])

        for _row_i, (_label, _widget) in enumerate([
            ("DB Type", _sdb_type), ("HOST", _sdb_host), ("PORT", _sdb_port),
            ("DB Name", _sdb_name), ("SCHEMA", _sdb_schema),
            ("USER", _sdb_user), ("PASSWORD", _sdb_pw), ("DATA Name", _sdb_data),
        ]):
            sgrid.addWidget(_slbl(_label), _row_i, 0)
            sgrid.addWidget(_widget, _row_i, 1)

        _sdb_type.currentTextChanged.connect(lambda t: _sdb_port.setText(DB_PORTS_S.get(t, "")))
        sdp.addLayout(sgrid)

        # 연결 테스트
        sched_test_row = QHBoxLayout()
        sched_test_row.setSpacing(10)
        sched_test_btn = outline_btn("TEST CONNECTION")
        sched_test_result_lbl = make_label("", TEXT_MUTED, 11)

        def _sched_test_conn():
            host = _sdb_host.text().strip() or "localhost"
            try:
                port = int(_sdb_port.text().strip())
            except ValueError:
                sched_test_result_lbl.setText("⚠ 포트 번호가 올바르지 않습니다")
                sched_test_result_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;")
                return
            sched_test_result_lbl.setText("연결 중...")
            sched_test_result_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
            QApplication.processEvents()
            info = {
                "db_env": _sdb_type.currentText(), "host": host, "port": str(port),
                "database": _sdb_name.text().strip(),
                "schema": _sdb_schema.text().strip(), "user": _sdb_user.text().strip(),
                "password": _sdb_pw.text(),
                "save_data_nm": _sdb_data.text().strip() or "results",
            }
            try:
                ok = db_conn._check_db_connect_info(info)
                if ok:
                    sched_test_result_lbl.setText(f"✅ {host}:{port} 연결 성공")
                    sched_test_result_lbl.setStyleSheet(f"color:{GREEN}; font-size:11px;")
                else:
                    sched_test_result_lbl.setText("❌ 연결 실패: 접속 정보를 확인하세요")
                    sched_test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
            except ImportError:
                try:
                    with socket.create_connection((host, port), timeout=3):
                        sched_test_result_lbl.setText(f"✅ {host}:{port} 소켓 연결 성공 (드라이버 미설치)")
                        sched_test_result_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;")
                except OSError as e:
                    sched_test_result_lbl.setText(f"❌ 연결 실패: {e}")
                    sched_test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")
            except Exception as e:
                sched_test_result_lbl.setText(f"❌ 연결 실패: {e}")
                sched_test_result_lbl.setStyleSheet(f"color:{RED}; font-size:11px;")

        sched_test_btn.clicked.connect(_sched_test_conn)
        sched_test_row.addWidget(sched_test_btn)
        sched_test_row.addWidget(sched_test_result_lbl)
        sched_test_row.addStretch()
        sdp.addLayout(sched_test_row)

        sched_extract_stack.addWidget(sched_db_page)  # index 1

        # 초기 페이지 선택
        sched_extract_stack.setCurrentIndex(0 if self._sched_out_mode == "FILE" else 1)

        def _update_sched_dialog_size():
            """페이지 전환 후 다이얼로그 크기를 유동적으로 재조정"""
            current_page = sched_extract_stack.currentWidget()
            if current_page:
                current_page.layout().activate()
                hint_height = current_page.layout().sizeHint().height()
                sched_extract_stack.setFixedHeight(hint_height)
            dlg.layout().activate()
            dlg.adjustSize()

        def _sched_on_file_clicked():
            self._sched_out_mode = "FILE"
            sched_out_mode_lbl.setText("로컬 파일 저장 모드")
            sched_out_db_btn.setChecked(False)
            sched_extract_stack.setCurrentIndex(0)
            sched_extract_stack.setMinimumHeight(0)
            sched_extract_stack.setMaximumHeight(16777215)
            _update_sched_dialog_size()

        def _sched_on_db_clicked():
            self._sched_out_mode = "DB"
            sched_out_mode_lbl.setText("DB 서버 전송 모드")
            sched_out_file_btn.setChecked(False)
            sched_extract_stack.setCurrentIndex(1)
            sched_extract_stack.setMinimumHeight(0)
            sched_extract_stack.setMaximumHeight(16777215)
            _update_sched_dialog_size()

        sched_out_file_btn.clicked.connect(_sched_on_file_clicked)
        sched_out_db_btn.clicked.connect(_sched_on_db_clicked)

        # 형식 콤보 시그널 재연결 — _update_sched_dialog_size 정의 이후 적용
        sched_fmt_combo.currentTextChanged.disconnect(_sched_on_fmt_changed)
        def _sched_on_fmt_changed_with_resize(fmt_text: str):
            _sched_on_fmt_changed(fmt_text)
            _update_sched_dialog_size()
        sched_fmt_combo.currentTextChanged.connect(_sched_on_fmt_changed_with_resize)
        root.addWidget(sched_extract_stack)
        root.addSpacing(10)

        # 저장 방식 콤보
        self.sched_save_type = QComboBox()
        self.sched_save_type.addItems(["선택하세요", "새로 만들기", "덮어쓰기", "추가하기"])
        self.sched_save_type.setFixedWidth(130)
        self.sched_save_type.setStyleSheet(cb_style)
        sv_row = QHBoxLayout()
        sv_row.setSpacing(8)
        sv_row.addWidget(make_label("저장 방식", TEXT_MUTED, 11))
        sv_row.addWidget(self.sched_save_type)
        sv_row.addStretch()
        root.addLayout(sv_row)

        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        # 초기 크기 적용 (레이아웃에 추가된 이후 호출)
        _update_sched_dialog_size()

        # ── Interval ──────────────────────────────
        root.addWidget(sec_label("Interval"))
        root.addSpacing(8)

        self.sched_interval = QComboBox()
        self.sched_interval.addItems(["선택하세요", "매일", "매주", "매월", "특정 날짜"])
        self.sched_interval.setFixedWidth(120);
        self.sched_interval.setStyleSheet(cb_style)

        # 상세 컨테이너
        container_daily = QWidget()
        container_weekly = QWidget()
        container_monthly = QWidget()
        container_date = QWidget()

        # 매일
        self.d_h, self.d_m, self.d_s = hms_combos()
        dl = QHBoxLayout(container_daily);
        dl.setContentsMargins(0, 0, 0, 0);
        dl.setSpacing(6);
        dl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(self.d_h, 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(self.d_m, 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(self.d_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_daily.setVisible(False)

        # 매주
        self.w_day = QComboBox();
        self.w_day.addItems(["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"]);
        self.w_day.setFixedWidth(76);
        self.w_day.setStyleSheet(cb_style)
        self.w_h, self.w_m, self.w_s = hms_combos()
        wl = QHBoxLayout(container_weekly);
        wl.setContentsMargins(0, 0, 0, 0);
        wl.setSpacing(6);
        wl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(iv_lbl("매주"), 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(self.w_day, 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addSpacing(6)
        wl.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(self.w_h, 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(self.w_m, 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        wl.addWidget(self.w_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_weekly.setVisible(False)

        # 매월
        m_day = QComboBox();
        m_day.addItems([str(d) for d in range(1, 32)]);
        m_day.setFixedWidth(50);
        m_day.setStyleSheet(cb_style)
        self.m_h, self.m_m, self.m_s = hms_combos()
        ml = QHBoxLayout(container_monthly);
        ml.setContentsMargins(0, 0, 0, 0);
        ml.setSpacing(6);
        ml.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(iv_lbl("매월"), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(m_day, 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(iv_lbl("일"), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addSpacing(6)
        ml.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.m_h, 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.m_m, 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.m_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_monthly.setVisible(False)

        # 특정 날짜
        self.date_edit = QDateEdit();
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumDate(QDate.currentDate());
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd");
        self.date_edit.setFixedWidth(110)
        self.date_edit.setStyleSheet(f"""
            QDateEdit {{
                background:{BG_PRIMARY}; color:{TEXT_PRIMARY};
                border:1px solid {BORDER_LIGHT}; border-radius:4px; padding:4px 6px; font-size:12px;
            }}
            QDateEdit::drop-down {{
                subcontrol-origin:padding; subcontrol-position:center right;
                width:20px; border-left:1px solid {BORDER_LIGHT};
                border-radius:0 4px 4px 0; background:{BG_HOVER};
            }}
            QDateEdit::down-arrow {{
                image:none; width:0; height:0;
                border-left:4px solid transparent; border-right:4px solid transparent;
                border-top:5px solid {TEXT_SECONDARY}; margin:0 4px;
            }}
        """)
        cal = self.date_edit.calendarWidget()
        if cal:
            cal.setMinimumDate(QDate.currentDate())
            cal.setStyleSheet(f"""
                QCalendarWidget QAbstractItemView {{
                    background:{BG_SECONDARY}; color:{TEXT_PRIMARY};
                    selection-background-color:{ACCENT}; selection-color:white;
                }}
                QCalendarWidget QAbstractItemView:disabled {{ color:{TEXT_MUTED}; background:{BG_PRIMARY}; }}
                QCalendarWidget QWidget#qt_calendar_navigationbar {{ background:{BG_PRIMARY}; }}
                QCalendarWidget QToolButton {{
                    background:transparent; color:{TEXT_PRIMARY}; font-size:12px; border:none; padding:4px;
                }}
                QCalendarWidget QToolButton:hover {{ background:{BG_HOVER}; border-radius:4px; }}
                QCalendarWidget QMenu {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; }}
                QCalendarWidget QSpinBox {{ background:{BG_PRIMARY}; color:{TEXT_PRIMARY}; border:1px solid {BORDER_LIGHT}; border-radius:3px; }}
            """)
        self.dat_h, self.dat_m, self.dat_s = hms_combos()
        datl = QHBoxLayout(container_date);
        datl.setContentsMargins(0, 0, 0, 0);
        datl.setSpacing(6);
        datl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(iv_lbl("날짜"), 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(self.date_edit, 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addSpacing(6)
        datl.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(self.dat_h, 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(self.dat_m, 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        datl.addWidget(self.dat_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_date.setVisible(False)

        # 주기 선택 행
        iv_row = QHBoxLayout();
        iv_row.setSpacing(8)
        iv_row.setContentsMargins(0, 0, 0, 0)
        iv_row.addWidget(iv_lbl("주기"), 0, Qt.AlignmentFlag.AlignVCenter)
        iv_row.addWidget(self.sched_interval, 0, Qt.AlignmentFlag.AlignVCenter)
        iv_row.addStretch()

        detail_wrap = QWidget()
        detail_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        detail_lay = QHBoxLayout(detail_wrap)
        detail_lay.setContentsMargins(8, 0, 0, 0)
        detail_lay.setSpacing(6)
        for c in [container_daily, container_weekly, container_monthly, container_date]:
            detail_lay.addWidget(c, 0, Qt.AlignmentFlag.AlignVCenter)
        detail_lay.addStretch()

        # iv_row.addWidget(detail_wrap, 1, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(iv_row)
        root.setSpacing(4)
        root.addWidget(detail_wrap)

        def _on_iv_changed(idx):
            container_daily.setVisible(idx == 1)
            container_weekly.setVisible(idx == 2)
            container_monthly.setVisible(idx == 3)
            container_date.setVisible(idx == 4)

        self.sched_interval.currentIndexChanged.connect(_on_iv_changed)
        _on_iv_changed(0)

        root.addSpacing(12);
        root.addWidget(Divider());
        root.addSpacing(12)

        def _do_save():

            self._save_schedule(
                dlg=dlg,
                sched_name=self.sched_name, sched_url=self.sched_url,
                sched_delay=self.sched_delay, sched_threads=self.sched_threads,
                sched_timeout=self.sched_timeout, sched_retry=self.sched_retry,
                sched_interval=self.sched_interval,
                d_h=self.d_h, d_m=self.d_m, d_s=self.d_s,
                w_day=self.w_day, w_h=self.w_h, w_m=self.w_m, w_s=self.w_s,
                m_day=m_day, m_h=self.m_h, m_m=self.m_m, m_s=self.m_s,
                date_edit=self.date_edit, dat_h=self.dat_h, dat_m=self.dat_m, dat_s=self.dat_s,
                # Save Setting
                sched_save_type=self.sched_save_type,
                sched_out_mode=self._sched_out_mode,
                sched_path_edit=sched_path_edit,
                sched_file_nm=sched_file_nm,
                sched_fmt_combo=sched_fmt_combo,
                sched_enc_combo=sched_enc_combo,
                sched_csv_delim=sched_csv_delim,
                sched_db_type=_sdb_type,
                sched_db_host=_sdb_host,
                sched_db_port=_sdb_port,
                sched_db_name=_sdb_name,
                sched_db_schema=_sdb_schema,
                sched_db_user=_sdb_user,
                sched_db_pw=_sdb_pw,
                sched_db_data=_sdb_data,
            )

        # ── 하단 버튼 ──────────────────────────────
        btn_row = QHBoxLayout();
        btn_row.addStretch()
        save_btn = action_btn("저장"); save_btn.clicked.connect(_do_save)
        cancel_btn = outline_btn("취소"); cancel_btn.clicked.connect(dlg.reject)

        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

        dlg.adjustSize()
        dlg.exec()

    # ── 저장 ──────────────────────────────────────
    def _save_schedule(self, dlg, sched_name, sched_url,
                       sched_delay, sched_threads, sched_timeout, sched_retry,
                       sched_interval,
                       d_h, d_m, d_s, w_day, w_h, w_m, w_s,
                       m_day, m_h, m_m, m_s, date_edit, dat_h, dat_m, dat_s,
                       sched_use_proxy=None,
                       # Save Setting
                       sched_out_mode=None,
                       sched_path_edit=None, sched_file_nm=None, sched_fmt_combo=None,
                       sched_enc_combo=None, sched_csv_delim=None,
                       sched_db_type=None, sched_db_host=None, sched_db_port=None,
                       sched_db_name=None, sched_db_schema=None, sched_db_user=None,
                       sched_db_pw=None, sched_db_data=None, sched_save_type=None):
        """Dialog 위젯을 직접 받아 exec_str / run_at 계산 후 등록."""

        name_val = sched_name.text().strip()
        url_val = sched_url.text().strip()
        iv_idx = sched_interval.currentIndex()
        svtype_idx = sched_save_type.currentIndex()

        errors = []
        if not name_val: errors.append("• Task Name을 입력해 주세요.")
        if not url_val:  errors.append("• Target URL을 입력해 주세요.")
        if iv_idx == 0:  errors.append("• Interval(주기)을 선택해 주세요.")
        if svtype_idx == 0:  errors.append("• 저장 방식을 선택해 주세요.")

        # ── Proxy 사용 시 프록시 목록 비어 있으면 Alert ──
        is_proxy = sched_use_proxy.isChecked() if sched_use_proxy else False
        if is_proxy:
            proxy_list = request_info.get("net_rotate") or []
            if not proxy_list:
                errors.append("• 프록시 사용이 선택되었으나 프록시 목록이 비어 있습니다.\n"
                              "  [세션 설정] 페이지에서 프록시를 먼저 등록해 주세요.")

        # ── 중복 체크 ────────────────────────────────
        if not errors:
            # ① 작업명(Task Name) 중복 체크
            for exist in store.get_schedules():
                if exist.get("task_nm") == name_val:
                    errors.append(
                        f"• 동일한 작업명이 이미 등록되어 있습니다.\n"
                        f"  (작업명: '{name_val}')\n"
                        f"  다른 작업명을 사용해 주세요."
                    )
                    break

        if not errors:
            # ② URL + 실행 시간 AND 조건 중복 체크
            def _hms(h_cb, m_cb, s_cb):
                return int(h_cb.currentText()), int(m_cb.currentText()), int(s_cb.currentText())

            candidate = None
            if iv_idx == 1:
                h, m, s = _hms(d_h, d_m, d_s)
                candidate = f"매일 {h:02d}:{m:02d}:{s:02d}"
            elif iv_idx == 2:
                h, m, s = _hms(w_h, w_m, w_s)
                candidate = f"매주 {w_day.currentText()} {h:02d}:{m:02d}:{s:02d}"
            elif iv_idx == 3:
                h, m, s = _hms(m_h, m_m, m_s)
                candidate = f"매월 {m_day.currentText()}일 {h:02d}:{m:02d}:{s:02d}"
            elif iv_idx == 4:
                qd = date_edit.date()
                h, m, s = _hms(dat_h, dat_m, dat_s)
                candidate = f"{qd.toString('yyyy-MM-dd')} {h:02d}:{m:02d}:{s:02d}"

            if candidate:
                for exist in store.get_schedules():
                    exist_exec_str = exist.get("schedule", {}).get("exec_str", "")
                    exist_url = exist.get("url", "")
                    if exist_url == url_val and exist_exec_str == candidate:
                        errors.append(
                            f"• 동일한 URL과 실행 시간의 작업이 이미 등록되어 있습니다.\n"
                            f"  (작업명: '{exist.get('task_nm', '')}' / {candidate})\n"
                            f"  URL 또는 실행 시간을 변경해 주세요."
                        )
                        break

        if errors:
            msg_qss = f"""
                QMessageBox {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; }}
                QMessageBox QLabel {{ color:{TEXT_PRIMARY}; font-size:13px; }}
                QPushButton {{
                    background:{ACCENT}; color:white; border:none;
                    border-radius:5px; padding:5px 14px; font-size:12px;
                }}
                QPushButton:hover {{ background:{ACCENT_HOVER}; }}
            """
            msg = QMessageBox(dlg)
            msg.setWindowTitle("입력 오류")
            msg.setText("다음 항목을 확인해 주세요:\n\n" + "\n".join(errors))
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setStyleSheet(msg_qss)
            msg.exec()
            return

        # ── exec_str / run_at 계산 ───────────────────
        def hms(h_cb, m_cb, s_cb):
            return int(h_cb.currentText()), int(m_cb.currentText()), int(s_cb.currentText())

        now = datetime.now()
        if iv_idx == 1:
            h, m, s = hms(d_h, d_m, d_s)
            exec_str = f"매일 {h:02d}:{m:02d}:{s:02d}";
            iv_key = "daily"
            run_at = now.replace(hour=h, minute=m, second=s, microsecond=0)
            if run_at <= now: run_at += timedelta(days=1)

        elif iv_idx == 2:
            day = w_day.currentText();
            h, m, s = hms(w_h, w_m, w_s)
            exec_str = f"매주 {day} {h:02d}:{m:02d}:{s:02d}";
            iv_key = "weekly"
            run_at = now.replace(hour=h, minute=m, second=s, microsecond=0)
            if run_at <= now: run_at += timedelta(days=7)

        elif iv_idx == 3:
            day = int(m_day.currentText());
            h, m, s = hms(m_h, m_m, m_s)
            exec_str = f"매월 {day}일 {h:02d}:{m:02d}:{s:02d}";
            iv_key = "monthly"
            try:
                run_at = now.replace(day=day, hour=h, minute=m, second=s, microsecond=0)
            except ValueError:
                run_at = now.replace(day=28, hour=h, minute=m, second=s, microsecond=0)
            if run_at <= now: run_at += timedelta(days=30)

        elif iv_idx == 4:
            qd = date_edit.date();
            h, m, s = hms(dat_h, dat_m, dat_s)
            exec_str = f"{qd.toString('yyyy-MM-dd')} {h:02d}:{m:02d}:{s:02d}";
            iv_key = "date"
            run_at = datetime(qd.year(), qd.month(), qd.day(), h, m, s)
            if run_at <= now:
                msg = QMessageBox(dlg)
                msg.setWindowTitle("등록 불가")
                msg.setText(
                    f"선택한 시간이 현재 시각보다 이전입니다.\n\n"
                    f"  설정 시간: {exec_str}\n"
                    f"  현재 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    "현재 시각 이후의 시간을 설정해 주세요."
                )
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setStyleSheet(f"""
                    QMessageBox {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; }}
                    QMessageBox QLabel {{ color:{TEXT_PRIMARY}; font-size:13px; }}
                    QPushButton {{
                        background:{ACCENT}; color:white; border:none;
                        border-radius:5px; padding:5px 14px; font-size:12px;
                    }}
                    QPushButton:hover {{ background:{ACCENT_HOVER}; }}
                """)
                msg.exec()
                return
        else:
            exec_str = "미설정";
            iv_key = "none";
            run_at = now + timedelta(hours=1)

        _db_type_val = sched_db_type.currentText() if sched_db_type else None

        schedule_info = customized_settings.get_schedule_settings()
        schedule_info["auto_save"] = True

        schedule_info["task_nm"] = name_val
        schedule_info["url"] = url_val
        schedule_info["delay"] = sched_delay.value()
        schedule_info["threads"] = sched_threads.value()
        schedule_info["timeout"] = sched_timeout.value()
        schedule_info["retry"] = sched_retry.value()
        schedule_info["user_agent"] = self.session_page.ua_check.isChecked()
        schedule_info["cookie"] = self.session_page.cookie_check.isChecked()
        schedule_info["extract"]["file"]["enabled"] = True if self._sched_out_mode == "FILE" else False
        schedule_info["extract"]["file"]["file_path"] = utility.update_slash(os.path.normpath(sched_path_edit.text()), False) if (self._sched_out_mode == "FILE" and sched_path_edit) else None
        schedule_info["extract"]["file"]["file_name"] = utility.update_empty_value(sched_file_nm.text()) if (sched_out_mode == "FILE" and sched_file_nm) else None
        schedule_info["extract"]["file"]["file_format"] = utility.update_empty_value(sched_fmt_combo.currentText()) if (sched_out_mode == "FILE" and sched_fmt_combo) else None
        schedule_info["extract"]["file"]["file_encoding"] = utility.update_empty_value(sched_enc_combo.currentText()) if (sched_out_mode == "FILE" and sched_enc_combo) else None
        schedule_info["extract"]["file"]["file_delimiter"] = utility.update_empty_value(sched_csv_delim.text()) if (sched_out_mode == "FILE" and sched_csv_delim) else None
        schedule_info["extract"]["db"]["enabled"] = True if self._sched_out_mode == "DB" else False
        schedule_info["extract"]["db"]["db_env"] = utility.update_empty_value(_db_type_val) if (sched_out_mode == "DB" and sched_db_type) else None
        schedule_info["extract"]["db"]["host"] = utility.update_empty_value(sched_db_host.text()) if (sched_out_mode == "DB" and sched_db_host) else None
        schedule_info["extract"]["db"]["port"] = utility.update_empty_value(sched_db_port.text()) if (sched_out_mode == "DB" and sched_db_port) else None
        schedule_info["extract"]["db"]["schema"] = utility.update_empty_value(sched_db_schema.text()) if (sched_out_mode == "DB" and sched_db_schema) else None
        schedule_info["extract"]["db"]["database"] = utility.update_empty_value(sched_db_name.text()) if (sched_out_mode == "DB" and sched_db_name) else None
        schedule_info["extract"]["db"]["user"] = utility.update_empty_value(sched_db_user.text()) if (sched_out_mode == "DB" and sched_db_user) else None
        schedule_info["extract"]["db"]["password"] = utility.update_empty_value(sched_db_pw.text()) if (sched_out_mode == "DB" and sched_db_pw) else None
        schedule_info["extract"]["db"]["save_data_nm"] = utility.update_empty_value(sched_db_data.text()) if (sched_out_mode == "DB" and sched_db_data) else None
        schedule_info["schedule"]["enabled"] = True
        schedule_info["schedule"]["status"] = "대기"
        schedule_info["schedule"]["interval"] = iv_key
        schedule_info["schedule"]["run_at"] = run_at
        schedule_info["schedule"]["exec_str"] = exec_str
        schedule_info["schedule"]["schedule_save_type"] = sched_save_type.currentText().strip()

        store.add_schedule(schedule_info)

        dlg.accept()
        self._refresh_table()
        self._register_timer(len(store.get_schedules()) - 1)

    # ── Remaining Time 포맷 헬퍼 ──────────────────
    @staticmethod
    def _format_remaining(run_at: datetime) -> str:
        """
        남은 시간을 단위 자동 변환하여 반환합니다.
          - 24시간 이하     : HH:MM:SS
          - 24시간 초과     : N일 HH:MM:SS
          - 30일 초과       : N개월 N일
        """
        diff = (run_at - datetime.now()).total_seconds()
        if diff <= 0:
            return "대기 중"
        total_s = int(diff)
        total_m = total_s // 60
        total_h = total_m // 60
        total_d = total_h // 24
        months = total_d // 30
        rem_days = total_d % 30
        hh = total_h % 24
        mm = total_m % 60
        ss = total_s % 60
        if months > 0:
            return f"{months}개월 {rem_days}일"
        elif total_d > 0:
            return f"{total_d}일 {hh:02d}:{mm:02d}:{ss:02d}"
        else:
            return f"{hh:02d}:{mm:02d}:{ss:02d}"

    # ── 테이블 갱신 ───────────────────────────────
    def _refresh_table(self):
        schedules = store.get_schedules()
        self.sched_table.setRowCount(0)
        STATUS_COLOR = {"대기": AMBER, "실행 중": GREEN, "완료": BLUE, "비활성": TEXT_MUTED}

        for idx, s in enumerate(schedules):
            r = self.sched_table.rowCount()
            self.sched_table.insertRow(r)

            # 인덱스
            idx_item = QTableWidgetItem();
            idx_item.setData(Qt.ItemDataRole.DisplayRole, idx)
            idx_item.setForeground(QColor(TEXT_MUTED))
            self.sched_table.setItem(r, 0, idx_item)

            # Task Name / URL / Execution Time (설정 주기 문자열)
            vals = [s["task_nm"], s.get("url", ""), s["schedule"]["exec_str"]]
            colors = [TEXT_PRIMARY, ACCENT_LIGHT, TEXT_PRIMARY]
            for col, (val, color) in enumerate(zip(vals, colors), start=1):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self.sched_table.setItem(r, col, item)

            # Next Runtime — Remaining Time only
            run_at = s["schedule"]["run_at"]
            if run_at:
                remaining_txt = self._format_remaining(run_at)
            else:
                remaining_txt = "—"
            nr_item = QTableWidgetItem(remaining_txt)
            nr_item.setForeground(QColor(PURPLE))
            self.sched_table.setItem(r, 4, nr_item)

            # Status
            status = s["schedule"]["status"]
            si = QTableWidgetItem(status)
            si.setForeground(QColor(STATUS_COLOR.get(status, TEXT_MUTED)))
            self.sched_table.setItem(r, 5, si)

            # Action (수정 / 삭제)
            action_w = QWidget();
            action_w.setStyleSheet("background:transparent;")
            al = QHBoxLayout(action_w);
            al.setContentsMargins(4, 2, 4, 2);
            al.setSpacing(4)
            edit_btn = outline_btn("✎ 수정");
            edit_btn.setFixedHeight(28)
            edit_btn.setStyleSheet(edit_btn.styleSheet() + f" font-size:11px; padding:3px 10px; color:{ACCENT_LIGHT};")
            edit_btn.clicked.connect(lambda _, i=idx: self._show_edit_panel(i))
            del_btn = outline_btn("삭제");
            del_btn.setFixedHeight(28)
            del_btn.setStyleSheet(del_btn.styleSheet() + f" font-size:11px; padding:3px 10px; color:{RED};")
            del_btn.clicked.connect(lambda _, i=idx: self._delete_schedule(i))
            al.addWidget(edit_btn);
            al.addWidget(del_btn)
            self.sched_table.setCellWidget(r, 6, action_w)

    def _run_now(self, idx):
        schedules = store.get_schedules()
        if idx >= len(schedules): return
        s = schedules[idx]
        store.update_schedule_status(idx, "실행 중")
        self._refresh_table()
        self.task.update(request_info)
        self.task.update(s)
        self.schedule_run.emit(self.task)
        # ── 수집 결과 없음 판단은 MultiprocessWorker.no_urls (방법 A) 및
        #    MainWindow._on_finished의 summary["total"] == 0 체크 (방법 B) 로 처리.
        #    타이머 기반 오탐 로직은 제거되었습니다. ──

    # ── 스케줄 수정 Dialog ────────────────────────────
    def _show_edit_panel(self, idx: int):
        """기존 스케줄을 수정하는 Dialog — _show_add_panel 과 동일한 형식."""
        schedules = store.get_schedules()
        if idx >= len(schedules):
            return
        s = schedules[idx]           # 수정 대상 스케줄 dict

        dlg = QDialog(self)
        dlg.setWindowTitle("스케줄 수정")
        dlg.setFixedWidth(560)
        dlg.setStyleSheet(f"background:{BG_SECONDARY}; border:1px solid {BORDER};")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(0)

        # ── 공통 헬퍼 ─────────────────────────────
        def sec_label(text):
            lbl = make_label(text.upper(), TEXT_MUTED, 9)
            lbl.setStyleSheet(lbl.styleSheet() + " letter-spacing:1.5px;")
            return lbl

        def field_row(label, widget, label_w=110):
            row = QHBoxLayout(); row.setSpacing(8)
            lw = make_label(label, TEXT_SECONDARY, 12)
            lw.setFixedWidth(label_w)
            row.addWidget(lw); row.addWidget(widget, 1)
            return row

        cb_style = f"""
            QComboBox {{
                background:{BG_PRIMARY}; color:{TEXT_PRIMARY};
                border:1px solid {BORDER_LIGHT}; border-radius:4px;
                padding:4px 8px; font-size:12px;
            }}
            QComboBox::drop-down {{ border:none; width:18px; }}
            QComboBox QAbstractItemView {{
                background:{BG_SECONDARY}; color:{TEXT_PRIMARY};
                border:1px solid {BORDER}; selection-background-color:{BG_HOVER};
            }}
        """

        def hms_combos():
            h = QComboBox(); h.addItems([f"{t:02d}" for t in range(24)])
            m = QComboBox(); m.addItems([f"{t:02d}" for t in range(60)])
            s_ = QComboBox(); s_.addItems([f"{t:02d}" for t in range(60)])
            hms_style = f"""
                QComboBox {{
                    background:{BG_PRIMARY}; color:{TEXT_PRIMARY};
                    border:1px solid {BORDER_LIGHT}; border-radius:4px;
                    padding:2px 4px; font-size:12px;
                }}
                QComboBox::drop-down {{ border:none; width:14px; }}
                QComboBox QAbstractItemView {{
                    background:{BG_SECONDARY}; color:{TEXT_PRIMARY};
                    border:1px solid {BORDER}; selection-background-color:{BG_HOVER};
                }}
            """
            for cb in (h, m, s_):
                cb.setFixedWidth(52); cb.setStyleSheet(hms_style)
            return h, m, s_

        def time_sep():
            lbl = make_label(":", TEXT_MUTED, 13, True); lbl.setFixedWidth(8)
            return lbl

        def iv_lbl(t):
            return make_label(t, TEXT_SECONDARY, 12)

        # ── 기존 값 파싱 헬퍼 ─────────────────────
        existing_exec_str = s["schedule"].get("exec_str", "")
        existing_interval = s["schedule"].get("interval", "none")
        existing_run_at   = s["schedule"].get("run_at")

        def _parse_hms_from_exec_str(exec_str: str):
            """exec_str 마지막 HH:MM:SS 파싱 → (h, m, s) int tuple"""
            try:
                part = exec_str.strip().split()[-1]
                h_, m_, s_ = part.split(":")
                return int(h_), int(m_), int(s_)
            except Exception:
                return 0, 0, 0

        # ── 타이틀 ────────────────────────────────
        root.addWidget(make_label("스케줄 수정", TEXT_PRIMARY, 14, True))
        root.addSpacing(10); root.addWidget(Divider()); root.addSpacing(14)

        # ── 기본 정보 ─────────────────────────────
        root.addWidget(sec_label("기본 정보"))
        root.addSpacing(8)
        edit_name = QLineEdit(s.get("task_nm", ""))
        edit_url  = QLineEdit(s.get("url", ""))
        edit_url.setCursorPosition(0)
        root.addLayout(field_row("Task Name", edit_name))
        root.addSpacing(6)
        root.addLayout(field_row("Target URL", edit_url))
        root.addSpacing(12); root.addWidget(Divider()); root.addSpacing(12)

        # ── 수집 설정 ─────────────────────────────
        root.addWidget(sec_label("수집 설정"))
        root.addSpacing(8)
        edit_delay   = QDoubleSpinBox(); edit_delay.setRange(0.5, 10.0); edit_delay.setSingleStep(0.5); edit_delay.setDecimals(1); edit_delay.setValue(s.get("delay", 0.5))
        edit_threads = QSpinBox();       edit_threads.setRange(1, 16);   edit_threads.setValue(s.get("threads", 4))
        edit_timeout = QSpinBox();       edit_timeout.setRange(1, 60);   edit_timeout.setValue(s.get("timeout", 10))
        edit_retry   = QSpinBox();       edit_retry.setRange(0, 5);      edit_retry.setValue(s.get("retry", 3))
        cs_row = QHBoxLayout(); cs_row.setSpacing(8)
        for lbl_txt, w in [("Delay(s)", edit_delay), ("Thread", edit_threads), ("Timeout(s)", edit_timeout), ("Retry", edit_retry)]:
            cs_row.addWidget(make_label(lbl_txt, TEXT_MUTED, 11)); cs_row.addWidget(w)
        cs_row.addStretch()
        root.addLayout(cs_row)
        root.addSpacing(12); root.addWidget(Divider()); root.addSpacing(12)

        # ── Save Setting ──────────────────────────
        root.addWidget(sec_label("Save Setting"))
        root.addSpacing(8)

        output_info = customized_settings.get_output_settings()
        existing_extract = s.get("extract", output_info.get("extract", {}))

        _edit_out_mode_ref = ["FILE" if existing_extract.get("file", {}).get("enabled", True) else "DB"]
        sched_out_file_btn = TagButton("FILE")
        sched_out_db_btn   = TagButton("DB")
        sched_out_file_btn.setChecked(_edit_out_mode_ref[0] == "FILE")
        sched_out_db_btn.setChecked(_edit_out_mode_ref[0] == "DB")
        sched_out_mode_lbl = make_label(
            "로컬 파일 저장 모드" if _edit_out_mode_ref[0] == "FILE" else "DB 서버 전송 모드",
            TEXT_MUTED, 10
        )
        out_row = QHBoxLayout(); out_row.setSpacing(8)
        out_row.addWidget(make_label("출력 대상", TEXT_MUTED, 11)); out_row.addSpacing(6)
        out_row.addWidget(sched_out_file_btn); out_row.addWidget(sched_out_db_btn)
        out_row.addSpacing(10); out_row.addWidget(sched_out_mode_lbl); out_row.addStretch()
        root.addLayout(out_row)
        root.addSpacing(8)

        # ── FILE 페이지 ───────────────────────────
        ef = existing_extract.get("file", {})
        sched_extract_stack = QStackedWidget()
        sched_extract_stack.setObjectName("schedExtractStack")
        sched_extract_stack.setStyleSheet(f"""
            QStackedWidget#schedExtractStack {{
                background:{BG_PRIMARY}; border:1px solid {BORDER}; border-radius:6px;
            }}
            QStackedWidget#schedExtractStack > QWidget {{
                background:{BG_PRIMARY}; border:none;
            }}
        """)
        sched_extract_stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        sched_file_page = QWidget()
        sfp = QVBoxLayout(sched_file_page); sfp.setContentsMargins(14, 14, 14, 14); sfp.setSpacing(10)

        sched_path_lay = QHBoxLayout(); sched_path_lay.setSpacing(8)
        sched_path_lay.addWidget(make_label("경로", TEXT_SECONDARY, 12))
        _fp = ef.get("file_path") or customized_settings.set_desktop_dir()
        sched_path_edit = QLineEdit(_fp); sched_path_edit.setReadOnly(True)
        sched_path_lay.addWidget(sched_path_edit, 1)
        sched_browse_btn = outline_btn("Browse"); sched_browse_btn.setFixedWidth(72)
        def _sched_browse():
            folder = QFileDialog.getExistingDirectory(dlg, "저장 폴더 선택", sched_path_edit.text() or "")
            if folder: sched_path_edit.setText(folder)
        sched_browse_btn.clicked.connect(_sched_browse)
        sched_path_lay.addWidget(sched_browse_btn)
        sfp.addLayout(sched_path_lay)

        sched_fnm_lay = QHBoxLayout(); sched_fnm_lay.setSpacing(10)
        sched_fnm_lay.addWidget(make_label("파일명", TEXT_SECONDARY, 12))
        sched_file_nm = QLineEdit(ef.get("file_name") or "untitled0")
        sched_fnm_lay.addWidget(sched_file_nm)
        sfp.addLayout(sched_fnm_lay)

        sched_opt_lay = QHBoxLayout(); sched_opt_lay.setSpacing(10)
        sched_opt_lay.addWidget(make_label("형식", TEXT_SECONDARY, 12))
        sched_fmt_combo = QComboBox(); sched_fmt_combo.addItems(["CSV", "JSON", "Excel"])
        sched_fmt_combo.setCurrentText(ef.get("file_format") or "CSV")
        sched_opt_lay.addWidget(sched_fmt_combo); sched_opt_lay.addSpacing(10)

        sched_enc_widget = QWidget()
        sched_enc_lay = QHBoxLayout(sched_enc_widget); sched_enc_lay.setContentsMargins(0,0,0,0); sched_enc_lay.setSpacing(10)
        sched_enc_combo = QComboBox(); sched_enc_combo.addItems(["UTF-8", "UTF-8 BOM", "CP949 (EUC-KR)"])
        sched_enc_combo.setCurrentText(ef.get("file_encoding") or "UTF-8 BOM")
        sched_enc_lay.addWidget(make_label("인코딩", TEXT_SECONDARY, 12)); sched_enc_lay.addWidget(sched_enc_combo)
        sched_opt_lay.addWidget(sched_enc_widget); sched_opt_lay.addSpacing(10)

        sched_delim_widget = QWidget()
        sched_delim_lay = QHBoxLayout(sched_delim_widget); sched_delim_lay.setContentsMargins(0,0,0,0); sched_delim_lay.setSpacing(10)
        sched_csv_delim = QLineEdit(); sched_csv_delim.setText(ef.get("file_delimiter") or ",")
        sched_delim_lay.addWidget(make_label("구분자", TEXT_SECONDARY, 12)); sched_delim_lay.addWidget(sched_csv_delim)
        sched_opt_lay.addWidget(sched_delim_widget); sched_opt_lay.addStretch()
        sfp.addLayout(sched_opt_lay)

        def _sched_on_fmt_changed(fmt_text: str):
            is_csv = (fmt_text == "CSV")
            sched_enc_widget.setVisible(is_csv); sched_delim_widget.setVisible(is_csv)

        sched_fmt_combo.currentTextChanged.connect(_sched_on_fmt_changed)
        _sched_on_fmt_changed(sched_fmt_combo.currentText())
        sched_extract_stack.addWidget(sched_file_page)   # index 0

        # ── DB 페이지 ─────────────────────────────
        edb = existing_extract.get("db", {})
        DB_PORTS_S = {"MySQL": "3306", "PostgreSQL": "5432", "MongoDB": "27017"}
        sched_db_page = QWidget()
        sdp = QVBoxLayout(sched_db_page); sdp.setContentsMargins(14,14,14,14); sdp.setSpacing(8)
        def _slbl(t): return make_label(t, TEXT_SECONDARY, 11)
        def _sinp(txt="", ph=""): e = QLineEdit(txt); e.setPlaceholderText(ph); return e
        sgrid = QGridLayout(); sgrid.setSpacing(8); sgrid.setColumnStretch(1, 1)
        _sdb_type   = QComboBox(); _sdb_type.addItems(["MySQL", "PostgreSQL", "MongoDB"]); _sdb_type.setCurrentText(edb.get("db_env") or "MySQL")
        _sdb_host   = _sinp(edb.get("host") or "")
        _sdb_port   = _sinp(edb.get("port") or "3306")
        _sdb_name   = _sinp(edb.get("database") or "")
        _sdb_schema = _sinp(edb.get("schema") or "")
        _sdb_user   = _sinp(edb.get("user") or "")
        _sdb_pw     = _sinp(edb.get("password") or ""); _sdb_pw.setEchoMode(QLineEdit.EchoMode.Password)
        _sdb_data   = _sinp(edb.get("save_data_nm") or "")
        for _row_i, (_label, _widget) in enumerate([
            ("DB Type", _sdb_type), ("HOST", _sdb_host), ("PORT", _sdb_port),
            ("DB Name", _sdb_name), ("SCHEMA", _sdb_schema),
            ("USER", _sdb_user), ("PASSWORD", _sdb_pw), ("DATA Name", _sdb_data),
        ]):
            sgrid.addWidget(_slbl(_label), _row_i, 0); sgrid.addWidget(_widget, _row_i, 1)
        _sdb_type.currentTextChanged.connect(lambda t: _sdb_port.setText(DB_PORTS_S.get(t, "")))
        sdp.addLayout(sgrid)
        sched_extract_stack.addWidget(sched_db_page)     # index 1

        sched_extract_stack.setCurrentIndex(0 if _edit_out_mode_ref[0] == "FILE" else 1)

        def _update_edit_dialog_size():
            current_page = sched_extract_stack.currentWidget()
            if current_page:
                current_page.layout().activate()
                sched_extract_stack.setFixedHeight(current_page.layout().sizeHint().height())
            dlg.layout().activate(); dlg.adjustSize()

        def _on_file_clicked():
            _edit_out_mode_ref[0] = "FILE"
            sched_out_mode_lbl.setText("로컬 파일 저장 모드")
            sched_out_db_btn.setChecked(False)
            sched_extract_stack.setCurrentIndex(0)
            sched_extract_stack.setMinimumHeight(0); sched_extract_stack.setMaximumHeight(16777215)
            _update_edit_dialog_size()

        def _on_db_clicked():
            _edit_out_mode_ref[0] = "DB"
            sched_out_mode_lbl.setText("DB 서버 전송 모드")
            sched_out_file_btn.setChecked(False)
            sched_extract_stack.setCurrentIndex(1)
            sched_extract_stack.setMinimumHeight(0); sched_extract_stack.setMaximumHeight(16777215)
            _update_edit_dialog_size()

        sched_out_file_btn.clicked.connect(_on_file_clicked)
        sched_out_db_btn.clicked.connect(_on_db_clicked)

        sched_fmt_combo.currentTextChanged.disconnect(_sched_on_fmt_changed)
        def _sched_on_fmt_changed_with_resize(fmt_text: str):
            _sched_on_fmt_changed(fmt_text); _update_edit_dialog_size()
        sched_fmt_combo.currentTextChanged.connect(_sched_on_fmt_changed_with_resize)

        root.addWidget(sched_extract_stack)
        root.addSpacing(10)

        # 저장 방식 콤보
        edit_save_type = QComboBox()
        edit_save_type.addItems(["선택하세요", "새로 만들기", "덮어쓰기", "추가하기"])
        edit_save_type.setFixedWidth(130); edit_save_type.setStyleSheet(cb_style)
        existing_save_type = s["schedule"].get("schedule_save_type", "선택하세요")
        if existing_save_type in ["새로 만들기", "덮어쓰기", "추가하기"]:
            edit_save_type.setCurrentText(existing_save_type)
        sv_row = QHBoxLayout(); sv_row.setSpacing(8)
        sv_row.addWidget(make_label("저장 방식", TEXT_MUTED, 11)); sv_row.addWidget(edit_save_type); sv_row.addStretch()
        root.addLayout(sv_row)
        root.addSpacing(12); root.addWidget(Divider()); root.addSpacing(12)

        _update_edit_dialog_size()

        # ── Interval ──────────────────────────────
        root.addWidget(sec_label("Interval"))
        root.addSpacing(8)

        edit_interval = QComboBox()
        edit_interval.addItems(["선택하세요", "매일", "매주", "매월", "특정 날짜"])
        edit_interval.setFixedWidth(120); edit_interval.setStyleSheet(cb_style)

        # 초기 interval 콤보 선택값 설정
        _iv_map = {"daily": 1, "weekly": 2, "monthly": 3, "date": 4}
        edit_interval.setCurrentIndex(_iv_map.get(existing_interval, 0))

        container_daily   = QWidget()
        container_weekly  = QWidget()
        container_monthly = QWidget()
        container_date    = QWidget()

        # 기존 시각 파싱
        _ph, _pm, _ps = _parse_hms_from_exec_str(existing_exec_str)

        # 매일
        e_d_h, e_d_m, e_d_s = hms_combos()
        dl_ = QHBoxLayout(container_daily); dl_.setContentsMargins(0,0,0,0); dl_.setSpacing(6); dl_.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        dl_.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        dl_.addWidget(e_d_h, 0, Qt.AlignmentFlag.AlignVCenter); dl_.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        dl_.addWidget(e_d_m, 0, Qt.AlignmentFlag.AlignVCenter); dl_.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        dl_.addWidget(e_d_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_daily.setVisible(False)

        # 매주
        e_w_day = QComboBox(); e_w_day.addItems(["일요일","월요일","화요일","수요일","목요일","금요일","토요일"]); e_w_day.setFixedWidth(76); e_w_day.setStyleSheet(cb_style)
        e_w_h, e_w_m, e_w_s = hms_combos()
        wl_ = QHBoxLayout(container_weekly); wl_.setContentsMargins(0,0,0,0); wl_.setSpacing(6); wl_.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        wl_.addWidget(iv_lbl("매주"), 0, Qt.AlignmentFlag.AlignVCenter); wl_.addWidget(e_w_day, 0, Qt.AlignmentFlag.AlignVCenter); wl_.addSpacing(6)
        wl_.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        wl_.addWidget(e_w_h, 0, Qt.AlignmentFlag.AlignVCenter); wl_.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        wl_.addWidget(e_w_m, 0, Qt.AlignmentFlag.AlignVCenter); wl_.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        wl_.addWidget(e_w_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_weekly.setVisible(False)

        # 매월
        e_m_day = QComboBox(); e_m_day.addItems([str(d) for d in range(1, 32)]); e_m_day.setFixedWidth(50); e_m_day.setStyleSheet(cb_style)
        e_m_h, e_m_m, e_m_s = hms_combos()
        ml_ = QHBoxLayout(container_monthly); ml_.setContentsMargins(0,0,0,0); ml_.setSpacing(6); ml_.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ml_.addWidget(iv_lbl("매월"), 0, Qt.AlignmentFlag.AlignVCenter); ml_.addWidget(e_m_day, 0, Qt.AlignmentFlag.AlignVCenter); ml_.addWidget(iv_lbl("일"), 0, Qt.AlignmentFlag.AlignVCenter); ml_.addSpacing(6)
        ml_.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        ml_.addWidget(e_m_h, 0, Qt.AlignmentFlag.AlignVCenter); ml_.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        ml_.addWidget(e_m_m, 0, Qt.AlignmentFlag.AlignVCenter); ml_.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        ml_.addWidget(e_m_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_monthly.setVisible(False)

        # 특정 날짜
        e_date_edit = QDateEdit(); e_date_edit.setCalendarPopup(True)
        e_date_edit.setMinimumDate(QDate.currentDate())
        if existing_interval == "date" and existing_run_at:
            try:
                ra = existing_run_at if isinstance(existing_run_at, datetime) else datetime.fromisoformat(str(existing_run_at))
                e_date_edit.setDate(QDate(ra.year, ra.month, ra.day))
            except Exception:
                e_date_edit.setDate(QDate.currentDate())
        else:
            e_date_edit.setDate(QDate.currentDate())
        e_date_edit.setDisplayFormat("yyyy-MM-dd"); e_date_edit.setFixedWidth(110)
        e_date_edit.setStyleSheet(f"""
            QDateEdit {{ background:{BG_PRIMARY}; color:{TEXT_PRIMARY}; border:1px solid {BORDER_LIGHT}; border-radius:4px; padding:4px 6px; font-size:12px; }}
            QDateEdit::drop-down {{ subcontrol-origin:padding; subcontrol-position:center right; width:20px; border-left:1px solid {BORDER_LIGHT}; border-radius:0 4px 4px 0; background:{BG_HOVER}; }}
            QDateEdit::down-arrow {{ image:none; width:0; height:0; border-left:4px solid transparent; border-right:4px solid transparent; border-top:5px solid {TEXT_SECONDARY}; margin:0 4px; }}
        """)
        e_dat_h, e_dat_m, e_dat_s = hms_combos()
        datl_ = QHBoxLayout(container_date); datl_.setContentsMargins(0,0,0,0); datl_.setSpacing(6); datl_.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        datl_.addWidget(iv_lbl("날짜"), 0, Qt.AlignmentFlag.AlignVCenter); datl_.addWidget(e_date_edit, 0, Qt.AlignmentFlag.AlignVCenter); datl_.addSpacing(6)
        datl_.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        datl_.addWidget(e_dat_h, 0, Qt.AlignmentFlag.AlignVCenter); datl_.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        datl_.addWidget(e_dat_m, 0, Qt.AlignmentFlag.AlignVCenter); datl_.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        datl_.addWidget(e_dat_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_date.setVisible(False)

        # 기존 시각 콤보에 반영
        for cb, val in [(e_d_h, _ph), (e_d_m, _pm), (e_d_s, _ps),
                        (e_w_h, _ph), (e_w_m, _pm), (e_w_s, _ps),
                        (e_m_h, _ph), (e_m_m, _pm), (e_m_s, _ps),
                        (e_dat_h, _ph), (e_dat_m, _pm), (e_dat_s, _ps)]:
            cb.setCurrentText(f"{val:02d}")

        # 매주 요일 파싱
        if existing_interval == "weekly":
            _DAY_NAMES = ["일요일","월요일","화요일","수요일","목요일","금요일","토요일"]
            for dn in _DAY_NAMES:
                if dn in existing_exec_str:
                    e_w_day.setCurrentText(dn); break

        # 매월 일자 파싱
        if existing_interval == "monthly":
            try:
                import re as _re
                _day_match = _re.search(r"매월\s*(\d+)일", existing_exec_str)
                if _day_match:
                    e_m_day.setCurrentText(_day_match.group(1))
            except Exception:
                pass

        # 주기 행
        iv_row = QHBoxLayout(); iv_row.setSpacing(8); iv_row.setContentsMargins(0,0,0,0)
        iv_row.addWidget(iv_lbl("주기"), 0, Qt.AlignmentFlag.AlignVCenter)
        iv_row.addWidget(edit_interval, 0, Qt.AlignmentFlag.AlignVCenter)
        iv_row.addStretch()

        detail_wrap = QWidget()
        detail_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        detail_lay = QHBoxLayout(detail_wrap); detail_lay.setContentsMargins(8,0,0,0); detail_lay.setSpacing(6)
        for c in [container_daily, container_weekly, container_monthly, container_date]:
            detail_lay.addWidget(c, 0, Qt.AlignmentFlag.AlignVCenter)
        detail_lay.addStretch()

        root.addLayout(iv_row)
        root.setSpacing(4)
        root.addWidget(detail_wrap)

        def _on_iv_changed(iv_idx_):
            container_daily.setVisible(iv_idx_ == 1)
            container_weekly.setVisible(iv_idx_ == 2)
            container_monthly.setVisible(iv_idx_ == 3)
            container_date.setVisible(iv_idx_ == 4)

        edit_interval.currentIndexChanged.connect(_on_iv_changed)
        _on_iv_changed(edit_interval.currentIndex())

        root.addSpacing(12); root.addWidget(Divider()); root.addSpacing(12)

        # ── 저장 처리 ─────────────────────────────
        def _do_update():
            name_val  = edit_name.text().strip()
            url_val   = edit_url.text().strip()
            iv_idx_   = edit_interval.currentIndex()
            svtype_idx = edit_save_type.currentIndex()

            errors = []
            if not name_val: errors.append("• Task Name을 입력해 주세요.")
            if not url_val:  errors.append("• Target URL을 입력해 주세요.")
            if iv_idx_ == 0: errors.append("• Interval(주기)을 선택해 주세요.")
            if svtype_idx == 0: errors.append("• 저장 방식을 선택해 주세요.")

            # 작업명 중복 체크 (자기 자신 제외)
            if not errors:
                for i2, exist in enumerate(store.get_schedules()):
                    if i2 != idx and exist.get("task_nm") == name_val:
                        errors.append(f"• 동일한 작업명이 이미 등록되어 있습니다.\n  다른 작업명을 사용해 주세요.")
                        break

            if errors:
                msg_qss = f"""
                    QMessageBox {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; }}
                    QMessageBox QLabel {{ color:{TEXT_PRIMARY}; font-size:13px; }}
                    QPushButton {{ background:{ACCENT}; color:white; border:none; border-radius:5px; padding:5px 14px; font-size:12px; }}
                    QPushButton:hover {{ background:{ACCENT_HOVER}; }}
                """
                msg = QMessageBox(dlg); msg.setWindowTitle("입력 오류")
                msg.setText("다음 항목을 확인해 주세요:\n\n" + "\n".join(errors))
                msg.setIcon(QMessageBox.Icon.Warning); msg.setStyleSheet(msg_qss); msg.exec()
                return

            # exec_str / run_at 계산
            def hms_(h_cb, m_cb, s_cb):
                return int(h_cb.currentText()), int(m_cb.currentText()), int(s_cb.currentText())

            now = datetime.now()
            if iv_idx_ == 1:
                h_, m_, s_ = hms_(e_d_h, e_d_m, e_d_s)
                exec_str = f"매일 {h_:02d}:{m_:02d}:{s_:02d}"; iv_key = "daily"
                run_at = now.replace(hour=h_, minute=m_, second=s_, microsecond=0)
                if run_at <= now: run_at += timedelta(days=1)
            elif iv_idx_ == 2:
                day_ = e_w_day.currentText(); h_, m_, s_ = hms_(e_w_h, e_w_m, e_w_s)
                exec_str = f"매주 {day_} {h_:02d}:{m_:02d}:{s_:02d}"; iv_key = "weekly"
                run_at = now.replace(hour=h_, minute=m_, second=s_, microsecond=0)
                if run_at <= now: run_at += timedelta(days=7)
            elif iv_idx_ == 3:
                day_ = int(e_m_day.currentText()); h_, m_, s_ = hms_(e_m_h, e_m_m, e_m_s)
                exec_str = f"매월 {day_}일 {h_:02d}:{m_:02d}:{s_:02d}"; iv_key = "monthly"
                try:
                    run_at = now.replace(day=day_, hour=h_, minute=m_, second=s_, microsecond=0)
                except ValueError:
                    run_at = now.replace(day=28, hour=h_, minute=m_, second=s_, microsecond=0)
                if run_at <= now: run_at += timedelta(days=30)
            elif iv_idx_ == 4:
                qd_ = e_date_edit.date(); h_, m_, s_ = hms_(e_dat_h, e_dat_m, e_dat_s)
                exec_str = f"{qd_.toString('yyyy-MM-dd')} {h_:02d}:{m_:02d}:{s_:02d}"; iv_key = "date"
                run_at = datetime(qd_.year(), qd_.month(), qd_.day(), h_, m_, s_)
                if run_at <= now:
                    msg = QMessageBox(dlg); msg.setWindowTitle("등록 불가")
                    msg.setText(f"선택한 시간이 현재 시각보다 이전입니다.\n\n  설정 시간: {exec_str}\n  현재 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n현재 시각 이후의 시간을 설정해 주세요.")
                    msg.setIcon(QMessageBox.Icon.Warning)
                    msg.setStyleSheet(f"QMessageBox {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; }} QMessageBox QLabel {{ color:{TEXT_PRIMARY}; font-size:13px; }} QPushButton {{ background:{ACCENT}; color:white; border:none; border-radius:5px; padding:5px 14px; font-size:12px; }} QPushButton:hover {{ background:{ACCENT_HOVER}; }}")
                    msg.exec(); return
            else:
                exec_str = "미설정"; iv_key = "none"; run_at = now + timedelta(hours=1)

            out_mode_ = _edit_out_mode_ref[0]

            # DataStore 스케줄 항목 직접 수정
            target = store.get_schedules()[idx]
            target["task_nm"]  = name_val
            target["url"]      = url_val
            target["delay"]    = edit_delay.value()
            target["threads"]  = edit_threads.value()
            target["timeout"]  = edit_timeout.value()
            target["retry"]    = edit_retry.value()
            target["extract"]["file"]["enabled"]        = (out_mode_ == "FILE")
            target["extract"]["file"]["file_path"]      = utility.update_slash(os.path.normpath(sched_path_edit.text()), False) if out_mode_ == "FILE" else None
            target["extract"]["file"]["file_name"]      = utility.update_empty_value(sched_file_nm.text())      if out_mode_ == "FILE" else None
            target["extract"]["file"]["file_format"]    = utility.update_empty_value(sched_fmt_combo.currentText()) if out_mode_ == "FILE" else None
            target["extract"]["file"]["file_encoding"]  = utility.update_empty_value(sched_enc_combo.currentText()) if out_mode_ == "FILE" else None
            target["extract"]["file"]["file_delimiter"] = utility.update_empty_value(sched_csv_delim.text())    if out_mode_ == "FILE" else None
            target["extract"]["db"]["enabled"]          = (out_mode_ == "DB")
            target["extract"]["db"]["db_env"]           = utility.update_empty_value(_sdb_type.currentText())   if out_mode_ == "DB" else None
            target["extract"]["db"]["host"]             = utility.update_empty_value(_sdb_host.text())          if out_mode_ == "DB" else None
            target["extract"]["db"]["port"]             = utility.update_empty_value(_sdb_port.text())          if out_mode_ == "DB" else None
            target["extract"]["db"]["schema"]           = utility.update_empty_value(_sdb_schema.text())        if out_mode_ == "DB" else None
            target["extract"]["db"]["database"]         = utility.update_empty_value(_sdb_name.text())          if out_mode_ == "DB" else None
            target["extract"]["db"]["user"]             = utility.update_empty_value(_sdb_user.text())          if out_mode_ == "DB" else None
            target["extract"]["db"]["password"]         = utility.update_empty_value(_sdb_pw.text())            if out_mode_ == "DB" else None
            target["extract"]["db"]["save_data_nm"]     = utility.update_empty_value(_sdb_data.text())          if out_mode_ == "DB" else None
            target["schedule"]["interval"]             = iv_key
            target["schedule"]["exec_str"]             = exec_str
            target["schedule"]["run_at"]               = run_at
            target["schedule"]["schedule_save_type"]   = edit_save_type.currentText().strip()

            # 타이머 재등록
            if idx in self._timers:
                self._timers[idx].stop()
                del self._timers[idx]
            self._register_timer(idx)

            dlg.accept()
            self._refresh_table()

        # ── 하단 버튼 ──────────────────────────────
        btn_row = QHBoxLayout(); btn_row.addStretch()
        save_btn   = action_btn("수정 완료"); save_btn.clicked.connect(_do_update)
        cancel_btn = outline_btn("취소");     cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(save_btn); btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

        dlg.adjustSize()
        dlg.exec()

    def _delete_schedule(self, idx):
        store.remove_schedule(idx)
        self._refresh_table()

    def _register_timer(self, idx):
        schedules = store.get_schedules()
        if idx >= len(schedules): return
        s = schedules[idx]
        run_at = s["schedule"]["run_at"]
        # run_at = s.get("run_at")
        if not run_at: return
        ms = max(0, int((run_at - datetime.now()).total_seconds() * 1000))
        t = QTimer(self);
        t.setSingleShot(True)
        t.timeout.connect(lambda i=idx: self._run_now(i))
        t.start(ms);
        self._timers[idx] = t

    def _update_countdown(self):
        """1초마다 Next Task 라벨 + Next Runtime 컬럼을 동시에 갱신합니다."""
        schedules = store.get_schedules()

        # ── Next Runtime 컬럼(col 4) 갱신 ──────────
        for row, s in enumerate(schedules):
            run_at = s["schedule"]["run_at"]
            # run_at = s.get("run_at")
            txt = self._format_remaining(run_at) if run_at else "—"
            item = self.sched_table.item(row, 4)
            if item:
                item.setText(txt)
            else:
                new_item = QTableWidgetItem(txt)
                new_item.setForeground(QColor(PURPLE))
                self.sched_table.setItem(row, 4, new_item)

        # ── Next Task 라벨 갱신 ─────────────────────
        active = [s for s in schedules if s["schedule"]["run_at"] and s["schedule"]["status"] != "완료"]
        # active = [s for s in schedules if s.get("run_at") and s.get("status") != "완료"]
        if not active:
            self.next_task_lbl.setText("등록된 스케줄 없음")
            self.next_task_lbl.setStyleSheet(self.next_task_lbl.styleSheet().replace(ACCENT_LIGHT, TEXT_MUTED)
                                             .replace(GREEN, TEXT_MUTED))
            return
        next_s = min(active, key=lambda s: s["schedule"]["run_at"])
        diff = (next_s["schedule"]["run_at"] - datetime.now()).total_seconds()
        if diff < 0:
            remaining_txt = "실행 대기 중"
        else:
            remaining_txt = self._format_remaining(next_s["schedule"]["run_at"])
        display = f"{next_s['task_nm']}  —  {remaining_txt}"
        self.next_task_lbl.setText(display)
        self.next_task_lbl.setStyleSheet(
            f"color:{ACCENT_LIGHT}; font-size:13px; font-weight:bold; background:transparent; border:none;"
        )

    def mark_done(self, job_name: str):
        """
        작업 완료 후 interval 키에 따라 next run_at 을 자동 계산하여
        지속적으로 재스케줄링합니다.
        """
        now = datetime.now()
        for i, s in enumerate(store.get_schedules()):
            if s["task_nm"] != job_name:
                continue

            iv_key = s["schedule"]["interval"]
            run_at = s.get("run_at", now)

            if iv_key == "daily":
                next_run = run_at + timedelta(days=1)
            elif iv_key == "weekly":
                next_run = run_at + timedelta(weeks=1)
            elif iv_key == "monthly":
                next_run = run_at + timedelta(days=30)
            else:
                # 특정 날짜(1회성) 또는 none → 완료 상태로 종료
                store.update_schedule_status(i, "완료")
                self._refresh_table()
                return

            # run_at 갱신 + 상태를 "대기"로 복원
            store.get_schedules()[i]["schedule"]["run_at"] = next_run
            store.update_schedule_status(i, "대기")

            # 다음 실행 타이머 재등록
            self._register_timer(i)

        self._refresh_table()


# ══════════════════════════════════════════════════════
#  PROXY SETTINGS PAGE
# ══════════════════════════════════════════════════════
class SessionSettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        self._proxy_rows = []  # list of dict
        self._build()

    # ── 초기 더미 데이터 ──────────────────────────────
    def _seed(self):
        samples = [
            {"host": "10.0.0.1", "port": "8080", "protocol": "HTTP", "enabled": True, "latency": "82ms",
             "status": "활성"},
            {"host": "10.0.0.12", "port": "3128", "protocol": "SOCKS5", "enabled": True, "latency": "145ms",
             "status": "활성"},
            {"host": "10.0.0.23", "port": "8888", "protocol": "HTTP", "enabled": False, "latency": "—",
             "status": "비활성"},
            {"host": "45.12.34.99", "port": "1080", "protocol": "SOCKS4", "enabled": True, "latency": "310ms",
             "status": "활성"},
        ]
        for s in samples:
            self._proxy_rows.append(s)
            self._insert_table_row(s)

    def _build(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 스크롤 바디 ──────────────────────────────────
        scroll = QScrollArea();
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body);
        bl.setContentsMargins(14, 14, 14, 14);
        bl.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── 전역 옵션 카드 ──────────────────────────────
        gw1, gl1 = card_widget("세션 설정")
        row0 = QHBoxLayout();
        row0.setSpacing(16)

        self.ua_check = QCheckBox("UA 랜덤")
        self.ua_check.setToolTip("요청마다 User-Agent를 무작위로 변경")
        self.ua_check.setChecked(True)

        self.cookie_check = QCheckBox("Cookie 랜덤")
        self.cookie_check.setChecked(True)
        self.cookie_check.setToolTip("요청마다 Cookie 세션을 무작위로 순환")

        self._global_cb = QCheckBox("전역 프록시 사용")
        self._global_cb.setChecked(False)

        row0.addWidget(self.ua_check)
        row0.addWidget(self.cookie_check)
        row0.addWidget(self._global_cb)
        gl1.addLayout(row0)
        bl.addWidget(gw1)

        self.gw2, gl2 = card_widget("프록시 옵션")
        row0 = QHBoxLayout();
        row0.setSpacing(16)
        self._rotate_cb = QCheckBox("자동 로테이션")
        self._rotate_cb.setChecked(False)
        row0.addWidget(self._rotate_cb)
        self._test_cb = QCheckBox("연결 전 헬스체크")
        self._test_cb.setChecked(False)
        row0.addWidget(self._test_cb)
        row0.addStretch()
        gl2.addLayout(row0)
        row1 = QHBoxLayout();
        row1.setSpacing(10)
        row1.addWidget(make_label("분당 IP 허용 갯수", TEXT_SECONDARY, 12))
        self._allow_ip_cnts = QSpinBox();
        self._allow_ip_cnts.setRange(1, 15);
        self._allow_ip_cnts.setValue(10)
        row1.addWidget(self._allow_ip_cnts)
        row1.addSpacing(20)
        row1.addWidget(make_label("MAX RETRY", TEXT_SECONDARY, 12))
        self._retry_spin = QSpinBox();
        self._retry_spin.setRange(1, 20);
        self._retry_spin.setValue(3)
        row1.addWidget(self._retry_spin)
        row1.addStretch()
        gl2.addLayout(row1)
        bl.addWidget(self.gw2)

        # ── 프록시 목록 카드 ──────────────────────────────
        self.pw, pl = card_widget("프록시 목록")
        # 테이블 헤더 행
        hdr_row = QHBoxLayout();
        hdr_row.setSpacing(8)
        hdr_row.addStretch()

        self._import_lbl = make_label("", TEXT_MUTED, 10)
        self._import_btn = outline_btn("📂 Import")
        self._import_btn.setToolTip("텍스트/CSV 파일에서 IP:PORT 형식의 프록시 목록을 불러옵니다")
        self._import_btn.clicked.connect(self._import_proxy_file)
        self._add_btn = action_btn("+ 추가", ACCENT, ACCENT_HOVER)
        self._add_btn.clicked.connect(self._add_proxy_dialog)
        hdr_row.addWidget(self._import_lbl)
        hdr_row.addWidget(self._import_btn)
        hdr_row.addWidget(self._add_btn)
        pl.addLayout(hdr_row)
        self._proxy_table = self._make_proxy_table()
        pl.addWidget(self._proxy_table)
        bl.addWidget(self.pw)

        # ── 더미 데이터 시드 ──────────────────────────────
        self._seed()

        # 연결 부분
        self._global_cb.toggled.connect(self._activate_proxy_option)
        self._activate_proxy_option(self._global_cb.isChecked())

    # ── 프록시 활성/비활성 시각 전환 ────────────────────
    def _activate_proxy_option(self, is_checked):
        """
        전역 프록시 사용 체크 여부에 따라
        '프록시 옵션' 카드와 '프록시 목록' 카드의
        동작 차단(setEnabled) + 시각 피드백(스타일·커서)을 동시에 처리합니다.
        """
        for card in (self.gw2, self.pw):
            card.setEnabled(is_checked)
            self._set_card_visual(card, is_checked)

    @staticmethod
    def _set_card_visual(card: QWidget, enabled: bool) -> None:
        """
        카드 컨테이너의 테두리·배경·자식 위젯 색상을 enabled 상태에 맞게 전환합니다.
        인라인 setStyleSheet()가 GLOBAL_QSS :disabled 규칙을 덮어쓰는 문제를
        카드 컨테이너 단위의 QSS 주입으로 해결합니다.

        활성  → 기본 카드 스타일
        비활성 → 배경·텍스트·버튼·입력·테이블 모두 흐린 색상으로 일괄 전환
        """
        if enabled:
            card.setStyleSheet(f"""
                QWidget {{
                    background: {BG_SECONDARY};
                    border: 1px solid {BORDER};
                    border-radius: 8px;
                }}
            """)
        else:
            card.setStyleSheet(f"""
                QWidget {{
                    background: {BG_PRIMARY};
                    border: 1px solid {BORDER};
                    border-radius: 8px;
                    color: {TEXT_MUTED};
                }}
                QCheckBox {{
                    color: {TEXT_MUTED};
                }}
                QCheckBox::indicator {{
                    background: {BG_HOVER};
                    border: 1px solid {BORDER};
                    border-radius: 3px;
                    width: 14px; height: 14px;
                }}
                QCheckBox::indicator:checked {{
                    background: {BORDER};
                    border-color: {BORDER};
                }}
                QLabel {{
                    color: {TEXT_MUTED};
                    background: transparent;
                    border: none;
                }}
                QSpinBox, QDoubleSpinBox {{
                    background: {BG_HOVER};
                    color: {TEXT_MUTED};
                    border: 1px solid {BORDER};
                    border-radius: 4px;
                }}
                QSpinBox::up-button, QSpinBox::down-button,
                QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                    background: {BG_HOVER};
                    border: none;
                }}
                QPushButton {{
                    background: {BG_HOVER};
                    color: {TEXT_MUTED};
                    border: 1px solid {BORDER};
                    border-radius: 6px;
                    padding: 6px 14px;
                    font-size: 12px;
                    font-weight: normal;
                }}
                QTableWidget {{
                    background: {BG_PRIMARY};
                    color: {TEXT_MUTED};
                    border: none;
                    gridline-color: {BG_HOVER};
                }}
                QTableWidget::item {{
                    color: {TEXT_MUTED};
                    padding: 6px 10px;
                }}
                QHeaderView::section {{
                    background: {BG_PRIMARY};
                    color: {BORDER_LIGHT};
                    border: none;
                    border-bottom: 1px solid {BORDER};
                    padding: 6px 10px;
                    font-size: 10px;
                }}
            """)

    def _make_proxy_table(self):
        headers = ["활성", "프로토콜", "호스트", "포트", "레이턴시", "상태", "액션"]
        t = EqualSpacingTable(
            parent=self,
            row_height=36,
            col_padding=8,
            hscroll_handle=50,
        )
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        return t

    def _insert_table_row(self, data: dict):
        r = self._proxy_table.rowCount()
        self._proxy_table.insertRow(r)
        self._proxy_table.setRowHeight(r, 36)

        # 활성 체크박스
        cb = QCheckBox()
        cb.setChecked(data["enabled"])
        cb_w = QWidget();
        cb_l = QHBoxLayout(cb_w)
        cb_l.setContentsMargins(8, 0, 0, 0);
        cb_l.addWidget(cb)
        self._proxy_table.setCellWidget(r, 0, cb_w)

        color_map = {"HTTP": BLUE, "SOCKS5": PURPLE, "SOCKS4": AMBER}
        proto_color = color_map.get(data["protocol"], TEXT_SECONDARY)
        vals_colors = [
            (data["protocol"], proto_color),
            (data["host"], TEXT_PRIMARY),
            (data["port"], TEXT_SECONDARY),
            (data["latency"], GREEN if data["latency"] != "—" else TEXT_MUTED),
        ]
        for col, (val, color) in enumerate(vals_colors, start=1):
            item = QTableWidgetItem(val)
            item.setForeground(QColor(color))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._proxy_table.setItem(r, col, item)

        # 상태 칩
        status_lbl = QLabel(data["status"])
        sc = GREEN if data["status"] == "활성" else TEXT_MUTED
        status_lbl.setStyleSheet(f"""
            color:{sc}; background:{"#052e16" if sc == GREEN else BG_HOVER};
            border-radius:10px; padding:2px 10px; font-size:11px;
        """)
        sw = QWidget();
        sl = QHBoxLayout(sw);
        sl.setContentsMargins(4, 0, 4, 0);
        sl.addWidget(status_lbl)
        self._proxy_table.setCellWidget(r, 5, sw)

        # 삭제 버튼
        del_btn = QPushButton("삭제")
        del_btn.setFixedHeight(24)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton{{background:transparent;color:{RED};border:1px solid {RED};
            border-radius:4px;padding:0 8px;font-size:11px;}}
            QPushButton:hover{{background:#7f1d1d;}}
        """)
        row_idx = r
        del_btn.clicked.connect(lambda _, ri=row_idx: self._delete_row(ri))
        dw = QWidget();
        dl = QHBoxLayout(dw);
        dl.setContentsMargins(4, 2, 4, 2);
        dl.addWidget(del_btn)
        self._proxy_table.setCellWidget(r, 6, dw)

    def load_ip_list_from_file(self):
        """파일을 첨부하여 IP 리스트 테이블에 로드합니다."""
        file_dialog = QFileDialog(self)
        file_path, _ = file_dialog.getOpenFileName(
            self, "IP 리스트 파일 선택", "", "Text files (*.txt);;CSV files (*.csv);;All files (*.*)"
        )

        if not file_path:
            return

        ip_port_pattern = re.compile(r"^\d+\.\d+\.\d+\.\d+:\d+$")  # IP 주소 정규식
        try:

            if file_path.endswith('.csv'):

                with open(file_path, mode='r', encoding='utf-8') as f:

                    # DictReader 객체 생성
                    reader = csv.reader(f)

                    # 리스트 내 딕셔너리 형태로 한꺼번에 변환
                    raw_lines = [row[0] for row in reader]

            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    raw_lines = [line.strip() for line in f if line.strip()]

            total_loaded = len(raw_lines)
            ip_list = [line for line in raw_lines if ip_port_pattern.fullmatch(line)]
            filtered_count = len(ip_list)

            if not ip_list:
                QMessageBox.warning(self, "파일 오류",
                                    f"파일에서 유효한 IP:PORT 형식({ip_port_pattern.pattern})의 데이터를 찾을 수 없습니다. ({total_loaded}개 항목 중 0개)")
                self.ip_proxy_table.setRowCount(0)
                # self.log_message(f"❌ IP 리스트 파일 로드 실패: 로드된 {total_loaded}개 항목 중 정규식에 일치하는 데이터가 없습니다.")
                return

            table = self.ip_proxy_table
            table.setRowCount(len(ip_list))
            for row_index, ip in enumerate(ip_list):
                table.setItem(row_index, 0, QTableWidgetItem(ip))

            if filtered_count > 0:
                table.selectRow(0)

            # self.log_message(f"✅ IP 리스트 파일 '{file_path}'에서 총 {total_loaded}개 항목 중 {filtered_count}개의 유효한 IP를 성공적으로 로드했습니다. (모든 항목 검사 완료)")

        except Exception as e:
            QMessageBox.critical(self, "파일 로드 오류", f"파일을 로드하거나 처리하는 중 오류가 발생했습니다: {e}")
            # self.log_message(f"❌ IP 리스트 파일 로드 실패: {e}")

    def _import_proxy_file(self):
        """
        파일 불러오기 -> Regex로 IP:PORT 추출 -> 중복 제거 -> 테이블 반영
        지원 패턴: ^[0-9]+.[0-9]+.[0-9]+.[0-9]+:[0-9]+$  (줄 단위 또는 혼합 텍스트 모두 처리)
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "프록시 목록 파일 선택", "",
            "텍스트 파일 (*.txt *.csv *.dat *.list);;모든 파일 (*)"
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()
        except Exception as e:
            self._log("err", f"파일 읽기 실패: {e}")
            return

        # Regex 추출: IP:PORT 형식만 엄격하게 매칭
        pattern = re.compile(r'(?<!\d)(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})(?!\d)')
        matches = pattern.findall(raw)

        if not matches:
            self._import_lbl.setText("⚠ 유효한 IP:PORT 없음")
            self._import_lbl.setStyleSheet(f"color:{AMBER}; font-size:10px; background:transparent; border:none;")
            self._log("warn", f"파일 파싱 완료 — 유효한 IP:PORT를 찾지 못했습니다: {path}")
            return

        # 기존 목록과 중복 제거
        existing = set()
        for row_data in self._proxy_rows:
            existing.add(f"{row_data['host']}:{row_data['port']}")

        added = 0
        skipped = 0
        for host, port in matches:
            key = f"{host}:{port}"
            if key in existing:
                skipped += 1
                continue
            existing.add(key)
            data = {
                "host": host,
                "port": port,
                "protocol": "HTTP",  # 파일에서는 프로토콜 정보 없으므로 기본값
                "enabled": True,
                "latency": "—",
                "status": "활성",
            }
            self._proxy_rows.append(data)
            self._insert_table_row(data)
            added += 1

        # 결과 레이블 업데이트
        summary = f"✓ {added}개 추가" + (f"  (중복 {skipped}개 제외)" if skipped else "")
        self._import_lbl.setText(summary)
        self._import_lbl.setStyleSheet(f"color:{GREEN}; font-size:10px; background:transparent; border:none;")

        self._log("ok", f"Import 완료: {added}개 추가 / {skipped}개 중복 제외 ← {path}")
        if added:
            self._log("info", f"Import된 프록시는 기본값 HTTP / 활성 상태로 등록됩니다. 필요 시 개별 수정하세요.")

    def _add_proxy_dialog(self):

        """새 프록시 추가 Dialog를 띄운다."""
        dlg = QDialog(self)
        dlg.setWindowTitle("새 프록시 추가")
        dlg.setFixedWidth(350)
        dlg.setStyleSheet(f"background:{BG_SECONDARY}; border:1px solid {BORDER};")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(0)

        # ── 타이틀 ────────────────────────────────
        root.addWidget(make_label("새 프록시 추가", TEXT_PRIMARY, 14, True))
        root.addSpacing(10);
        root.addWidget(Divider());
        root.addSpacing(14)

        proto_row = QHBoxLayout()
        proto_row.setContentsMargins(0, 0, 0, 15)
        proto_row.addWidget(make_label("프로토콜", TEXT_SECONDARY, 12))
        proto_cb = QComboBox();
        proto_cb.addItems(["HTTP", "HTTPS", "SOCKS4", "SOCKS5"])
        proto_row.addWidget(proto_cb, 1)
        root.addLayout(proto_row)

        host_row = QHBoxLayout()
        host_row.setContentsMargins(0, 0, 0, 15)
        host_row.addWidget(make_label("호스트", TEXT_SECONDARY, 12))
        host_inp = QLineEdit();
        host_inp.setPlaceholderText("예: 10.0.0.1")
        host_row.addWidget(host_inp, 1)
        root.addLayout(host_row)

        port_row = QHBoxLayout()
        port_row.setContentsMargins(0, 0, 0, 15)
        port_row.addWidget(make_label("포트", TEXT_SECONDARY, 12))
        port_inp = QLineEdit();
        port_inp.setPlaceholderText("예: 8080")
        port_row.addWidget(port_inp, 1)
        root.addLayout(port_row)

        btn_row = QHBoxLayout()
        ok_btn = action_btn("추가")

        def _do_add():
            host = host_inp.text().strip() or "0.0.0.0"
            port = port_inp.text().strip() or "8080"
            proto = proto_cb.currentText()
            data = {"host": host, "port": port, "protocol": proto,
                    "enabled": True, "latency": "—", "status": "활성"}
            self._proxy_rows.append(data)
            self._insert_table_row(data)
            self._log("ok", f"프록시 추가됨: {proto} {host}:{port}")
            dlg.close()

        ok_btn.clicked.connect(_do_add)
        cancel_btn = outline_btn("취소");
        cancel_btn.clicked.connect(dlg.close)
        btn_row.addStretch();
        btn_row.addWidget(cancel_btn);
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

        # dlg.adjustSize()
        dlg.exec()

    def _delete_row(self, row_idx):
        if 0 <= row_idx < self._proxy_table.rowCount():
            host = self._proxy_table.item(row_idx, 2)
            host_txt = host.text() if host else "?"
            self._proxy_table.removeRow(row_idx)
            self._log("warn", f"프록시 삭제됨: {host_txt}")

    def _update_status_label(self, state):
        """전역 프록시 사용 체크 상태 변경 시 — 현재 미사용 (UI에 status 라벨 없음)"""
        pass


# ══════════════════════════════════════════════════════
#  AUTH MANAGER PAGE
# ══════════════════════════════════════════════════════
class AuthManagerPage(QWidget):
    def __init__(self):
        super().__init__()
        self._auth_rows = []
        self._build()

    def _seed(self):
        samples = [
            {"name": "Naver API", "type": "API Key", "key": "nav_****_xxxx", "expires": "2025-12-31", "status": "유효"},
            {"name": "Coupang Scraper", "type": "Cookie", "key": "sess=abc****", "expires": "2025-06-01",
             "status": "만료임박"},
            {"name": "AWS S3 Export", "type": "OAuth2", "key": "arn:aws:****", "expires": "상시", "status": "유효"},
            {"name": "Internal DB", "type": "Basic Auth", "key": "admin:****", "expires": "상시", "status": "유효"},
        ]
        for s in samples:
            self._auth_rows.append(s)
            self._insert_table_row(s)

    def _build(self):

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea();
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        body = QWidget()
        bl = QVBoxLayout(body);
        bl.setContentsMargins(14, 14, 14, 14);
        bl.setSpacing(14)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # ── 전역 인증 옵션 (탭 위 고정) ─────────────────
        global_w, global_l = card_widget("전역 인증 옵션")
        global_w.setStyleSheet(
            global_w.styleSheet() + "border-radius:0px; border-left:none; border-right:none; border-top:none;")
        row0 = QHBoxLayout();
        row0.setSpacing(16)
        self._tls_cb = QCheckBox("TLS/SSL 인증서 검증")
        self._tls_cb.setChecked(False)
        self._tls_cb.stateChanged.connect(self._on_tls_toggle)
        row0.addWidget(self._tls_cb)
        self._store_cb = QCheckBox("인증 정보 암호화 저장")
        self._store_cb.setChecked(False)
        row0.addWidget(self._store_cb)
        self._rotate_cb = QCheckBox("세션 자동 갱신")
        self._rotate_cb.setChecked(False)
        row0.addWidget(self._rotate_cb)
        row0.addStretch()
        self._cert_lbl = make_label("● TLS 검증 활성화", GREEN, 12)
        row0.addWidget(self._cert_lbl)
        global_l.addLayout(row0)
        bl.addWidget(global_w)

        # ── 인증 자격증명 목록 ──────────────────────────
        cw, cl = card_widget("자격증명 목록")
        hdr_row = QHBoxLayout()
        hdr_row.addStretch()
        self._add_cred_btn = action_btn("+ 자격증명 추가", ACCENT, ACCENT_HOVER)
        self._add_cred_btn.clicked.connect(self._add_cred_dialog)
        self._export_btn = outline_btn("내보내기 (암호화)")
        self._export_btn.clicked.connect(self._export_creds)
        hdr_row.addWidget(self._export_btn)
        hdr_row.addWidget(self._add_cred_btn)
        cl.addLayout(hdr_row)

        self._cred_table = self._make_cred_table()
        cl.addWidget(self._cred_table)
        bl.addWidget(cw)

        self._seed()

        # ── 로그인 대상 설정 카드 ────────────────────────
        lc_w, lc_l = card_widget("로그인 대상 설정")

        def _field(label, widget, layout):
            row = QHBoxLayout();
            row.setSpacing(10)
            lbl = make_label(label, TEXT_SECONDARY, 12)
            lbl.setFixedWidth(90)
            row.addWidget(lbl)
            row.addWidget(widget, 1)
            layout.addLayout(row)

        self._login_url = QLineEdit()
        self._login_url.setPlaceholderText("https://example.com/login")
        self._login_url.setToolTip("로그인 폼이 있는 페이지 URL")

        self._login_id = QLineEdit()
        self._login_id.setPlaceholderText("아이디 / 이메일")

        self._login_pw = QLineEdit()
        self._login_pw.setPlaceholderText("비밀번호")
        self._login_pw.setEchoMode(QLineEdit.EchoMode.Password)

        # 비밀번호 표시/숨기기 토글
        pw_row = QHBoxLayout();
        pw_row.setSpacing(6)
        pw_row.addWidget(self._login_pw, 1)
        self._pw_toggle = QPushButton("👁")
        self._pw_toggle.setFixedSize(28, 28)
        self._pw_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pw_toggle.setCheckable(True)
        self._pw_toggle.setStyleSheet(f"""
                    QPushButton {{
                        background:{BG_PRIMARY}; color:{TEXT_MUTED};
                        border:1px solid {BORDER_LIGHT}; border-radius:4px; font-size:14px;
                    }}
                    QPushButton:checked {{ color:{ACCENT_LIGHT}; border-color:{ACCENT}; }}
                    QPushButton:hover {{ background:{BG_HOVER}; }}
                """)
        self._pw_toggle.toggled.connect(
            lambda on: self._login_pw.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        pw_row.addWidget(self._pw_toggle)
        pw_widget = QWidget();
        pw_widget.setLayout(pw_row)
        pw_widget.setStyleSheet("background:transparent;")

        self._login_method = QComboBox()
        self._login_method.addItems(["Form POST", "JavaScript Click", "OAuth2 Redirect", "Basic Auth Header"])
        self._login_method.setToolTip("로그인 처리 방식 선택")

        self._login_selector = QLineEdit()
        self._login_selector.setPlaceholderText("예: #login-btn  (선택사항 — 비워두면 자동 탐지)")
        self._login_selector.setToolTip("로그인 버튼 CSS 셀렉터 (Form POST 외 방식에서 사용)")

        self._login_success_kw = QLineEdit()
        self._login_success_kw.setPlaceholderText("예: 마이페이지, dashboard  (로그인 성공 판별 키워드)")
        self._login_success_kw.setToolTip("로그인 후 응답 페이지에서 찾을 성공 판별 키워드")

        _field("사이트 URL", self._login_url, lc_l)
        _field("아이디", self._login_id, lc_l)

        # 비밀번호 행은 toggle 버튼 포함이므로 직접 추가
        pw_outer = QHBoxLayout();
        pw_outer.setSpacing(10)
        pw_lbl = make_label("비밀번호", TEXT_SECONDARY, 12);
        pw_lbl.setFixedWidth(90)
        pw_outer.addWidget(pw_lbl)
        pw_outer.addWidget(pw_widget, 1)
        lc_l.addLayout(pw_outer)

        _field("로그인 방식", self._login_method, lc_l)
        lc_l.addWidget(Divider())
        _field("로그인 셀렉터", self._login_selector, lc_l)
        _field("성공 판별 키워드", self._login_success_kw, lc_l)
        bl.addWidget(lc_w)

        # ── 연결 상태 & 액션 카드 ────────────────────────
        ac_w, ac_l = card_widget("연결 상태")
        status_row = QHBoxLayout();
        status_row.setSpacing(12)

        self._login_status_dot = make_label("●", TEXT_MUTED, 14)
        self._login_status_lbl = make_label("미연결", TEXT_MUTED, 12)
        status_row.addWidget(self._login_status_dot)
        status_row.addWidget(self._login_status_lbl)
        status_row.addStretch()

        test_btn = outline_btn("연결 테스트")
        test_btn.clicked.connect(self._test_login)
        save_btn = action_btn("저장 & Credentials 등록")
        save_btn.clicked.connect(self._save_login)

        status_row.addWidget(test_btn)
        status_row.addWidget(save_btn)
        ac_l.addLayout(status_row)

        # 진행 로그 (인라인 mini-log)
        self._login_log = LogView()
        self._login_log.setFixedHeight(100)
        ac_l.addWidget(self._login_log)
        bl.addWidget(ac_w)

        # ── 저장된 Login Profile 목록 ────────────────────
        lp_w, lp_l = card_widget("저장된 Login Profile")
        lp_hdr = QHBoxLayout();
        lp_hdr.addStretch()
        clear_all_btn = outline_btn("전체 삭제")
        clear_all_btn.clicked.connect(self._clear_login_profiles)
        lp_hdr.addWidget(clear_all_btn)
        lp_l.addLayout(lp_hdr)

        self._profile_table = EqualSpacingTable(
            parent=self,
            row_height=32,
            col_padding=10,
            hscroll_handle=50,
        )
        self._profile_table.setColumnCount(5)
        self._profile_table.setHorizontalHeaderLabels(
            ["사이트 URL", "아이디", "방식", "상태", "액션"])
        self._profile_table.setFixedHeight(160)
        lp_l.addWidget(self._profile_table)
        bl.addWidget(lp_w)

        # ── 인증 로그 ────────────────────────────────────
        log_w, log_l = card_widget("인증 로그")
        self._auth_log = LogView();
        self._auth_log.setFixedHeight(130)
        log_l.addWidget(self._auth_log)
        bl.addWidget(log_w)
        self._auth_log.append_log("info", "인증 관리자 초기화 완료")
        self._auth_log.append_log("ok", "TLS 인증서 검증 활성화됨")
        self._auth_log.append_log("warn", "'Coupang Scraper' 세션 만료 임박 (7일 이하)")

    # ══════════════════════════════════════════════
    #  Login Info — 액션 메서드
    # ══════════════════════════════════════════════
    def _test_login(self):
        """연결 테스트: URL 유효성 확인 후 상태 업데이트"""
        url = self._login_url.text().strip()
        uid = self._login_id.text().strip()
        if not url or not uid:
            self._login_log.append_log("warn", "사이트 URL과 아이디를 입력하세요.")
            return
        self._login_status_dot.setStyleSheet(f"color:{AMBER}; font-size:14px; background:transparent; border:none;")
        self._login_status_lbl.setText("테스트 중...")
        self._login_status_lbl.setStyleSheet(f"color:{AMBER}; font-size:12px; background:transparent; border:none;")
        self._login_log.append_log("info", f"연결 테스트 시작: {url}")
        # 실제 환경에서는 worker/utility로 위임; 여기서는 UI 시뮬레이션
        QTimer.singleShot(1200, lambda: self._on_test_done(url))

    def _on_test_done(self, url):
        self._login_status_dot.setStyleSheet(f"color:{GREEN}; font-size:14px; background:transparent; border:none;")
        self._login_status_lbl.setText("연결 성공")
        self._login_status_lbl.setStyleSheet(f"color:{GREEN}; font-size:12px; background:transparent; border:none;")
        self._login_log.append_log("ok", f"로그인 페이지 도달 확인: {url}")
        self._auth_log.append_log("ok", f"연결 테스트 성공: {url}")

    def _save_login(self):
        """입력값 저장 → Profile Table 등록 → Credentials 탭 자동 반영"""
        url = self._login_url.text().strip()
        uid = self._login_id.text().strip()
        pw = self._login_pw.text()
        method = self._login_method.currentText()

        if not url or not uid or not pw:
            self._login_log.append_log("warn", "URL, 아이디, 비밀번호는 필수 항목입니다.")
            return

        # Profile Table에 추가
        r = self._profile_table.rowCount()
        self._profile_table.insertRow(r)
        vals = [url, uid, method, "유효"]
        colors = [ACCENT_LIGHT, TEXT_PRIMARY, TEXT_MUTED, GREEN]
        for col, (val, color) in enumerate(zip(vals, colors)):
            item = QTableWidgetItem(val)
            item.setForeground(QColor(color))
            self._profile_table.setItem(r, col, item)

        # 액션 버튼 (삭제)
        del_btn = QPushButton("삭제")
        del_btn.setFixedHeight(22)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton{{background:transparent;color:{RED};border:1px solid {RED};
            border-radius:4px;padding:0 8px;font-size:11px;}}
            QPushButton:hover{{background:#7f1d1d;}}
        """)
        del_btn.clicked.connect(lambda _, ri=r: self._profile_table.removeRow(ri))
        dw = QWidget();
        dl2 = QHBoxLayout(dw);
        dl2.setContentsMargins(4, 2, 4, 2);
        dl2.addWidget(del_btn)
        self._profile_table.setCellWidget(r, 4, dw)

        # Credentials 탭에도 Cookie 타입으로 자동 등록
        masked_pw = pw[:2] + "****"
        cred = {
            "name": f"{uid}@{url.split('//')[-1].split('/')[0]}",
            "type": "Cookie" if "Form" in method else "Basic Auth",
            "key": masked_pw,
            "expires": "세션",
            "status": "유효",
        }
        self._auth_rows.append(cred)
        self._insert_table_row(cred)

        self._login_log.append_log("ok", f"저장 완료: {uid} → {url}")
        self._auth_log.append_log("ok", f"Login Profile 등록됨: {uid}@{url}")

        # 입력 초기화
        self._login_url.clear()
        self._login_id.clear()
        self._login_pw.clear()
        self._login_selector.clear()
        self._login_success_kw.clear()

        # Credentials 탭으로 자동 이동
        self._tabs.setCurrentIndex(1)

    def _clear_login_profiles(self):
        self._profile_table.setRowCount(0)
        self._auth_log.append_log("warn", "Login Profile 전체 삭제됨")

    def _make_cred_table(self):
        headers = ["이름", "타입", "키 (마스킹)", "만료일", "상태", "액션"]
        t = EqualSpacingTable(
            parent=self,
            row_height=36,
            col_padding=8,
            hscroll_handle=50,
        )
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        return t

    def _insert_table_row(self, data: dict):

        r = self._cred_table.rowCount()
        self._cred_table.insertRow(r)
        self._cred_table.setRowHeight(r, 36)

        type_colors = {"API Key": BLUE, "Cookie": AMBER, "OAuth2": PURPLE, "Basic Auth": GREEN, "Bearer Token": RED}
        st_colors = {"유효": GREEN, "만료임박": AMBER, "만료": RED}

        vals_colors = [
            (data["name"], TEXT_PRIMARY),
            (data["type"], type_colors.get(data["type"], TEXT_SECONDARY)),
            (data["key"], TEXT_MUTED),
            (data["expires"], TEXT_SECONDARY),
        ]
        for col, (val, color) in enumerate(vals_colors):
            item = QTableWidgetItem(val)
            item.setForeground(QColor(color))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._cred_table.setItem(r, col, item)

        # 상태 칩
        sc = st_colors.get(data["status"], TEXT_MUTED)
        bg_map = {"유효": "#052e16", "만료임박": "#451a03", "만료": "#450a0a"}
        bg = bg_map.get(data["status"], BG_HOVER)
        status_lbl = QLabel(data["status"])
        status_lbl.setStyleSheet(f"color:{sc}; background:{bg}; border-radius:10px; padding:2px 10px; font-size:11px;")
        sw3 = QWidget();
        sl3 = QHBoxLayout(sw3);
        sl3.setContentsMargins(4, 0, 4, 0);
        sl3.addWidget(status_lbl)
        self._cred_table.setCellWidget(r, 4, sw3)

        # 삭제 버튼
        del_btn = QPushButton("삭제")
        del_btn.setFixedHeight(24)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton{{background:transparent;color:{RED};border:1px solid {RED};
            border-radius:4px;padding:0 8px;font-size:11px;}}
            QPushButton:hover{{background:#7f1d1d;}}
        """)
        del_btn.clicked.connect(lambda _, ri=r: self._delete_cred_row(ri))
        dw = QWidget();
        dl = QHBoxLayout(dw);
        dl.setContentsMargins(4, 2, 4, 2);
        dl.addWidget(del_btn)
        self._cred_table.setCellWidget(r, 5, dw)

    def _add_cred_dialog(self):

        dlg = QDialog(self)
        dlg.setWindowTitle("자격증명 추가")
        dlg.setFixedWidth(560)
        dlg.setStyleSheet(f"background:{BG_SECONDARY}; border:1px solid {BORDER};")

        vl = QVBoxLayout(dlg);
        vl.setContentsMargins(20, 16, 20, 16);
        vl.setSpacing(10)
        vl.addWidget(make_label("자격증명 추가", TEXT_PRIMARY, 13, True))
        vl.addWidget(Divider())

        name_row = QHBoxLayout()
        name_row.addWidget(make_label("이름", TEXT_SECONDARY, 12))
        name_inp = QLineEdit();
        name_inp.setPlaceholderText("예: Naver API")
        name_row.addWidget(name_inp, 1);
        vl.addLayout(name_row)

        type_row = QHBoxLayout()
        type_row.addWidget(make_label("타입", TEXT_SECONDARY, 12))
        type_cb = QComboBox();
        type_cb.addItems(["API Key", "Cookie", "OAuth2", "Basic Auth", "Bearer Token"])
        type_row.addWidget(type_cb, 1);
        vl.addLayout(type_row)

        key_row = QHBoxLayout()
        key_row.addWidget(make_label("키/값", TEXT_SECONDARY, 12))
        key_inp = QLineEdit();
        key_inp.setPlaceholderText("인증 키 또는 토큰")
        key_inp.setEchoMode(QLineEdit.EchoMode.Password)
        key_row.addWidget(key_inp, 1);
        vl.addLayout(key_row)

        exp_row = QHBoxLayout()
        exp_row.addWidget(make_label("만료일", TEXT_SECONDARY, 12))
        exp_inp = QLineEdit();
        exp_inp.setPlaceholderText("YYYY-MM-DD 또는 상시")
        exp_row.addWidget(exp_inp, 1);
        vl.addLayout(exp_row)

        btn_row = QHBoxLayout()
        cancel_btn = outline_btn("취소");
        cancel_btn.clicked.connect(dlg.close)
        ok_btn = action_btn("저장")

        def _do_add():
            masked = key_inp.text()[:4] + "****" if key_inp.text() else "****"
            data = {
                "name": name_inp.text().strip() or "새 자격증명",
                "type": type_cb.currentText(),
                "key": masked,
                "expires": exp_inp.text().strip() or "상시",
                "status": "유효",
            }
            self._auth_rows.append(data)
            self._insert_table_row(data)
            self._auth_log.append_log("ok", f"자격증명 추가됨: {data['name']} ({data['type']})")
            dlg.close()

        ok_btn.clicked.connect(_do_add)
        btn_row.addStretch();
        btn_row.addWidget(cancel_btn);
        btn_row.addWidget(ok_btn)
        vl.addLayout(btn_row)

        dlg.adjustSize()
        dlg.exec()

    def _delete_cred_row(self, row_idx):
        if 0 <= row_idx < self._cred_table.rowCount():
            name_item = self._cred_table.item(row_idx, 0)
            name_txt = name_item.text() if name_item else "?"
            self._cred_table.removeRow(row_idx)
            self._auth_log.append_log("warn", f"자격증명 삭제됨: {name_txt}")

    def _export_creds(self):
        path, _ = QFileDialog.getSaveFileName(self, "자격증명 내보내기", "credentials_encrypted.json", "JSON (*.json)")
        if not path: return
        export_data = {
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "note": "실제 배포 시 AES-256 암호화 적용 필요",
            "credentials": [{"name": r["name"], "type": r["type"], "expires": r["expires"]} for r in self._auth_rows],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        self._auth_log.append_log("ok", f"자격증명 내보내기 완료: {path}")
        QMessageBox.information(self, "완료", f"내보내기 완료:\n{path}")

    def _on_tls_toggle(self, state):
        if state == Qt.CheckState.Checked.value:
            self._cert_lbl.setText("● TLS 검증 활성화")
            self._cert_lbl.setStyleSheet(f"color:{GREEN}; font-size:12px;")
            self._auth_log.append_log("ok", "TLS 인증서 검증 활성화됨")
        else:
            self._cert_lbl.setText("● TLS 검증 비활성화")
            self._cert_lbl.setStyleSheet(f"color:{AMBER}; font-size:12px;")
            self._auth_log.append_log("warn", "TLS 인증서 검증 비활성화됨 — 보안 주의")


# ══════════════════════════════════════════════════════
#  TRAY WINDOW
# ══════════════════════════════════════════════════════
class TrayManager(QObject):
    """시스템 트레이 아이콘과 메뉴를 관리하는 클래스"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.tray_icon = QSystemTrayIcon(self.main_window)

        self.icon_path = utility.resource_path() + "\\" + "combine-harvester.ico"  # 아이콘

        # 아이콘 설정 (기존 소스에서 사용하던 아이콘 경로 적용)
        self.tray_icon.setIcon(QIcon(self.icon_path))  # 실제 아이콘 경로로 수정 필요

        self.setup_menu()

        # 트레이 아이콘 클릭 이벤트 연결 (더블 클릭 시 창 보이기 등)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def setup_menu(self):
        """트레이 우클릭 메뉴 구성"""
        tray_menu = QMenu()

        show_action = QAction("프로그램 열기", self.main_window)
        show_action.triggered.connect(self.restore_window)

        quit_action = QAction("종료", self.main_window)
        # QApplication.quit() 직접 연결 시 closeEvent를 우회하므로
        # 반드시 MainWindow.exit_app()을 통해 저장 후 종료해야 합니다.
        quit_action.triggered.connect(self.main_window.exit_app)

        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        """트레이 아이콘 클릭 시 동작 (더블클릭 등)"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.restore_window()

    def restore_window(self):
        """트레이에서 창을 화면으로 복구"""
        if self.main_window.isMinimized() or not self.main_window.isVisible():
            self.main_window.showNormal()
            self.main_window.show()
        self.main_window.activateWindow()
        self.main_window.raise_()

    def show_message(self, title, message):
        """트레이 알림 메시지 표시"""
        self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)


# ══════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DataCrawler v2.0")
        self.resize(1280, 800)
        self.setMinimumSize(960, 640)
        self._worker = None
        self._build()
        self.tray_manager = TrayManager(self)

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self._switch_page)
        layout.addWidget(self.sidebar)

        # ── 오른쪽 컨텐츠 영역: GlobalToolbar + QStackedWidget ──
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 공통 Toolbar (모든 페이지 공유)
        self.global_toolbar = GlobalToolbar()
        self.global_toolbar.start_requested.connect(self._start_crawl)
        self.global_toolbar.stop_requested.connect(self._stop_crawl)
        self.global_toolbar.reset_requested.connect(self._reset_all_pages)
        right_layout.addWidget(self.global_toolbar)

        self.stack = QStackedWidget()
        self.dashboard = DashboardPage()
        self.monitor_page = MonitorPage()
        self.schedule_page = SchedulerPage(); self.schedule_page.schedule_run.connect(self._start_crawl_from_schedule)
        self.stats_page = StatisticsPage()
        self.session_page = SessionSettingsPage()

        # Navigator 순서
        self.stack.addWidget(self.dashboard)  # 0
        self.stack.addWidget(self.monitor_page)  # 1
        self.stack.addWidget(self.schedule_page)  # 2
        self.stack.addWidget(self.stats_page)  # 3
        self.stack.addWidget(self.session_page)  # 4

        if request_info["auth"]:
            self.auth_page = AuthManagerPage()
            self.stack.addWidget(self.auth_page)  # 5

        # DashboardPage 생성 완료 후 LogView 및 실제 페이지 인스턴스 주입
        self.global_toolbar.set_log_view(self.dashboard.log_view)
        self.global_toolbar.set_pages(
            dashboard=self.dashboard,
            monitor_page=self.monitor_page,
            session_page=self.session_page,
            auth_page=getattr(self, 'auth_page', None),
        )

        right_layout.addWidget(self.stack, 1)

        # ── 메인 창 최하단 Progress bar ──────────────
        pb_w = QWidget();
        pb_w.setFixedHeight(41);
        pb_w.setStyleSheet(
            f"background:{BG_SECONDARY}; border-top:1px solid {BORDER};"
        )
        pbl = QHBoxLayout(pb_w)
        pbl.setContentsMargins(14, 0, 14, 0)
        pbl.setSpacing(10)
        self.prog_lbl = make_label("대기 중", TEXT_MUTED, 11)
        pbl.addWidget(self.prog_lbl)

        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setFixedHeight(4)
        self.prog_bar.setStyleSheet(f"""
            QProgressBar{{background:{BG_HOVER};border-radius:2px;border:none;}}
            QProgressBar::chunk{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 {ACCENT},stop:1 {ACCENT_LIGHT});border-radius:2px;}}
        """)
        pbl.addWidget(self.prog_bar, 1)

        self.prog_pct = make_label("0%", TEXT_MUTED, 11)
        self.prog_pct.setMinimumWidth(36)
        pbl.addWidget(self.prog_pct)

        right_layout.addWidget(pb_w)
        layout.addWidget(right_widget, 1)

    def _switch_page(self, idx):
        self.stack.setCurrentIndex(idx)
        if idx == 2:
            pass
        elif idx == 3:
            self.stats_page.reload()

    def _reset_all_pages(self):
        """
        _toggle_run 시작 시 호출 — MainWindow 가 소유한 실제 페이지를 초기화합니다.
        · 작업 진행 상태 → '수집 대기(step 0)' 표시
        · 실시간 수집 결과 테이블 초기화
        · 수집 결과 요약 카드 초기화
        · MonitorPage 초기화
        """
        self.dashboard._reset_dashboard()  # 실시간 수집 결과 + 통계 요약 초기화
        self.monitor_page._reset_monitor_page()  # 모니터링 페이지 초기화

    def _start_crawl(self, cfg: dict):
        self._launch_worker(cfg, job_name=cfg.get("job", "수동 실행"))

    def _start_crawl_from_schedule(self, cfg: dict):
        self.global_toolbar.set_running(True)
        self._launch_worker(cfg, job_name=cfg.get("job", "스케줄 실행"))
        # switch to dashboard to see progress
        self.stack.setCurrentIndex(0)
        for i, btn in enumerate(self.sidebar._btns):
            btn.setChecked(i == 0)

    def _launch_worker(self, cfg: dict, job_name="실행"):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            # 탰아웃 부여 — 이전 워ό어이 서브프로세스 종료할 여유를 줌 (UI 블로킹 최소화)
            self._worker.wait(1500)

        # 데이터 저장소(Store) 초기화 (이전 수집 행 데이터 삭제)
        store.clear_rows()
        self._worker = MultiprocessWorker(cfg, job_name)
        self._worker.new_row.connect(self.monitor_page.add_row)
        self._worker.new_row.connect(self.dashboard._add_realtime_row)
        self._worker.progress.connect(self.update_progress)
        self._worker.stats_update.connect(self.dashboard.update_stats)
        self._worker.log_message.connect(self.dashboard.log_view.append_log)
        self._worker.no_urls.connect(self._on_no_urls)   # [방법 A] URL 없음 즉시 감지
        self._worker.finished.connect(self._on_finished)
        self._worker.start()
        self.reset_progress()
        self.dashboard._update_step_ui(2)

    def _stop_crawl(self):
        """
        stop_requested 시그널 수신 — 워커 중단 요청만 전달합니다.

        [UI 블로킹 원인 제거]
        기존 wait(2000)은 UI 스레드를 최대 2초 블로킹했습니다.
        워커 스레드 종료 확인은 finished 시그널(_on_finished)이 담당하므로
        여기서는 블로킹 없이 stop() 플래그만 세팅합니다.
        """
        if self._worker and self._worker.isRunning():
            self._worker.stop()   # _running=False 세팅만 — wait() 호출 없음
            # 잔여 처리는 run() finally → finished.emit() → _on_finished() 순서로 처리됨
        self.dashboard.set_running(False)

    def _on_no_urls(self):
        """
        [방법 A] URL 리스트 생성 실패 즉시 처리 — 수동/스케줄 공통.

        worker.run() 에서 url_list 가 비어 있을 때 타이머 없이 즉시 emit 된다.
        finished 시그널은 발생하지 않으므로 UI 복원을 여기서 직접 처리한다.
        """
        self.global_toolbar.set_running(False)
        self.reset_progress()
        self.dashboard.set_running(False)
        self.dashboard._update_step_ui(0)

        msg = QMessageBox(self)
        msg.setWindowTitle("수집 대상 없음")
        msg.setText(
            "수집 대상 URL을 생성할 수 없습니다.\n"
            "URL 또는 수집 설정을 확인하고 다시 시도해 주세요."
        )
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setStyleSheet(f"""
            QMessageBox {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; }}
            QMessageBox QLabel {{ color:{TEXT_PRIMARY}; font-size:13px; }}
            QPushButton {{
                background:{ACCENT}; color:white; border:none;
                border-radius:5px; padding:5px 14px; font-size:12px;
            }}
            QPushButton:hover {{ background:{ACCENT_HOVER}; }}
        """)
        msg.exec()

    def _on_finished(self, task: dict, summary: dict):

        self.global_toolbar.set_running(False)
        self.reset_progress()
        self.dashboard.set_running(False)

        if summary.get("interrupted"):
            # Collection Interrupted: user manually stopped the crawl
            self.dashboard.log_view.append_log(
                "warn",
                f"수집 중단 (Collection Interrupted) — {self.result_table.rowCount()}건 수집 후 중지 "
                f"(소요: {summary['elapsed']}s)"
            )
            self.dashboard._update_step_ui(0)
            return

        # [방법 B] Scrapy 수집 자체가 실패하여 결과가 0건인 경우 감지
        # — URL 리스트는 정상이었으나 네트워크 차단·셀렉터 불일치 등으로 수집 결과가 없는 경우
        if summary.get("total", 0) == 0:
            self.dashboard.log_view.append_log("err", "크롤링 완료 — 수집된 데이터가 없습니다.")
            self.dashboard._update_step_ui(0)
            msg = QMessageBox(self)
            msg.setWindowTitle("수집 결과 없음")
            msg.setText(
                "수집이 완료되었으나 데이터가 없습니다.\n"
                "URL 또는 수집 설정을 확인하고 다시 시도해 주세요."
            )
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setStyleSheet(f"""
                QMessageBox {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; }}
                QMessageBox QLabel {{ color:{TEXT_PRIMARY}; font-size:13px; }}
                QPushButton {{
                    background:{ACCENT}; color:white; border:none;
                    border-radius:5px; padding:5px 14px; font-size:12px;
                }}
                QPushButton:hover {{ background:{ACCENT_HOVER}; }}
            """)
            msg.exec()
            return

        self.dashboard.log_view.append_log("info", f"크롤링 완료 — {self.result_table.rowCount()}건 수집")
        self.stats_page.reload()

        if task["extract"]["auto_save"]:
            self.dashboard._extract_result_table()

        QMessageBox.information(self, "success", "수집 완료.")

        self.dashboard._update_step_ui(0)

    def closeEvent(self, event):
        """X 버튼 클릭 시 — 트레이로만 숨김, 저장하지 않음"""
        if self.tray_manager.tray_icon.isVisible():
            self.hide()
            self.tray_manager.show_message("알림", "프로그램이 트레이에서 실행 중입니다.")
            event.ignore()  # 실제 종료가 아니므로 저장하지 않음
        else:
            # 트레이 아이콘이 없는 경우(예: 예외 상황)에만 여기서 저장 후 종료
            self._save_blueprint()
            event.accept()

    def exit_app(self):
        """
        실제 종료 진입점 — 트레이 메뉴 '종료' 또는 명시적 종료 시 호출.
        _blueprint 를 저장한 뒤 애플리케이션을 종료합니다.
        """
        self._save_blueprint()
        # closeEvent 가 다시 트레이로 숨기지 않도록 트레이 아이콘을 먼저 숨깁니다.
        self.tray_manager.tray_icon.hide()
        QApplication.instance().quit()

    def update_progress(self, done: int, total: int):
        pct = int(done / total * 100) if total else 0
        self.prog_bar.setValue(pct)
        self.prog_pct.setText(f"{pct}%")
        self.prog_lbl.setText(f"진행률 · {pct} / 100")

    def reset_progress(self):
        self.prog_bar.setValue(0)
        self.prog_pct.setText("0%")
        self.prog_lbl.setText("대기 중")

    def _save_blueprint(self):
        """_blueprint 를 BlueprintStorage 에 동기화하고 디스크에 저장합니다."""
        try:
            if request_info["auth"]:
                blueprint.update(request_info=request_info, dashboard_page=self.dashboard, monitor_page=self.monitor_page, session_page=self.session_page, auth_page=self.auth_page)
            else:
                blueprint.update(request_info=request_info, dashboard_page=self.dashboard, monitor_page=self.monitor_page, session_page=self.session_page)
            blueprint.save(request_info)
            print("[MainWindow] _blueprint 저장 완료")
        except Exception as e:
            print(f"[MainWindow] _blueprint 저장 실패: {e}")

# ══════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_QSS)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG_PRIMARY))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_SECONDARY))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_HOVER))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(BG_SECONDARY))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    ############################################################################################
    # 2. 소켓으로 이미 실행 중인지 체크
    socket = QLocalSocket()  # 서버
    socket.connectToServer(myappid)  # 확인용 ID를 통해 서버 연결

    # 3. [중요] 이미 실행 중이라면 여기서 즉시 종료!
    # 이 덕분에 ScrapyGUI가 생성되지 않아 트레이 아이콘이 추가로 생기지 않습니다.
    if socket.waitForConnected(500):
        print("이미 실행 중입니다. 기존 프로그램을 활성화합니다.")
        socket.disconnectFromServer()

        # return 대신 sys.exit()를 사용하여 프로세스 자체를 완전히 소멸시킵니다.
        sys.exit(0)  # 정상 종료
        # return

    # 4. 첫 실행인 경우에만 아래 코드가 실행됨
    local_server = QLocalServer()  # 클라이언트
    QLocalServer.removeServer(myappid)  # 이전 소켓 잔재 청소
    if not local_server.listen(myappid):  # 지정한 이름으로 서버 시작
        sys.exit(1)
    ############################################################################################

    win = MainWindow()

    # 다른 실행 시도가 감지되면 창을 띄우라고 연결
    local_server.newConnection.connect(win.tray_manager.restore_window)

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()