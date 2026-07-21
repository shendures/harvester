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
from layout import MainWindow, theme
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

    win = MainWindow()

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
