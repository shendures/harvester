import json
import scrapy
import engine
import glean
import utility

class JsonExtractorSpider(scrapy.Spider):

    name = "spider_json"

    # CONCURRENT_REQUESTS를 settings.py 대신 여기서 커스터마이징할 수 있습니다.
    # custom_settings = {
    #     'CONCURRENT_REQUESTS': 32,
    #     # 'ITEM_PIPELINES': {
    #     #     'pipelines.CsvExportPipeline': 300
    #     # }
    # }

    # 1. __init__: main.py로부터 로드된 수집 목록 리스트를 받습니다.
    def __init__(self, request_info=None, *args, **kwargs):
        super(JsonExtractorSpider, self).__init__(*args, **kwargs)

        # main.py에서 전달받은 수집 목록 리스트 (딕셔너리 리스트 형태)
        if request_info is None:
            self.request_info = {}
            self.logger.error("❌ 수집 목록 리스트가 main.py로부터 전달되지 않았습니다.")
        else:
            self.request_info = request_info
            # self.collect_info["conditions"] = json.loads(self.collect_info["conditions"])

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

            # RESPONSE STATUS 출력
            engine.get_response_status(response)

            if response.status != 200:
                self.logger.warning(f'HTTP Status {response.status} for URL: {response.url}')
                return

            root = self.request_info["conditions"]["items"]["root"]
            _items = {key: value for key, value in self.request_info["conditions"]["items"].items() if key != 'root'}
            result = engine.get_result(self.request_info, utility.get_target(json.loads(response.text), root), _items)

            # 데이터 처리
            loader = engine.set_item_loader(response, self.request_info, result)

            yield loader.load_item()

        except IndexError as e:
            self.logger.error('IndexError : %s at %s', e, response.url)
        except Exception as e:
            self.logger.error('Exception : %s at %s', e, response.url)


