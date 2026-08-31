"""
DataCrawler v2.0  —  PyQt6
대시보드 / 스케줄러 / 모니터링 / 통계 분석 완성본
"""

import sys
import ctypes
import multiprocessing
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from layout import MainWindowSingle, theme
from conf import BlueprintStorage
import utility

# Windows 작업 표시줄 아이콘 해결을 위한 코드
myappid = 'my.scrapy.collector.v0_8'
if sys.platform == 'win32':
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

def main():

    app = QApplication(sys.argv)
    theme.set_pallete(app)
    # 창/작업 표시줄 아이콘 — 미지정 시 PyInstaller --icon(exe 파일 아이콘)과 무관하게
    # 실행 중에는 기본 아이콘으로 표시됨(트레이 아이콘은 TrayManager가 별도로 설정 중)
    app.setWindowIcon(QIcon(utility.resource_path() + "\\" + "combine-harvester.ico"))

    socket = QLocalSocket()
    socket.connectToServer(myappid)

    if socket.waitForConnected(500):
        print("이미 실행 중입니다. 기존 프로그램을 활성화합니다.")
        socket.disconnectFromServer()
        sys.exit(0)

    local_server = QLocalServer()  # 클라이언트
    QLocalServer.removeServer(myappid)  # 이전 소켓 잔재 청소
    if not local_server.listen(myappid):  # 지정한 이름으로 서버 시작
        sys.exit(1)

    # 레이아웃 선택: request_info.json의 블루프린트 개수로 자동 판단
    # (1개 = 단일 수집, 2개 이상 = 다중 수집 순차 배치). --multi/--single
    # 플래그로 수동 오버라이드 가능(크로스체크·디버깅용 — 개수와 무관하게 특정
    # 레이아웃을 강제 지정)하되, 그 플래그가 실제 블루프린트 개수와 모순되면
    # (예: 1개인데 --multi, 2개 이상인데 --single) 잘못된 레이아웃으로 조용히
    # 기동되지 않도록 여기서 즉시 중단한다.
    forced_multi = "--multi" in sys.argv
    forced_single = "--single" in sys.argv
    # 개수만 필요하므로 list_blueprints()(전체 deepcopy)가 아니라
    # list_seq_nos()(deepcopy 없음)로 가볍게 조회한다.
    blueprint_count = len(BlueprintStorage().list_seq_nos())

    # 플래그와 실제 개수가 모순되면(예: 1개인데 --multi, 2개 이상인데 --single)
    # 잘못된 레이아웃으로 조용히 기동되지 않도록 즉시 중단한다.
    mismatch = None
    if forced_multi and blueprint_count < 2:
        mismatch = (
            "--multi", blueprint_count,
            "다중 수집 레이아웃은 블루프린트가 2개 이상일 때만 사용할 수 있습니다.",
            "단일", "--single",
        )
    elif forced_single and blueprint_count >= 2:
        mismatch = (
            "--single", blueprint_count,
            f"단일 수집 레이아웃은 1개만 다룰 수 있어 나머지 {blueprint_count - 1}개가 무시됩니다.",
            "다중", "--multi",
        )

    if mismatch:
        bad_flag, count, reason, correct_layout, correct_flag = mismatch
        # --multi/--single은 터미널에서만 쓰는 플래그이므로 알림창 없이
        # 콘솔 로그만 남기고 중단한다.
        print(
            f"[Harvest] 실행 중단\n"
            f"[원인] {bad_flag} 플래그를 지정했지만 request_info.json의 블루프린트가 "
            f"{count}개입니다 — {reason}\n"
            f"  [올바른 실행] python main.py            "
            f"(플래그 없이 실행 — 개수에 맞춰 자동으로 {correct_layout} 수집 레이아웃 선택)\n"
            f"               또는 python main.py {correct_flag}",
            file=sys.stderr,
        )
        sys.exit(1)

    use_multi = forced_multi or (not forced_single and blueprint_count >= 2)

    if use_multi:
        from layout.multi import MainWindowMulti
        win = MainWindowMulti()
    else:
        win = MainWindowSingle()

    local_server.newConnection.connect(win.tray_manager.restore_window)

    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    # PyInstaller onefile exe + multiprocessing.Process(worker.run_spider) 조합에서
    # 필수: 없으면 자식 프로세스가 __main__을 처음부터 다시 실행해 GUI를 한 번 더
    # 띄우려다 QLocalServer 단일 실행 감지에 걸려 조용히 종료됨 — run_spider()가
    # 아예 호출되지 않아 수집 결과가 에러 없이 0건으로 남는다.
    multiprocessing.freeze_support()
    main()
