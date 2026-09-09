import re
import json
import logging
import scrapy
from scrapy.http import JsonRequest
from typing import List, Dict, Any
import utility
import conf
from http import HTTPStatus

from items import DonasItem, DonasItemLoader
from scrapy.selector import Selector

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.remote_connection import RemoteConnection
from webdriver_manager.chrome import ChromeDriverManager  # 드라이버 자동 설치/관리

# spiders
from spiders.spihtml import HtmlExtractorSpider
from spiders.spirenderer import HtmlSeleniumSpider
from spiders.spijson import JsonExtractorSpider
from spiders.spixml import XmlExtractorSpider
from spiders.spidetail import DetailExtractorSpider

logger = logging.getLogger(__name__)

# 개별 WebDriver 명령(페이지 로드 포함)의 최대 대기 시간 — 기본값은 사실상 무제한이라
# 사이트 응답이 느리거나 멈추면 perform_login()/parse()가 영영 리턴하지 않게 됨.
SELENIUM_COMMAND_TIMEOUT_SECONDS = 30

def get_login_failure_phrases():
    """로그인 실패 시 사이트에서 흔히 쓰는 문구(사이트 무관 공통 판별용, 소문자 비교)"""
    return [
        "비밀번호가 일치하지", "아이디 또는 비밀번호가 올바르지",
        "아이디/비밀번호를 확인", "로그인에 실패", "계정 정보가 일치하지",
        "invalid password", "incorrect username or password", "login failed",
        "invalid credentials",
    ]

def get_json_form(url):

    if "?" not in url:
        raise ValueError(f"POST 요청 URL은 '<url>?<JSON 쿼리>' 형식이어야 합니다: {url!r}")

    processed_url = re.search(r".*(?=\?)", url)[0]
    body = json.loads(re.search(r"(?<=\?).*", url)[0])

    return processed_url, body


def get_spider(request_info: dict):

    spiders = conf.get_spider_mode(request_info)

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


REQUIRED_CONDITION_KEYS = {
    "html":        ["method", "items.root"],
    "json":        ["method", "items.root"],
    "xml":         ["method", "items.root"],
    "html_render": ["method", "items.root"],
}


def _dig(d: dict, dotted_path: str):
    for key in dotted_path.split("."):
        if not isinstance(d, dict) or key not in d:
            return None
        d = d[key]
    return d


def validate_blueprint_conditions(request_info: dict) -> str | None:
    """수집 시작 전 conditions에 스파이더 타입별 필수 키가 채워져 있는지 검사한다.
    문제 없으면 None, 있으면 사용자에게 보여줄 안내 문자열을 반환한다 — URL마다
    반복해서 같은 KeyError를 내며 낭비하는 대신 요청을 한 건도 보내기 전에 막는다."""
    mode = conf.get_spider_mode(request_info)
    conditions = request_info.get("conditions") or {}
    missing = []

    if mode == "detail":
        for path in ("mainUrl", "mainFormat"):
            if not _dig(conditions, path):
                missing.append(path)
        main_format = conditions.get("mainFormat")
        if main_format == "html" and not _dig(conditions, "items.detail"):
            missing.append("items.detail")
        elif main_format == "json":
            for path in ("items.detail_root", "items.detail", "items.main_root"):
                if not _dig(conditions, path):
                    missing.append(path)
        elif main_format not in ("html", "json"):
            missing.append("mainFormat(html 또는 json이어야 함)")
    else:
        for path in REQUIRED_CONDITION_KEYS.get(mode, []):
            if not _dig(conditions, path):
                missing.append(path)

    if not missing:
        return None
    title = request_info.get("title") or "(제목 없음)"
    return (
        f"'{title}' 블루프린트의 수집 설정(conditions)에 필수 항목이 비어 있어 "
        f"수집을 시작할 수 없습니다.\n\n누락된 항목: {', '.join(missing)}\n\n"
        f"블루프린트 편집에서 해당 항목을 채운 뒤 다시 시도하세요."
    )


