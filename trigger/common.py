# trigger/common.py
# trigger 패키지의 모든 서브모듈이 공유하는 싱글턴·테마 상수·설정값과,
# 2개 이상의 페이지에서 반복되던 로직을 통합한 모듈 함수들.

from copy import deepcopy
import socket

from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QMessageBox,
    QVBoxLayout, QHBoxLayout, QLineEdit, QCheckBox, QSpinBox,
    QComboBox, QWidget, QGridLayout,
)
from PyQt6.QtCore import Qt, QTimer

import db_conn
from conf import DataStore
from style import THEME, Parts, Divider, TagButton, BoundNoticeSpinBox, BoundNoticeDoubleSpinBox
from preprocess import DEFAULT_RULES, custom_rule_exists

store    = DataStore()
theme    = THEME()
parts    = Parts()

BG_PRIMARY    = theme.BG_PRIMARY
BG_SECONDARY  = theme.BG_SECONDARY
BG_HOVER      = theme.BG_HOVER
ACCENT        = theme.ACCENT
ACCENT_LIGHT  = theme.ACCENT_LIGHT
ACCENT_HOVER  = theme.ACCENT_HOVER
TEXT_PRIMARY  = theme.TEXT_PRIMARY
TEXT_SECONDARY= theme.TEXT_SECONDARY
TEXT_MUTED    = theme.TEXT_MUTED
BORDER        = theme.BORDER
BORDER_LIGHT  = theme.BORDER_LIGHT
GREEN         = theme.GREEN
AMBER         = theme.AMBER
RED           = theme.RED
BLUE          = theme.BLUE
PURPLE        = theme.PURPLE

# 상세 보기(_show_detail 계열)에서 값 유무에 따른 텍스트 색상
VALUE_COLORS = {0: ACCENT_LIGHT, 1: TEXT_PRIMARY, 2: GREEN, 3: RED}

# 로그 레벨("ok"/"err"/"warn"/"info")별 색상 — 하단 상태바(MainWindowTriggers)와
# 전체 로그 뷰어(LogViewerDialog)가 동일하게 사용
LOG_LEVEL_COLORS = {"ok": GREEN, "err": RED, "warn": AMBER, "info": ACCENT_LIGHT}

# DB 타입별 기본 포트 (추출 설정/스케줄 DB 저장 다이얼로그 공용)
DB_PORTS = {"MySQL": "3306", "PostgreSQL": "5432", "MongoDB": "27017"}

# 메인 창 self.stack(QStackedWidget)의 고정 페이지 인덱스 — 단일·다중 레이아웃
# 공용이며, 사이드바 "표시 순서"(NAV_ITEMS)와는 독립적인 값이다(다중은 표시
# 순서가 이 값과 다르게 재배열되어 있음 — layout/multi/sidebar.py 참고).
NAV_MONITOR = 0          # 대시보드 (구 모니터링)
NAV_REFINE = 1           # 데이터 정제
NAV_SCHEDULE = 2         # 스케줄러
NAV_STATS = 3            # 통계 분석
NAV_SESSION = 4          # 세션 설정
NAV_AUTH = 5             # 인증 관리 — 단일 전용, 인증 필요 블루프린트일 때만 조건부 추가
NAV_BLUEPRINT_LIST = 5   # 수집 목록 — 다중 전용 (단일의 NAV_AUTH와 값은 같으나 레이아웃별 배타적 사용)

# 스케줄(무인) 실행에서 정제 데이터 자동 저장 시 적용하는 규칙 — 원래는 모든
# 스케줄에 고정 적용되는 상수였으나(2026-07-17 이전), 이제 "새 스케줄 등록"
# 다이얼로그의 "⚙ 정제 규칙 설정"에서 스케줄별로 구성 가능해졌다. 이 상수는
# ①해당 다이얼로그를 아직 한 번도 열지 않은 신규 등록의 기본값, ②"refine_rules"
# 키가 없는 기존(구버전) 스케줄의 실행 시 폴백값으로만 쓰인다(_on_finished() 참고).
# "② 커스텀 정제 규칙 적용" 체크 시 자동으로 켜지는 조합(①③④)과는 별개 설정이다
# (2026-07-17, fill_null을 자동 연동 대상에서 제외하며 분리 — 이 상수의 fill_null
# 값은 그대로 유지해 이미 저장된 스케줄의 동작이 조용히 바뀌지 않도록 함).
SCHEDULED_REFINE_RULES = {
    "remove_null_row":  True,
    "custom_rule":      True,
    "trim_whitespace":  True,
    "remove_duplicate": True,
    "drop_columns":     False,
    "fill_null":        True,
    "cast_numeric":     False,
}

