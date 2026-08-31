# trigger/auth.py
# AuthManagerPage의 자격증명·로그인·TLS 메서드(AuthManagerPageTriggers).

import json
from datetime import datetime

from PyQt6.QtWidgets import (
    QFileDialog, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
)
from PyQt6.QtCore import Qt

from style import Divider

from .common import parts, BG_SECONDARY, TEXT_PRIMARY, TEXT_SECONDARY, BORDER, GREEN, AMBER, _get_log_manager

class AuthManagerPageTriggers:
    """AuthManagerPage의 자격증명·로그인·TLS 메서드"""

    def _log_auth(self, level: str, message: str) -> None:
        """log_manager에 인증 관련 로그를 기록합니다."""
        lm = _get_log_manager(self)
        if lm is not None:
            lm.append_log(level, message)

    def _add_cred_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("자격증명 추가")
        dlg.setFixedWidth(560)
        dlg.setStyleSheet(f"background:{BG_SECONDARY}; border:1px solid {BORDER};")

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(22, 18, 22, 18)
        vl.setSpacing(10)
        vl.addWidget(parts.make_label("자격증명 추가", TEXT_PRIMARY, 13, True))
        vl.addWidget(Divider())

        name_row = QHBoxLayout()
        name_row.addWidget(parts.make_label("이름", TEXT_SECONDARY, 12))
        name_inp = QLineEdit()
        name_inp.setPlaceholderText("예: Naver API")
        name_row.addWidget(name_inp, 1)
        vl.addLayout(name_row)

        type_row = QHBoxLayout()
        type_row.addWidget(parts.make_label("타입", TEXT_SECONDARY, 12))
        type_cb = QComboBox()
        type_cb.addItems(["API Key", "Cookie", "OAuth2", "Basic Auth", "Bearer Token"])
        type_row.addWidget(type_cb, 1)
        vl.addLayout(type_row)

        key_row = QHBoxLayout()
        key_row.addWidget(parts.make_label("키/값", TEXT_SECONDARY, 12))
        key_inp = QLineEdit()
        key_inp.setPlaceholderText("인증 키 또는 토큰")
        key_inp.setEchoMode(QLineEdit.EchoMode.Password)
        key_row.addWidget(key_inp, 1)
        vl.addLayout(key_row)

        exp_row = QHBoxLayout()
        exp_row.addWidget(parts.make_label("만료일", TEXT_SECONDARY, 12))
        exp_inp = QLineEdit()
        exp_inp.setPlaceholderText("YYYY-MM-DD 또는 상시")
        exp_row.addWidget(exp_inp, 1)
        vl.addLayout(exp_row)

        btn_row = QHBoxLayout()
        cancel_btn = parts.outline_btn("취소")
        cancel_btn.clicked.connect(dlg.close)
        ok_btn = parts.action_btn("저장")

        def _do_add():
            masked = key_inp.text()[:4] + "****" if key_inp.text() else "****"
            data   = {
                "name":    name_inp.text().strip() or "새 자격증명",
                "type":    type_cb.currentText(),
                "key":     masked,
                "expires": exp_inp.text().strip() or "상시",
                "status":  "유효",
            }
            self._auth_rows.append(data)
            self._insert_table_row(data)
            self._log_auth("ok", f"자격증명 추가됨: {data['name']} ({data['type']})")
            dlg.close()

        ok_btn.clicked.connect(_do_add)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        vl.addLayout(btn_row)
        dlg.adjustSize()
        dlg.exec()

    def _delete_cred_row(self, row_idx):
        if 0 <= row_idx < self._cred_table.rowCount():
            name_item = self._cred_table.item(row_idx, 0)
            name_txt  = name_item.text() if name_item else "?"
            self._cred_table.removeRow(row_idx)
            self._log_auth("warn", f"자격증명 삭제됨: {name_txt}")

    def _export_creds(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "자격증명 내보내기", "credentials_encrypted.json", "JSON (*.json)")
        if not path:
            return
        export_data = {
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "note":        "실제 배포 시 AES-256 암호화 적용 필요",
            "credentials": [{"name": r["name"], "type": r["type"], "expires": r["expires"]}
                            for r in self._auth_rows],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        self._log_auth("ok", f"자격증명 내보내기 완료: {path}")
        QMessageBox.information(self, "완료", f"내보내기 완료:\n{path}")

    def _on_tls_toggle(self, state):
        if state == Qt.CheckState.Checked.value:
            self._cert_lbl.setText("● TLS 검증 활성화")
            self._cert_lbl.setStyleSheet(f"color:{GREEN}; font-size:12px;")
            self._log_auth("ok", "TLS 인증서 검증 활성화됨")
        else:
            self._cert_lbl.setText("● TLS 검증 비활성화")
            self._cert_lbl.setStyleSheet(f"color:{AMBER}; font-size:12px;")
            self._log_auth("warn", "TLS 인증서 검증 비활성화됨 — 보안 주의")
