# trigger/dashboard.py
# DashboardPageSingle의 테이블·필터·내보내기 메서드(DashboardPageTriggers).

import csv

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from .common import (
    ACCENT_LIGHT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, GREEN, AMBER, RED, BLUE,
    _show_extract_error_dialog,
)


class DashboardPageTriggers:
    """DashboardPageSingle의 테이블·필터·내보내기 메서드"""

    def add_row(self, row: dict):
        """워커 new_row 시그널 수신 → 대시보드 수집 모니터링 테이블에 행 추가"""
        if not row or "resp_info" not in row:
            return
        resp_info = row["resp_info"]

        target_url = resp_info.get("url", "")
        self.monitor_table.setSortingEnabled(False)
        current_row = self.monitor_table.rowCount()
        self.monitor_table.insertRow(current_row)

        STATUS_COLOR = {"200": GREEN, "404": RED, "429": AMBER, "500": RED, "301": BLUE, "000": TEXT_MUTED}
        status_val = resp_info.get("status", "")
        # 200 응답이지만 추출 자체는 실패한 행(engine.build_failure_item이 남긴
        # extract_error) — 클릭하면 원인/해결방법을 볼 수 있다는 표시로 ⚠를 덧붙인다.
        extract_error = resp_info.get("extract_error")
        status_display = f"{status_val} ⚠" if extract_error else status_val
        vals = [
            current_row,
            target_url,
            status_display,
            resp_info.get("ip_address", ""),
            resp_info.get("user_agents", ""),
            resp_info.get("cookies", ""),
            resp_info.get("pure_latency", ""),
            resp_info.get("total_latency", ""),
            row.get("job_name", ""),
        ]
        colors = [
            TEXT_MUTED, TEXT_MUTED,
            STATUS_COLOR.get(str(status_val), TEXT_SECONDARY),
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
            if col == 2 and extract_error:
                item.setData(Qt.ItemDataRole.UserRole, resp_info)
            self.monitor_table.setItem(current_row, col, item)

        self.monitor_table.setSortingEnabled(True)
        self.mon_row_count_lbl.setText(f"{self.monitor_table.rowCount()} rows")

        if str(resp_info.get("status", "")).strip() != "200":
            self._session_error_count += 1
        try:
            self._session_latency_sum += float(resp_info.get("pure_latency", ""))
            self._session_latency_count += 1
        except (ValueError, TypeError):
            pass
        self._refresh_session_stats()

    def _on_monitor_item_clicked(self, item):
        """수집 모니터링 테이블 행 클릭 — 추출 실패(200 ⚠) 행이면 원인/해결방법 안내"""
        status_item = self.monitor_table.item(item.row(), 2)
        resp_info = status_item.data(Qt.ItemDataRole.UserRole) if status_item else None
        if resp_info and resp_info.get("extract_error"):
            _show_extract_error_dialog(self, resp_info)

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
            w.writerow(["NO", "URL", "Status", "IP Address", "User Agent",
                        "Cookies", "Latency (Pure)", "Latency (Total)", "Job Name"])
            for r in range(self.monitor_table.rowCount()):
                w.writerow([
                    self.monitor_table.item(r, c).text()
                    if self.monitor_table.item(r, c) else ""
                    for c in range(9)
                ])
        QMessageBox.information(self, "완료", f"저장 완료:\n{path}")