# "새 스케줄 등록"의 "저장 방식" 콤보 표시 문자열 → 내부 canonical 값 매핑.
# 구버전 schedules.json(필드 도입 이전)이나 "선택하세요" 잔존값 등 알 수 없는
# 값은 모두 "new"로 폴백한다 — 기존 파일/DB를 절대 건드리지 않는 가장
# 비파괴적인 기본 동작이기 때문.
_SAVE_TYPE_MAP = {"새로 만들기": "new", "덮어쓰기": "overwrite", "추가하기": "append"}


def _normalize_save_type(raw):
    """schedule_save_type 원문자열을 canonical 값("new"/"overwrite"/"append")으로 정규화."""
    return _SAVE_TYPE_MAP.get((raw or "").strip(), "new")

# 스케줄 정제 규칙 설정 다이얼로그의 신규 등록 기본값 — SCHEDULED_REFINE_RULES가
# 아니라 preprocess.DEFAULT_RULES(정제 엔진 자체의 기본값, MonitorPageSingle "②
# 정제 규칙 설정" 탭의 초기 체크 상태와 값이 동일)에서 파생시킨다(2026-07-17).
# custom_rule 값은 이 상수에서 시작점(폴백)만 가져올 뿐이다 — 실제 초기
# 체크 상태는 trigger/scheduler.py가 "대상 블루프린트" 콤보의 현재 선택값으로
# custom_rule_exists(seq_no)를 확인해 즉시 덮어쓴다(MonitorPageSingle과 동일한
# 규칙: 파일 없으면 무조건 False, 있으면 이 기본값/저장된 값을 유지).
# "값이 우연히 같다"가 아니라 같은 소스에서 나오도록 해, 향후 DEFAULT_RULES가
# 다시 바뀌어도 이 다이얼로그의 기본값이 자동으로 함께 맞춰지게 하기 위함.
# "제외 필드 지정"은 설정 항목 자체에서 빠지므로 키를 포함하지 않는다(Raw 수집
# 결과를 봐야 설정 가능한 규칙이라 무인 실행에는 애초에 노출하지 않음 —
# preprocess.DataRefiner는 누락된 키를 DEFAULT_RULES 기준으로 취급하므로 문제
# 없음). SCHEDULED_REFINE_RULES(실행 시 폴백값)와는 이제 별개 값이다 — fill_null이
# DEFAULT_RULES 기준 False인 반면 SCHEDULED_REFINE_RULES는 True로 유지된다.
SCHEDULED_REFINE_RULES_DIALOG_DEFAULT = {
    k: v for k, v in DEFAULT_RULES.items() if k != "drop_columns"
}


