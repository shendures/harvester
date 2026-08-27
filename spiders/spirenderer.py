import time
import glean
import engine
import conf

from selenium.webdriver.common.by import By
from scrapy.selector import Selector
from spiders.base import BaseExtractorSpider

# Chrome WebDriver로 렌더링한 페이지를 두 경로로 처리합니다:
# render/{seq_no}.py에 render()가 있으면 Selenium 엘리먼트(By.XPATH)를
# 그대로 넘기고, 없으면 driver.page_source를 Selector로 감싸 범용 XPath 추출로 폴백합니다.

PAGE_LOAD_WAIT_SECONDS = 3  # 렌더링 대기 시간 (페이지 로드/로그인/DOM 렌더링 완료 대기)


class HtmlSeleniumSpider(BaseExtractorSpider):

    name = "spider_html_selenium"

    # Threads/Delay 안전 상한·하한은 대시보드(layout_single.py)와 스케줄 다이얼로그
    # (trigger/scheduler.py)의 스핀박스 범위(setMaximum/setMinimum)에서만 강제한다. 스케줄로
    # 저장된 작업은 저장 당시 값을 그대로 재실행하므로(대상 블루프린트가 나중에
    # html_render로 바뀌어도 갱신되지 않음) 이 스파이더 자체는 값을 재검증하지
    # 않는다 — 알려진 트레이드오프이며 의도적으로 UI 강제만 채택한 것이다.

    def __init__(self, request_info=None, *args, **kwargs):
        super().__init__(request_info, *args, **kwargs)

        # 이 스파이더 실행(수집 세션) 전체에서 재사용하는 단일 브라우저 세션.
        # start_requests()에서 생성하고, closed()에서 한 번만 종료합니다 —
        # 로그인 성공 시 같은 세션이 쿠키를 그대로 유지하므로 요청마다 새
        # driver를 만들거나 쿠키를 재주입할 필요가 없습니다.
        self.driver = None

    # 2. start_requests: 모든 수집 목록의 URL을 예약합니다.
    def start_requests(self):
        try:
            conditions = self.request_info["conditions"]
            seq_no = self.request_info["seq_no"]

            self.driver = engine.set_chrome_webdriver()

            # 로그인 인증이 필요하면, engine.get_scrapy_request()로 타겟 URL 요청을
            # 만들기 전에 반드시 먼저 로그인을 완료합니다. (로그인 전에 인증이
            # 필요한 URL을 요청하면 서버가 로그인 페이지로 리다이렉트시켜 실제
            # 타겟 URL을 잃어버리는 문제를 방지하기 위함)
            if not self._try_login(conditions, seq_no):
                return

            url_list = glean.get_grains(self.request_info)
            for url in url_list:
                yield engine.get_scrapy_request(url, conditions, callback=self.parse)
                self.logger.info(f'➡️ 요청 예약 완료: URL {url}')

        except Exception as e:
            self.logger.error('Exception during start_requests: %s', e)

    def _try_login(self, conditions, seq_no) -> bool:
        """로그인이 필요 없는 사이트는 즉시 True. 필요한 사이트는 login/{seq_no}.py로
        로그인을 시도하고 성공 여부를 반환합니다(수집 흐름을 계속할지 결정하는 게이트)."""
        if not engine.requires_login(conditions):
            return True

        login_info = conditions["login"]
        if not engine.perform_login(self.driver, login_info, seq_no):
            self.logger.error(f'❌ 로그인 인증 실패로 수집을 시작하지 않습니다 (seq_no={seq_no})')
            return False

        self.logger.info(f'✅ 로그인 인증 완료 (seq_no={seq_no}) — 타겟 URL 수집을 시작합니다.')
        return True

    def parse(self, response):
        try:

            # RESPONSE STATUS 출력
            engine.get_response_status(response)

            if response.status != 200:
                self.logger.warning(f'HTTP Status {response.status} for URL: {response.url}')
                return

            # 인증이 필요한 URL은 리다이렉트를 거쳐 response.url이 로그인 페이지 등으로
            # 바뀌어 있을 수 있으므로, 리다이렉트 전 원래 요청했던 URL로 이동합니다.
            target_url = response.meta.get("redirect_urls", [response.url])[0]

            # 웹 페이지 실행 — 세션 전체에서 재사용하는 self.driver (로그인 상태 유지됨)
            time.sleep(PAGE_LOAD_WAIT_SECONDS)
            self.driver.get(target_url)
            time.sleep(PAGE_LOAD_WAIT_SECONDS)

            conditions = self.request_info["conditions"]
            seq_no = self.request_info["seq_no"]
            root = conditions["items"]["root"]
            _items = {key: value for key, value in conditions["items"].items() if key != 'root'}

            # 렌더링 결과 추출
            # JS 렌더링 수집은 HTML 기반 수집이므로, 클릭 등 커스텀 인터랙션이 필요한
            # 경우에만 render/{seq_no}.py의 render()를 사용하고, 없으면
            # 범용 root/items 추출(html 스파이더와 동일한 로직)로 폴백합니다.
            render_fn = conf.CustomModuleStorage().load_render(seq_no) if conditions.get("rendering") else None
            if render_fn is not None:
                self.logger.info(f'ℹ️ render/{seq_no}.py의 render()로 커스텀 인터랙션 수집을 진행합니다.')
                selectors = self.driver.find_elements(By.XPATH, root)
                result = render_fn(self.driver, selectors, _items)
            else:
                root_selectors = Selector(text=self.driver.page_source).xpath(root)
                result = engine.get_result(self.request_info, root_selectors, _items)

            # 데이터 처리
            loader = engine.set_item_loader(response, self.request_info, result)

            yield loader.load_item()

        except IndexError as e:
            self.logger.error('IndexError : %s at %s', e, response.url)
        except Exception as e:
            self.logger.error('Exception : %s at %s', e, response.url)

    def closed(self, reason):
        """스파이더 종료 시 Scrapy가 자동 호출 — 로그인 상태 정리 후, 세션 전체에서 재사용한 driver를 한 번만 종료합니다."""
        if self.driver is not None:
            conditions = self.request_info.get("conditions") or {}
            if engine.requires_login(conditions):
                engine.perform_logout(self.request_info.get("seq_no", ""))
            self.driver.quit()
            self.driver = None