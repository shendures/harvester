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


class LatencyTrackingMiddleware:
    def process_request(self, request, spider):
        request.meta['actual_start_time'] = time.time()
        return None

    def process_response(self, request, response, spider):
        start_time = request.meta.get('actual_start_time')
        if start_time:
            latency = time.time() - start_time
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

        # IP별 요청 시각 기록: {'http://ip:port': [timestamp1, timestamp2, ...]}
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
                usage_list.append(current_time)
                if not self.rotate:
                    self._next_index = idx + 1
                request.meta['proxy'] = proxy
                spider.logger.debug(f"🌐 Requesting {request.url} using {proxy}. Count: {len(usage_list)}")
                return None

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
            if isinstance(request_or_item, scrapy.Request) and 'delay_until' in request_or_item.meta:
                delay_until = request_or_item.meta.pop('delay_until')
                wait_time = delay_until - time.time()

                if wait_time > 0:
                    # 즉시 yield하지 않고 지연 후 재주입합니다.
                    spider.logger.debug(
                        f"Re-scheduling request {request_or_item.url} for later ({wait_time:.2f}s delay).")
                    self.rescheduler.schedule(request_or_item, wait_time)
                    continue

            yield request_or_item


class RandomUserAgentMiddleware:
    USER_AGENT_LIST = [
        # 데스크톱 환경
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',

        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',

        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:118.0) Gecko/20100101 Firefox/118.0',

        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',

        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.2210.133',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.2151.72',

        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',

        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',

        # 모바일 환경 — 모바일 UA 입력 시 response_url에서 모바일 페이지를 받게 되어 요청 URL중복 검증 시 이슈가 발생함(비활성화)

        # 검색엔진 봇 UA — 주요 검색 엔진 봇 행세를 하는 것이 차단 회피에 도움이 되는 경우가 있어 포함
        'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)',
        'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    ]

    def process_request(self, request, spider):
        user_agent = random.choice(self.USER_AGENT_LIST)
        request.headers.setdefault('User-Agent', user_agent)

        spider.logger.debug(f"🎭 Using User-Agent: {user_agent}")

        return None


class RandomCookieMiddleware:

    def _generate_random_hex(self, length=32):
        return ''.join(random.choices(string.hexdigits.lower(), k=length))

    def _generate_tracking_id(self):
        random_part = random.randint(100000000, 999999999)
        timestamp = int(time.time() * 1000)
        return f"GA1.2.{random_part}.{timestamp}"

    def _generate_uuid(self):
        return str(uuid.uuid4())

    def process_request(self, request, spider):
        if request.cookies:
            return None

        random_uuid_session = self._generate_uuid()
        random_hex_session = self._generate_random_hex(length=32)
        random_ga_id = self._generate_tracking_id()

        # 사이트가 사용하는 키 이름을 추정하여 적용합니다.
        request.cookies = {
            'session_uuid': random_uuid_session,
            'sessionid_hex': random_hex_session,
            '_ga': random_ga_id,
        }

        # 핵심 우회 설정: IP 로테이션 시 쿠키 병합 방지
        request.meta['dont_merge_cookies'] = True

        # dont_merge_cookies가 True면 Scrapy 내장 CookiesMiddleware가
        # request.cookies → Cookie 헤더 변환을 건너뛰므로, 여기서 직접 헤더를 채운다.
        request.headers['Cookie'] = '; '.join(
            f'{name}={value}' for name, value in request.cookies.items()
        )

        spider.logger.debug(f"🍪 랜덤 쿠키 주입: UUID={random_uuid_session}")

        return None