def _apply_task_settings(task: dict, *, collect: dict, session_page, monitor_page,
                          auth_page, job_name: str) -> None:
    """
    실행 태스크(task)에 공통 설정(딜레이/스레드/타임아웃/재시도/UA/쿠키/프록시/
    추출 설정/로그인 정보 오버라이드)을 채워 넣는다.
    `GlobalToolbarTriggers._actual_start()`가 self.task를 채울 때 사용하는
    로직 — 모듈 함수로 분리해 두어 향후 다른 호출부에서도 재사용 가능하다.
    collect: delay/threads/timeout/retry/auto_save/auto_save_source 키를 가진 dict —
    단일은 대시보드 위젯에서, 다중은 BlueprintPageBundle.collect_settings에서 값을
    읽어 호출부가 직접 구성한다("수집 & 저장 설정" 카드가 다중 대시보드에는 없으므로).
    """
    # 로그인 인증이면 인증 관리 페이지에 입력된 현재 값으로 로그인 정보를 덮어씀
    # (request_info.json 파일에는 저장하지 않고, 이번 실행 task에만 반영)
    auth_conditions = task.get("conditions") or {}
    if (auth_conditions.get("authMethod") == "login"
            and auth_page is not None
            and getattr(auth_page, "_auth_method", None) == "login"):
        auth_conditions["login"] = {
            "loginUrl": auth_page._login_url.text().strip() or None,
            "id": auth_page._login_id.text().strip() or None,
            "password": auth_page._login_pw.text() or None,
            "login_method": (auth_conditions.get("login") or {}).get("login_method"),
        }

    task["job"]        = job_name
    task["delay"]      = collect["delay"]
    task["threads"]    = collect["threads"]
    task["timeout"]    = collect["timeout"]
    task["retry"]      = collect["retry"]
    task["user_agent"] = session_page.ua_check.isChecked()
    task["cookie"]     = session_page.cookie_check.isChecked()
    task["proxy"] = {
        "enabled":       session_page._global_cb.isChecked(),
        # "자동 로테이션" 체크박스 제거 — 전역 프록시 사용 시 항상 로테이션을 사용한다.
        "rotate":        session_page._global_cb.isChecked(),
        "allow_ip_cnts": session_page._allow_ip_cnts.value(),
        "ip_list":       deepcopy(getattr(session_page, "_proxy_rows", [])),
    }
    task["extract"] = monitor_page.output_info["extract"]
    task["extract"]["auto_save"] = collect["auto_save"]
    task["extract"]["auto_save_source"] = collect["auto_save_source"]


def _reset_pages(dashboard, monitor_page) -> None:
    """대시보드·모니터링 페이지의 세션 상태를 함께 초기화한다 (여러 곳에서 반복되던 2줄 패턴)."""
    if dashboard is not None:
        dashboard._reset_dashboard()
    if monitor_page is not None:
        monitor_page._reset_monitor_page()


def _default_dialog_qss() -> str:
    """앱 전역에서 반복 사용되는 QDialog 스타일시트 (여러 다이얼로그에 그대로 복사돼 있던 블록)"""
    return f"""
        QDialog {{
            background:{BG_SECONDARY};
            border:1px solid {BORDER};
            border-radius:10px;
        }}
    """


def _default_msgbox_qss(label_font_size: int = 12) -> str:
    """앱 전역에서 반복 사용되는 QMessageBox 스타일시트 (여러 다이얼로그에 그대로 복사돼 있던 블록)"""
    return f"""
        QMessageBox {{ background:{BG_SECONDARY}; color:{TEXT_PRIMARY}; }}
        QMessageBox QLabel {{ color:{TEXT_PRIMARY}; font-size:{label_font_size}px; }}
        QPushButton {{
            background:{ACCENT}; color:white; border:none;
            border-radius:5px; padding:5px 14px; font-size:12px;
        }}
        QPushButton:hover {{ background:{ACCENT_HOVER}; }}
    """


def _show_db_conn_fail_dialog(parent, reason: str) -> None:
    """DB 연결 실패 안내 다이얼로그 (출력 설정 / 스케줄 등록 양쪽에서 동일하게 사용)"""
    msg = QMessageBox(parent)
    msg.setWindowTitle("연결 실패")
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setText("<b>DB 연결에 실패했습니다.</b>")
    msg.setInformativeText(reason)
    msg.setStyleSheet(_default_msgbox_qss(12))
    msg.exec()


def _sync_custom_rule_checkbox(seq_no, checkboxes) -> bool:
    """"커스텀 정제 규칙 적용" 체크박스를 refine/{seq_no}.py 존재 여부로
    맞춘다 — 파일이 없으면 checkboxes["custom_rule"]을 무조건 끄고, 있으면
    현재 체크 상태를 그대로 둔다(사용자가 남긴 선택 존중). 정제 페이지
    (탭 재진입마다, 수집 완료 시)와 스케줄 등록 다이얼로그("대상 블루프린트"
    변경 시)가 동일한 규칙을 공유한다.

    Returns:
        bool: 파일이 없어서(=missing) 체크를 껐으면 True, 아니면 False.
    """
    missing = bool(seq_no) and not custom_rule_exists(seq_no)
    if missing:
        cb = checkboxes.get("custom_rule")
        if cb is not None:
            cb.setChecked(False)
    return missing


