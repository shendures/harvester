import re
import json
import logging
import scrapy
from scrapy.http import JsonRequest
from furl import furl
from typing import List, Dict, Any
import utility
import conf
from http import HTTPStatus
import glean

from items import DonasItem, DonasItemLoader
from scrapy.selector import Selector

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager  # 드라이버 자동 설치/관리

# spiders
from spiders.spihtml import HtmlExtractorSpider
from spiders.spirenderer import HtmlSeleniumSpider
from spiders.spijson import JsonExtractorSpider
from spiders.spixml import XmlExtractorSpider
from spiders.spidetail import DetailExtractorSpider

logger = logging.getLogger(__name__)

def get_login_failure_phrases():
    """로그인 실패 시 사이트에서 흔히 쓰는 문구(사이트 무관 공통 판별용, 소문자 비교)"""
    return [
        "비밀번호가 일치하지", "아이디 또는 비밀번호가 올바르지",
        "아이디/비밀번호를 확인", "로그인에 실패", "계정 정보가 일치하지",
        "invalid password", "incorrect username or password", "login failed",
        "invalid credentials",
    ]

def get_json_form(url, payload_yn):

    if "?" not in url:
        raise ValueError(f"POST 요청 URL은 '<url>?<JSON 쿼리>' 형식이어야 합니다: {url!r}")

    processed_url = re.search(r".*(?=\?)", url)[0]
    body = json.loads(re.search(r"(?<=\?).*", url)[0])

    return processed_url, body


def get_spider(request_info: dict):

    # conditions 내부 spiders 우선, 없으면 최상위 fallback (현행 request_info.json 호환)
    spiders = (request_info.get("conditions") or {}).get("spiders", request_info.get("spiders"))

    if spiders == "html":
        return HtmlExtractorSpider

    elif spiders == "html_render":
        return HtmlSeleniumSpider

    elif spiders == "json":
        return JsonExtractorSpider

    elif spiders == "xml":
        return XmlExtractorSpider

    elif spiders == "detail":
        return DetailExtractorSpider

    elif spiders in ("html_render_detail", "json_detail", "json_payload_detail"):
        raise NotImplementedError(f"'{spiders}' 스파이더는 아직 구현되지 않았습니다.")

    else:
        raise ValueError(f"알 수 없는 spiders 값입니다: {spiders!r}")


def set_requests(collect_info, callback):
    url_list = glean.get_grains(collect_info)
    for url in url_list:
        yield get_scrapy_request(url, collect_info["conditions"], callback)


def get_scrapy_request(url, conditions, callback):
    """
    조건 딕셔너리에 따라 Scrapy Request 또는 FormRequest 객체를 생성합니다.
    """

    # 1. 공통 파라미터 딕셔너리 준비
    request_kwargs = {
        'url': url,
        'callback': callback,
        'method': conditions['method'],
        'headers': conditions.get("headers"),  # headers가 None이어도 Request 객체는 이를 처리함
        'meta': conditions
    }

    if conditions['method'] == "GET":

        # 일반 요청 (렌더링 페이지도 spirenderer가 자체 Chrome 드라이버로 처리하므로 동일)
        return scrapy.Request(**request_kwargs)

    # 2. POST 요청에 대한 추가 처리
    elif conditions['method'] == "POST":

        processed_url, body = get_json_form(url, conditions.get("payload"))

        # URL이 변경되었을 경우 업데이트
        request_kwargs['url'] = processed_url

        # 3. 데이터 전송 방식에 따른 분기 (FormRequest vs. Request with Body)
        if conditions.get("payload") is False:
            request_kwargs['formdata'] = body
            # Form Data 전송 (application/x-www-form-urlencoded)
            return scrapy.FormRequest(**request_kwargs)

        elif conditions.get("payload") is True:  # conditions["payload"] == True (JSON Body 또는 Raw Body)
            request_kwargs['data'] = body
            return JsonRequest(**request_kwargs)

        else:
            raise ValueError(f"지원하지 않는 payload 값입니다: {conditions.get('payload')!r} (True/False만 지원)")

    else:
        raise ValueError(f"지원하지 않는 method 값입니다: {conditions['method']!r} (GET/POST만 지원)")


def set_chrome_webdriver(headless=False):
    options = webdriver.ChromeOptions()

    # 브라우저창 없이 실행 시
    if headless:
        options.add_argument('headless')
    options.add_argument('window-size=1920x1080')
    options.add_argument("disable-gpu")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    return driver


def check_login_success(driver, login_info, pre_login_url, pre_login_cookie_names) -> bool:
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
    if any(phrase.lower() in page_source_lower for phrase in get_login_failure_phrases()):
        return False

    new_cookie_appeared = bool(
        {c["name"] for c in driver.get_cookies()} - pre_login_cookie_names
    )
    password_field_gone = len(driver.find_elements(By.CSS_SELECTOR, "input[type='password']")) == 0
    url_changed = driver.current_url != pre_login_url

    return new_cookie_appeared or password_field_gone or url_changed


