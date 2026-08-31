# layout/scheduler.py
# 스케줄러 페이지 — Single/Multi가 동일 클래스를 그대로 공유한다(대응 클래스 없음).

import os
import utility
from datetime import datetime

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QTableWidgetItem
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor

from conf import BlueprintStorage
from trigger import SchedulerPageTriggers
from style import EqualSpacingTable
from .common import (
    store, parts, build_scroll_body,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_LIGHT, AMBER, GREEN, BLUE, PURPLE, RED,
)


class SchedulerPage(QWidget, SchedulerPageTriggers):

    schedule_run = pyqtSignal(dict)

    def __init__(self):
        super().__init__()

        self.root_path = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
        self.app_dir = os.path.join(self.root_path, utility.get_app_name())
        self.file_path = os.path.join(self.app_dir, "schedules.json")
        self.default_source = os.path.join(utility.resource_path(), "schedules.json")

        self._timers: dict[int, QTimer] = {}
        self._build()
        self._load_schedules_from_json()   # ← 앱 시작 시 저장된 스케줄 로드
        self._refresh_table()
        self.sched_task = {}
        self.session_page = None  # MainWindowSingle가 실제 SessionSettingsPage 인스턴스를 주입

    # ────────────────────────────────────────────────
    def _build(self):

        bl = build_scroll_body(self, spacing=12)

        # ── 본문(bl) 내 상단 버튼 영역 추가 ───────────────
        btn_container = QHBoxLayout()
        btn_container.addStretch()  # 왼쪽 여백을 꽉 채워 버튼을 오른쪽으로 밀어냄
        add_btn = parts.action_btn("+ 작업 추가")
        add_btn.clicked.connect(lambda: self._manage_schedule_task(sched_task="등록"))
        btn_container.addWidget(add_btn)
        bl.addLayout(btn_container)  # bl 레이아웃의 가장 처음에 추가됨
        # ──────────────────────────────────────────────

        # ══ Schedule Table ════════════════════════════
        tw, tl = parts.card_widget("스케줄 목록")
        self.sched_table = EqualSpacingTable(parent=self, row_height=36, col_padding=10, hscroll_handle=50)
        self.sched_table.setColumnCount(8)
        self.sched_table.setHorizontalHeaderLabels(
            ["NO", "Task Name", "대상", "URL", "Execution Time", "Next Runtime", "Status", "Action"])
        tl.addWidget(self.sched_table)
        bl.addWidget(tw, 1)

        # ── Next Task ─────────────────────────────────
        nrw, nrl = parts.card_widget("Next Task")
        self.next_task_lbl = parts.make_label("등록된 스케줄 없음", TEXT_MUTED, 18, False)
        self.next_task_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        nrl.addWidget(self.next_task_lbl)
        bl.addWidget(nrw)

        self._cd_timer = QTimer()
        self._cd_timer.timeout.connect(self._update_countdown)
        self._cd_timer.start(1000)


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
            idx_item = QTableWidgetItem()
            idx_item.setData(Qt.ItemDataRole.DisplayRole, idx)
            idx_item.setForeground(QColor(TEXT_MUTED))
            self.sched_table.setItem(r, 0, idx_item)

            # Task Name
            name_item = QTableWidgetItem(s["task_nm"])
            name_item.setForeground(QColor(TEXT_PRIMARY))
            self.sched_table.setItem(r, 1, name_item)

            # 대상 (스케줄이 지정한 블루프린트의 title)
            target_bp = BlueprintStorage().get(s.get("seq_no"))
            target_item = QTableWidgetItem(target_bp.get("title") if target_bp else "—")
            target_item.setForeground(QColor(TEXT_SECONDARY))
            self.sched_table.setItem(r, 2, target_item)

            # URL / Execution Time (설정 주기 문자열)
            vals = [s.get("callback_url", ""), s["schedule"]["exec_str"]]
            colors = [ACCENT_LIGHT, TEXT_PRIMARY]
            for col, (val, color) in enumerate(zip(vals, colors), start=3):
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
            self.sched_table.setItem(r, 5, nr_item)

            # Status
            status = s["schedule"]["status"]
            si = QTableWidgetItem(status)
            si.setForeground(QColor(STATUS_COLOR.get(status, TEXT_MUTED)))
            self.sched_table.setItem(r, 6, si)

            # Action (수정 / 삭제)
            action_w = QWidget()
            action_w.setStyleSheet("background:transparent;")
            al = QHBoxLayout(action_w)
            al.setContentsMargins(4, 2, 4, 2)
            al.setSpacing(4)
            edit_btn = parts.outline_btn("✎ 수정")
            edit_btn.setFixedHeight(28)
            edit_btn.setStyleSheet(edit_btn.styleSheet() + f" font-size:11px; padding:3px 10px; color:{ACCENT_LIGHT};")
            edit_btn.clicked.connect(lambda _, i=idx: self._manage_schedule_task(sched_task="수정", idx=i))
            del_btn = parts.outline_btn("삭제")
            del_btn.setFixedHeight(28)
            del_btn.setStyleSheet(del_btn.styleSheet() + f" font-size:11px; padding:3px 10px; color:{RED};")
            del_btn.clicked.connect(lambda _, i=idx: self._delete_schedule(i))
            al.addWidget(edit_btn)
            al.addWidget(del_btn)
            self.sched_table.setCellWidget(r, 7, action_w)
