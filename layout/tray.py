# layout/tray.py
# 시스템 트레이 아이콘/메뉴 관리 — Single/Multi가 동일 클래스를 그대로 공유한다(대응 클래스 없음).

import utility

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction

from trigger import TrayManagerTriggers


class TrayManager(QObject, TrayManagerTriggers):
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
        # 반드시 MainWindowSingle.exit_app()을 통해 저장 후 종료해야 합니다.
        quit_action.triggered.connect(self.main_window.exit_app)

        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()


    def show_message(self, title, message, icon=QSystemTrayIcon.MessageIcon.Information):
        """트레이 알림 메시지 표시"""
        self.tray_icon.showMessage(title, message, icon, 3000)
