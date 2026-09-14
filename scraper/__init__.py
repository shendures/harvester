"""Scrapy 수집 엔진 구성 패키지.

Scrapy가 문자열 경로로 동적 import하는 구성요소(설정·미들웨어·파이프라인·
아이템·스파이더)를 한곳에 모아 둔다 — 어떤 파일이 수집 프로그램의 구성요소인지
디렉터리로 드러내고, PyInstaller 번들링 대상도 이 폴더 하나로 지정할 수 있다.

여기서는 하위 모듈을 re-export하지 않는다. settings를 끌어오면 Scrapy의 설정
모듈 로딩과, engine ↔ spiders 사이에 이미 존재하는 순환 import 회피 장치가
얽히기 때문이다(scraper/spiders/base.py의 지연 import 주석 참고).
"""