def handle_request_failure(failure):
    """응답 자체를 못 받은 요청(타임아웃/DNS 실패/연결거부 등, 재시도 소진 후)의 Scrapy
    errback — worker.py가 다른 응답과 동일하게 집계하도록 RESULT_INFO를 직접 보고한다.
    실제 Response가 없어 get_response_status()/DonasItemLoader(selector 필요)를 쓸 수
    없으므로 Request/Failure에서 복원 가능한 필드만으로 최소 resp_info를 직접 구성한다."""
    request = failure.request
    reason = failure.getErrorMessage() or type(failure.value).__name__
    logger.warning("[handle_request_failure] 요청 실패: %s | %s", request.url, reason)

    ua = request.headers.get('User-Agent')
    resp_info = {
        "url": request.url,
        "req_url": request.meta.get("original_url", request.url),
        "method": request.method,
        "params": request.body.decode('utf-8', errors='replace') if request.body else "",
        "ip_address": None,
        "user_agents": ua.decode('utf-8') if ua else "",
        "cookies": "",
        "status": "000",  # 상태 코드를 받지 못한 경우(연결 실패 등) — 실패 유형은 reason에 기록됨
        "reason": reason,
        "pure_latency": None,   # 응답이 없어 latency 없음 — 통계 페이지의 평균 응답시간 집계에서 자동 제외됨
        "total_latency": None,
    }
    print(f"RESULT_INFO:{json.dumps({'resp_info': resp_info}, ensure_ascii=False)}")


def get_scrapy_request(url, conditions, callback):
    """
    조건 딕셔너리에 따라 Scrapy Request 또는 FormRequest 객체를 생성합니다.
    """

    # 1. 공통 파라미터 딕셔너리 준비
    # meta에 original_url(치환 전 요청 URL)을 함께 실어 보낸다 — POST 요청은 아래에서
    # url_list 매칭용 쿼리스트링(JSON 리터럴)이 제거된 processed_url로 바뀌므로, 응답
    # 쪽(get_response_status)에서 워커의 url_list와 대조 가능한 원본 URL을 복원하려면
    # 이 값이 필요하다. dict를 복사해 넣는다 — conditions는 url_list의 모든 요청이
    # 공유하는 같은 객체라 여기서 직접 mutate하면 마지막 요청의 url로 덮어써진다.
    request_kwargs = {
        'url': url,
        'callback': callback,
        'errback': handle_request_failure,  # 응답 자체를 못 받은 요청(타임아웃 등)도 집계되도록
        'method': conditions['method'],
        'headers': conditions.get("headers"),  # headers가 None이어도 Request 객체는 이를 처리함
        'meta': {**conditions, 'original_url': url},
    }

    if conditions['method'] == "GET":

        # 일반 요청 (렌더링 페이지도 spirenderer가 자체 Chrome 드라이버로 처리하므로 동일)
        return scrapy.Request(**request_kwargs)

    # 2. POST 요청에 대한 추가 처리
    elif conditions['method'] == "POST":

        processed_url, body = get_json_form(url)

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

    # 크롬 네이티브 "알림 허용" 등 권한 요청 팝업 차단(2=차단). 사이트 자체가
    # DOM으로 그리는 공지사항/이벤트 모달은 이 설정으로 막을 수 없음 —
    # 그런 경우는 render()/login() 커스텀 스크립트에서 닫기 버튼을 클릭해야 함.
    options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values.geolocation": 2,
    })
    options.add_argument("--disable-notifications")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # RemoteConnection은 driver 생성 시점에 자기 _client_config로 클래스 속성을
    # 새로 덮어쓰므로, 타임아웃 설정은 반드시 driver 생성 "이후"에 호출해야 함
    # (생성 전에 호출하면 무시되거나 최초 호출 시 AttributeError 발생).
    RemoteConnection.set_timeout(SELENIUM_COMMAND_TIMEOUT_SECONDS)
    driver.set_page_load_timeout(SELENIUM_COMMAND_TIMEOUT_SECONDS)

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
    # pre_login_url은 login() 호출 전(driver 생성 직후 "data:," 등 미탐색 상태)이라,
    # login()이 내부에서 loginUrl로 자체 이동하는 사이트는 로그인 성공 여부와 무관하게
    # "로그인 페이지 도착"만으로 url_changed가 항상 True가 되어 무의미해짐. loginUrl이
    # 있으면 "로그인 페이지 자체에서 벗어났는가"로 비교 기준을 보정하고, 없는 사이트
    # (대상 페이지에서 바로 로그인 박스를 클릭하는 방식)는 기존처럼 pre_login_url을 씀.
    baseline_url = login_info.get("loginUrl") or pre_login_url
    url_changed = driver.current_url != baseline_url

    return new_cookie_appeared or password_field_gone or url_changed


def requires_login(conditions: dict) -> bool:
    """이 수집 조건이 로그인 인증을 필요로 하는지 판단합니다 (conditions.login 존재 여부)."""
    return (conditions or {}).get("login") is not None


