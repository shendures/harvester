# RateLimitedProxyMiddleware / set_ip_settings 단위 테스트
#
# 실행 방법 (프로젝트 루트에서):
#   python -m pytest tests/
# (python -m pytest 는 현재 디렉터리를 sys.path에 추가하므로
#  middlewares / customized_settings 를 최상위 모듈로 import 할 수 있습니다.)

import pytest
from scrapy import Request, Spider
from scrapy.settings import Settings
from scrapy.exceptions import IgnoreRequest

from middlewares import RateLimitedProxyMiddleware
from customized_settings import set_ip_settings


def make_middleware(proxies, allow_ip_cnts):
    settings = Settings({"ip_list": proxies, "allow_ip_cnts": allow_ip_cnts})
    return RateLimitedProxyMiddleware(settings)


@pytest.fixture
def spider():
    return Spider(name="test_spider")


# ── set_ip_settings ──────────────────────────────────


def test_set_ip_settings_converts_gui_rows_to_proxy_urls():
    request_info = {
        "proxy": {
            "enabled": True,
            "allow_ip_cnts": 5,
            "ip_list": [
                {"host": "10.0.0.1", "port": "8080", "protocol": "HTTP", "enabled": True},
                {"host": "10.0.0.2", "port": "1080", "protocol": "SOCKS5", "enabled": True},
                {"host": "10.0.0.3", "port": "8888", "protocol": "HTTP", "enabled": False},
                "http://10.0.0.4:3128",  # 문자열 항목은 그대로 통과
            ],
        }
    }

    result = set_ip_settings(request_info)

    assert result["allow_ip_cnts"] == 5
    assert result["ip_list"] == [
        "http://10.0.0.1:8080",
        "socks5://10.0.0.2:1080",
        "http://10.0.0.4:3128",  # enabled=False 행은 제외됨
    ]


def test_set_ip_settings_disabled_returns_none():
    assert set_ip_settings({"proxy": {"enabled": False}}) is None
    assert set_ip_settings({}) is None


# ── RateLimitedProxyMiddleware ───────────────────────


def test_assigns_proxy_without_attribute_error(spider):
    mw = make_middleware(["http://10.0.0.1:8080"], allow_ip_cnts=5)
    request = Request("http://example.com")

    assert mw.process_request(request, spider) is None
    assert request.meta["proxy"] == "http://10.0.0.1:8080"


def test_no_proxies_is_noop(spider):
    mw = make_middleware([], allow_ip_cnts=5)
    request = Request("http://example.com")

    assert mw.process_request(request, spider) is None
    assert "proxy" not in request.meta


def test_rate_limit_exceeded_raises_ignore_request(spider):
    mw = make_middleware(["http://10.0.0.1:8080"], allow_ip_cnts=2)

    mw.process_request(Request("http://example.com/1"), spider)
    mw.process_request(Request("http://example.com/2"), spider)

    with pytest.raises(IgnoreRequest):
        mw.process_request(Request("http://example.com/3"), spider)


def test_rate_limit_spreads_across_proxies(spider):
    proxies = ["http://10.0.0.1:8080", "http://10.0.0.2:8080"]
    mw = make_middleware(proxies, allow_ip_cnts=1)

    req1 = Request("http://example.com/1")
    req2 = Request("http://example.com/2")
    mw.process_request(req1, spider)
    mw.process_request(req2, spider)

    # 프록시당 1회 제한이므로 두 요청은 서로 다른 프록시를 사용해야 함
    assert {req1.meta["proxy"], req2.meta["proxy"]} == set(proxies)

    with pytest.raises(IgnoreRequest):
        mw.process_request(Request("http://example.com/3"), spider)


def test_zero_limit_means_unlimited(spider):
    mw = make_middleware(["http://10.0.0.1:8080"], allow_ip_cnts=0)

    for i in range(50):
        request = Request(f"http://example.com/{i}")
        assert mw.process_request(request, spider) is None
        assert request.meta["proxy"] == "http://10.0.0.1:8080"


def test_window_expiry_frees_capacity(spider, monkeypatch):
    import middlewares as mw_module

    mw = make_middleware(["http://10.0.0.1:8080"], allow_ip_cnts=1)

    now = 1_000_000.0
    monkeypatch.setattr(mw_module.time, "time", lambda: now)
    mw.process_request(Request("http://example.com/1"), spider)
    with pytest.raises(IgnoreRequest):
        mw.process_request(Request("http://example.com/2"), spider)

    # TIME_WINDOW(60초) 경과 후에는 다시 허용
    monkeypatch.setattr(mw_module.time, "time", lambda: now + 61)
    request = Request("http://example.com/3")
    assert mw.process_request(request, spider) is None
    assert request.meta["proxy"] == "http://10.0.0.1:8080"
