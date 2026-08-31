# trigger/toolbar.py
# GlobalToolbarSingle의 버튼·시그널 콜백 메서드(GlobalToolbarTriggers).

from copy import deepcopy

from PyQt6.QtWidgets import QApplication, QMainWindow

from conf import BlueprintStorage

from .common import (
    store, ACCENT, ACCENT_HOVER, RED, _apply_task_settings, _reset_pages,
    _after_delay_unless_cancelled,
)


class GlobalToolbarTriggers:
    """GlobalToolbarSingle의 버튼·시그널 콜백 메서드"""

    def _copy_url(self):
        """URL을 클립보드에 복사하고 입력창의 텍스트를 전체 선택합니다."""
        QApplication.clipboard().setText(self.url_input.text())
        self.url_input.setFocus()
        self.url_input.selectAll()

    def _open_output_settings(self):
        """추출 설정 버튼 클릭 시 호출 — 활성 블루프린트의 모니터링 페이지가 가진 저장 설정 다이얼로그를 연다"""
        if self.monitor_page is None:
            return
        self.monitor_page._open_output_settings_dialog()

    def _toggle_run(self):
        """시작/중지 버튼 클릭 시 호출"""
        if not self._running:
            self._start_cancelled = False

            mw = self._main_window()
            if mw is not None:
                mw.dashboard._update_step_ui(0)

            store.clear_rows()
            _reset_pages(self.dashboard, self.monitor_page)

            self.set_running(True)
            self._log("info", "수집을 시작합니다.")
            QApplication.processEvents()
            _after_delay_unless_cancelled(lambda: self._start_cancelled, self._step_to_setting)
        else:
            self._start_cancelled = True
            self.stop_requested.emit()
            self.set_running(False)
            mw = self._main_window()
            if mw is not None:
                mw.dashboard._update_step_ui(0)
            self._full_reset()
            self._log("warn", "수집이 중단되었습니다. 수집 대기 상태로 초기화합니다.")

    def _step_to_setting(self):
        """[단계 1: 수집 세팅] 처리"""
        if self._start_cancelled:
            return

        mw = self._main_window()

        if self.dashboard is None or self.session_page is None or self.monitor_page is None:
            self._log("err", "페이지 초기화가 완료되지 않았습니다. 잠시 후 다시 시도해 주세요.")
            if mw is not None:
                mw.dashboard._update_step_ui(0)
            self.set_running(False)
            return

        if mw is not None:
            mw.dashboard._update_step_ui(1)

        QApplication.processEvents()

        self._log("info", "환경 설정을 로드합니다. (수집 세팅 중...)")
        _after_delay_unless_cancelled(lambda: self._start_cancelled, self._actual_start)

    def _actual_start(self):
        """[단계 2: 데이터 수집] 실제 시작"""
        if self._start_cancelled:
            return

        mw = self._main_window()

        try:
            dashboard_page = self.dashboard
            session_page   = self.session_page
            monitor_page   = self.monitor_page

            if dashboard_page is None or session_page is None or monitor_page is None:
                raise RuntimeError("페이지 인스턴스가 주입되지 않았습니다.")

            request_info = BlueprintStorage().read()

            collect = {
                "delay": dashboard_page.delay_spin.value(),
                "threads": dashboard_page.thread_spin.value(),
                "timeout": dashboard_page.timeout_spin.value(),
                "retry": dashboard_page.retry_spin.value(),
                "auto_save": dashboard_page.auto_save_chk.isChecked(),
                "auto_save_source": (
                    "refined" if dashboard_page.auto_src_ref_btn.isChecked() else "raw"
                ),
            }
            # 단일 레이아웃은 다중처럼 별도 "적용" 버튼이 없으므로, 수집 설정 카드의
            # 값을 실제로 확정 짓는 "시작" 클릭 시점에 블루프린트에 영속화한다 —
            # 재시작 후에도 마지막으로 수집에 쓰인 값이 그대로 표출된다.
            BlueprintStorage().update_settings(request_info.get("seq_no"), collect_settings=collect)

            self.task.update(deepcopy(request_info))
            _apply_task_settings(
                self.task, collect=collect, session_page=session_page,
                monitor_page=monitor_page, auth_page=self.auth_page,
                job_name="수동 실행",
            )
            self.start_requested.emit(self.task)

        except Exception as e:
            self._log("err", f"설정 로드 실패: {e}")
            self.set_running(False)
            if mw is not None:
                mw.dashboard._update_step_ui(0)

    def _full_reset(self):
        """중지 버튼 클릭 시 호출 — DataStore 및 모든 페이지 UI를 완전히 초기화합니다."""

        store.clear_rows()
        store.clear_url_maps()

        _reset_pages(self.dashboard, self.monitor_page)

        mw = self._main_window()
        if mw is not None:
            mw.reset_progress()

    def set_running(self, v: bool):
        self._running = v
        self._style_run_btn(v)

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

    def _log(self, level: str, message: str) -> None:
        """log_manager가 주입된 경우에만 로그를 출력합니다."""
        if self.log_manager is not None:
            self.log_manager.append_log(level, message)

    def _main_window(self):
        """부모 위젯을 순회하여 MainWindowSingle 인스턴스를 반환합니다. 없으면 None."""

        w = self.parent()
        while w is not None:
            if isinstance(w, QMainWindow):
                return w
            w = w.parent()
        return None

    def set_pages(self, dashboard=None, monitor_page=None,
                  session_page=None, auth_page=None) -> None:
        """MainWindowSingle 초기화 후 실제 페이지 인스턴스를 주입합니다."""
        if dashboard    is not None:
            self.dashboard    = dashboard
        if monitor_page is not None:
            self.monitor_page = monitor_page
        if session_page is not None:
            self.session_page = session_page
        if auth_page    is not None:
            self.auth_page    = auth_page

    def set_log_manager(self, log_manager) -> None:
        """MainWindowSingle 초기화 후 LogViewerDialog 싱글턴을 주입합니다."""
        self.log_manager = log_manager
