import json
import scrapy
import glean
import engine
import utility

class DetailExtractorSpider(scrapy.Spider):

    name = "spider_detail"

    # 1. __init__: main.py로부터 로드된 수집 목록 리스트를 받습니다.
    def __init__(self, request_info=None, *args, **kwargs):
        super(DetailExtractorSpider, self).__init__(*args, **kwargs)

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
                yield engine.get_scrapy_request(url, self.request_info["conditions"], callback=self.start_requests_detail)

                self.logger.info(f'➡️ 요청 예약 완료: URL {url}')

        except Exception as e:
            self.logger.error('Exception during start_requests: %s', e)

    def start_requests_detail(self, response):
        try:
            if response.status != 200:
                self.logger.warning(f'HTTP Status {response.status} for URL: {response.url}')
                return

            # 상세 페이지 요청할 정보가 있는 메인 페이지
            mainUrl = self.request_info["conditions"]["mainUrl"]

            # 상세 페이지 요청할 정보가 있는 메인 페이지가 "HTML"
            if self.request_info["conditions"]["mainFormat"] == "html":
                detail = self.request_info["conditions"]["items"]["detail"]
                detail_selectors = response.xpath(detail)
                for detail_selector in detail_selectors:
                    detail_param = detail_selector.get().strip()
                    detail_url = mainUrl.format(detail_kwd=str(detail_param))
                    yield engine.get_scrapy_request(detail_url, self.request_info["conditions"], callback=self.parse)

            # 상세 페이지 요청할 정보가 있는 메인 페이지가 "JSON"
            elif self.request_info["conditions"]["mainFormat"] == "json":

                root = self.request_info["conditions"]["items"]["detail_root"]
                detail_selectors = utility.get_target(json.loads(response.text), root)

                for detail_selector in detail_selectors:
                    detail_param = utility.get_target(detail_selector, self.request_info["conditions"]["items"]["detail"])
                    detail_url = mainUrl.format(detail_kwd=str(detail_param))
                    yield engine.get_scrapy_request(detail_url, self.request_info["conditions"], callback=self.parse)


        except IndexError as e:
            self.logger.error('IndexError : %s at %s', e, response.url)
        except Exception as e:
            self.logger.error('Exception : %s at %s', e, response.url)


    def parse(self, response):
        try:

            # RESPONSE STATUS 출력
            engine.get_response_status(response)

            if response.status != 200:
                self.logger.warning(f'HTTP Status {response.status} for URL: {response.url}')
                return

            _items = {key: value for key, value in self.request_info["conditions"]["items"].items() if key != 'detail_root' and key != 'detail' and key != 'main_root' and key != 'root'}

            # 데이터 생성
            if self.request_info["conditions"]["mainFormat"] == "html":
                selectors = response.xpath(".")
                result = engine.get_result(self.request_info, selectors, _items)
            elif self.request_info["conditions"]["mainFormat"] == "json":
                selectors = utility.get_target(json.loads(response.text), self.request_info["conditions"]["items"]["main_root"])
                result = engine.get_result(self.request_info, selectors, _items)

            # 데이터 처리
            loader = engine.set_item_loader(response, self.request_info, result)

            yield loader.load_item()


        except IndexError as e:
            self.logger.error('IndexError : %s at %s', e, response.url)
        except Exception as e:
            self.logger.error('Exception : %s at %s', e, response.url)



