# trigger/dashboard.py
# DashboardPageSingle의 테이블·필터·내보내기 메서드(DashboardPageTriggers).

import csv

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from .common import (
    ACCENT_LIGHT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, GREEN, AMBER, RED, BLUE,
)


class DashboardPageTriggers:
    """DashboardPageSingle의 테이블·필터·내보내기 메서드"""

    def _on_auto_save_toggled(self, checked: bool):
        """자동 저장 체크박스 — 꺼져 있으면 저장 대상(RAW/정제) 토글은 의미가 없어 비활성화"""
        self.auto_src_raw_btn.setEnabled(checked)
        self.auto_src_ref_btn.setEnabled(checked)

    def _on_auto_save_source_selected(self, is_refined: bool):
        """자동 저장 대상(RAW/정제) 토글 — 상호 배타 선택"""
        self.auto_src_raw_btn.setChecked(not is_refined)
        self.auto_src_ref_btn.setChecked(is_refined)

    def add_row(self, row: dict):
        """워커 new_row 시그널 수신 → 대시보드 수집 모니터링 테이블에 행 추가"""
        if not row or "resp_info" not in row:
            return
        resp_info = row["resp_info"]
        data = resp_info.get("data")
        if not data or isinstance(data, dict):
            return

        target_url = resp_info.get("url", "")
        self.monitor_table.setSortingEnabled(False)
        current_row = self.monitor_table.rowCount()
        self.monitor_table.insertRow(current_row)

        STATUS_COLOR = {"200": GREEN, "404": RED, "429": AMBER, "500": RED, "301": BLUE}
        vals = [
            current_row,
            target_url,
            resp_info.get("status", ""),
            resp_info.get("ip_address", ""),
            resp_info.get("user_agents", ""),
            resp_info.get("cookies", ""),
            resp_info.get("pure_latency", ""),
            resp_info.get("total_latency", ""),
            row.get("job_name", ""),
        ]
        colors = [
            TEXT_MUTED, TEXT_MUTED,
            STATUS_COLOR.get(str(resp_info.get("status", "")), TEXT_SECONDARY),
            TEXT_PRIMARY, TEXT_PRIMARY, TEXT_PRIMARY,
            TEXT_PRIMARY, ACCENT_LIGHT, TEXT_MUTED,
        ]
        for col, (val, color) in enumerate(zip(vals, colors)):
            item = QTableWidgetItem()
            if isinstance(val, (int, float)):
                item.setData(Qt.ItemDataRole.DisplayRole, val)
            else:
                item.setText(str(val))
            item.setForeground(QColor(color))
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.monitor_table.setItem(current_row, col, item)

        self.monitor_table.setSortingEnabled(True)
        self.mon_row_count_lbl.setText(f"{self.monitor_table.rowCount()} rows")

        ERROR_STATUSES = {"404", "500", "503", "502", "429"}
        if str(resp_info.get("status", "")).strip() in ERROR_STATUSES:
            self._session_error_count += 1
        try:
            self._session_latency_sum += float(resp_info.get("pure_latency", ""))
            self._session_latency_count += 1
        except (ValueError, TypeError):
            pass
        self._refresh_session_stats()

    def _refresh_session_stats(self):
        """누적된 세션 집계(에러 수/지연시간 합)로 통계 카드 갱신 — 테이블 전체 재순회 없음"""
        total_rows = self.monitor_table.rowCount()
        errors = self._session_error_count
        completed = total_rows - errors
        avg_latency = (
            f"{self._session_latency_sum / self._session_latency_count:.2f}s"
            if self._session_latency_count else "—"
        )
        self.s_total.update_value(completed)
        self.s_err.update_value(errors)
        self.s_pages.update_value(total_rows)
        self.s_speed.update_value(avg_latency)

    def _export_monitor_csv(self):
        """수집 모니터링 테이블을 CSV로 내보내기"""
        path, _ = QFileDialog.getSaveFileName(self, "CSV 저장", "crawl_monitor.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["NO", "URL", "STATUS", "IP_ADDRESS", "USER-AGENT",
                        "COOKIES", "LATENCY(PURE)", "LATENCY(TOTAL)", "JOB_NAME"])
            for r in range(self.monitor_table.rowCount()):
                w.writerow([
                    self.monitor_table.item(r, c).text()
                    if self.monitor_table.item(r, c) else ""
                    for c in range(9)
                ])
        QMessageBox.information(self, "완료", f"저장 완료:\n{path}")

    def update_stats(self, stats):
        """세션 통계 시그널 수신 — 테이블 기반 집계로 처리하므로 pass."""
        pass
