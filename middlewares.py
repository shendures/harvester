# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html


import random
import time
import string
from collections import defaultdict
from scrapy.exceptions import IgnoreRequest
from scrapy.exceptions import DontCloseSpider
import scrapy
from scrapy import signals
from twisted.internet import reactor
import uuid


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


class _DelayedRescheduler:
    """지정된 시간이 지난 뒤 요청을 엔진에 재주입합니다.

    대기 중인 요청이 있는 동안(spider_idle 시점)에는 DontCloseSpider를 발생시켜
    스파이더가 조기 종료되지 않도록 막습니다. CLOSESPIDER_* 등으로 spider_idle을
    거치지 않고 스파이더가 강제 종료되는 경우에는 spider_closed 시점에 남은
    타이머를 취소해, 이미 닫힌 엔진에 재주입을 시도하다 조용히 유실되는 대신
    명시적으로 경고 로그를 남깁니다.
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.pending_calls = set()
        crawler.signals.connect(self.spider_idle, signal=signals.spider_idle)
        crawler.signals.connect(self.spider_closed, signal=signals.spider_closed)

    def schedule(self, request, wait_time):
        # call은 reactor.callLater가 반환하기 전까지 존재하지 않으므로, 실행 시점에
        # 클로저로 자기 자신을 참조해 pending_calls에서 제거합니다.
        call = reactor.callLater(wait_time, lambda: self._reinject(call, request))
        self.pending_calls.add(call)

    def _reinject(self, call, request):
        self.pending_calls.discard(call)
        # 동일 요청이 이미 스케줄러를 한 번 거쳤을 수 있으므로 dupefilter에 막히지 않도록 재주입
        self.crawler.engine.crawl(request.replace(dont_filter=True))

    def spider_idle(self, spider):
        if self.pending_calls:
            raise DontCloseSpider

    def spider_closed(self, spider, reason=None):
        if not self.pending_calls:
            return
        spider.logger.warning(
            f"⚠️ 스파이더 종료(reason={reason})로 대기 중이던 재시도 요청 "
            f"{len(self.pending_calls)}건을 취소합니다.")
        for call in list(self.pending_calls):
            if call.active():
                call.cancel()
        self.pending_calls.clear()


class RateLimitedProxyMiddleware:

    # 특정 시간 당 IP 허용 횟수는 settings의 allow_ip_cnts로 결정됨 (self.req_per_minute)
    TIME_WINDOW = 60  # 특정 시간 ( 초 단위 )
    MAX_RATE_LIMIT_RETRIES = 5  # 재시도 상한 (Scrapy RetryMiddleware의 RETRY_TIMES와 동일한 취지)

    def __init__(self, settings, crawler):
        self.proxies = settings.getlist('ip_list')
        self.req_per_minute = settings.get('allow_ip_cnts', 0)
        # True(기본값) = 매 요청마다 무작위 프록시, False = 목록 순서대로 순차 사용
        self.rotate = settings.getbool('rotate', True)
        if not self.proxies:
            print("⚠️ ip_list 설정이 누락되었습니다. 프록시가 적용되지 않습니다.")

        # IP별 요청 시각을 저장하는 딕셔너리
        # 구조: {'http://ip:port': [timestamp1, timestamp2, ...]}
        self.proxy_usage = defaultdict(list)
        self.stats = crawler.stats
        self.rescheduler = _DelayedRescheduler(crawler)
        self._next_index = 0  # 순차(rotate=False) 모드에서 다음에 시도할 프록시 인덱스

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings, crawler)

    def process_request(self, request, spider):
        """여유 있는 프록시를 골라 요청에 할당합니다. (사용량 제한 검사 포함)"""
        if not self.proxies:
            return

        current_time = time.time()
        n = len(self.proxies)

        # rate limit 미설정(0 이하)이면 무제한으로 취급하고 rotate 설정에 따라서만 할당
        if self.req_per_minute <= 0:
            if self.rotate:
                request.meta['proxy'] = random.choice(self.proxies)
            else:
                request.meta['proxy'] = self.proxies[self._next_index % n]
                self._next_index += 1
            return None

        # rotate=True: 무작위 순서, rotate=False: 다음 인덱스부터 목록 순서대로 순회
        order = random.sample(range(n), n) if self.rotate else \
            [(self._next_index + i) % n for i in range(n)]

        for idx in order:
            proxy = self.proxies[idx]
            usage_list = self.proxy_usage[proxy]

            # 60초(TIME_WINDOW) 이전에 발생한 기록은 모두 제거합니다. (슬라이딩 윈도우)
            usage_list[:] = [t for t in usage_list if t > current_time - self.TIME_WINDOW]

            if len(usage_list) < self.req_per_minute:
                # 요청 시각을 기록하고 프록시를 할당합니다.
                usage_list.append(current_time)
                if not self.rotate:
                    self._next_index = idx + 1
                request.meta['proxy'] = proxy
                spider.logger.debug(f"🌐 Requesting {request.url} using {proxy}. Count: {len(usage_list)}")
                return None

        # --- 모든 프록시가 제한 초과 시 처리 ---
        retries = request.meta.get('rate_limit_retries', 0)
        if retries >= self.MAX_RATE_LIMIT_RETRIES:
            self.stats.inc_value('rate_limit/max_reached')
            spider.logger.error(
                f"❌ Rate Limit 재시도 한도({self.MAX_RATE_LIMIT_RETRIES}회) 초과로 요청을 포기합니다: {request.url}")
            raise IgnoreRequest(f"Rate limit retry limit ({self.MAX_RATE_LIMIT_RETRIES}) exceeded.")

        # 다음 요청 가능 시각 계산 (전체 프록시 중 가장 빨리 풀리는 기록 기준)
        earliest_time = min(self.proxy_usage[p][0] for p in self.proxies if self.proxy_usage[p])
        wait_time = (earliest_time + self.TIME_WINDOW) - current_time
        request.meta['rate_limit_retries'] = retries + 1

        self.stats.inc_value('rate_limit/rescheduled')
        spider.logger.warning(
            f"⏳ 모든 프록시가 Rate Limit 초과. {wait_time:.2f}초 후 재시도합니다 "
            f"({retries + 1}/{self.MAX_RATE_LIMIT_RETRIES}): {request.url}")
        self.rescheduler.schedule(request, wait_time)
        raise IgnoreRequest(f"All proxies rate limited. Re-queued in {wait_time:.2f}s.")


class DelaySchedulerMiddleware:
    """spider가 yield한 요청 중 meta['delay_until']이 설정된 요청을,
    해당 시각이 될 때까지 대기시킨 뒤 다시 큐에 넣는 미들웨어"""

    def __init__(self, crawler):
        self.rescheduler = _DelayedRescheduler(crawler)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_spider_output(self, response, result, spider):
        for request_or_item in result:
            # 결과가 Request 객체이고, 재시도 지연 정보가 있다면
            if isinstance(request_or_item, scrapy.Request) and 'delay_until' in request_or_item.meta:
                delay_until = request_or_item.meta.pop('delay_until')
                wait_time = delay_until - time.time()

                if wait_time > 0:
                    # 아직 대기 시간이 남았다면 지연 후 재주입 (즉시 yield하지 않음)
                    spider.logger.debug(
                        f"Re-scheduling request {request_or_item.url} for later ({wait_time:.2f}s delay).")
                    self.rescheduler.schedule(request_or_item, wait_time)
                    continue

                # 대기 시간이 지났다면 정상적으로 처리합니다.
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
            return None

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