def _handle_custom_rule_toggle(state, seq_no, checkboxes, warn_fn) -> None:
    """"커스텀 정제 규칙 적용" 체크박스의 stateChanged 공통 처리 — 켜려는
    시도인데 refine/{seq_no}.py가 없으면 체크를 되돌리고 warn_fn()을 호출한 뒤
    끝내고(drop_columns 체크박스의 검증 패턴과 동일, style.py의
    _on_drop_columns_toggled 참고), 있으면 규칙 ①③④(remove_null_row/
    trim_whitespace/remove_duplicate)를 자동으로 켠다. fill_null은 대상에서
    제외된다(커스텀 규칙이 정규화한 데이터라도 결측값 치환 여부는 별도로
    판단해야 하기 때문). 정제 페이지(trigger/monitor.py)와 스케줄 등록
    다이얼로그(trigger/scheduler.py)가 공유한다 — 두 호출부는 seq_no 조회
    방식과 경고 title 조회 방식이 서로 달라(_active_blueprint_info() vs
    BlueprintStorage().get()) warn_fn을 인자 없는 콜백으로 받는다."""
    if state != Qt.CheckState.Checked.value:
        return
    # 경고가 뜨기 전에 체크박스를 먼저 되돌린다 — setChecked(False)가 이
    # 핸들러를 재귀 호출하지만 state가 Unchecked라 위 guard에서 곧바로
    # return되므로 안전하다.
    if _sync_custom_rule_checkbox(seq_no, checkboxes):
        warn_fn()
        return
    for key in ("remove_null_row", "remove_duplicate", "trim_whitespace"):
        cb = checkboxes.get(key)
        if cb is not None:
            cb.setChecked(True)


def _warn_custom_rule_missing(parent, title) -> None:
    """"커스텀 정제 규칙 적용"에 필요한 정제 스크립트가 없을 때 공통으로 띄우는
    경고 — 정제 페이지(trigger/monitor.py)와 스케줄 등록 다이얼로그
    (trigger/scheduler.py) 양쪽에서 동일한 문구로 재사용한다."""
    QMessageBox.warning(
        parent, "정제 규칙 없음",
        f"'{title}'에 등록된 사용자 정의 정제 규칙이 존재하지 않습니다.\n"
        f"'커스텀 정제 규칙 적용'을 사용하려면 정제 스크립트 파일을 "
        f"먼저 등록해야 합니다."
    )


def _show_no_data_dialog(parent, url_count, skipped, elapsed) -> None:
    """'수집 결과 없음' 안내 다이얼로그 (단일/다중 _on_finished에서 동일하게 사용)"""
    msg = QMessageBox(parent)
    msg.setWindowTitle("수집 결과 없음")
    msg.setText("수집이 완료되었으나 데이터가 없습니다.\n"
                f"생성된 URL: {url_count}개 · URL 불일치 skip: {skipped}건 · 소요 시간: {elapsed}s\n"
                "URL 또는 수집 설정을 확인하고 다시 시도해 주세요.")
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setStyleSheet(_default_msgbox_qss(13))
    msg.exec()


def _stop_worker_if_running(worker) -> None:
    """실행 중인 워커가 있으면 중단 신호를 보내고 최대 1.5초 대기한다 (여러 곳에 반복되던 가드)."""
    if worker and worker.isRunning():
        worker.stop()
        worker.wait(1500)


def _after_delay_unless_cancelled(is_cancelled, fn, delay_ms: int = 1000) -> None:
    """delay_ms 뒤 is_cancelled()가 False면 fn()을 실행한다 — 정지 버튼 등으로 시작이
    취소된 경우 지연 중이던 콜백이 뒤늦게 실행되는 것을 막는다. 단일 '_toggle_run→
    _step_to_setting→_actual_start'와 다중 '_start_batch'의 시작 연출(수집 대기→수집
    세팅→데이터 수집 단계 표시)이 공유하는 타이머 유틸."""
    QTimer.singleShot(delay_ms, lambda: None if is_cancelled() else fn())


