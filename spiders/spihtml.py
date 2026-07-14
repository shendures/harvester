import scrapy
import glean
import engine

class HtmlExtractorSpider(scrapy.Spider):

    name = "spider_html"

    # 1. __init__: main.py로부터 로드된 수집 목록 리스트를 받습니다.
    def __init__(self, request_info=None, *args, **kwargs):
        super(HtmlExtractorSpider, self).__init__(*args, **kwargs)

        # main.py에서 전달받은 수집 목록 리스트 (딕셔너리 리스트 형태)
        if request_info is None:
            self.request_info = {}
            self.logger.error("❌ 수집 목록 리스트가 main.py로부터 전달되지 않았습니다.")
        else:
            self.request_info = request_info

    # 2. start_requests: 모든 수집 목록의 URL을 예약합니다.
    def start_requests(self):
        try:
            url_list = glean.get_grains(self.request_info)
            for url in url_list:
                yield engine.get_scrapy_request(url, self.request_info["conditions"], callback=self.parse)
                self.logger.info(f'➡️ 요청 예약 완료: URL {url}')

        except Exception as e:
            self.logger.error('Exception during start_requests: %s', e)

    def parse(self, response):
        try:
            if response.status != 200:
                self.logger.warning(f'HTTP Status {response.status} for URL: {response.url}')
                return

            root = self.request_info["conditions"]["items"]["root"]
            _items = {key: value for key, value in self.request_info["conditions"]["items"].items() if key != 'root'}

            # 데이터 생성
            selectors = response.xpath(root)
            result = engine.get_result(self.request_info, selectors, _items)

            # 데이터 처리
            loader = engine.set_item_loader(response, self.request_info, result)

            yield loader.load_item()

        except IndexError as e:
            self.logger.error('IndexError : %s at %s', e, response.url)
        except Exception as e:
            self.logger.error('Exception : %s at %s', e, response.url)