def requires_login(conditions: dict) -> bool:
    """이 수집 조건이 로그인 인증을 필요로 하는지 판단합니다 (conditions.login 존재 여부)."""
    return (conditions or {}).get("login") is not None


def perform_login(driver, login_info: dict, seq_no: str, cached_cookies: list = None):
    """
    로그인 인증을 수행하고, 이후 재사용할 쿠키 목록을 반환합니다.

    - cached_cookies가 주어지면(이전에 이미 이 수집 세션에서 로그인에 성공한 경우):
      custom_rules/render/{seq_no}.py의 login()을 다시 실행하지 않고, 그 쿠키를
      현재 페이지에 주입해 재사용합니다 (같은 수집 실행 안에서 매 요청마다
      아이디/비밀번호를 반복 제출하지 않기 위함). 이 경로는 driver가 호출 전에
      이미 쿠키의 대상 도메인 페이지로 이동해 있어야 합니다 — Selenium의
      add_cookie()는 쿠키의 도메인과 현재 페이지 도메인이 일치해야 동작합니다.
    - cached_cookies가 없으면 custom_rules/render/{seq_no}.py의 login()으로
      새로 로그인합니다. 이 경로는 login() 자신이 로그인 페이지로 이동하므로
      driver의 현재 페이지 위치와 무관하게 호출할 수 있습니다(타겟 URL 요청
      전, 스파이더 시작 시점에 호출하는 것을 전제로 함).

    Returns:
        list[dict] | None — 로그인(또는 쿠키 재사용) 성공 후 쿠키 목록.
        커스텀 로그인 함수 부재 또는 로그인 실패 시 None.
    """
    if cached_cookies:
        for cookie in cached_cookies:
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                logger.warning("[perform_login] 캐시된 쿠키 주입 실패 (name=%s): %s", cookie.get("name"), e)
        return cached_cookies

    login_fn = conf.CustomModuleStorage().load_login(seq_no)
    if login_fn is None:
        logger.error("[perform_login] custom_rules/render/%s.py에 login()이 정의되어 있지 않습니다.", seq_no)
        return None

    pre_login_url = driver.current_url
    pre_login_cookie_names = {c["name"] for c in driver.get_cookies()}
    login_fn(driver, login_info)

    if not check_login_success(driver, login_info, pre_login_url, pre_login_cookie_names):
        return None

    return driver.get_cookies()


def perform_logout(seq_no: str) -> None:
    """
    수집 종료 후 로그인 인증 상태를 정리합니다.

    현재는 로컬 정리(로그 기록)만 수행합니다 — 사이트에 실제 로그아웃 요청을
    보내는 것은 범위 밖입니다(추후 필요 시 custom_rules/render/{seq_no}.py에
    logout(driver) 훅을 추가하는 방향으로 확장 가능). 캐시된 쿠키 자체를
    비우는 것은 호출 측(스파이더)의 책임입니다.
    """
    logger.info("[perform_logout] seq_no=%s 로그인 세션 로컬 정리", seq_no)


def get_response_status(response):
    # 리다이렉트 발생 시 response.url은 최종 URL이므로,
    # 워커의 url_list 매칭용으로 최초 요청 URL을 별도로 보존합니다.
    # (redirect_urls의 첫 번째 원소 = 리다이렉트 전 최초 요청 URL)
    redirect_urls = response.meta.get("redirect_urls")
    req_url = redirect_urls[0] if redirect_urls else response.url

    # Selenium 등으로 생성된 응답은 ip_address가 None일 수 있고,
    # 비표준 상태 코드는 HTTPStatus()가 ValueError를 발생시키므로 방어적으로 처리합니다.
    ip_address = response.ip_address.compressed if response.ip_address else None
    try:
        reason = HTTPStatus(response.status).phrase
    except ValueError:
        reason = ""

    response_status = {
                        "url": response.url,
                        "req_url": req_url,
                        "method":response.request.method,
                        "params":response.request.body.decode('utf-8'),
                        "ip_address": ip_address,
                        "user_agents": response.request.headers.get('User-Agent').decode('utf-8'),
                        "cookies": set_cookies(response),
                        "status": response.status,
                        "reason": reason,
                        "pure_latency":response.meta["download_latency"],
                        "total_latency":response.meta["total_latency"]
                       }
    print(f"RESPONSE_STATUS:{json.dumps(response_status, ensure_ascii=False)}")
    return response_status


# run_login() / get_render_result()의 seq_no 하드코딩 분기는 custom_rules/render/{seq_no}.py의
# login() / render() 훅(conf.CustomModuleStorage)으로 대체되었습니다 — spirenderer.py 참고.


