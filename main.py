"""DataCrawler 실행 진입점 (PyInstaller 진입 스크립트 겸용). 본문은 harvest/app.py."""

import multiprocessing

from harvest.app import main

if __name__ == "__main__":
    # PyInstaller onefile + multiprocessing.Process(worker.run_spider) 조합 필수:
    # 없으면 자식 프로세스가 GUI를 다시 띄우려다 단일 실행 감지에 걸려 조용히 종료되어
    # 수집 결과가 에러 없이 0건으로 남는다.
    multiprocessing.freeze_support()
    main()