def _get_log_manager(widget):
    """
    최상위 MainWindowSingle의 log_manager(LogViewerDialog 싱글턴)를 반환한다.
    QWidget.window()는 위젯 트리 최상단 QMainWindow를 반환하므로
    별도의 부모 순회 없이 안전하게 참조할 수 있다.
    log_manager가 아직 준비되지 않은 경우 None을 반환한다.
    (SessionSettingsPageTriggers/AuthManagerPageTriggers에 동일하게 복제돼 있던 메서드를 통합)
    """
    return getattr(widget.window(), 'log_manager', None)


def _build_collect_settings_fields(defaults: dict, *, single_row: bool = False) -> tuple:
    """"수집 설정" 위젯(Delay/Threads/Timeout/Retry/Auto Save)을 만들어 (카드 위젯,
    위젯 딕셔너리)를 반환한다. defaults: delay/threads/timeout/retry/auto_save/
    auto_save_source 키를 가진 dict — 값만 채울 뿐 자체 기본값 로직은 갖지 않는다
    (_build_output_file_page와 동일한 패턴). 원래 DashboardPageSingle._build()의
    "수집 & 저장 설정" 카드(card1)에 있던 위젯 구성을 그대로 옮겨, 상시 페이지(단일
    대시보드)와 매번 새로 열리는 다이얼로그(다중 "⚙ 수집 설정") 양쪽에서 재사용한다.
    렌더링 안전 상한(apply_render_safety_limits) 적용 여부는 호출부가 반환된
    delay_spin/thread_spin에 대해 직접 판단한다 — 대상 블루프린트 정보를 이 함수는
    모르기 때문이다.
    single_row: Delay/Threads/Timeout/Retry를 한 줄에 배치할지(True) 기존처럼
    두 줄(Delay+Threads / Timeout+Retry)로 배치할지(False, 기본값). 단일 대시보드
    카드는 폭이 320px로 고정돼 있어 한 줄에 4개 필드가 들어가지 않으므로 기본값을
    유지하고, 폭이 넉넉한 다중 "⚙ 수집 설정" 다이얼로그만 True로 호출한다."""
    card = QWidget()
    c1 = QVBoxLayout(card)
    c1.setContentsMargins(0, 0, 0, 0)
    c1.setSpacing(8)

    delay_spin = BoundNoticeDoubleSpinBox()
    delay_spin.setRange(0.5, 10.0)
    delay_spin.setValue(defaults.get("delay", 0.5))
    delay_spin.setSingleStep(0.5)
    delay_spin.setDecimals(1)
    delay_spin.setToolTip("요청 간 대기 시간 (기본 0.5s)")

    thread_spin = BoundNoticeSpinBox()
    thread_spin.setRange(1, 16)
    thread_spin.setValue(defaults.get("threads", 4))
    thread_spin.setToolTip("병렬 수집 스레드 수")

    timeout_spin = QSpinBox()
    timeout_spin.setRange(1, 60)
    timeout_spin.setValue(defaults.get("timeout", 10))
    timeout_spin.setToolTip("요청 최대 대기 시간")

    retry_spin = QSpinBox()
    retry_spin.setRange(0, 5)
    retry_spin.setValue(defaults.get("retry", 2))
    retry_spin.setToolTip("실패 시 재시도 횟수 (기본 2회)")

    r1 = QHBoxLayout()
    r1.setSpacing(8)
    r1.addWidget(parts.make_label("Delay(s)", TEXT_SECONDARY, 12))
    r1.addWidget(delay_spin)
    r1.addSpacing(6)
    r1.addWidget(parts.make_label(" Threads", TEXT_SECONDARY, 12))
    r1.addWidget(thread_spin)
    r1.addSpacing(6)

    if single_row:
        r1.addWidget(parts.make_label("Timeout(s)", TEXT_SECONDARY, 12))
        r1.addWidget(timeout_spin)
        r1.addWidget(parts.make_label("   Retry", TEXT_SECONDARY, 12))
        r1.addWidget(retry_spin)
        r1.addSpacing(6)
        r1.addStretch()
        c1.addLayout(r1)
    else:
        r1.addStretch()
        c1.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setSpacing(8)
        r2.addWidget(parts.make_label("Timeout(s)", TEXT_SECONDARY, 12))
        r2.addWidget(timeout_spin)
        r2.addWidget(parts.make_label("   Retry", TEXT_SECONDARY, 12))
        r2.addWidget(retry_spin)
        r2.addSpacing(6)
        r2.addStretch()
        c1.addLayout(r2)

    c1.addSpacing(6)
    c1.addWidget(Divider())
    c1.addSpacing(6)

    r3 = QHBoxLayout()
    r3.setSpacing(8)
    auto_save_chk = QCheckBox("Auto Save")
    auto_save_chk.setToolTip("수집 완료 시 선택된 출력 대상(FILE/DB)에 자동 저장")
    auto_save_chk.setChecked(defaults.get("auto_save", True))
    r3.addWidget(auto_save_chk)
    r3.addSpacing(6)

    auto_src_raw_btn = TagButton("RAW")
    auto_src_ref_btn = TagButton("정제")
    auto_src_ref_btn.setToolTip(
        "'② 정제 규칙 설정' 탭에서 마지막으로 설정해 둔 규칙이 그대로 적용됩니다.\n"
        "이번 수집을 위해 규칙을 다시 확인하지 않았다면 의도한 결과가 아닐 수 있습니다."
    )
    is_refined_default = defaults.get("auto_save_source", "raw") == "refined"
    auto_src_raw_btn.setChecked(not is_refined_default)
    auto_src_ref_btn.setChecked(is_refined_default)
    r3.addWidget(auto_src_raw_btn)
    r3.addWidget(auto_src_ref_btn)
    r3.addStretch()
    c1.addLayout(r3)

    def _on_auto_save_toggled(checked: bool) -> None:
        auto_src_raw_btn.setEnabled(checked)
        auto_src_ref_btn.setEnabled(checked)

    def _on_source_selected(select_refined: bool) -> None:
        auto_src_raw_btn.setChecked(not select_refined)
        auto_src_ref_btn.setChecked(select_refined)

    auto_save_chk.toggled.connect(_on_auto_save_toggled)
    auto_src_raw_btn.clicked.connect(lambda: _on_source_selected(False))
    auto_src_ref_btn.clicked.connect(lambda: _on_source_selected(True))
    _on_auto_save_toggled(auto_save_chk.isChecked())

    widgets = {
        "delay_spin": delay_spin, "thread_spin": thread_spin,
        "timeout_spin": timeout_spin, "retry_spin": retry_spin,
        "auto_save_chk": auto_save_chk,
        "auto_src_raw_btn": auto_src_raw_btn, "auto_src_ref_btn": auto_src_ref_btn,
    }
    return card, widgets


