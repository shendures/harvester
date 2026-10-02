"""
DataCrawler v2.0  —  PyQt6
대시보드 / 스케줄러 / 모니터링 / 통계 분석 완성본
"""

import ctypes
import multiprocessing
import os
import sys
from typing import NoReturn

from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QStyleFactory

import conf
import utility
from layout import MainWindowSingle, theme
from style import SpinArrowProxyStyle

APP_ID = 'my.scrapy.collector.v0_8'
ICON_FILENAME = "combine-harvester.ico"
SINGLE_INSTANCE_TIMEOUT_MS = 500
MULTI_BLUEPRINT_MIN_COUNT = 2

FLAG_MULTI = "--multi"
FLAG_SINGLE = "--single"


def set_windows_app_id() -> None:
    # 작업 표시줄 아이콘이 python.exe로 묶이지 않도록 고유 AppUserModelID 등록
    if sys.platform == 'win32':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def apply_theme(app: QApplication) -> None:
    # Windows 네이티브 스타일은 초소형 QPushButton 등에서 QSS background-color를
    # 온전히 반영하지 않아, 플랫폼 무관하게 QSS를 그대로 그리는 Fusion으로 고정한다
    # (스타일시트 적용보다 먼저 호출). SpinArrowProxyStyle은 스핀박스 화살표만 직접 그린다.
    app.setStyle(SpinArrowProxyStyle(QStyleFactory.create("Fusion"), theme))
    theme.set_pallete(app)
    # 미지정 시 PyInstaller --icon과 무관하게 실행 중 창/작업 표시줄이 기본 아이콘으로 표시됨
    app.setWindowIcon(QIcon(os.path.join(utility.resource_path(), ICON_FILENAME)))


def is_already_running() -> bool:
    socket = QLocalSocket()
    socket.connectToServer(APP_ID)
    if not socket.waitForConnected(SINGLE_INSTANCE_TIMEOUT_MS):
        return False
    socket.disconnectFromServer()
    return True


def start_instance_server() -> QLocalServer:
    server = QLocalServer()
    QLocalServer.removeServer(APP_ID)  # 이전 소켓 잔재 청소
    if not server.listen(APP_ID):
        sys.exit(1)
    return server


def exit_on_flag_mismatch(flag: str, blueprint_count: int, reason: str,
                          auto_layout: str, correct_flag: str) -> NoReturn:
    # 터미널 전용 플래그이므로 알림창 없이 콘솔 로그만 남기고 중단한다.
    print(
        f"[Harvest] 실행 중단\n"
        f"[원인] {flag} 플래그를 지정했지만 request_info.json의 블루프린트가 "
        f"{blueprint_count}개입니다 — {reason}\n"
        f"  [올바른 실행] python main.py            "
        f"(플래그 없이 실행 — 개수에 맞춰 자동으로 {auto_layout} 수집 레이아웃 선택)\n"
        f"               또는 python main.py {correct_flag}",
        file=sys.stderr,
    )
    sys.exit(1)


def should_use_multi_layout(blueprint_count: int) -> bool:
    """블루프린트 개수로 레이아웃을 정하되 --multi/--single 강제 지정을 우선한다.

    플래그가 실제 개수와 모순되면 잘못된 레이아웃으로 조용히 기동되지 않도록 즉시 중단한다.
    """
    forced_multi = FLAG_MULTI in sys.argv
    forced_single = FLAG_SINGLE in sys.argv

    if forced_multi and blueprint_count < MULTI_BLUEPRINT_MIN_COUNT:
        exit_on_flag_mismatch(
            FLAG_MULTI, blueprint_count,
            "다중 수집 레이아웃은 블루프린트가 2개 이상일 때만 사용할 수 있습니다.",
            "단일", FLAG_SINGLE,
        )
    if forced_single and blueprint_count >= MULTI_BLUEPRINT_MIN_COUNT:
        exit_on_flag_mismatch(
            FLAG_SINGLE, blueprint_count,
            f"단일 수집 레이아웃은 1개만 다룰 수 있어 나머지 {blueprint_count - 1}개가 무시됩니다.",
            "다중", FLAG_MULTI,
        )
    return forced_multi or (
        not forced_single and blueprint_count >= MULTI_BLUEPRINT_MIN_COUNT
    )


def create_main_window():
    # 개수만 필요하므로 전체 deepcopy를 하는 list_blueprints() 대신 list_seq_nos()를 쓴다.
    blueprint_count = len(conf.BlueprintStorage().list_seq_nos())
    if should_use_multi_layout(blueprint_count):
        from layout.multi import MainWindowMulti
        return MainWindowMulti()
    return MainWindowSingle()


def main():
    set_windows_app_id()
    app = QApplication(sys.argv)
    apply_theme(app)

    if is_already_running():
        print("이미 실행 중입니다. 기존 프로그램을 활성화합니다.")
        sys.exit(0)
    instance_server = start_instance_server()

    win = create_main_window()

    # 창 생성 이전에 conf.py에서 쌓인 경고/오류를 로그 뷰어로 한꺼번에 전달한다.
    conf.set_error_reporter(win.log_manager.append_log)
    instance_server.newConnection.connect(win.tray_manager.restore_window)

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    # PyInstaller onefile + multiprocessing.Process(worker.run_spider) 조합 필수:
    # 없으면 자식 프로세스가 GUI를 다시 띄우려다 단일 실행 감지에 걸려 조용히 종료되어
    # 수집 결과가 에러 없이 0건으로 남는다.
    multiprocessing.freeze_support()
    main()
