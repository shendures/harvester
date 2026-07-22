import time
import scrapy
import glean
import engine
import conf

from selenium.webdriver.common.by import By
from scrapy.selector import Selector

# Chrome WebDriver로 렌더링한 페이지를 두 경로로 처리합니다:
# custom_rules/render/{seq_no}.py에 render()가 있으면 Selenium 엘리먼트(By.XPATH)를
# 그대로 넘기고, 없으면 driver.page_source를 Selector로 감싸 범용 XPath 추출로 폴백합니다.

PAGE_LOAD_WAIT_SECONDS = 3  # 렌더링 대기 시간 (페이지 로드/로그인/DOM 렌더링 완료 대기)

# 로그인 실패 시 사이트에서 흔히 쓰는 문구(사이트 무관 공통 판별용, 소문자 비교)
LOGIN_FAILURE_PHRASES = [
    "비밀번호가 일치하지", "아이디 또는 비밀번호가 올바르지",
    "아이디/비밀번호를 확인", "로그인에 실패", "계정 정보가 일치하지",
    "invalid password", "incorrect username or password", "login failed",
    "invalid credentials",
]


class HtmlSeleniumSpider(scrapy.Spider):

    name = "spider_html_selenium"

    # CONCURRENT_REQUESTS는 Scrapy 요청에만 적용됩니다.
    # Selenium은 자원 소모가 크므로 동시 요청 수를 낮추는 것이 일반적입니다.
    custom_settings = {
        'CONCURRENT_REQUESTS': 8, # Scrapy 요청의 동시성 (여기서는 Selenium 요청을 사용하므로, 낮게 유지)
        'DOWNLOAD_DELAY': 1,  # 렌더링 전 상태 확인용 요청의 다운로드 지연 시간 설정
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

    def _login_succeeded(self, driver, login_info, pre_login_url, pre_login_cookie_names) -> bool:
        """
        로그인 시도 후 성공 여부를 판단합니다.
        1) conditions.login.successKeywords(수동 지정)가 있으면 그 키워드 존재 여부로만 판단
        2) 없으면 공통 실패 문구 → 쿠키/비밀번호 입력창/URL 변화 순으로 자동 판별
        """
        page_source = driver.page_source

        manual_keywords = login_info.get("successKeywords")
        if manual_keywords:
            return any(kw in page_source for kw in manual_keywords)

        page_source_lower = page_source.lower()
        if any(phrase.lower() in page_source_lower for phrase in LOGIN_FAILURE_PHRASES):
            return False

        new_cookie_appeared = bool(
            {c["name"] for c in driver.get_cookies()} - pre_login_cookie_names
        )
        password_field_gone = len(driver.find_elements(By.CSS_SELECTOR, "input[type='password']")) == 0
        url_changed = driver.current_url != pre_login_url

        return new_cookie_appeared or password_field_gone or url_changed

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

            try:
                # 웹 페이지 실행
                time.sleep(PAGE_LOAD_WAIT_SECONDS)
                driver.get(response.url)
                time.sleep(PAGE_LOAD_WAIT_SECONDS)

                conditions = self.request_info["conditions"]
                seq_no = self.request_info["seq_no"]
                root = conditions["items"]["root"]
                _items = {key: value for key, value in conditions["items"].items() if key != 'root'}

                # 로그인 기능이 있는 사이트 시 로그인 실행 (custom_rules/render/{seq_no}.py의 login())
                login_info = conditions["login"]
                if login_info is not None:
                    login_fn = conf.CustomModuleStorage().load_login(seq_no)
                    if login_fn is None:
                        self.logger.error(f'❌ 로그인 설정(conditions.login)은 있으나 custom_rules/render/{seq_no}.py에 login()이 정의되어 있지 않습니다.')
                        return
                    pre_login_url = driver.current_url
                    pre_login_cookie_names = {c["name"] for c in driver.get_cookies()}
                    login_fn(driver, login_info)

                time.sleep(PAGE_LOAD_WAIT_SECONDS)

                if login_info is not None and not self._login_succeeded(
                        driver, login_info, pre_login_url, pre_login_cookie_names):
                    self.logger.error(f'❌ 로그인 실패로 판단되어 수집을 중단합니다 (seq_no={seq_no}, url={response.url})')
                    return

                # 렌더링 결과 추출
                # JS 렌더링 수집은 HTML 기반 수집이므로, 클릭 등 커스텀 인터랙션이 필요한
                # 경우에만 custom_rules/render/{seq_no}.py의 render()를 사용하고, 없으면
                # 범용 root/items 추출(html 스파이더와 동일한 로직)로 폴백합니다.
                render_fn = conf.CustomModuleStorage().load_render(seq_no) if conditions.get("rendering") else None
                if render_fn is not None:
                    self.logger.info(f'ℹ️ custom_rules/render/{seq_no}.py의 render()로 커스텀 인터랙션 수집을 진행합니다.')
                    selectors = driver.find_elements(By.XPATH, root)
                    result = render_fn(driver, selectors, _items)
                else:
                    root_selectors = Selector(text=driver.page_source).xpath(root)
                    result = engine.get_result(self.request_info, root_selectors, _items)

                # 데이터 처리
                loader = engine.set_item_loader(response, self.request_info, result)

                yield loader.load_item()
            finally:
                driver.quit()

        except IndexError as e:
            self.logger.error('IndexError : %s at %s', e, response.url)
        except Exception as e:
            self.logger.error('Exception : %s at %s', e, response.url)