# layout/__init__.py
# 단일/다중 수집 레이아웃 패키지의 외부 진입점.
# main.py가 필요로 하는 3개 심볼만 재export하는 얇은 facade입니다.
# 패키지 내부(single/<->multi/, scheduler.py 등 공용 페이지 파일)의 실제
# 의존은 이미 상대 import로 직접 연결되어 있어 이 파일을 거치지 않습니다.

from .common import theme
from .single import MainWindowSingle
from .multi import MainWindowMulti

__all__ = ["MainWindowSingle", "theme", "MainWindowMulti"]
