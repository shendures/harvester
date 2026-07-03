import time
import scrapy
import glean
import engine
from http import HTTPStatus


from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager  # 드라이버 자동 설치/관리

import utility
from items import DonasItem, DonasItemLoader

# Chrome WebDriver를 Scrapy의 응답 객체(Response object)로 사용할 수 있도록 준비합니다.

class HtmlSeleniumSpider(scrapy.Spider):

    name = "spider_html_selenium"

    # CONCURRENT_REQUESTS는 Scrapy 요청에만 적용됩니다.
    # Selenium은 자원 소모가 크므로 동시 요청 수를 낮추는 것이 일반적입니다.
    custom_settings = {
        'CONCURRENT_REQUESTS': 8, # Scrapy 요청의 동시성 (여기서는 Selenium 요청을 사용하므로, 낮게 유지)
        'DOWNLOAD_DELAY': 1,  # SeleniumRequest를 위한 다운로드 지연 시간 설정
        # 'ITEM_PIPELINES': {
        #     'pipelines.CsvExportPipeline': 300
        # }
    }

    # 1. __init__: main.py로부터 로드된 수집 목록 리스트를 받습니다.
    def __init__(self, request_info=None, *args, **kwargs):
        super(HtmlSeleniumSpider, self).__init__(*args, **kwargs)

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

            # RESPONSE STATUS 출력
            engine.get_response_status(response)

            if response.status != 200:
                self.logger.warning(f'HTTP Status {response.status} for URL: {response.url}')
                return

            # ChromeDriver 객체 생성
            driver = engine.set_chrome_webdriver()

            # 웹페이지 로드를 위한 대기 시간 설정 (최대 10초)
            wait = WebDriverWait(driver, 10)

            # 웹 페이지 실행
            time.sleep(3)
            driver.get(response.url)
            time.sleep(3)

            root = self.request_info["conditions"]["items"]["root"]
            _items = {key: value for key, value in self.request_info["conditions"]["items"].items() if key != 'root'}

            # 로그인 기능이 있는 사이트 시 로그인 실행
            if self.request_info["conditions"]["login"] is not None:
                login_info = self.request_info["conditions"]["login"]
                engine.run_login(driver, self.request_info["seq_no"], login_info)

            time.sleep(3)

            selectors = driver.find_elements(By.XPATH, root)
            result = engine.get_render_result(self.request_info["seq_no"], driver, selectors, _items)

            # 데이터 처리
            loader = engine.set_item_loader(response, self.request_info, result)

            yield loader.load_item()


            # # 맨 마지막에 연 윈도우창 종료
            # window_handles = driver.window_handles
            # new_window_handle = window_handles[-1]
            # driver.switch_to.window(new_window_handle)
            # driver.close()
            # original_window_handle = window_handles[0]
            # driver.switch_to.window(original_window_handle)

            driver.quit()

        except IndexError as e:
            self.logger.error('IndexError : %s at %s', e, response.url)
        except Exception as e:
            self.logger.error('Exception : %s at %s', e, response.url)