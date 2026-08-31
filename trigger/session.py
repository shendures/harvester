# trigger/session.py
# 프록시 연결 테스트 스레드/다이얼로그(ProxyHealthCheckThread, ProxyTestProgressDialog)와
# SessionSettingsPage의 세션·프록시 설정 메서드(SessionSettingsPageTriggers).

import re
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, CancelledError

import requests

from PyQt6.QtWidgets import (
    QFileDialog, QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QComboBox, QMenu, QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from style import Divider

from .common import theme, parts, BG_SECONDARY, TEXT_PRIMARY, TEXT_SECONDARY, BORDER, _get_log_manager

# 이 파일의 소형 다이얼로그(연결 테스트 진행창 / 새 프록시 추가창)가 공유하는 폭 —
# 둘 다 같은 "간단한 폼 다이얼로그" 형태라 서로 다른 값을 쓸 이유가 없다.
_SMALL_DIALOG_WIDTH = 360


class ProxyHealthCheckThread(QThread):
    """
    "연결 테스트" 버튼 클릭 시, 넘겨받은 프록시 각각에 실제로 연결을 시도해
    응답 가능 여부를 확인합니다. 어떤 행을 검사할지는 전적으로 호출자가 결정해
    rows로 넘기며(활성/비활성 여부와 무관하게 넘겨진 것은 모두 검사), 이 클래스는
    거르지 않고 그대로 검사합니다.

    GUI 스레드를 막지 않기 위해 QThread에서 실행되며, 프록시 목록이 많아도
    전체 대기 시간이 늘어지지 않도록 ThreadPoolExecutor로 병렬 검사합니다.
    검사 결과는 row_checked 시그널로만 전달하고 위젯은 직접 건드리지 않습니다
    (Qt 위젯은 GUI 스레드에서만 조작 가능 — 수신 측 슬롯에서 테이블을 갱신).
    cancel()로 중도 취소할 수 있으며, 취소 이후에도 all_checked는 항상 emit됩니다.
    """

    row_checked = pyqtSignal(int, bool)  # row_index, is_alive
    all_checked = pyqtSignal(int, int)  # alive_count, dead_count

    TEST_URL = "http://www.gstatic.com/generate_204"  # body 없이 204만 반환하는 경량 연결성 확인용 엔드포인트
    TIMEOUT = 5  # 초
    # 헬스체크는 대부분 소켓 connect/응답 대기인 I/O-bound 작업이라 GIL이 대기 구간에서
    # 풀리므로, 스레드 수를 늘리는 것만으로 처리량이 거의 선형에 가깝게 늘어난다.
    # 실측(2,026개 상용 프록시 목록, 대부분 무응답): 10 → 60에서 4.46배, 100까지는 여전히
    # 뚜렷하게 개선되고 150부터 수익 체감이 커져 100을 균형점으로 채택했다.
    MAX_WORKERS = 100

    def __init__(self, rows: list, parent=None):
        super().__init__(parent)
        # rows: (테이블 행 인덱스, row dict) 튜플 리스트. 전체 목록 검사든 일부(예: 방금
        # import된 행)만 검사든, 호출자가 실제 테이블 행 번호를 idx로 명시해 넘긴다.
        self._rows = rows
        self._executor = None
        self._cancelled = False

    def cancel(self):
        """
        GUI 스레드에서 호출 — 아직 시작되지 않은 검사는 취소하고, 이미 진행 중인
        요청은 자연 종료(최대 TIMEOUT초)까지만 기다린다. 취소 이후에도 all_checked는
        반드시 emit되므로 호출자는 완료를 기다리기만 하면 된다.
        """
        self._cancelled = True
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _check_one(self, idx: int, row: dict) -> bool:
        """단일 프록시를 검사하고 row_checked를 emit한 뒤, 생존 여부를 반환합니다."""
        protocol = str(row.get("protocol", "http")).lower()
        proxy_url = f"{protocol}://{row['host']}:{row['port']}"
        try:
            requests.get(
                self.TEST_URL,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=self.TIMEOUT,
            )
            self.row_checked.emit(idx, True)
            return True
        except requests.RequestException:
            self.row_checked.emit(idx, False)
            return False

    def run(self) -> None:
        targets = list(self._rows)
        alive_count = dead_count = 0
        if targets:
            self._executor = ThreadPoolExecutor(max_workers=min(self.MAX_WORKERS, len(targets)))
            try:
                futures = [self._executor.submit(self._check_one, idx, row) for idx, row in targets]
                for f in futures:
                    try:
                        if f.result():
                            alive_count += 1
                        else:
                            dead_count += 1
                    except CancelledError:
                        continue  # cancel() 이후 시작되지 못한 작업 — 집계에서 제외
            finally:
                self._executor.shutdown(wait=True)
        self.all_checked.emit(alive_count, dead_count)


class ProxyTestProgressDialog(QDialog):
    """
    "연결 테스트" 진행 중 진행률과 완료 결과를 보여주는 모달 다이얼로그.
    ProxyHealthCheckThread의 row_checked/all_checked를 그대로 연결해서 쓴다.
    진행 중에는 "취소" 버튼(= thread.cancel() 호출), 완료되면 같은 자리가 "닫기"로
    바뀐다.

    취소를 누르면(또는 완료 전 X 버튼) 화면은 그 순간 값으로 즉시 "완료(취소됨)"
    상태로 고정된다 — 이미 시작된 요청은 블로킹 소켓 호출이라 강제로 죽일 수
    없어 스레드는 백그라운드에서 마저 정리되지만, 그 이후 도착하는 row_checked/
    all_checked는 _finished 가드에 막혀 화면에 더 이상 반영되지 않는다.
    """

    def __init__(self, thread: ProxyHealthCheckThread, total: int, parent=None):
        super().__init__(parent)
        self._thread = thread
        self._total = total
        self._done = 0
        self._alive = 0
        self._dead = 0
        self._cancel_requested = False
        self._finished = False

        self.setWindowTitle("프록시 연결 테스트")
        self.setFixedWidth(_SMALL_DIALOG_WIDTH)
        self.setStyleSheet(f"background:{BG_SECONDARY}; border:1px solid {BORDER};")

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(10)

        root.addWidget(parts.make_label("프록시 연결 테스트", TEXT_PRIMARY, 14, True))
        root.addWidget(Divider())

        self._progress_lbl = parts.make_label(f"검사 중... (0 / {total})", TEXT_SECONDARY, 12)
        root.addWidget(self._progress_lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, max(total, 1))
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        root.addWidget(self._bar)

        self._tally_lbl = parts.make_label("정상 0 · 응답없음 0", TEXT_SECONDARY, 12)
        root.addWidget(self._tally_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._action_btn = parts.outline_btn("취소")
        self._action_btn.clicked.connect(self._on_action_clicked)
        btn_row.addWidget(self._action_btn)
        root.addLayout(btn_row)

    def _on_action_clicked(self):
        if self._finished:
            self.accept()
            return
        self._cancel_requested = True
        self._thread.cancel()
        # 대기 중이던 검사만 실제로 건너뛰고, 이미 시작된 요청은 백그라운드에서
        # 자연 종료되도록 둔다(강제로 죽일 수 없는 블로킹 소켓 호출이라) — 다만
        # 화면은 클릭 시점 값으로 즉시 고정한다("취소 중..." 대기 상태 없음).
        self._finish(cancelled=True)

    def _finish(self, cancelled: bool, alive: int = None, dead: int = None) -> None:
        """진행 화면을 "완료" 상태로 확정한다. 이미 확정된 뒤의 호출은 무시한다."""
        if self._finished:
            return
        self._finished = True
        if alive is None:
            alive, dead = self._alive, self._dead
        suffix = " (취소됨)" if cancelled else ""
        self._progress_lbl.setText(f"완료{suffix} ({self._done} / {self._total})")
        self._tally_lbl.setText(f"정상 {alive} · 응답없음 {dead}")
        self._action_btn.setText("닫기")
        self._action_btn.setEnabled(True)

    def on_row_checked(self, idx: int, is_alive: bool) -> None:
        if self._finished:
            return  # 취소로 이미 확정된 뒤 뒤늦게 도착한 신호는 화면에 반영하지 않음
        self._done += 1
        if is_alive:
            self._alive += 1
        else:
            self._dead += 1
        self._bar.setValue(self._done)
        self._progress_lbl.setText(f"검사 중... ({self._done} / {self._total})")
        self._tally_lbl.setText(f"정상 {self._alive} · 응답없음 {self._dead}")

    def on_all_checked(self, alive: int, dead: int) -> None:
        self._finish(cancelled=self._cancel_requested, alive=alive, dead=dead)

    def closeEvent(self, event):
        if not self._finished:
            self._on_action_clicked()  # 취소 처리 + 즉시 완료 전환 (곧바로 _finished=True)
        event.accept()


# ══════════════════════════════════════════════════════
#  SessionSettingsPage Mixin
# ══════════════════════════════════════════════════════
class SessionSettingsPageTriggers:
    """SessionSettingsPage의 프록시 추가·삭제·임포트·활성화 메서드"""

    def _activate_proxy_option(self, is_checked):
        for card in (self.gw2, self.pw):
            card.setEnabled(is_checked)
            self._set_card_visual(card, is_checked)

    def _import_proxy_file(self):
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

        pattern = re.compile(r'(?<!\d)(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})(?!\d)')
        matches = pattern.findall(raw)

        if not matches:
            self._log("warn", f"파일 파싱 완료 — 유효한 IP:PORT를 찾지 못했습니다: {path}")
            return

        existing = {f"{r['host']}:{r['port']}" for r in self._proxy_rows}
        new_rows = []
        skipped  = 0
        for host, port in matches:
            key = f"{host}:{port}"
            if key in existing:
                skipped += 1
                continue
            existing.add(key)
            new_rows.append({"host": host, "port": port, "protocol": "HTTP",
                              "enabled": True})

        added = len(new_rows)
        if added:
            # 대량 삽입 전 repaint·정렬·시그널 중단 — 전체 삽입 후 한 번만 그림
            # blockSignals: 행마다 itemChanged → _on_proxy_item_changed 디스패치 차단
            t = self._proxy_table
            t.setSortingEnabled(False)
            t.setUpdatesEnabled(False)
            t.blockSignals(True)
            try:
                for data in new_rows:
                    self._proxy_rows.append(data)
                    self._insert_table_row(data)
            finally:
                # 예외 발생 시에도 반드시 복원
                t.blockSignals(False)
                t.setUpdatesEnabled(True)
                t.setSortingEnabled(True)

        self._log("ok", f"Import 완료: {added}개 추가 / {skipped}개 중복 제외 ← {path}")

    def _test_all_proxies(self):
        """
        "🔌 연결 테스트" 버튼 클릭 시 호출 — 프록시 목록의 모든 행(활성/비활성 무관)을
        대상으로 ProxyHealthCheckThread를 돌리고, 진행 상황·결과는
        ProxyTestProgressDialog로 보여준다. 스레드 참조는 self에 보관해 실행 중
        GC되지 않도록 한다. 테스트 중에는 "프록시 목록" 카드 전체를 비활성화해
        Import/+ 추가/테이블 조작이 동시에 일어나지 않도록 막는다.
        """
        if not self._proxy_rows:
            self._log("info", "연결 테스트 요청 — 등록된 프록시가 없습니다.")
            return

        self.pw.setEnabled(False)
        rows = list(enumerate(deepcopy(self._proxy_rows)))
        self._proxy_test_thread = ProxyHealthCheckThread(rows, parent=self)
        dlg = ProxyTestProgressDialog(self._proxy_test_thread, total=len(rows), parent=self)
        self._proxy_test_thread.row_checked.connect(self._apply_health_check_result)
        self._proxy_test_thread.row_checked.connect(dlg.on_row_checked)
        self._proxy_test_thread.all_checked.connect(dlg.on_all_checked)
        self._proxy_test_thread.all_checked.connect(self._on_connection_test_finished)
        self._proxy_test_thread.start()
        dlg.exec()  # on_all_checked로 _finished=True가 될 때까지 닫히지 않음
        self.pw.setEnabled(True)

    def _on_connection_test_finished(self, alive: int, dead: int):
        self._proxy_test_thread = None
        self._log("ok" if dead == 0 else "info",
                   f"연결 테스트 완료 — 정상 {alive}건, 응답 없음 {dead}건")

    def _add_proxy_dialog(self):
        """새 프록시 추가 Dialog를 띄운다."""
        dlg = QDialog(self)
        dlg.setWindowTitle("새 프록시 추가")
        dlg.setFixedWidth(_SMALL_DIALOG_WIDTH)
        dlg.setStyleSheet(f"background:{BG_SECONDARY}; border:1px solid {BORDER};")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(0)

        root.addWidget(parts.make_label("새 프록시 추가", TEXT_PRIMARY, 14, True))
        root.addSpacing(10)
        root.addWidget(Divider())
        root.addSpacing(14)

        proto_row = QHBoxLayout()
        proto_row.addWidget(parts.make_label("프로토콜", TEXT_SECONDARY, 12))
        proto_cb = QComboBox()
        proto_cb.addItems(["HTTP", "HTTPS", "SOCKS4", "SOCKS5"])
        proto_row.addWidget(proto_cb, 1)
        root.addLayout(proto_row)
        root.addSpacing(10)

        host_row = QHBoxLayout()
        host_row.addWidget(parts.make_label("호스트", TEXT_SECONDARY, 12))
        host_inp = QLineEdit()
        host_inp.setPlaceholderText("예: 10.0.0.1")
        host_row.addWidget(host_inp, 1)
        root.addLayout(host_row)
        root.addSpacing(10)

        port_row = QHBoxLayout()
        port_row.addWidget(parts.make_label("포트", TEXT_SECONDARY, 12))
        port_inp = QLineEdit()
        port_inp.setPlaceholderText("예: 8080")
        port_row.addWidget(port_inp, 1)
        root.addLayout(port_row)
        root.addSpacing(10)

        btn_row = QHBoxLayout()
        ok_btn = parts.action_btn("추가")

        def _do_add():
            host  = host_inp.text().strip() or "0.0.0.0"
            port  = port_inp.text().strip() or "8080"
            proto = proto_cb.currentText()
            data  = {"host": host, "port": port, "protocol": proto,
                     "enabled": True}
            self._proxy_rows.append(data)
            self._insert_table_row(data)
            self._log("ok", f"프록시 추가됨: {proto} {host}:{port}")
            dlg.close()

        ok_btn.clicked.connect(_do_add)
        cancel_btn = parts.outline_btn("취소")
        cancel_btn.clicked.connect(dlg.close)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)
        dlg.exec()

    def _delete_row(self, row_idx):
        if 0 <= row_idx < self._proxy_table.rowCount():
            host     = self._proxy_table.item(row_idx, 2)
            host_txt = host.text() if host else "?"
            self._proxy_table.removeRow(row_idx)
            # NO(col 0)가 항상 1..N 연속이 되도록, 삭제된 행 아래의 번호를 다시 매김
            t = self._proxy_table
            for r in range(row_idx, t.rowCount()):
                no_item = t.item(r, 0)
                if no_item:
                    no_item.setText(str(r + 1))
            self._log("warn", f"프록시 삭제됨: {host_txt}")

    def _on_proxy_row_clicked(self, item):
        """
        모든 컬럼의 모든 행 클릭 시 활성/비활성 토글.

        [col 4(체크박스) 처리]
        itemChanged 는 체크 상태가 실제로 변경될 때만 발화하므로
        이미 체크된 셀을 다시 클릭하면 itemChanged 가 발화하지 않아
        _on_proxy_item_changed 만으로는 토글이 동작하지 않습니다.
        따라서 col 4 도 itemClicked 에서 처리하고,
        _on_proxy_item_changed 는 programmatic 변경(blockSignals 해제 후 재발화)
        방지 목적으로만 남겨둡니다.
        """
        row = item.row()
        if row >= len(self._proxy_rows):
            return
        current_enabled = self._proxy_rows[row]["enabled"]
        self._proxy_table.blockSignals(True)
        try:
            self._toggle_proxy_enabled(row, not current_enabled)
        finally:
            self._proxy_table.blockSignals(False)

    def _proxy_table_context_menu(self, pos):
        """
        우클릭 컨텍스트 메뉴 — 삭제 버튼(setCellWidget) 제거 대체.
        선택된 행을 삭제하거나 활성 상태를 토글합니다.
        """
        index = self._proxy_table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        menu = QMenu(self)
        # QSS는 THEME.PROXY_CONTEXT_MENU_QSS 프로퍼티에서 관리
        menu.setStyleSheet(theme.PROXY_CONTEXT_MENU_QSS)
        # 활성 토글 — checkState() 기준 (ItemIsUserCheckable 체크박스, col 4 "상태")
        enabled_item = self._proxy_table.item(row, 4)
        is_enabled = (
            enabled_item.checkState() == Qt.CheckState.Checked
        ) if enabled_item else False
        toggle_txt = "비활성으로 전환" if is_enabled else "활성으로 전환"
        toggle_act = menu.addAction(toggle_txt)
        menu.addSeparator()
        # 삭제
        del_act = menu.addAction("🗑  이 행 삭제")
        del_act.setProperty("is_delete", True)

        action = menu.exec(self._proxy_table.viewport().mapToGlobal(pos))
        if action == del_act:
            self._delete_row(row)
        elif action == toggle_act:
            # blockSignals: _toggle_proxy_enabled 내 col 4 setCheckState 시
            # itemChanged 재발생 → _on_proxy_item_changed 중복 호출 방지
            self._proxy_table.blockSignals(True)
            try:
                self._toggle_proxy_enabled(row, not is_enabled)
            finally:
                self._proxy_table.blockSignals(False)

    def _toggle_proxy_enabled(self, row: int, enable: bool):
        """
        상태(col 4) 체크박스·_proxy_rows 동기화.
        호출 전 반드시 blockSignals(True)로 감싸야 itemChanged 재귀를 방지합니다.
        """
        t = self._proxy_table
        if row >= t.rowCount():
            return
        # col 4 — 사용 여부 체크박스
        status_item = t.item(row, 4)
        if status_item:
            status_item.setCheckState(
                Qt.CheckState.Checked if enable else Qt.CheckState.Unchecked
            )
        # _proxy_rows 동기화
        if row < len(self._proxy_rows):
            self._proxy_rows[row]["enabled"] = enable

    def _apply_health_check_result(self, row: int, is_alive: bool) -> None:
        """
        ProxyHealthCheckThread.row_checked 수신 시 호출 — 응답 없는 프록시는
        _toggle_proxy_enabled()로 비활성화해 실제 수집 대상에서 제외합니다.
        """
        t = self._proxy_table
        if row >= t.rowCount():
            return
        if not is_alive:
            t.blockSignals(True)
            try:
                self._toggle_proxy_enabled(row, False)
            finally:
                t.blockSignals(False)

    def _on_proxy_item_changed(self, item):
        """
        itemChanged 시그널 수신 — 사용자가 체크박스를 직접 클릭했을 때 호출됩니다.

        [재귀 방지]
        col 4(상태 체크박스)가 아닌 변경(NO 컬럼 등)은 즉시 return합니다.
        _toggle_proxy_enabled() 호출 전 blockSignals(True)로 감싸
        col 4 setCheckState 시 itemChanged 재발생을 차단합니다.

        [_seed / 대량 import 중 호출 방지]
        blockSignals(True)로 삽입 루프를 감싸면 이 슬롯이 호출되지 않습니다.
        방어 조건으로 row >= len(_proxy_rows)이면 return합니다.
        """
        if item.column() != 4:
            return   # 상태 컬럼(col 4) 이외 변경은 무시
        row = item.row()
        if row >= len(self._proxy_rows):
            return   # _proxy_rows 미등록 행 방어 (seed/import 중 누수 방지)
        enable = item.checkState() == Qt.CheckState.Checked
        # blockSignals: _toggle_proxy_enabled 내 setCheckState → itemChanged 재귀 차단
        self._proxy_table.blockSignals(True)
        try:
            self._toggle_proxy_enabled(row, enable)
        finally:
            self._proxy_table.blockSignals(False)

    def _log(self, level: str, message: str) -> None:
        lm = _get_log_manager(self)
        if lm is not None:
            lm.append_log(level, message)
