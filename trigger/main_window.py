# trigger/main_window.py
# 트레이 이벤트(TrayManagerTriggers)와 메인 윈도우 오케스트레이션
# (MainWindowTriggersSingle, MainWindowTriggersMulti — 단일/다중 수집 공용).

from copy import deepcopy

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from worker import MultiprocessWorker
from conf import BlueprintStorage

from .common import (
    store, ACCENT_LIGHT, TEXT_SECONDARY, GREEN, AMBER, RED, SCHEDULED_REFINE_RULES,
    _apply_task_settings, _reset_pages, _show_no_data_dialog, _stop_worker_if_running,
    _after_delay_unless_cancelled,
    NAV_MONITOR, NAV_REFINE, NAV_STATS, NAV_BLUEPRINT_LIST,
)

class TrayManagerTriggers:
    """TrayManager의 트레이 이벤트 메서드"""

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.restore_window()

    def restore_window(self):
        if self.main_window.isMinimized() or not self.main_window.isVisible():
            self.main_window.showNormal()
            self.main_window.show()
        self.main_window.activateWindow()
        self.main_window.raise_()


# ══════════════════════════════════════════════════════
#  MainWindowSingle Mixin
# ══════════════════════════════════════════════════════
class MainWindowTriggersSingle:
    """MainWindowSingle의 페이지 전환·워커·종료 메서드"""

    def _switch_page(self, idx):
        self.stack.setCurrentIndex(idx)
        if idx == NAV_STATS:
            self.stats_page.reload()

    def _activate_nav_page(self, stack_idx: int) -> None:
        """표시 순서가 아닌 실제 스택 인덱스 기준으로 페이지를 전환하고 사이드바 체크를 동기화한다."""
        self.stack.setCurrentIndex(stack_idx)
        for btn, idx in self.sidebar._nav_idx_by_btn.items():
            btn.setChecked(idx == stack_idx)

    def _reset_all_pages(self):
        _reset_pages(self.dashboard, self.monitor_page)

    def _start_crawl(self, cfg: dict):
        self._launch_worker(cfg, job_name=cfg.get("job", "수동 실행"))

    def _start_crawl_from_schedule(self, cfg: dict):
        # schedule 키는 워커에 전달할 필요가 없으므로 제거 후 대기 큐 경유
        cfg = dict(cfg)   # 원본 dict 보호 (호출자의 sched_task 변형 방지)
        schedule_meta = cfg.pop("schedule", None) or {}
        # schedule_save_type은 위에서 제거되는 "schedule" 서브딕트 안에 있지만
        # _on_finished()의 자동 저장 단계에서 필요하다. extract는 그대로 task로
        # 살아남으므로 여기 얹어 함께 흘려보낸다. extract는 store에 저장된
        # 스케줄 dict와 같은 객체이므로 얕은 복사 후 추가해 원본을 오염시키지 않는다.
        if schedule_meta.get("schedule_save_type"):
            cfg["extract"] = dict(cfg.get("extract", {}))
            cfg["extract"]["schedule_save_type"] = schedule_meta["schedule_save_type"]
        cfg.setdefault("job", "스케줄 실행")

        if self._worker and self._worker.isRunning():
            # ── 실행 중인 작업이 있으면 대기 큐에 추가 ──
            self._pending_queue.append(cfg)
            queue_pos = len(self._pending_queue)
            self.log_manager.append_log(
                "info",
                f"[스케줄] '{cfg.get('task_nm', cfg['job'])}' 대기 등록 "
                f"(대기 순번: {queue_pos}번)"
            )
            return

        # 수동 실행과 동일하게 대시보드·모니터링 페이지 리셋 후 실행
        self._reset_for_schedule(cfg)
        self._launch_worker(cfg, job_name=cfg["job"])

    def _reset_for_schedule(self, cfg: dict) -> None:
        """스케줄 실행 시작 전 페이지 리셋 — MainWindowTriggersMulti가 번들 단위로 오버라이드한다."""
        self._reset_all_pages()

    def _launch_worker(self, cfg: dict, job_name="실행"):
        # 수동 실행 경로는 기존과 동일하게 기존 워커를 중단하고 교체
        _stop_worker_if_running(self._worker)

        self._worker = MultiprocessWorker(cfg, job_name)
        self._worker.new_row.connect(self.dashboard.add_row)
        self._worker.new_row.connect(self.monitor_page._add_realtime_row)
        self._worker.progress.connect(self.update_progress)
        self._worker.stats_update.connect(self.dashboard.update_stats)
        self._worker.log_message.connect(self.log_manager.append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()
        self.reset_progress()
        self.global_toolbar.set_running(True)
        self.dashboard._update_step_ui(2)
        self._activate_nav_page(NAV_MONITOR)

    def _consume_pending_queue(self):
        """
        대기 큐에서 다음 스케줄 작업을 꺼내 실행합니다.
        큐가 비어 있으면 아무것도 하지 않습니다.
        _on_finished() 말미에서만 호출됩니다.
        """
        if not self._pending_queue:
            return
        next_cfg = self._pending_queue.pop(0)
        remaining = len(self._pending_queue)
        self.log_manager.append_log(
            "info",
            f"[스케줄] '{next_cfg.get('task_nm', next_cfg.get('job', ''))}' 대기 큐에서 실행 "
            f"(남은 대기: {remaining}건)"
        )

        self._reset_all_pages()

        self._launch_worker(next_cfg, job_name=next_cfg.get("job", "스케줄 실행"))

    def _stop_crawl(self):
        self._batch_start_cancelled = True

        if self._worker and self._worker.isRunning():
            self._worker.stop()

        store.clear_rows()

        # 수동 중지 시 대기 큐도 함께 비워 후속 스케줄이 자동 실행되지 않도록 함
        if self._pending_queue:
            cleared = len(self._pending_queue)
            self._pending_queue.clear()
            self.log_manager.append_log(
                "warn",
                f"수동 중지 — 대기 중인 스케줄 {cleared}건 취소됨"
            )
        self.dashboard.set_running(False)

    def _on_finished(self, task: dict, summary: dict):
        # 중지 직후 곧바로 재시작하면, 교체되기 전 워커의 finished 신호가
        # 새 워커 시작 이후에 뒤늦게 도착할 수 있음(QThread.wait()가 메인
        # 스레드 이벤트 루프를 막는 동안 큐잉되었다가 처리됨). 그 경우
        # 실제로 실행 중인 현재 워커의 상태를 건드리면 안 되므로 무시.
        if self.sender() is not self._worker:
            return

        self.global_toolbar.set_running(False)
        self.reset_progress()
        self.dashboard.set_running(False)

        if summary.get("interrupted"):
            row_count = self.monitor_page.result_table.rowCount()
            self.log_manager.append_log(
                "warn",
                f"수집 중단 (Collection Interrupted) — {row_count}건 수집 후 중지 "
                f"(소요: {summary['elapsed']}s)"
            )
            self.dashboard._update_step_ui(0)
            # 중단은 _stop_crawl()에서 큐를 이미 비웠으므로 큐 소비 불필요
            return

        if summary.get("total", 0) == 0:
            url_count = summary.get("url_count", 0)
            skipped   = summary.get("skipped", 0)
            elapsed   = summary.get("elapsed", 0)
            is_unattended = task.get("job") == "스케줄 실행"
            self.log_manager.append_log(
                "err",
                f"크롤링 완료 — 수집된 데이터가 없습니다 "
                f"(생성 URL {url_count}개 · URL 불일치 skip {skipped}건 · 소요 {elapsed}s)"
            )
            self.dashboard._update_step_ui(0)
            if is_unattended:
                # 무인(스케줄) 실행 — 모달은 아무도 없는 자리에서 프로세스를
                # 막아버리므로 띄우지 않고, 트레이 알림으로만 경고한다.
                self.tray_manager.show_message(
                    "⚠ 수집 결과 없음",
                    f"'{task.get('task_nm', '')}' 스케줄 실행이 완료됐지만 수집된 데이터가 0건입니다.\n"
                    "사이트 구조 변경 여부를 확인해 주세요.",
                    icon=QSystemTrayIcon.MessageIcon.Warning,
                )
            else:
                _show_no_data_dialog(self, url_count, skipped, elapsed)
                if task.get("job") == "수동 실행":
                    self._activate_nav_page(NAV_REFINE)
                    self.monitor_page.tab_widget.setCurrentIndex(0)
            # 0건이어도 스케줄은 재무장해야 함 — 그렇지 않으면 다음 회차가
            # 영영 예약되지 않고 스케줄이 조용히 멈춘다.
            job_name = task.get("task_nm")
            if job_name:
                self.schedule_page.mark_done(job_name, total=0)
            # 결과 없어도 대기 큐 소비는 계속 진행
            self._consume_pending_queue()
            return

        self.log_manager.append_log("info", "크롤링 완료")

        # step(3) — 정제 단계 표시
        self.dashboard._update_step_ui(3)
        QApplication.processEvents()

        self.monitor_page.preprocess(task)
        self.stats_page.reload()

        # step(4) — 결과물 추출 단계 표시
        self.dashboard._update_step_ui(4)

        is_unattended = task.get("job") == "스케줄 실행"
        try:
            extract_cfg = task.get("extract", {})
            if extract_cfg.get("auto_save"):
                auto_save_source = extract_cfg.get("auto_save_source", "raw")
                if auto_save_source == "refined" and is_unattended:
                    # 무인 실행 — 화면 체크박스 상태가 아닌 스케줄별 설정(없으면
                    # SCHEDULED_REFINE_RULES 폴백, §"새 스케줄 등록"의 "⚙ 정제
                    # 규칙 설정" 참고)을 적용, 결과 테이블/탭 전환 등 화면 갱신도 건너뜀
                    sched_refine_rules = extract_cfg.get("refine_rules", SCHEDULED_REFINE_RULES)
                    sched_fill_value   = extract_cfg.get("fill_null_value", "")
                    self.monitor_page._run_refine(
                        rules_override=sched_refine_rules, skip_ui_update=True,
                        fill_value_override=sched_fill_value,
                    )
                # 무인(스케줄) 실행일 때만 스케줄 자신의 extract 설정(저장 위치/DB
                # 접속정보/저장 방식)을 강제 주입한다. 수동 실행은 override 없이
                # 넘겨 기존과 동일하게 self.output_info["extract"]를 그대로 쓴다.
                self.monitor_page._extract_result_table(
                    source=auto_save_source,
                    silent=is_unattended,
                    extract_override=extract_cfg if is_unattended else None,
                )
        except Exception as e:
            self.log_manager.append_log("err", f"자동 저장 실패: {e}")

        self.dashboard._update_step_ui(0)

        job_name = task.get("task_nm")
        if job_name:
            self.schedule_page.mark_done(job_name, total=summary.get("total", 0))

        if task.get("job") == "수동 실행":
            self._activate_nav_page(NAV_REFINE)
            self.monitor_page.tab_widget.setCurrentIndex(0)

        # ── 정상 완료 후 대기 큐 소비 ──
        self._consume_pending_queue()

    def closeEvent(self, event):
        if self.tray_manager.tray_icon.isVisible():
            self.hide()
            self.tray_manager.show_message("알림", "프로그램이 트레이에서 실행 중입니다.")
            event.ignore()
        else:
            event.accept()

    def exit_app(self):
        self._pending_queue.clear()   # 종료 시 대기 큐 비워 후속 실행 방지
        _stop_worker_if_running(self._worker)
        self.tray_manager.tray_icon.hide()
        QApplication.instance().quit()

    def update_progress(self, done: int, total: int):
        pct = int(done / total * 100) if total else 0
        self.dashboard.prog_bar.setValue(pct)
        self.dashboard.prog_pct.setText(f"{pct}%")
        self.dashboard.prog_lbl.setText(f"진행률 · {done} / {total}")

    def reset_progress(self):
        self.dashboard.prog_bar.setValue(0)
        self.dashboard.prog_pct.setText("0%")
        self.dashboard.prog_lbl.setText("대기 중")

    # ── 하단 상태바 슬롯 ─────────────────────────────
    _STATUS_COLORS = {
        "ok":   GREEN,
        "err":  RED,
        "warn": AMBER,
        "info": ACCENT_LIGHT,
    }

    def _update_status_bar(self, level: str, message: str):
        """last_log 시그널 수신 — 하단 상태바에 최신 로그 한 줄 표시"""
        color = self._STATUS_COLORS.get(level, TEXT_SECONDARY)
        tag   = f"[{level.upper():4s}]"
        self.status_level.setText(tag)
        self.status_level.setStyleSheet(
            f"color:{color}; font-size:11px; font-weight:bold;"
        )
        self.status_msg.setText(message)
        self.status_msg.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")

    # ── 전체 로그 다이얼로그 ─────────────────────────
    def _open_log_viewer(self):
        """상태바 버튼 클릭 — 이미 열려 있으면 앞으로 가져오고, 없으면 표시"""
        if self.log_manager.isVisible():
            self.log_manager.raise_()
            self.log_manager.activateWindow()
            return
        # 열릴 때 기존 이력을 뷰어에 일괄 렌더링 후 표시
        self.log_manager._viewer.clear()
        self.log_manager._load_history()
        self.log_manager.show()


# ══════════════════════════════════════════════════════
#  다중 수집 전용 트리거 — layout_multi.MainWindowMulti가 사용
# ══════════════════════════════════════════════════════
# MainWindowTriggersMulti는 MainWindowTriggersSingle를 상속해, 단일 블루프린트를
# 전제한 워커 기동/완료 처리를 "블루프린트 번들 라우팅" 방식으로 오버라이드합니다.
# _start_crawl_from_schedule도 스케줄이 지정한 seq_no의 번들을 리셋해야 하므로
# 함께 오버라이드합니다(§ 아래). 나머지 동작(_switch_page, _stop_crawl, exit_app
# 등)은 위 MainWindowTriggersSingle를 그대로 상속합니다 — 다중 수집 쪽에서
# self.dashboard/self.monitor_page가 항상 "활성 번들"의 페이지를 가리키도록
# layout_multi._activate_blueprint()가 유지하므로 참조가 안전합니다.
#
# _build_task()/_on_finished()는 위 MainWindowTriggersSingle의 단일 수집용
# 해당 로직(GlobalToolbarTriggers._actual_start()/_on_finished())을
# seq_no 인자화해 옮긴 것이므로, 그쪽을 수정하면 여기도 함께 확인해야 합니다.

BATCH_JOB = "전체 수집"


class MainWindowTriggersMulti(MainWindowTriggersSingle):
    """MainWindowMulti(다중 수집 레이아웃)의 순차 수집·번들 라우팅 메서드"""

    # ── 태스크 빌드 ───────────────────────────────────
    def _build_task(self, seq_no: str) -> dict:
        """
        특정 블루프린트(seq_no)의 실행 태스크 dict를 구성합니다.
        (단일 GlobalToolbarTriggers._actual_start()와 공통 로직을 공유 —
        모듈 함수 _apply_task_settings() 참고)
        """
        bundle = self._get_or_create_bundle(seq_no)
        task = BlueprintStorage().get(seq_no)
        _apply_task_settings(
            task, collect=bundle.collect_settings, session_page=self.session_page,
            monitor_page=bundle.monitor_page, auth_page=bundle.auth_page,
            job_name=BATCH_JOB,
        )
        # 순차 수집은 대기 큐에 여러 태스크가 동시에 존재하므로,
        # monitor_page.output_info["extract"] 참조를 그대로 두면 나중에 그
        # 페이지 설정이 바뀔 때 대기 중인 태스크까지 함께 바뀐다 — 제출
        # 시점 스냅샷으로 분리해 둔다.
        task["extract"] = deepcopy(task["extract"])
        return task

    # ── 순차 수집 시작 ─────────────────────────────────
    def _start_batch(self, seq_no_list: list):
        """"수집 목록" 페이지에서 체크된 블루프린트들을 순서대로 순차 실행합니다."""
        if not seq_no_list:
            self.log_manager.append_log("warn", "[전체 수집] 선택된 블루프린트가 없습니다.")
            return

        tasks = [self._build_task(s) for s in seq_no_list]
        for i, t in enumerate(tasks):
            t["batch_meta"] = {"index": i, "total": len(tasks)}

        if self._worker and self._worker.isRunning():
            # 실행 중 요청 — 진행 중 작업을 죽이지 않고 뒤에 순차 대기
            self._pending_queue.extend(tasks)
            self.log_manager.append_log(
                "info",
                f"[전체 수집] 실행 중인 작업이 있어 {len(tasks)}건을 대기 큐에 등록했습니다."
            )
            return

        first, rest = tasks[0], tasks[1:]
        self._pending_queue.extend(rest)
        store.clear_rows()
        self._reset_bundle_pages(first.get("seq_no"))
        self.log_manager.append_log(
            "info",
            f"[전체 수집] 총 {len(tasks)}건 순차 실행 시작 — 1/{len(tasks)}번째 "
            f"'{first.get('title') or first.get('seq_no')}'"
        )

        # 단일 레이아웃의 _toggle_run→_step_to_setting과 동일한 "수집 대기(0, 위
        # _reset_bundle_pages가 이미 표시함)→수집 세팅(1)→데이터 수집(2)" 연출을
        # 재현한다 — _after_delay_unless_cancelled는 두 레이아웃이 공유하는 헬퍼.
        self._batch_start_cancelled = False
        dash = self._get_or_create_bundle(first.get("seq_no")).dashboard

        def _to_setting():
            dash._update_step_ui(1)
            _after_delay_unless_cancelled(
                lambda: self._batch_start_cancelled,
                lambda: self._launch_worker(first, job_name=BATCH_JOB),
            )

        _after_delay_unless_cancelled(lambda: self._batch_start_cancelled, _to_setting)

    def _reset_bundle_pages(self, seq_no) -> None:
        """실행 직전 해당 번들의 대시보드/모니터링 페이지를 초기화합니다."""
        bundle = self._get_or_create_bundle(seq_no)
        _reset_pages(bundle.dashboard, bundle.monitor_page)

    # ── 스케줄 실행 (번들 라우팅) ──────────────────────
    def _reset_for_schedule(self, cfg: dict) -> None:
        """단일 버전과 동일하되, 리셋 대상을 "현재 활성 번들"이 아니라
        cfg가 지정한 seq_no의 번들로 고정합니다 — 스케줄 발동 시점에
        사용자가 다른 블루프린트를 보고 있어도 엉뚱한 번들이 리셋되지 않도록."""
        self._reset_bundle_pages(cfg.get("seq_no"))

    # ── 워커 기동 (번들 라우팅) ────────────────────────
    def _launch_worker(self, cfg: dict, job_name="실행"):
        _stop_worker_if_running(self._worker)

        # 실행 대상 블루프린트로 화면 자동 포커스 — 이후 시그널은 아래에서
        # 캡처한 "그 번들"에 정적으로 연결되므로, 사용자가 다른 블루프린트로
        # 전환해도 진행 중 작업의 갱신은 원래 번들에 계속 반영된다.
        seq_no = cfg.get("seq_no")
        self._activate_blueprint(seq_no)
        bundle = self._get_or_create_bundle(seq_no)
        dash, mon = bundle.dashboard, bundle.monitor_page

        self._worker = MultiprocessWorker(cfg, job_name)
        self._worker.new_row.connect(dash.add_row)
        self._worker.new_row.connect(mon._add_realtime_row)
        self._worker.progress.connect(
            lambda done, total, d=dash: self._update_progress_for(d, done, total))
        self._worker.stats_update.connect(dash.update_stats)
        self._worker.log_message.connect(self.log_manager.append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

        self._reset_progress_for(dash)
        self._broadcast_blueprint_status(seq_no, "running")
        self.global_toolbar.set_running(True)
        dash._update_step_ui(2)
        # 다중 레이아웃은 "모니터링"이 "수집 목록"(NAV_BLUEPRINT_LIST) 하단 상세로
        # 통합됐으므로, 단일과 달리 NAV_MONITOR가 아니라 그쪽으로 전환한다.
        self._activate_nav_page(NAV_BLUEPRINT_LIST)

    # ── 진행률 (번들별) ────────────────────────────────
    @staticmethod
    def _update_progress_for(dash, done: int, total: int):
        pct = int(done / total * 100) if total else 0
        dash.prog_bar.setValue(pct)
        dash.prog_pct.setText(f"{pct}%")
        dash.prog_lbl.setText(f"진행률 · {done} / {total}")

    @staticmethod
    def _reset_progress_for(dash):
        dash.prog_bar.setValue(0)
        dash.prog_pct.setText("0%")
        dash.prog_lbl.setText("대기 중")

    # ── 대기 큐 소비 (전체 수집/스케줄 공용) ────────────
    def _consume_pending_queue(self):
        if not self._pending_queue:
            return
        next_cfg = self._pending_queue.pop(0)
        remaining = len(self._pending_queue)

        meta = next_cfg.get("batch_meta")
        if meta:
            self.log_manager.append_log(
                "info",
                f"[전체 수집] {meta['index'] + 1}/{meta['total']}번째 "
                f"'{next_cfg.get('title') or next_cfg.get('seq_no')}' 실행 "
                f"(남은 대기: {remaining}건)"
            )
        else:
            self.log_manager.append_log(
                "info",
                f"[스케줄] '{next_cfg.get('task_nm', next_cfg.get('job', ''))}' 대기 큐에서 실행 "
                f"(남은 대기: {remaining}건)"
            )

        self._reset_bundle_pages(next_cfg.get("seq_no"))
        self._launch_worker(next_cfg, job_name=next_cfg.get("job", "스케줄 실행"))

    # ── 완료 처리 (번들 라우팅) ────────────────────────
    def _on_finished(self, task: dict, summary: dict):
        # 늦게 도착한 이전 워커의 finished 신호 무시 (단일과 동일한 가드)
        if self.sender() is not self._worker:
            return

        seq_no = task.get("seq_no")
        bundle = self._get_or_create_bundle(seq_no)
        dash, mon = bundle.dashboard, bundle.monitor_page

        self.global_toolbar.set_running(False)
        self._reset_progress_for(dash)
        dash.set_running(False)
        self._broadcast_blueprint_status(seq_no, "done")

        if summary.get("interrupted"):
            row_count = mon.result_table.rowCount()
            self.log_manager.append_log(
                "warn",
                f"수집 중단 (Collection Interrupted) — {row_count}건 수집 후 중지 "
                f"(소요: {summary['elapsed']}s)"
            )
            dash._update_step_ui(0)
            self._broadcast_blueprint_status(seq_no, "idle")
            # 중단은 _stop_crawl()에서 큐를 이미 비웠으므로 큐 소비 불필요
            return

        # 전체 수집·스케줄 실행은 "무인 흐름" — 모달을 띄우면 사용자가
        # 닫아줄 때까지 다음 순번이 영영 시작되지 않으므로 트레이 알림만 사용.
        is_unattended = task.get("job") in ("스케줄 실행", BATCH_JOB)

        if summary.get("total", 0) == 0:
            url_count = summary.get("url_count", 0)
            skipped   = summary.get("skipped", 0)
            elapsed   = summary.get("elapsed", 0)
            self.log_manager.append_log(
                "err",
                f"크롤링 완료 — 수집된 데이터가 없습니다 "
                f"(생성 URL {url_count}개 · URL 불일치 skip {skipped}건 · 소요 {elapsed}s)"
            )
            dash._update_step_ui(0)
            if is_unattended:
                job_label = task.get("task_nm") or task.get("title") or seq_no
                self.tray_manager.show_message(
                    "⚠ 수집 결과 없음",
                    f"'{job_label}' 실행이 완료됐지만 수집된 데이터가 0건입니다.\n"
                    "사이트 구조 변경 여부를 확인해 주세요.",
                    icon=QSystemTrayIcon.MessageIcon.Warning,
                )
            else:
                _show_no_data_dialog(self, url_count, skipped, elapsed)
                if task.get("job") == "수동 실행":
                    self._show_monitor_for(seq_no)
            # 0건이어도 스케줄 재무장·대기 큐 소비는 계속 진행 (단일과 동일)
            job_name = task.get("task_nm")
            if job_name:
                self.schedule_page.mark_done(job_name, total=0)
            self._consume_pending_queue()
            return

        self.log_manager.append_log("info", "크롤링 완료")

        dash._update_step_ui(3)
        QApplication.processEvents()

        mon.preprocess(task)
        self.stats_page.reload()

        dash._update_step_ui(4)

        try:
            extract_cfg = task.get("extract", {})
            if extract_cfg.get("auto_save"):
                auto_save_source = extract_cfg.get("auto_save_source", "raw")
                if auto_save_source == "refined" and is_unattended:
                    sched_refine_rules = extract_cfg.get("refine_rules", SCHEDULED_REFINE_RULES)
                    sched_fill_value   = extract_cfg.get("fill_null_value", "")
                    mon._run_refine(
                        rules_override=sched_refine_rules, skip_ui_update=True,
                        fill_value_override=sched_fill_value,
                    )
                # 스케줄 실행일 때만 스케줄 자신의 extract 설정을 강제 주입 (단일과
                # 동일). 배치는 각 번들의 화면 설정 스냅샷을 그대로 사용한다.
                is_schedule = task.get("job") == "스케줄 실행"
                mon._extract_result_table(
                    source=auto_save_source,
                    silent=is_unattended,
                    extract_override=extract_cfg if is_schedule else None,
                )
        except Exception as e:
            self.log_manager.append_log("err", f"자동 저장 실패: {e}")

        dash._update_step_ui(0)

        job_name = task.get("task_nm")
        if job_name:
            self.schedule_page.mark_done(job_name, total=summary.get("total", 0))

        # 수동 실행: 즉시 모니터링 화면으로. 전체 수집: 마지막 순번이 끝난
        # 뒤에만(대기 큐가 비었을 때) 마지막 블루프린트의 모니터링 화면으로 전환.
        if task.get("job") == "수동 실행":
            self._show_monitor_for(seq_no)
        elif task.get("job") == BATCH_JOB and not self._pending_queue:
            self.log_manager.append_log("info", "[전체 수집] 전체 순차 실행 완료")
            self._show_monitor_for(seq_no)

        self._consume_pending_queue()

    def _show_monitor_for(self, seq_no) -> None:
        """해당 블루프린트를 활성화하고 데이터 정제(nav 1) 화면을 표시합니다."""
        self._activate_blueprint(seq_no)
        self._activate_nav_page(NAV_REFINE)
        self._get_or_create_bundle(seq_no).monitor_page.tab_widget.setCurrentIndex(0)
