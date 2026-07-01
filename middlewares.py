# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html


import random
import time
import string
from collections import defaultdict
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.exceptions import DontCloseSpider
import scrapy
from scrapy import signals
import uuid
from datetime import datetime as dt

# useful for handling different item types with a single interface
from itemadapter import ItemAdapter


class DonasSpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    async def process_start(self, start):
        # Called with an async iterator over the spider start() method or the
        # maching method of an earlier spider middleware.
        async for item_or_request in start:
            yield item_or_request

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class DonasDownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        # Called for each request that goes through the downloader
        # middleware.

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.

        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class LatencyTrackingMiddleware:
    def process_request(self, request, spider):
        # 🌟 실제 다운로더로 넘어가기 직전에 시간을 기록합니다.
        request.meta['actual_start_time'] = time.time()
        return None  # 다음 단계로 진행

    def process_response(self, request, response, spider):
        # 🌟 응답이 돌아온 직후 시간을 계산합니다.
        start_time = request.meta.get('actual_start_time')
        if start_time:
            latency = time.time() - start_time
            # 스파이더 로그가 아닌 여기서 직접 찍거나, response.meta에 다시 담아줍니다.
            request.meta['total_latency'] = latency
        return response


class RandomProxyMiddleware:
    def __init__(self, proxies):
        # PROXY_LIST 설정이 없으면 에러 발생
        if not proxies:
            raise NotConfigured("PROXY_LIST 설정이 settings.py에 정의되지 않았습니다.")

        self.proxies = proxies
        self.logger = None

    @classmethod
    def from_crawler(cls, crawler):
        # settings.py에서 PROXY_LIST를 가져옴
        proxies = crawler.settings.getlist('PROXY_LIST')
        instance = cls(proxies)
        instance.logger = crawler.spider.logger
        return instance

    def process_request(self, request, spider):
        """
        요청에 무작위 프록시를 할당합니다.
        """
        # 이미 proxy가 설정되어 있지 않은 경우에만 처리
        if not request.meta.get('proxy'):
            # self.proxies 리스트에서 무작위로 하나를 선택
            proxy_url = random.choice(self.proxies)

            # 요청의 meta에 'proxy' 키를 설정합니다.
            request.meta['proxy'] = proxy_url

            self.logger.debug(f"요청 {request.url}에 무작위 프록시 {proxy_url} 할당")

        return None

    def process_response(self, request, response, spider):
        """사용된 IP를 response.meta에 기록 (선택 사항)"""
        used_proxy = request.meta.get('proxy')
        if used_proxy:
            response.meta['ip'] = used_proxy.split('//')[-1]
        return response