def _build_db_settings_fields(grid: QGridLayout, db_info: dict) -> dict:
    """DB Type/Host/Port/... 8행 그리드를 만들어 grid에 채우고 위젯 딕셔너리를 반환한다.
    db_info: db_env/host/port/database/schema/user/password/save_data_nm 키(값은 이미
    호출부에서 등록/수정 모드에 맞게 해석된 상태여야 함)."""
    def _lbl(t):
        return parts.make_label(t, TEXT_SECONDARY, 11)

    def _inp(txt="", ph=""):
        e = QLineEdit(txt)
        e.setPlaceholderText(ph)
        return e

    db_type = QComboBox()
    db_type.addItems(["MySQL", "PostgreSQL", "MongoDB"])
    db_type.setCurrentText(db_info.get("db_env") or "MySQL")
    widgets = {
        "db_type": db_type,
        "host":    _inp(txt=db_info.get("host") or ""),
        "port":    _inp(txt=db_info.get("port") or ""),
        "name":    _inp(db_info.get("database") or ""),
        "schema":  _inp(db_info.get("schema") or ""),
        "user":    _inp(db_info.get("user") or ""),
        "password": _inp(db_info.get("password") or ""),
        "save_data_nm": _inp(db_info.get("save_data_nm") or ""),
    }
    widgets["password"].setEchoMode(QLineEdit.EchoMode.Password)

    for row_i, (label, widget) in enumerate([
        ("DB Type", widgets["db_type"]), ("HOST", widgets["host"]), ("PORT", widgets["port"]),
        ("DB Name", widgets["name"]), ("SCHEMA", widgets["schema"]),
        ("USER", widgets["user"]), ("PASSWORD", widgets["password"]), ("DATA Name", widgets["save_data_nm"]),
    ]):
        grid.addWidget(_lbl(label), row_i, 0)
        grid.addWidget(widget, row_i, 1)

    def _on_db_type_changed(t):
        widgets["port"].setText(DB_PORTS.get(t, ""))
        widgets["port"].setCursorPosition(0)
    db_type.currentTextChanged.connect(_on_db_type_changed)

    return widgets