def get_result(collect_info, target, _items):

    if collect_info["conditions"]["dataFormat"] == "html":
        result = []
        for row in target:
            datas = extract_data_from_root(row, _items)
            for data in datas:
                if type(data) is dict:
                    result = result + [data]
                elif type(data) is list:
                    result = result + data

    elif collect_info["conditions"]["dataFormat"] == "json" or collect_info["conditions"]["dataFormat"] == "xml":
        if len(_items) != 0:
            if isinstance(target, dict):
                target = [target]

            result = []
            for row in target:
                data = { k:utility.get_target(row, v) for k,v in _items.items() }
                result.append(data)
        else:
            result = target

    else:
        raise ValueError(f"지원하지 않는 dataFormat 값입니다: {collect_info['conditions']['dataFormat']!r} (html/json/xml만 지원)")

    return result


def extract_data_from_root(root: Selector, _items: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    주어진 root Selector를 기준으로 scrape_info에 명시된 상대 XPath를 사용하여
    데이터를 추출하고, 딕셔너리 리스트로 변환합니다.

    Args:
        root: 데이터를 추출할 시작 노드(컨테이너) Selector 객체.
        _items: {컬럼명: 상대 XPath} 형태의 딕셔너리.

    Returns:
        [{"컬럼명1": 값1, "컬럼명2": 값2}, ...] 형태의 딕셔너리 리스트.
    """

    # 1. 컬럼별 데이터를 추출합니다.
    result_map = {}
    row_count = 0

    for column_name, relative_xpath in _items.items():
        # ⭐ root 셀렉터에 대해 상대 XPath를 실행합니다.
        # .xpath() 결과를 .getall()을 사용하여 텍스트 리스트로 추출합니다.
        # XPath가 'text()'를 포함하지 않는 경우를 대비해, 추출된 노드를 다시 .get()하여 내부 HTML/텍스트를 가져옵니다.
        extracted_nodes = root.xpath(relative_xpath)

        values = []
        for node in extracted_nodes:
            if isinstance(node.root, str):
                # text()/@attr 결과 — root가 문자열이므로 그대로 사용합니다.
                # (문자열 셀렉터에 .xpath(".")를 재호출하면 빈 값이 되거나,
                #  JSON 파싱 가능한 문자열은 json 타입 판정으로 ValueError가 발생합니다)
                value = node.root.strip()
            else:
                # 요소 노드 — node.xpath(".").get()으로 HTML 문자열을 얻고
                # re.sub를 사용하여 HTML 태그를 제거하고 공백을 정리합니다.
                value = re.sub('<.+?>', ' ', node.xpath(".").get(default='').strip(), 0).strip()
            values.append(value)

        # 데이터 없으면 None으로 처리
        if len(values) != 0:
            result_map[column_name] = values
        elif len(values) == 0:
            result_map[column_name] = [None]

        # 행(row)의 개수를 설정하고 일관성을 확인합니다.
        if row_count == 0:
            row_count = len(values)
        elif len(values) != row_count:
            # 데이터 수 불일치에 대한 경고 로그 (실제 크롤링 시 매우 중요)
            print(f"⚠️ 경고: '{column_name}' 컬럼의 데이터 수({len(values)})가 기준 수({row_count})와 일치하지 않습니다. 매핑 오류가 발생할 수 있습니다.")

    # 2. 추출된 값들을 행(row) 단위로 묶고 딕셔너리로 변환합니다.

    # zip(*result_map.values())를 사용하여 각 컬럼의 리스트를 행 단위로 묶습니다.
    zipped_data = zip(*result_map.values())

    column_names = list(result_map.keys())

    final_list = []

    # 각 행을 순회하며 딕셔너리를 생성합니다.
    for row_values in zipped_data:
        row_dict = dict(zip(column_names, row_values))
        final_list.append(row_dict)

    return final_list


def set_item_loader(response, collect_info, data):

    loader = DonasItemLoader(item=DonasItem(), selector=response)

    result_info = {}

    resp_info = get_response_status(response)
    resp_info["data"] = data
    result_info["resp_info"] = resp_info
    result_info["collect_info"] = collect_info

    loader.add_value('result_info', result_info)

    return loader


def set_cookies(response):
    """
    DB에 저장할 쿠키값으로 수정
    """

    cookies = response.headers.getlist('Set-Cookie')
    cookie = ""
    for code in cookies:
        code = code.decode('utf-8')
        cookie = cookie + code + " "
    return cookie.strip()


def requests_info(response, collect_info, time):

    # 요청 결과
    result = "success" if response.status == 200 else "fail"

    requests_info_dict = {
                            "seq_no": collect_info["seq_no"],
                            "titles": collect_info["title"],
                            "callback_url": response.url,
                            "ip": response.ip_address.compressed,
                            "user_agents": response.request.headers.get('User-Agent').decode('utf-8'),
                            "cookies": set_cookies(response),
                            "time": time,
                            "results" : result
                         }

    return requests_info_dict


def make_form_data_for_url_args(url):
    result_dict = {}
    args = furl(url).args
    keys = args.keys()
    for key in keys:
        try:
            if type(json.loads(args.get(key))) is int:
                result_dict[key] = str(json.loads(args.get(key)))
            else:
                result_dict[key] = json.loads(args.get(key))
        except Exception as e:
            print(e)
            result_dict[key] = args.get(key)
    return result_dict