class RateLimitedProxyMiddleware:

    # 1. 특정 시간 당 IP 허용 횟수 설정
    # REQUESTS_PER_MINUTE = 15 # IP 허용 횟수
    TIME_WINDOW = 60  # 특정 시간 ( 초 단위 )

    def __init__(self, settings):
        self.proxies = settings.getlist('ip_list')
        self.req_per_minute = settings.get('allow_ip_cnts', 0)
        if not self.proxies:
            print("⚠️ PROXY_LIST 설정이 누락되었습니다. 프록시가 적용되지 않습니다.")

        # IP별 요청 시각을 저장하는 딕셔너리
        # 구조: {'http://ip:port': [timestamp1, timestamp2, ...]}
        self.proxy_usage = defaultdict(list)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_request(self, request, spider):
        """요청에 무작위 프록시 할당 및 사용량 제한 검사"""
        if not self.proxies:
            return

        # 1. 사용할 프록시 선택 및 할당
        # (이 단계에서는 아직 요청을 보내지 않고, 검사/할당만 합니다.)
        proxy = random.choice(self.proxies)
        request.meta['proxy'] = proxy

        current_time = time.time()

        # 2. IP 사용 기록 정리 및 횟수 검사

        # 현재 IP의 사용 기록 리스트를 가져옵니다.
        usage_list = self.proxy_usage[proxy]

        # 60초(TIME_WINDOW) 이전에 발생한 기록은 모두 제거합니다. (슬라이딩 윈도우)
        usage_list[:] = [t for t in usage_list if t > current_time - self.TIME_WINDOW]

        # 3. Rate Limit 검사
        if len(usage_list) >= self.REQUESTS_PER_MINUTE:
            # --- 제한 초과 시 처리 ---

            # 다음 요청 가능 시각 계산
            # (가장 오래된 기록(리스트의 첫 번째 요소) 시각 + 60초)
            earliest_time = usage_list[0]
            wait_time = (earliest_time + self.TIME_WINDOW) - current_time

            # 요청을 즉시 보내지 않고, Scrapy에게 잠시 보류하도록 지시합니다.
            # return request으로 요청을 다시 스케줄러 큐에 넣고 싶지만, 미들웨어에서 직접 재스케줄링은 까다롭습니다.

            # 가장 간단한 방법: 요청을 무시하고 스케줄러로 재스케줄링을 요청합니다.
            # Scrapy의 지연 로직을 활용하기 위해 요청에 재시도 정보를 추가합니다.
            spider.logger.warning(f"⏳ Rate Limit 초과. IP '{proxy}'는 {wait_time:.2f}초 후 사용 가능. 재예약 요청.")

            # 요청을 버리고, 스케줄러 미들웨어에서 재스케줄링을 처리하거나,
            # 다운로더 미들웨어에서 지연 후 재요청을 유도해야 합니다.

            # *****************************************************************
            # 현실적인 구현: 재시도 메타데이터를 추가하고 에러를 발생시켜 재스케줄링 유도
            # *****************************************************************
            request.dont_filter = True  # 필터링하지 않고 다시 큐에 넣도록 설정
            request.meta['delay_until'] = current_time + wait_time

            # 임시 에러를 발생시켜 Scrapy가 이 요청을 재시도하도록 유도합니다.
            # 이는 요청을 버리고 다시 스케줄링하는 일반적인 패턴입니다.
            raise IgnoreRequest(f"Proxy rate limit exceeded for {proxy}. Delay requested.")

        else:
            # --- 제한 미초과 시 처리 ---

            # 요청 시각을 기록합니다.
            usage_list.append(current_time)
            spider.logger.debug(f"🌐 Requesting {request.url} using {proxy}. Count: {len(usage_list)}")

            # 다음 미들웨어 또는 다운로더로 요청을 전달합니다.
            return None


class DelaySchedulerMiddleware:
    """다운로더에서 요청이 무시된 후, 지연 메타데이터를 기반으로 요청을 큐에 다시 넣는 미들웨어"""

    def process_spider_output(self, response, result, spider):
        for request_or_item in result:
            # 결과가 Request 객체이고, 재시도 지연 정보가 있다면
            if isinstance(request_or_item, scrapy.Request) and 'delay_until' in request_or_item.meta:
                delay_until = request_or_item.meta['delay_until']
                current_time = time.time()

                if delay_until > current_time:
                    # 아직 대기 시간이 남았다면
                    wait_time = delay_until - current_time

                    # 요청을 스케줄러 큐에 다시 넣기 전에 지연 시간을 설정합니다.
                    # Scrapy는 이 요청을 즉시 처리하지 않고, 잠시 후 다시 시도합니다.
                    # 이 방법은 명확한 지연 보장이 어려우므로, 다음 tick에서 다시 process_request를 거치게 합니다.
                    spider.crawler.engine.schedule(request_or_item)
                    spider.logger.debug(
                        f"Re-scheduling request {request_or_item.url} for later ({wait_time:.2f}s delay).")

                    # 스파이더가 요청을 기다리는 동안 닫히지 않도록 합니다.
                    raise DontCloseSpider()

                    # 대기 시간이 지났다면 정상적으로 처리합니다.
                else:
                    yield request_or_item
            else:
                yield request_or_item