def perform_login(driver, login_info: dict, seq_no: str) -> bool:
    """
    로그인 인증을 수행합니다.

    이 driver로 이후 모든 타겟 URL을 계속 탐색하는 것을 전제로 합니다 —
    스파이더 실행(수집 세션) 전체에서 재사용되는 단일 브라우저 세션이므로,
    로그인에 성공하면 같은 세션이 쿠키를 그대로 유지해 별도로 쿠키를
    추출·재주입할 필요가 없습니다.

    Returns:
        bool — 로그인 성공 여부. login/{seq_no}.py에 login()이
        정의돼 있지 않거나 로그인에 실패(응답 지연·타임아웃 포함)하면 False.
    """
    login_fn = conf.CustomModuleStorage().load_login(seq_no)
    if login_fn is None:
        logger.error("[perform_login] login/%s.py에 login()이 정의되어 있지 않습니다.", seq_no)
        return False

    pre_login_url = driver.current_url
    pre_login_cookie_names = {c["name"] for c in driver.get_cookies()}
    try:
        login_fn(driver, login_info)
        return check_login_success(driver, login_info, pre_login_url, pre_login_cookie_names)
    except Exception as e:
        # SELENIUM_COMMAND_TIMEOUT_SECONDS 초과(응답 지연·행) 등으로 로그인
        # 처리 중 예외가 나면, 이후 수집 자체를 시작하지 않도록 실패로 처리.
        logger.error("[perform_login] 로그인 처리 중 오류 발생(seq_no=%s): %s", seq_no, e)
        return False


def perform_logout(seq_no: str) -> None:
    """
    수집 종료 후 로그인 인증 상태를 정리합니다.

    현재는 로컬 정리(로그 기록)만 수행합니다 — 사이트에 실제 로그아웃 요청을
    보내는 것은 범위 밖입니다(추후 필요 시 login/{seq_no}.py에
    logout(driver) 훅을 추가하는 방향으로 확장 가능). 캐시된 쿠키 자체를
    비우는 것은 호출 측(스파이더)의 책임입니다.
    """
    logger.info("[perform_logout] seq_no=%s 로그인 세션 로컬 정리", seq_no)


def get_response_status(response):
    # 워커의 url_list 매칭용 URL을 복원합니다. 우선순위:
    # 1) original_url — get_scrapy_request()가 심어둔, url_list 생성에 쓰인 것과 동일한
    #    치환 전 원본 URL. POST 요청은 get_json_form()이 쿼리스트링(JSON 리터럴)을
    #    떼어 바디로 옮기고 URL을 축약하므로, response.url은 이미 그 축약된 URL이라
    #    url_list와 절대 매칭되지 않는다 — 반드시 이 값을 써야 한다.
    # 2) redirect_urls[0] — 리다이렉트 발생 시 response.url은 최종 URL이므로 그 대신
    #    최초 요청 URL(위 original_url이 없을 때의 하위 호환 폴백).
    # 3) response.url — 그 외 기본값.
    redirect_urls = response.meta.get("redirect_urls")
    original_url = response.meta.get("original_url")
    req_url = original_url or (redirect_urls[0] if redirect_urls else response.url)

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


# run_login() / get_render_result()의 seq_no 하드코딩 분기는 login/{seq_no}.py의
# login() 훅과 render/{seq_no}.py의 render() 훅(conf.CustomModuleStorage)으로 대체되었습니다 — spirenderer.py 참고.


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


def build_failure_item(response, collect_info, error=None):
    """비정상 상태코드 또는 추출 중 예외가 발생한 응답을 데이터 없는 최소 아이템으로
    변환한다 — 실제 추출 결과는 없지만 RESULT_INFO로 흘러들어가 worker.py가 실패로
    집계할 수 있게 한다. status는 응답을 받은 이상 항상 실제 HTTP 상태코드를 유지한다
    (worker.py의 성공/실패 판정 기준). error가 주어지면(추출 단계에서 발생한 예외)
    reason에 예외 메시지를 남기고, extract_error에 예외 타입명을 별도로 기록해
    "200 응답이지만 데이터 추출은 실패"한 경우를 status/성공 판정과 무관하게 구분할
    수 있게 한다."""
    loader = set_item_loader(response, collect_info, None)
    item = loader.load_item()
    if error is not None:
        item['result_info']['resp_info']['reason'] = str(error)
        item['result_info']['resp_info']['extract_error'] = type(error).__name__
    return item


def set_cookies(response):
    """
    DB/대시보드에 표시할 쿠키값을 반환합니다.

    RandomCookieMiddleware 등이 이번 요청에 실제로 실어 보낸 Cookie 헤더를
    우선 사용하고, 없으면(랜덤 쿠키 비활성 등) 서버가 Set-Cookie로 내려준
    값을 대신 반환합니다.
    """

    req_cookie = response.request.headers.get('Cookie')
    if req_cookie:
        return req_cookie.decode('utf-8')

    cookies = response.headers.getlist('Set-Cookie')
    cookie = ""
    for code in cookies:
        code = code.decode('utf-8')
        cookie = cookie + code + " "
    return cookie.strip()


