# trigger/scheduler.py
# SchedulerPage의 스케줄 등록·수정·삭제·실행·타이머 메서드(SchedulerPageTriggers).

import os
import re
import json
from copy import deepcopy
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QApplication, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QComboBox, QCheckBox, QWidget, QTableWidgetItem, QGridLayout, QStackedWidget,
    QSizePolicy, QSpinBox, QDateEdit,
)
from PyQt6.QtCore import Qt, QTimer, QDate
from PyQt6.QtGui import QColor

from conf import BlueprintStorage, get_spider_mode
import utility
import customized_settings
from style import (
    TagButton, Divider, build_refine_rule_rows,
    BoundNoticeSpinBox, BoundNoticeDoubleSpinBox,
    apply_render_safety_limits, reset_render_safety_limits,
)

from .common import (
    store, theme, parts, BG_PRIMARY, BG_SECONDARY, BG_HOVER, ACCENT, ACCENT_LIGHT,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, BORDER, BORDER_LIGHT, GREEN, PURPLE,
    SCHEDULED_REFINE_RULES_DIALOG_DEFAULT, _default_msgbox_qss,
    _build_db_settings_fields, _build_output_file_page, _wire_db_test_button,
    _warn_custom_rule_missing, _sync_custom_rule_checkbox, _handle_custom_rule_toggle,
)