class RandomUserAgentMiddleware:
    # 사용할 User-Agent 목록을 정의합니다.
    USER_AGENT_LIST = [
        # --- 1. 데스크톱 환경 (Desktop) ---

        # [Chrome] Windows 10/11 (가장 흔함)
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',

        # [Chrome] macOS
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',

        # [Firefox] Windows 10/11
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:118.0) Gecko/20100101 Firefox/118.0',

        # [Firefox] macOS
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',

        # [Edge] Windows 10/11
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.2210.133',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.2151.72',

        # [Safari] macOS
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',

        # [Linux] (데스크톱)
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',

        # --- 2. 모바일 환경 (Mobile) ---  ::: 모바일 UA를 입력 시, response_url에서 모바일 페이지받게 되어 요청 URL중복 검증 시 이슈가 발생함.

        # # [iOS] iPhone (Safari)
        # 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        # # [iOS] iPad (Safari)
        # 'Mozilla/5.0 (iPad; CPU OS 16_7_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Safari/604.1',
        # # [Android] Chrome (최신 안드로이드)
        # 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36',
        # # [Android] Chrome (구형 안드로이드)
        # 'Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.6045.163 Mobile Safari/537.36',

        # --- 3. 기타/특수 User-Agent (선택 사항) ---

        # Bing 봇 (가끔은 주요 검색 엔진 봇 행세를 하는 것이 차단 회피에 도움)
        'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)',
        # Google 봇
        'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    ]

    def process_request(self, request, spider):
        """요청에 무작위 User-Agent 헤더를 설정합니다."""

        # 'User-Agent' 헤더를 무작위로 선택된 문자열로 덮어씁니다.
        user_agent = random.choice(self.USER_AGENT_LIST)
        request.headers.setdefault('User-Agent', user_agent)

        spider.logger.debug(f"🎭 Using User-Agent: {user_agent}")

        return None  # 요청을 다음 미들웨어로 전달


class RandomCookieMiddleware:

    # 1. 2차 규칙 모방을 위한 값 생성 함수 정의

    def _generate_random_hex(self, length=32):
        """지정된 길이의 랜덤 16진수 문자열을 생성합니다."""
        return ''.join(random.choices(string.hexdigits.lower(), k=length))

    def _generate_simple_id(self, length=10):
        """숫자와 알파벳을 섞은 단순 ID를 생성합니다."""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=length))

    def _generate_tracking_id(self):
        """Google Analytics (_ga)와 유사한 형식의 랜덤 트래킹 ID를 모방합니다."""
        random_part = random.randint(100000000, 999999999)
        timestamp = int(time.time() * 1000)
        return f"GA1.2.{random_part}.{timestamp}"

    def _generate_uuid(self):
        """⭐️ UUIDv4 형식을 생성합니다. (32자 16진수 + 하이픈)"""
        # uuid4()는 무작위성을 기반으로 생성되므로 세션 ID로 적합합니다.
        return str(uuid.uuid4())

    def process_request(self, request, spider):
        """요청에 다양한 규칙을 가진 랜덤 쿠키를 주입합니다."""

        # 이미 요청에 쿠키가 설정되어 있다면 건너뜁니다.
        if request.cookies:
            return request.cookies

        # 1. UUID 세션 ID 모방 (가장 강력한 무작위 값)
        random_uuid_session = self._generate_uuid()

        # 2. 무작위성이 높은 일반 세션 ID 모방 (32자 길이)
        random_hex_session = self._generate_random_hex(length=32)

        # 3. 특정 포맷을 가진 트래킹 ID 모방
        random_ga_id = self._generate_tracking_id()

        # 4. 요청에 쿠키 딕셔너리 주입
        # 사이트가 사용하는 키 이름을 추정하여 적용합니다.
        request.cookies = {
            'session_uuid': random_uuid_session,  # UUID 형식 세션 ID
            'sessionid_hex': random_hex_session,  # 일반 16진수 세션 ID
            '_ga': random_ga_id,  # 트래킹 ID
        }

        # 5. 핵심 우회 설정: IP 로테이션 시 쿠키 병합 방지
        request.meta['dont_merge_cookies'] = True

        spider.logger.debug(f"🍪 랜덤 쿠키 주입: UUID={random_uuid_session}")

        return None  # 다음 미들웨어로 요청 전달