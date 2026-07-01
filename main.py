"""
DataCrawler v2.0  —  PyQt6
대시보드 / 스케줄러 / 모니터링 / 통계 분석 완성본
"""

import sys, ctypes
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication
from layout import MainWindow, theme

# Windows 작업 표시줄 아이콘 해결을 위한 코드
myappid = 'my.scrapy.collector.v0_8'
if sys.platform == 'win32':
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

def main():

    app = QApplication(sys.argv)
    theme.set_pallete(app)

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
    main()