def _build_output_file_page(defaults: dict, dlg) -> tuple:
    """FILE 설정 페이지(경로/파일명/포맷·인코딩·구분자)를 만들어 (페이지 위젯,
    위젯 딕셔너리, CSV 전용 필드 표시 토글 콜백)을 반환한다. defaults의 각 값은
    호출부가 이미 자신의 등록/수정 모드 규칙에 맞게 완전히 해석해 넘겨야 한다 —
    이 함수는 값을 그대로 위젯에 채울 뿐 자체적인 기본값 로직을 갖지 않는다
    (출력 설정 / 스케줄 등록 다이얼로그에 통째로 복제돼 있던 FILE 페이지 구성을 통합
    — DB 페이지 쪽 _build_db_settings_fields와 동일한 패턴).
    "저장 완료 후 폴더 열기" 체크박스는 출력 설정 다이얼로그에만 있고 스케줄
    다이얼로그에는 없으므로(무인 실행은 항상 무시 — _extract_result_table의
    `not silent` 조건 참고) 이 함수에 포함하지 않는다 — 필요한 호출부가
    file_page.layout()에 직접 addWidget()한다.
    fmt 변경 시 다이얼로그 리사이즈까지 하려면 호출부가 반환된 토글 콜백을
    fmt_combo.currentTextChanged에 직접 연결한 뒤 자신의 리사이즈 로직을 이어 호출한다."""
    file_page = QWidget()
    fp = QVBoxLayout(file_page)
    fp.setContentsMargins(14, 14, 14, 14)
    fp.setSpacing(10)

    path_lay = QHBoxLayout()
    path_lay.setSpacing(8)
    path_lay.addWidget(parts.make_label("경로", TEXT_SECONDARY, 12))
    path_edit = QLineEdit(defaults.get("file_path") or "")
    path_edit.setReadOnly(True)
    path_lay.addWidget(path_edit, 1)
    browse_btn = parts.outline_btn("Browse")
    browse_btn.setFixedWidth(72)

    def _browse():
        folder = QFileDialog.getExistingDirectory(dlg, "저장 폴더 선택", path_edit.text() or "")
        if folder:
            path_edit.setText(folder)

    browse_btn.clicked.connect(_browse)
    path_lay.addWidget(browse_btn)
    fp.addLayout(path_lay)

    file_nm_lay = QHBoxLayout()
    file_nm_lay.setSpacing(10)
    file_nm_lay.addWidget(parts.make_label("파일명", TEXT_SECONDARY, 12))
    file_nm = QLineEdit(defaults.get("file_name") or "")
    file_nm_lay.addWidget(file_nm)
    fp.addLayout(file_nm_lay)

    opt_lay = QHBoxLayout()
    opt_lay.setSpacing(10)
    opt_lay.addWidget(parts.make_label("형식", TEXT_SECONDARY, 12))
    fmt_combo = QComboBox()
    fmt_combo.addItems(["CSV", "JSON", "Excel"])
    fmt_combo.setCurrentText(defaults.get("file_format") or "")
    opt_lay.addWidget(fmt_combo)
    opt_lay.addSpacing(10)

    enc_widget = QWidget()
    enc_lay = QHBoxLayout(enc_widget)
    enc_lay.setContentsMargins(0, 0, 0, 0)
    enc_lay.setSpacing(10)
    enc_combo = QComboBox()
    enc_combo.addItems(["UTF-8", "UTF-8 BOM", "CP949 (EUC-KR)"])
    enc_combo.setCurrentText(defaults.get("file_encoding") or "")
    enc_lay.addWidget(parts.make_label("인코딩", TEXT_SECONDARY, 12))
    enc_lay.addWidget(enc_combo)
    opt_lay.addWidget(enc_widget)
    opt_lay.addSpacing(10)

    delim_widget = QWidget()
    delim_lay = QHBoxLayout(delim_widget)
    delim_lay.setContentsMargins(0, 0, 0, 0)
    delim_lay.setSpacing(10)
    csv_delimeter = QLineEdit(defaults.get("file_delimiter") or "")
    delim_lay.addWidget(parts.make_label("구분자", TEXT_SECONDARY, 12))
    delim_lay.addWidget(csv_delimeter)
    opt_lay.addWidget(delim_widget)
    opt_lay.addStretch()
    fp.addLayout(opt_lay)

    def _toggle_csv_fields(fmt_text: str):
        is_csv = (fmt_text == "CSV")
        enc_widget.setVisible(is_csv)
        delim_widget.setVisible(is_csv)

    widgets = {
        "path_edit": path_edit, "file_nm": file_nm, "fmt_combo": fmt_combo,
        "enc_combo": enc_combo, "csv_delimeter": csv_delimeter,
    }
    return file_page, widgets, _toggle_csv_fields