class SchedulerPageTriggers:
    """SchedulerPage의 스케줄 등록·수정·삭제·실행·타이머 메서드"""

    # QTimer.start()는 C int(최대 2,147,483,647ms ≈ 24.8일)를 받으므로,
    # 이보다 긴 대기는 이 단위로 쪼개어 재등록한다 (월간 주기=30일 등에서 OverflowError 방지).
    _MAX_TIMER_MS = 7 * 24 * 60 * 60 * 1000

    def _apply_schedule(self, dlg, sched_info_dict):
        """다이얼로그 위젯값을 읽어 유효성 검사 → 등록 또는 수정 수행"""
        sched_task  = sched_info_dict["sched_task"]
        idx         = sched_info_dict.get("idx")
        name_val    = sched_info_dict["sched_name"].text().strip()
        url_val     = sched_info_dict["callback_url"].text().strip()
        iv_idx      = sched_info_dict["interval"].currentIndex()
        svtype_idx  = sched_info_dict["save_type"].currentIndex()
        out_mode    = self._sched_out_mode

        _msg_qss = _default_msgbox_qss(13)

        def _warn(title, text):
            msg = QMessageBox(dlg)
            msg.setWindowTitle(title)
            msg.setText(text)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setStyleSheet(_msg_qss)
            msg.exec()

        errors = []
        if not name_val:
            errors.append("• Task Name을 입력해 주세요.")
        if not url_val:
            errors.append("• Target URL을 입력해 주세요.")
        if iv_idx == 0:
            errors.append("• Interval(주기)을 선택해 주세요.")
        if svtype_idx == 0:
            errors.append("• 저장 방식을 선택해 주세요.")

        if self.session_page._global_cb.isChecked():

            if not getattr(self.session_page, "_proxy_rows", []):
                errors.append(
                    "• 프록시 사용이 선택되었으나 프록시 목록이 비어 있습니다.\n"
                    "  [세션 설정] 페이지에서 프록시를 먼저 등록해 주세요."
                )

        if errors:
            _warn("입력 오류", "다음 항목을 확인해 주세요:\n\n" + "\n".join(errors))
            return

        for i2, exist in enumerate(store.get_schedules()):
            if sched_task == "수정" and i2 == idx:
                continue
            if exist.get("task_nm") == name_val:
                _warn("입력 오류",
                      f"• 동일한 작업명이 이미 등록되어 있습니다.\n"
                      f"  (작업명: '{name_val}')\n  다른 작업명을 사용해 주세요.")
                return

        def _hms(h_cb, m_cb, s_cb):
            return (int(h_cb.currentText()),
                    int(m_cb.currentText()),
                    int(s_cb.currentText()))

        candidate = None
        if iv_idx == 1:
            h, m, s = _hms(sched_info_dict["d_h"], sched_info_dict["d_m"], sched_info_dict["d_s"])
        elif iv_idx == 2:
            h, m, s = _hms(sched_info_dict["w_h"], sched_info_dict["w_m"], sched_info_dict["w_s"])
        elif iv_idx == 3:
            h, m, s = _hms(sched_info_dict["m_h"], sched_info_dict["m_m"], sched_info_dict["m_s"])
        elif iv_idx == 4:
            h, m, s = _hms(sched_info_dict["dat_h"], sched_info_dict["dat_m"], sched_info_dict["dat_s"])
        else:
            h, m, s = None, None, None

        if h is not None:
            candidate = f"{h:02d}:{m:02d}:{s:02d}"

        if candidate:
            for i2, exist in enumerate(store.get_schedules()):
                if sched_task == "수정" and i2 == idx:
                    continue
                exist_exec_str = exist.get("schedule", {}).get("exec_str", "")
                exist_time = exist_exec_str.strip().split()[-1] if exist_exec_str else ""
                if exist.get("callback_url", "") == url_val and exist_time == candidate:
                    _warn("입력 오류",
                          f"• 동일한 URL과 실행 시간의 작업이 이미 등록되어 있습니다.\n"
                          f"  (작업명: '{exist.get('task_nm', '')}' / {candidate})\n"
                          f"  URL 또는 실행 시간을 변경해 주세요.")
                    return

        now    = datetime.now()
        iv_key = "none"
        exec_str = "미설정"
        run_at   = now + timedelta(hours=1)

        if iv_idx == 1:
            h, m, s  = _hms(sched_info_dict["d_h"], sched_info_dict["d_m"], sched_info_dict["d_s"])
            exec_str = f"매일 {h:02d}:{m:02d}:{s:02d}"
            iv_key   = "daily"
            run_at   = now.replace(hour=h, minute=m, second=s, microsecond=0)
            if run_at <= now:
                run_at += timedelta(days=1)
        elif iv_idx == 2:
            day      = sched_info_dict["w_day"].currentText()
            h, m, s  = _hms(sched_info_dict["w_h"], sched_info_dict["w_m"], sched_info_dict["w_s"])
            exec_str = f"매주 {day} {h:02d}:{m:02d}:{s:02d}"
            iv_key   = "weekly"
            run_at   = now.replace(hour=h, minute=m, second=s, microsecond=0)
            if run_at <= now:
                run_at += timedelta(days=7)
        elif iv_idx == 3:
            day      = int(sched_info_dict["m_day"].currentText())
            h, m, s  = _hms(sched_info_dict["m_h"], sched_info_dict["m_m"], sched_info_dict["m_s"])
            exec_str = f"매월 {day}일 {h:02d}:{m:02d}:{s:02d}"
            iv_key   = "monthly"
            try:
                run_at = now.replace(day=day, hour=h, minute=m, second=s, microsecond=0)
            except ValueError:
                run_at = now.replace(day=28, hour=h, minute=m, second=s, microsecond=0)
            if run_at <= now:
                run_at += timedelta(days=30)
        elif iv_idx == 4:
            qd       = sched_info_dict["date_edit"].date()
            h, m, s  = _hms(sched_info_dict["dat_h"], sched_info_dict["dat_m"], sched_info_dict["dat_s"])
            exec_str = f"{qd.toString('yyyy-MM-dd')} {h:02d}:{m:02d}:{s:02d}"
            iv_key   = "date"
            run_at   = datetime(qd.year(), qd.month(), qd.day(), h, m, s)
            if run_at <= now:
                _warn("등록 불가",
                      f"선택한 시간이 현재 시각보다 이전입니다.\n\n"
                      f"  설정 시간: {exec_str}\n"
                      f"  현재 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                      "현재 시각 이후의 시간을 설정해 주세요.")
                return

        is_file = (out_mode == "FILE")
        is_db   = (out_mode == "DB")

        def _val(widget, method="text"):
            raw = getattr(widget, method)() if widget else ""
            return utility.update_empty_value(raw) if raw else None

        common_fields = {
            "task_nm":      name_val,
            "seq_no":       sched_info_dict["blueprint_combo"].currentData(),
            "callback_url": url_val,
            "delay":        sched_info_dict["delay"].value(),
            "threads":      sched_info_dict["threads"].value(),
            "timeout":      sched_info_dict["timeout"].value(),
            "retry":        sched_info_dict["retry"].value(),
            "user_agent":   self.session_page.ua_check.isChecked(),
            "cookie":       self.session_page.cookie_check.isChecked(),
            "proxy": {
                "enabled":       self.session_page._global_cb.isChecked(),
                # "자동 로테이션" 체크박스 제거 — 전역 프록시 사용 시 항상 로테이션을 사용한다.
                "rotate":        self.session_page._global_cb.isChecked(),
                "allow_ip_cnts": self.session_page._allow_ip_cnts.value(),
                "ip_list":       deepcopy(getattr(self.session_page, "_proxy_rows", [])),
            },
            "extract": {
                "file": {
                    "enabled":      is_file,
                    "file_path":    (utility.to_forward_slash(
                                        os.path.normpath(sched_info_dict["path_edit"].text()))
                                     if is_file and sched_info_dict["path_edit"].text() else None),
                    "file_name":    _val(sched_info_dict["file_nm"]) if is_file else None,
                    "file_format":  _val(sched_info_dict["fmt_combo"], "currentText") if is_file else None,
                    "file_encoding":_val(sched_info_dict["enc_combo"], "currentText") if is_file else None,
                    "file_delimiter":_val(sched_info_dict["csv_delim"]) if is_file else None,
                },
                "db": {
                    "enabled":      is_db,
                    "db_env":       _val(sched_info_dict["db_type"], "currentText") if is_db else None,
                    "host":         _val(sched_info_dict["db_host"]) if is_db else None,
                    "port":         _val(sched_info_dict["db_port"]) if is_db else None,
                    "database":     _val(sched_info_dict["db_name"]) if is_db else None,
                    "schema":       _val(sched_info_dict["db_schema"]) if is_db else None,
                    "user":         _val(sched_info_dict["db_user"]) if is_db else None,
                    "password":     _val(sched_info_dict["db_pw"]) if is_db else None,
                    "save_data_nm": _val(sched_info_dict["db_data"]) if is_db else None,
                },
            },
            "schedule": {
                "enabled":            True,
                "status":             "대기",
                "interval":           iv_key,
                "exec_str":           exec_str,
                "run_at":             run_at,
                "schedule_save_type": sched_info_dict["save_type"].currentText().strip(),
            },
        }

        auto_save_source  = "refined" if sched_info_dict["auto_src_ref_btn"].isChecked() else "raw"
        refine_checkboxes = sched_info_dict["refine_checkboxes"]
        refine_fill_input = sched_info_dict["refine_fill_input"]
        refine_rules_values = {key: cb.isChecked() for key, cb in refine_checkboxes.items()}
        refine_fill_value   = refine_fill_input.text() if refine_fill_input is not None else ""

        if sched_task == "등록":
            schedule_info = customized_settings.get_schedule_settings()
            schedule_info.update(common_fields)
            schedule_info["extract"].update(common_fields["extract"])
            # 스케줄 실행은 무인 실행이라 수동으로 "추출"을 누를 사람이 없음 —
            # extract 병합 이후에 강제해야 common_fields["extract"](file/db만
            # 있고 auto_save 키가 없음)에 덮어써지지 않음
            schedule_info["extract"]["auto_save"] = True
            schedule_info["extract"]["auto_save_source"] = auto_save_source
            schedule_info["extract"]["refine_rules"] = refine_rules_values
            schedule_info["extract"]["fill_null_value"] = refine_fill_value
            schedule_info["schedule"].update(common_fields["schedule"])
            store.add_schedule(schedule_info)
            dlg.accept()
            self._refresh_table()
            self._register_timer(len(store.get_schedules()) - 1)
        else:
            target = store.get_schedules()[idx]
            for key in ("task_nm", "seq_no", "callback_url", "delay", "threads",
                        "timeout", "retry", "user_agent", "cookie", "proxy"):
                target[key] = common_fields[key]
            target["extract"]["file"].update(common_fields["extract"]["file"])
            target["extract"]["db"].update(common_fields["extract"]["db"])
            target["extract"]["auto_save"] = True
            target["extract"]["auto_save_source"] = auto_save_source
            target["extract"]["refine_rules"] = refine_rules_values
            target["extract"]["fill_null_value"] = refine_fill_value
            target["schedule"].update(common_fields["schedule"])
            if idx in self._timers:
                self._timers[idx].stop()
                del self._timers[idx]
            dlg.accept()
            self._refresh_table()
            self._register_timer(idx)

        self._save_schedules_to_json()

    def _delete_schedule(self, idx):
        store.remove_schedule(idx)
        self._refresh_table()
        self._save_schedules_to_json()

    def _run_now(self, idx):
        schedules = store.get_schedules()
        if idx >= len(schedules):
            return
        s = schedules[idx]
        store.update_schedule_status(idx, "실행 중")
        self._refresh_table()

        blueprint = BlueprintStorage().get(s.get("seq_no"))
        if blueprint is None:
            # seq_no가 없는(구버전) 스케줄이거나 대상 블루프린트가 삭제된 경우 —
            # 활성 블루프린트로 폴백(기존 동작 유지)
            blueprint = deepcopy(BlueprintStorage().read())
        self.sched_task.update(blueprint)
        self.sched_task.update(s)
        self.schedule_run.emit(self.sched_task)

    def _register_timer(self, idx):
        schedules = store.get_schedules()
        if idx >= len(schedules):
            return
        s      = schedules[idx]
        run_at = s["schedule"]["run_at"]
        if not run_at:
            return
        ms = max(0, int((run_at - datetime.now()).total_seconds() * 1000))
        t  = QTimer(self)
        t.setSingleShot(True)
        if ms > self._MAX_TIMER_MS:
            t.timeout.connect(lambda i=idx: self._register_timer(i))
            t.start(self._MAX_TIMER_MS)
        else:
            t.timeout.connect(lambda i=idx: self._run_now(i))
            t.start(ms)
        self._timers[idx] = t

    def _update_countdown(self):
        """1초마다 Next Task 라벨 + Next Runtime 컬럼 갱신"""
        schedules = store.get_schedules()
        for row, s in enumerate(schedules):
            run_at = s["schedule"]["run_at"]
            txt    = self._format_remaining(run_at) if run_at else "—"
            item   = self.sched_table.item(row, 5)
            if item:
                item.setText(txt)
            else:
                new_item = QTableWidgetItem(txt)
                new_item.setForeground(QColor(PURPLE))
                self.sched_table.setItem(row, 5, new_item)

        active = [s for s in schedules
                  if s["schedule"]["run_at"] and s["schedule"]["status"] != "완료"]
        if not active:
            self.next_task_lbl.setText("등록된 스케줄 없음")
            self.next_task_lbl.setStyleSheet(
                self.next_task_lbl.styleSheet()
                .replace(ACCENT_LIGHT, TEXT_MUTED).replace(GREEN, TEXT_MUTED))
            return
        next_s = min(active, key=lambda s: s["schedule"]["run_at"])
        diff   = (next_s["schedule"]["run_at"] - datetime.now()).total_seconds()
        remaining_txt = "실행 대기 중" if diff < 0 else self._format_remaining(next_s["schedule"]["run_at"])
        self.next_task_lbl.setText(f"{next_s['task_nm']}  —  {remaining_txt}")
        self.next_task_lbl.setStyleSheet(
            f"color:{ACCENT_LIGHT}; font-size:13px; font-weight:bold; "
            f"background:transparent; border:none;")

    def mark_done(self, job_name: str, total: int | None = None):
        """작업 완료 후 interval에 따라 next run_at 자동 계산하여 재스케줄링"""
        now = datetime.now()
        for i, s in enumerate(store.get_schedules()):
            if s["task_nm"] != job_name:
                continue
            if total is not None:
                s["last_result"] = {"total": total, "finished_at": now.isoformat()}
            iv_key = s["schedule"]["interval"]
            run_at = s["schedule"].get("run_at", now)
            if iv_key not in self._RECUR_STEP:
                store.remove_schedule(i)
                self._refresh_table()
                return
            # 대기 큐에 밀려 늦게 실행되는 등 지연이 한 주기를 넘어도 다음 실행
            # 시각이 과거에 남지 않도록 _advance_to_future()로 한 번 더 보정
            # (과거에 남으면 _register_timer()가 즉시 재실행시키는 것과 같은 버그).
            next_run = self._advance_to_future(run_at + self._RECUR_STEP[iv_key], iv_key)
            store.get_schedules()[i]["schedule"]["run_at"] = next_run
            store.update_schedule_status(i, "대기")
            self._register_timer(i)
        self._refresh_table()
        self._save_schedules_to_json()

    def _save_schedules_to_json(self):
        try:
            serializable = []
            for s in store.get_schedules():
                entry  = deepcopy(s)
                run_at = entry.get("schedule", {}).get("run_at")
                if isinstance(run_at, datetime):
                    entry["schedule"]["run_at"] = run_at.isoformat()
                serializable.append(entry)
            os.makedirs(self.app_dir, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SchedulerPage] 스케줄 저장 실패: {e}")

    _RECUR_STEP = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1), "monthly": timedelta(days=30)}

    def _advance_to_future(self, run_at: datetime, iv_key: str) -> datetime:
        """run_at이 과거 시각이면 iv_key 주기만큼 반복해서 더해 미래 시각으로 당깁니다.

        앱이 꺼져 있는 동안 실행 시각이 지나버린 반복 스케줄을 그대로 두면
        _register_timer()가 ms=max(0, 음수)=0으로 계산해 앱 기동 직후
        (시작 버튼을 누르지 않아도) 즉시 실행돼 버리므로, 로드 시점에 다음
        미래 시각으로 보정합니다.
        """
        step = self._RECUR_STEP.get(iv_key)
        if step is None:
            return run_at
        now = datetime.now()
        while run_at <= now:
            run_at += step
        return run_at

    def _load_schedules_from_json(self):
        target = self.file_path if os.path.exists(self.file_path) else self.default_source
        if not os.path.exists(target):
            return
        try:
            with open(target, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if not isinstance(saved, list):
                return
            now = datetime.now()
            for entry in saved:
                try:
                    run_at_raw = entry.get("schedule", {}).get("run_at")
                    run_at_dt  = (datetime.fromisoformat(run_at_raw)
                                  if isinstance(run_at_raw, str) else None)
                    iv_key = entry.get("schedule", {}).get("interval")
                    if iv_key == "date" and run_at_dt and run_at_dt < now:
                        entry["schedule"]["status"] = "완료"
                        entry["schedule"]["run_at"]  = None
                    elif run_at_dt and run_at_dt < now and iv_key in self._RECUR_STEP:
                        entry["schedule"]["run_at"] = self._advance_to_future(run_at_dt, iv_key)
                    else:
                        entry["schedule"]["run_at"] = run_at_dt
                    store.add_schedule(entry)
                except Exception as e:
                    print(f"[SchedulerPage] 스케줄 항목 복원 실패: {e}")
                    continue
            for idx, s in enumerate(store.get_schedules()):
                if s["schedule"].get("status") != "완료":
                    self._register_timer(idx)
        except Exception as e:
            print(f"[SchedulerPage] 스케줄 파일 로드 실패: {e}")

    # ── 스케줄 작업 등록·수정 통합 저장 ──────────────────

    # ── 스케줄 작업 Dialog (등록 / 수정 통합) ──────────────
    def _manage_schedule_task(self, sched_task=None, idx=None):
        """
        스케줄 등록·수정 다이얼로그를 띄운다.

        Parameters
        ----------
        sched_task : str  '등록' | '수정'
        idx        : int  수정 대상 스케줄 인덱스 (수정 모드에서만 필요)
        """
        # ── 수정 모드 선가드 ──────────────────────────────
        s = None
        if sched_task == "수정":
            if idx is None:
                return
            schedules = store.get_schedules()
            if idx >= len(schedules):
                return
            s = schedules[idx]

            # 수정 모드에서 공통으로 쓰이는 기존 값을 한 번만 파싱
            output_info      = customized_settings.get_output_settings()
            existing_extract = s.get("extract", output_info.get("extract", {}))
            ef               = existing_extract.get("file", {})
            edb              = existing_extract.get("db", {})
            existing_schedule   = s.get("schedule", {})
            existing_exec_str   = existing_schedule.get("exec_str", "")
            existing_interval   = existing_schedule.get("interval", "none")
            existing_run_at     = existing_schedule.get("run_at")
        else:
            output_info = customized_settings.get_output_settings()

        # ── 정제 규칙 설정(스케줄 전용) 초기값 ─────────────
        # "refine_rules" 키가 없으면(구버전 스케줄 또는 신규 등록) 기본값으로 폴백.
        # "제외 필드 지정"(drop_columns)은 애초에 키 자체를 두지 않는다(오른쪽 정제
        # 규칙 패널 참고 — Raw 수집 결과를 봐야 설정 가능한 규칙이라 무인 실행
        # 특성상 제외).
        if sched_task == "수정":
            _saved_refine_rules = existing_extract.get("refine_rules", SCHEDULED_REFINE_RULES_DIALOG_DEFAULT)
            _saved_fill_value   = existing_extract.get("fill_null_value", "")
        else:
            _saved_refine_rules = SCHEDULED_REFINE_RULES_DIALOG_DEFAULT
            _saved_fill_value   = ""

        # ── 다이얼로그 기본 설정 ──────────────────────────
        dlg = QDialog(self)
        dlg.setWindowTitle("새 스케줄 등록" if sched_task == "등록" else "스케줄 수정")
        dlg.setMinimumWidth(560)
        dlg.setStyleSheet(f"background:{BG_SECONDARY}; border:1px solid {BORDER};")

        # 좌(기존 폼)/우(정제 규칙 패널, "정제" 선택 시에만 노출) 2열 구조 —
        # 정제 규칙 설정을 세로가 아닌 가로 방향으로 확장해 다이얼로그가
        # 무한정 길어지지 않도록 함(2026-07-17, UI/UX 피드백)
        outer = QHBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        left_container = QWidget()
        outer.addWidget(left_container, 2)

        root = QVBoxLayout(left_container)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(0)

        # ── 공통 헬퍼 ─────────────────────────────────────
        def sec_label(text):
            lbl = parts.make_label(text.upper(), TEXT_MUTED, 9)
            lbl.setStyleSheet(lbl.styleSheet() + " letter-spacing:1.5px;")
            return lbl

        def field_row(label, widget, label_w=110):
            row = QHBoxLayout()
            row.setSpacing(8)
            lw = parts.make_label(label, TEXT_SECONDARY, 12)
            lw.setFixedWidth(label_w)
            row.addWidget(lw)
            row.addWidget(widget, 1)
            return row

        def hms_combos():
            h = QComboBox()
            h.addItems([f"{t:02d}" for t in range(24)])
            m = QComboBox()
            m.addItems([f"{t:02d}" for t in range(60)])
            sc = QComboBox()
            sc.addItems([f"{t:02d}" for t in range(60)])
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
            for cb in (h, m, sc):
                cb.setFixedWidth(52)
                cb.setStyleSheet(hms_style)
            return h, m, sc

        def time_sep():
            lbl = parts.make_label(":", TEXT_MUTED, 13, True)
            lbl.setFixedWidth(8)
            return lbl

        def iv_lbl(t):
            return parts.make_label(t, TEXT_SECONDARY, 12)

        def _parse_hms_from_exec_str(exec_str: str):
            """exec_str 마지막 HH:MM:SS 파싱 → (h, m, s) int tuple"""
            try:
                part = exec_str.strip().split()[-1]
                h_, m_, s_ = part.split(":")
                return int(h_), int(m_), int(s_)
            except Exception:
                return 0, 0, 0

        # ── 타이틀 ────────────────────────────────────────
        root.addWidget(parts.make_label(
            "새 스케줄 등록" if sched_task == "등록" else "스케줄 수정",
            TEXT_PRIMARY, 14, True
        ))
        root.addSpacing(10)
        root.addWidget(Divider())
        root.addSpacing(14)

        # ── 기본 정보 ─────────────────────────────────────
        root.addWidget(sec_label("기본 정보"))
        root.addSpacing(8)

        # 대상 블루프린트 선택 — 이 스케줄이 어느 수집 항목을 실행할지 지정
        sched_blueprint_combo = QComboBox()
        for bp in BlueprintStorage().list_blueprints():
            sched_blueprint_combo.addItem(bp.get("title") or bp.get("seq_no"), bp.get("seq_no"))
        if len(BlueprintStorage().list_seq_nos()) <= 1:
            sched_blueprint_combo.setEnabled(False)

        if sched_task == "등록":
            sched_name   = QLineEdit("작업명을 입력하세요.")
            callback_url = QLineEdit(BlueprintStorage().read()["callback_url"])
            default_idx = sched_blueprint_combo.findData(BlueprintStorage().active_seq_no)
            sched_blueprint_combo.setCurrentIndex(max(default_idx, 0))
            # 대상 선택이 바뀌면 그 블루프린트의 URL로 Target URL을 갱신
            def _on_sched_blueprint_changed(_):
                callback_url.setText(
                    (BlueprintStorage().get(sched_blueprint_combo.currentData()) or {}).get("callback_url", "")
                )
                callback_url.setCursorPosition(0)
                _apply_render_safety_limits(sched_blueprint_combo.currentData())
            sched_blueprint_combo.currentIndexChanged.connect(_on_sched_blueprint_changed)
        else:
            sched_name   = QLineEdit(s.get("task_nm", ""))
            callback_url = QLineEdit(s.get("callback_url", ""))
            saved_idx = sched_blueprint_combo.findData(s.get("seq_no"))
            if saved_idx < 0:
                saved_idx = sched_blueprint_combo.findData(BlueprintStorage().active_seq_no)
            sched_blueprint_combo.setCurrentIndex(max(saved_idx, 0))

        callback_url.setCursorPosition(0)
        root.addLayout(field_row("Task Name", sched_name))
        root.addSpacing(6)
        root.addLayout(field_row("수집 대상", sched_blueprint_combo))
        root.addSpacing(6)
        root.addLayout(field_row("Target URL", callback_url))
        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        # ── 수집 설정 ─────────────────────────────────────
        root.addWidget(sec_label("수집 설정"))
        root.addSpacing(8)

        sched_delay = BoundNoticeDoubleSpinBox()
        sched_delay.setRange(0.5, 10.0)
        sched_delay.setSingleStep(0.5)
        sched_delay.setDecimals(1)
        sched_delay.setValue(s.get("delay", 0.5) if sched_task == "수정" else 0.5)
        default_min_delay = sched_delay.minimum()

        sched_threads = BoundNoticeSpinBox()
        sched_threads.setRange(1, 16)
        sched_threads.setValue(s.get("threads", 4) if sched_task == "수정" else 4)
        default_max_threads = sched_threads.maximum()

        sched_timeout = QSpinBox()
        sched_timeout.setRange(1, 60)
        sched_timeout.setValue(s.get("timeout", 10) if sched_task == "수정" else 10)

        sched_retry = QSpinBox()
        sched_retry.setRange(0, 5)
        sched_retry.setValue(s.get("retry", 3) if sched_task == "수정" else 3)

        # 대상 블루프린트가 렌더링(html_render) 모드면 Threads/Delay 범위를 안전
        # 상한/하한으로 좁힌다 (단일 소스: customized_settings.get_render_safety_limits()).
        # 상한/하한을 넘으려는 시도는 상시 문구 대신 QToolTip 말풍선으로만 안내한다.
        def _apply_render_safety_limits(seq_no):
            blueprint = BlueprintStorage().get(seq_no) or {}
            if get_spider_mode(blueprint) == "html_render":
                apply_render_safety_limits(
                    sched_threads, sched_delay, customized_settings.get_render_safety_limits()
                )
            else:
                reset_render_safety_limits(
                    sched_threads, sched_delay, default_max_threads, default_min_delay
                )

        if sched_task == "수정":
            sched_blueprint_combo.currentIndexChanged.connect(
                lambda _: _apply_render_safety_limits(sched_blueprint_combo.currentData())
            )
        _apply_render_safety_limits(sched_blueprint_combo.currentData())

        cs_row = QHBoxLayout()
        cs_row.setSpacing(8)
        for lbl_txt, w in [
            ("Delay(s)", sched_delay), ("Thread", sched_threads),
            ("Timeout(s)", sched_timeout), ("Retry", sched_retry)
        ]:
            cs_row.addWidget(parts.make_label(lbl_txt, TEXT_MUTED, 11))
            cs_row.addWidget(w)
        cs_row.addStretch()
        root.addLayout(cs_row)
        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        # ── Save Setting ──────────────────────────────────
        root.addWidget(sec_label("Save Setting"))
        root.addSpacing(8)

        if sched_task == "등록":
            self._sched_out_mode = "FILE" if output_info["extract"]["file"]["enabled"] else "DB"
        else:
            self._sched_out_mode = "FILE" if ef.get("enabled", True) else "DB"

        sched_out_file_btn = TagButton("FILE")
        sched_out_file_btn.setToolTip("로컬 파일로 저장 (CSV / JSON / Excel)")
        sched_out_db_btn = TagButton("DB")
        sched_out_db_btn.setToolTip("데이터베이스 서버로 전송")
        sched_out_file_btn.setChecked(self._sched_out_mode == "FILE")
        sched_out_db_btn.setChecked(self._sched_out_mode == "DB")

        sched_out_mode_lbl = parts.make_label(
            "로컬 파일 저장 모드" if self._sched_out_mode == "FILE" else "DB 서버 전송 모드",
            TEXT_MUTED, 10
        )
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        out_row.addWidget(parts.make_label("출력 대상", TEXT_MUTED, 11))
        out_row.addSpacing(6)
        out_row.addWidget(sched_out_file_btn)
        out_row.addWidget(sched_out_db_btn)
        out_row.addSpacing(10)
        out_row.addWidget(sched_out_mode_lbl)
        out_row.addStretch()
        root.addLayout(out_row)
        root.addSpacing(8)

        # ── 자동 저장 대상 (RAW / 정제) ────────────────────
        if sched_task == "등록":
            sched_auto_save_source = output_info["extract"].get("auto_save_source", "raw")
        else:
            sched_auto_save_source = existing_extract.get("auto_save_source", "raw")

        sched_auto_raw_btn = TagButton("RAW")
        sched_auto_ref_btn = TagButton("정제")
        sched_auto_raw_btn.setChecked(sched_auto_save_source != "refined")
        sched_auto_ref_btn.setChecked(sched_auto_save_source == "refined")
        sched_auto_ref_btn.setToolTip(
            "정제 선택 시 오른쪽에 이 스케줄에 적용할 정제 규칙 패널이 나타납니다. "
            "현재 화면의 '② 정제 규칙 설정' 탭 체크 상태와는 무관합니다."
        )

        auto_src_row = QHBoxLayout()
        auto_src_row.setSpacing(8)
        auto_src_row.addWidget(parts.make_label("저장 대상", TEXT_MUTED, 11))
        auto_src_row.addSpacing(6)
        auto_src_row.addWidget(sched_auto_raw_btn)
        auto_src_row.addWidget(sched_auto_ref_btn)
        auto_src_row.addStretch()
        root.addLayout(auto_src_row)
        root.addSpacing(8)

        # ── 정제 규칙 설정 패널 (오른쪽, "정제" 선택 시에만 노출) ──────
        # "제외 필드 지정"은 Raw 수집 결과를 봐야 설정 가능한 규칙이라 무인 실행
        # 특성상 제공하지 않음(나머지 6개 규칙만 구성 가능).
        sched_refine_divider = Divider(orientation="v")
        sched_refine_panel = QWidget()
        # 고정 폭 대신 최소/최대 폭만 지정 — 창을 가로로 늘리면 이 패널도 함께
        # 넓어져 규칙 설명 텍스트가 더 여유 있게 보이도록 함(2026-07-17, 텍스트
        # 잘림 피드백. wordWrap도 함께 켰지만 창 폭을 넓혀 더 여유를 줄 수 있게)
        sched_refine_panel.setMinimumWidth(260)
        sched_refine_panel.setMaximumWidth(400)
        refine_panel_layout = QVBoxLayout(sched_refine_panel)
        refine_panel_layout.setContentsMargins(16, 18, 16, 18)
        refine_panel_layout.setSpacing(8)

        refine_panel_layout.addWidget(parts.make_label("정제 규칙 설정", TEXT_PRIMARY, 12, bold=True))
        refine_panel_desc = parts.make_label(
            "무인(스케줄) 실행 시 적용할 규칙입니다. \"제외 필드 지정\"은 Raw 수집 결과를 "
            "직접 봐야 설정 가능해 여기서는 제공되지 않습니다.",
            TEXT_MUTED, 10
        )
        refine_panel_desc.setWordWrap(True)
        refine_panel_layout.addWidget(refine_panel_desc)
        refine_panel_layout.addSpacing(4)

        sched_refine_checkboxes: dict[str, QCheckBox] = {}
        _refine_panel_result = build_refine_rule_rows(
            parts, refine_panel_layout, sched_refine_checkboxes, dict(_saved_refine_rules),
            include_keys=[
                "remove_null_row", "custom_rule", "trim_whitespace",
                "remove_duplicate", "fill_null", "cast_numeric",
            ],
        )
        sched_refine_fill_input = _refine_panel_result["fill_null_input"]
        if sched_refine_fill_input is not None:
            sched_refine_fill_input.setText(_saved_fill_value)

        # "커스텀 정제 규칙 적용" 초기값 재확인 — 현재 선택된 "대상 블루프린트"에
        # refine/{seq_no}.py가 없으면 위에서 넣은 _saved_refine_rules(기본값 또는
        # 저장된 값)와 무관하게 무조건 꺼둔다. 파일이 있으면 그대로 둔다
        # (MonitorPageSingle __init__과 동일한 규칙 — 판단 기준은
        # trigger/common.py의 _sync_custom_rule_checkbox 한 곳뿐).
        _sync_custom_rule_checkbox(sched_blueprint_combo.currentData(), sched_refine_checkboxes)

        # "커스텀 정제 규칙 적용" 체크박스의 stateChanged 핸들러 — 실제
        # 검증/자동 연동 로직은 trigger/common.py의 _handle_custom_rule_toggle이
        # 전담하며(정제 페이지의 _on_custom_rule_toggled와 공유), 여기서는
        # seq_no와 경고 콜백만 이 다이얼로그의 컨텍스트로 채워 넘긴다. seq_no는
        # 이 패널이 아니라 "대상 블루프린트" 콤보의 현재 선택값에서 가져온다 —
        # 이 다이얼로그는 seq_no가 고정이 아니라 콤보로 실행 중에 바뀌기 때문이다.
        _sched_refine_custom_cb = sched_refine_checkboxes.get("custom_rule")
        if _sched_refine_custom_cb is not None:
            def _on_sched_refine_custom_rule_toggled(chk_state):
                seq_no = sched_blueprint_combo.currentData()
                def _warn():
                    bp = BlueprintStorage().get(seq_no) or {}
                    _warn_custom_rule_missing(dlg, bp.get("title") or seq_no)
                _handle_custom_rule_toggle(chk_state, seq_no, sched_refine_checkboxes, _warn)
            _sched_refine_custom_cb.stateChanged.connect(_on_sched_refine_custom_rule_toggled)

            # "대상 블루프린트" 선택이 바뀔 때마다 그 블루프린트의 스크립트
            # 존재 여부로 재동기화한다 — 정제 페이지의 "탭 재진입마다 재동기화"에
            # 대응. 파일이 없으면 무조건 끄고(팝업 없이 조용히 — 콤보를 여러 번
            # 눌러볼 때마다 모달이 뜨면 방해가 됨), 있으면 사용자가 남긴 상태를
            # 그대로 둔다. 기존에 이 콤보에 이미 연결된 URL/렌더링 안전 한도
            # 핸들러와는 무관하게 별도로 추가 연결한다.
            def _sync_sched_custom_rule_on_blueprint_change(_):
                _sync_custom_rule_checkbox(sched_blueprint_combo.currentData(), sched_refine_checkboxes)
            sched_blueprint_combo.currentIndexChanged.connect(_sync_sched_custom_rule_on_blueprint_change)

        refine_panel_layout.addStretch()

        sched_refine_divider.setVisible(sched_auto_ref_btn.isChecked())
        sched_refine_panel.setVisible(sched_auto_ref_btn.isChecked())
        outer.addWidget(sched_refine_divider)
        outer.addWidget(sched_refine_panel, 1)

        def _sched_select_auto_src(is_refined):
            sched_auto_raw_btn.setChecked(not is_refined)
            sched_auto_ref_btn.setChecked(is_refined)
            sched_refine_divider.setVisible(is_refined)
            sched_refine_panel.setVisible(is_refined)
            dlg.layout().activate()
            # setVisible() 직후에는 dlg.sizeHint()가 아직 새 크기를 반영하지
            # 못한 경우가 있어(_update_sched_dialog_size()와 동일 원인), 이벤트
            # 루프를 한 번 처리시켜 레이아웃을 정착시킨 뒤 resize. adjustSize()는
            # 이미 show()된 다이얼로그에서는 줄어드는 방향으로 갱신되지 않아 미사용.
            QApplication.processEvents()
            dlg.layout().activate()
            dlg.resize(dlg.sizeHint())

        sched_auto_raw_btn.clicked.connect(lambda: _sched_select_auto_src(False))
        sched_auto_ref_btn.clicked.connect(lambda: _sched_select_auto_src(True))

        # ── 추출 설정 스택 (FILE / DB) ────────────────────
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

        # ── PAGE 0 : FILE 설정 ────────────────────────────
        sched_file_defaults = {
            "file_path": (ef.get("file_path") or customized_settings.set_desktop_dir()) if sched_task == "수정"
                         else (output_info["extract"]["file"]["file_path"] or customized_settings.set_desktop_dir()),
            "file_name": (ef.get("file_name") or "untitled0") if sched_task == "수정"
                         else (output_info["extract"]["file"]["file_name"] or "untitled0"),
            "file_format": (
                ef.get("file_format") or "CSV" if sched_task == "수정"
                else output_info["extract"]["file"]["file_format"]
            ),
            "file_encoding": (
                ef.get("file_encoding") or "UTF-8 BOM" if sched_task == "수정"
                else output_info["extract"]["file"]["file_encoding"]
            ),
            "file_delimiter": (
                ef.get("file_delimiter") or "," if sched_task == "수정"
                else (output_info["extract"]["file"]["file_delimiter"] or ",")
            ),
        }
        sched_file_page, _sched_file_widgets, _sched_toggle_csv_fields = _build_output_file_page(
            sched_file_defaults, dlg
        )
        sched_path_edit = _sched_file_widgets["path_edit"]
        sched_file_nm   = _sched_file_widgets["file_nm"]
        sched_fmt_combo = _sched_file_widgets["fmt_combo"]
        sched_enc_combo = _sched_file_widgets["enc_combo"]
        sched_csv_delim = _sched_file_widgets["csv_delimeter"]

        def _sched_on_fmt_changed(fmt_text: str):
            _sched_toggle_csv_fields(fmt_text)

        sched_fmt_combo.currentTextChanged.connect(_sched_on_fmt_changed)
        _sched_on_fmt_changed(sched_fmt_combo.currentText())

        sched_extract_stack.addWidget(sched_file_page)  # index 0

        # ── PAGE 1 : DB 설정 ──────────────────────────────
        sched_db_page = QWidget()
        sdp = QVBoxLayout(sched_db_page)
        sdp.setContentsMargins(14, 14, 14, 14)
        sdp.setSpacing(8)

        if sched_task == "등록":
            _sched_db_info = output_info["extract"]["db"]
        else:
            edb_dflt = {"host": "localhost", "port": "3306", "db_env": "MySQL"}
            _sched_db_info = {k: edb.get(k) or edb_dflt.get(k, "") for k in
                               ("db_env", "host", "port", "database", "schema", "user", "password", "save_data_nm")}

        sgrid = QGridLayout()
        sgrid.setSpacing(8)
        sgrid.setColumnStretch(1, 1)
        sdb_widgets = _build_db_settings_fields(sgrid, _sched_db_info)
        _sdb_type, _sdb_host, _sdb_port = sdb_widgets["db_type"], sdb_widgets["host"], sdb_widgets["port"]
        _sdb_name, _sdb_schema          = sdb_widgets["name"], sdb_widgets["schema"]
        _sdb_user, _sdb_pw, _sdb_data   = sdb_widgets["user"], sdb_widgets["password"], sdb_widgets["save_data_nm"]
        sdp.addLayout(sgrid)

        sched_test_row = QHBoxLayout()
        sched_test_row.setSpacing(10)
        sched_test_btn = parts.outline_btn("TEST CONNECTION")
        sched_test_result_lbl = parts.make_label("", TEXT_MUTED, 11)
        _wire_db_test_button(sched_test_btn, sched_test_result_lbl, sdb_widgets, dlg)
        sched_test_row.addWidget(sched_test_btn)
        sched_test_row.addWidget(sched_test_result_lbl)
        sched_test_row.addStretch()
        sdp.addLayout(sched_test_row)

        sched_extract_stack.addWidget(sched_db_page)  # index 1
        sched_extract_stack.setCurrentIndex(0 if self._sched_out_mode == "FILE" else 1)

        def _update_sched_dialog_size():
            current_page = sched_extract_stack.currentWidget()
            if current_page:
                current_page.layout().activate()
                sched_extract_stack.setFixedHeight(current_page.layout().sizeHint().height())
            dlg.layout().activate()
            # setFixedHeight() 직후에는 dlg.sizeHint()가 아직 새 높이를 반영하지
            # 못한 상태(한 박자 뒤처진 값)를 돌려주는 경우가 있어(실측 확인 —
            # DB→FILE 전환 시 늘어난 세로 길이가 되돌아가지 않던 버그의 원인),
            # 이벤트 루프를 한 번 처리시켜 레이아웃을 완전히 정착시킨 뒤 sizeHint
            # 기준으로 resize. adjustSize()는 이미 show()된 다이얼로그에서 창을
            # 줄이는 방향으로는 갱신되지 않아 사용하지 않음.
            QApplication.processEvents()
            dlg.layout().activate()
            dlg.resize(dlg.sizeHint())

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

        sched_fmt_combo.currentTextChanged.disconnect(_sched_on_fmt_changed)
        def _sched_on_fmt_changed_with_resize(fmt_text: str):
            _sched_on_fmt_changed(fmt_text)
            _update_sched_dialog_size()
        sched_fmt_combo.currentTextChanged.connect(_sched_on_fmt_changed_with_resize)

        root.addWidget(sched_extract_stack)
        root.addSpacing(10)

        # ── 저장 방식 콤보 ────────────────────────────────
        sched_save_type = QComboBox()
        sched_save_type.addItems(["선택하세요", "새로 만들기", "덮어쓰기", "추가하기"])
        if sched_task == "수정":
            existing_save_type = existing_schedule.get("schedule_save_type", "선택하세요")
            if existing_save_type in ["새로 만들기", "덮어쓰기", "추가하기"]:
                sched_save_type.setCurrentText(existing_save_type)
        sched_save_type.setFixedWidth(130)
        sched_save_type.setStyleSheet(theme.CB_STYLE)

        sv_row = QHBoxLayout()
        sv_row.setSpacing(8)
        sv_row.addWidget(parts.make_label("저장 방식", TEXT_MUTED, 11))
        sv_row.addWidget(sched_save_type)
        sv_row.addStretch()
        root.addLayout(sv_row)
        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        _update_sched_dialog_size()

        # ── Interval ──────────────────────────────────────
        root.addWidget(sec_label("Interval"))
        root.addSpacing(8)

        sched_interval = QComboBox()
        sched_interval.addItems(["선택하세요", "매일", "매주", "매월", "특정 날짜"])
        sched_interval.setFixedWidth(120)
        sched_interval.setStyleSheet(theme.CB_STYLE)

        container_daily   = QWidget()
        container_weekly  = QWidget()
        container_monthly = QWidget()
        container_date    = QWidget()

        # 매일
        self.d_h, self.d_m, self.d_s = hms_combos()
        dl = QHBoxLayout(container_daily)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(6)
        dl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(iv_lbl("시간"), 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(self.d_h, 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(self.d_m, 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(time_sep(), 0, Qt.AlignmentFlag.AlignVCenter)
        dl.addWidget(self.d_s, 0, Qt.AlignmentFlag.AlignVCenter)
        container_daily.setVisible(False)

        # 매주
        self.w_day = QComboBox()
        self.w_day.addItems(["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"])
        self.w_day.setFixedWidth(76)
        self.w_day.setStyleSheet(theme.CB_STYLE)
        self.w_h, self.w_m, self.w_s = hms_combos()
        wl = QHBoxLayout(container_weekly)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(6)
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
        self.m_day = QComboBox()
        self.m_day.addItems([str(d) for d in range(1, 32)])
        self.m_day.setFixedWidth(50)
        self.m_day.setStyleSheet(theme.CB_STYLE)
        self.m_h, self.m_m, self.m_s = hms_combos()
        ml = QHBoxLayout(container_monthly)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(6)
        ml.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(iv_lbl("매월"), 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.m_day, 0, Qt.AlignmentFlag.AlignVCenter)
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
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
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
        datl = QHBoxLayout(container_date)
        datl.setContentsMargins(0, 0, 0, 0)
        datl.setSpacing(6)
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

        # ── 수정 모드: 기존 값을 위젯에 반영 ─────────────
        if sched_task == "수정":
            _iv_map = {"daily": 1, "weekly": 2, "monthly": 3, "date": 4}
            sched_interval.setCurrentIndex(_iv_map.get(existing_interval, 0))

            _ph, _pm, _ps = _parse_hms_from_exec_str(existing_exec_str)
            for cb, val in [
                (self.d_h, _ph), (self.d_m, _pm), (self.d_s, _ps),
                (self.w_h, _ph), (self.w_m, _pm), (self.w_s, _ps),
                (self.m_h, _ph), (self.m_m, _pm), (self.m_s, _ps),
                (self.dat_h, _ph), (self.dat_m, _pm), (self.dat_s, _ps),
            ]:
                cb.setCurrentText(f"{val:02d}")

            if existing_interval == "weekly":
                _DAY_NAMES = ["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"]
                for dn in _DAY_NAMES:
                    if dn in existing_exec_str:
                        self.w_day.setCurrentText(dn)
                        break

            if existing_interval == "monthly":
                try:
                    _day_match = re.search(r"매월\s*(\d+)일", existing_exec_str)
                    if _day_match:
                        self.m_day.setCurrentText(_day_match.group(1))
                except Exception:
                    pass

            if existing_interval == "date" and existing_run_at:
                try:
                    ra = existing_run_at if isinstance(existing_run_at, datetime) \
                         else datetime.fromisoformat(str(existing_run_at))
                    self.date_edit.setDate(QDate(ra.year, ra.month, ra.day))
                except Exception:
                    self.date_edit.setDate(QDate.currentDate())
            else:
                self.date_edit.setDate(QDate.currentDate())
        else:
            self.date_edit.setDate(QDate.currentDate())

        # ── 주기 선택 행 ──────────────────────────────────
        iv_row = QHBoxLayout()
        iv_row.setSpacing(8)
        iv_row.setContentsMargins(0, 0, 0, 0)
        iv_row.addWidget(iv_lbl("주기"), 0, Qt.AlignmentFlag.AlignVCenter)
        iv_row.addWidget(sched_interval, 0, Qt.AlignmentFlag.AlignVCenter)
        iv_row.addStretch()

        detail_wrap = QWidget()
        detail_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        detail_lay = QHBoxLayout(detail_wrap)
        detail_lay.setContentsMargins(8, 0, 0, 0)
        detail_lay.setSpacing(6)
        for c in [container_daily, container_weekly, container_monthly, container_date]:
            detail_lay.addWidget(c, 0, Qt.AlignmentFlag.AlignVCenter)
        detail_lay.addStretch()

        def _on_iv_changed(iv_idx):
            container_daily.setVisible(iv_idx == 1)
            container_weekly.setVisible(iv_idx == 2)
            container_monthly.setVisible(iv_idx == 3)
            container_date.setVisible(iv_idx == 4)

        sched_interval.currentIndexChanged.connect(_on_iv_changed)
        _on_iv_changed(sched_interval.currentIndex())

        root.addLayout(iv_row)
        root.addSpacing(4)
        root.addWidget(detail_wrap)
        root.addSpacing(12)
        root.addWidget(Divider())
        root.addSpacing(12)

        # ── sched_info_dict 구성 ──────────────────────────
        sched_info_dict = {
            "sched_task":   sched_task,         # _apply_schedule이 모드를 구분하는 키
            "idx":          idx,                 # 수정 시 int, 등록 시 None
            "sched_name":   sched_name,
            "blueprint_combo": sched_blueprint_combo,
            "callback_url": callback_url,
            "delay":        sched_delay,
            "threads":      sched_threads,
            "timeout":      sched_timeout,
            "retry":        sched_retry,
            "interval":     sched_interval,
            "d_h": self.d_h,   "d_m": self.d_m,   "d_s": self.d_s,
            "w_day": self.w_day,
            "w_h": self.w_h,   "w_m": self.w_m,   "w_s": self.w_s,
            "m_day": self.m_day,
            "m_h": self.m_h,   "m_m": self.m_m,   "m_s": self.m_s,
            "date_edit":    self.date_edit,
            "dat_h": self.dat_h, "dat_m": self.dat_m, "dat_s": self.dat_s,
            "save_type":    sched_save_type,
            "auto_src_ref_btn": sched_auto_ref_btn,
            "refine_checkboxes": sched_refine_checkboxes,   # {key: QCheckBox}
            "refine_fill_input": sched_refine_fill_input,   # QLineEdit | None
            "path_edit":    sched_path_edit,
            "file_nm":      sched_file_nm,
            "fmt_combo":    sched_fmt_combo,
            "enc_combo":    sched_enc_combo,
            "csv_delim":    sched_csv_delim,
            "db_type":      _sdb_type,
            "db_host":      _sdb_host,
            "db_port":      _sdb_port,
            "db_name":      _sdb_name,
            "db_schema":    _sdb_schema,
            "db_user":      _sdb_user,
            "db_pw":        _sdb_pw,
            "db_data":      _sdb_data,
        }

        # ── 하단 버튼 ─────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        apply_btn  = parts.action_btn("적용")
        cancel_btn = parts.outline_btn("취소")
        apply_btn.clicked.connect(lambda: self._apply_schedule(dlg=dlg, sched_info_dict=sched_info_dict))
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

        dlg.adjustSize()
        dlg.exec()
