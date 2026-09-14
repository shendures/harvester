import scrapy


class BaseExtractorSpider(scrapy.Spider):
    """request_info 검증(__init__)과 기본 URL 예약 루프(start_requests)를 공통 제공하는 베이스.

    parse()로 콜백하는 스파이더(spihtml/spijson/spixml)는 이 클래스를 그대로 상속해
    __init__/start_requests를 재사용한다. 콜백 대상이 다르거나(spidetail) 로그인
    게이트/브라우저 세션이 필요한(spirenderer) 스파이더는 start_requests를 오버라이드한다.
    name 속성이 없어 Scrapy SpiderLoader가 실행 대상 스파이더로 인식하지 않는다.
    """

    def __init__(self, request_info=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # main.py에서 전달받은 수집 목록 리스트 (딕셔너리 리스트 형태)
        if request_info is None:
            self.request_info = {}
            self.logger.error("❌ 수집 목록 리스트가 main.py로부터 전달되지 않았습니다.")
        else:
            self.request_info = request_info

    def start_requests(self):
        """모든 수집 목록의 URL을 예약한다."""
        # engine/glean은 여기서 지연 import — engine.py가 모듈 최상단에서
        # 각 스파이더 클래스를 import하므로, 이 모듈이 base가 최상단에서
        # engine을 import하면 로드 순서에 따라 순환 임포트가 발생할 수 있다.
        import engine
        import glean
        try:
            url_list = glean.get_grains(self.request_info)
            for url in url_list:
                yield engine.get_scrapy_request(url, self.request_info["conditions"], callback=self.parse)
                self.logger.info(f'➡️ 요청 예약 완료: URL {url}')

        except Exception as e:
            self.logger.error('Exception during start_requests: %s', e)