def _wire_db_test_button(test_btn, test_result_lbl, widgets: dict, parent_dialog) -> None:
    """TEST CONNECTION 버튼 클릭 시 공통 DB 연결 테스트 로직을 수행한다
    (출력 설정 / 스케줄 등록 다이얼로그에서 통째로 복제돼 있던 로직을 통합)."""
    def _set_result(text: str, color: str) -> None:
        test_result_lbl.setText(text)
        test_result_lbl.setStyleSheet(f"color:{color}; font-size:11px;")

    def _test_conn():
        host = widgets["host"].text().strip() or "localhost"
        try:
            port = int(widgets["port"].text().strip())
        except ValueError:
            _set_result("⚠ 포트 번호가 올바르지 않습니다", AMBER)
            _show_db_conn_fail_dialog(
                parent_dialog, "포트 번호에 숫자가 아닌 값이 입력되어 있습니다.\n올바른 포트 번호를 입력하세요."
            )
            return
        _set_result("⏳ 연결 중...", TEXT_MUTED)
        test_btn.setEnabled(False)
        QApplication.processEvents()
        info = {
            "db_env": widgets["db_type"].currentText(), "host": host, "port": str(port),
            "database": widgets["name"].text().strip(), "schema": widgets["schema"].text().strip(),
            "user": widgets["user"].text().strip(), "password": widgets["password"].text(),
            "save_data_nm": widgets["save_data_nm"].text().strip() or "results",
        }
        try:
            ok, reason = db_conn._check_db_connect_info(info)
            if ok:
                _set_result(f"✅ {host}:{port} 연결 성공", GREEN)
            else:
                _set_result("❌ 연결 실패", RED)
                _show_db_conn_fail_dialog(parent_dialog, reason)
        except ImportError:
            try:
                with socket.create_connection((host, port), timeout=3):
                    _set_result(f"✅ {host}:{port} 소켓 연결 성공 (DB 드라이버 미설치)", AMBER)
            except OSError as e:
                _set_result("❌ 연결 실패", RED)
                _show_db_conn_fail_dialog(
                    parent_dialog,
                    f"DB 드라이버가 설치되어 있지 않아 소켓 연결을 시도했으나 실패했습니다.\n\n원인: {e}"
                )
        except Exception as e:
            _set_result("❌ 연결 실패", RED)
            _show_db_conn_fail_dialog(parent_dialog, str(e))
        finally:
            test_btn.setEnabled(True)

    test_btn.clicked.connect(_test_conn)
