import os

# Scrapy settings for donas project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "harvester"

SPIDER_MODULES = ["spiders"]
NEWSPIDER_MODULE = "spiders"

ADDONS = {}

# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = "donas (+http://www.yourdomain.com)"

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Concurrency and throttling settings
CONCURRENT_REQUESTS = 32  # Scrapy 엔진이 동시에 처리할 수 있는 최대 요청의 총합입니다. 수집 대상 사이트가 1개든 100개든 상관없이, 이 수치를 넘겨서 요청을 보낼 수 없습니다.
CONCURRENT_REQUESTS_PER_DOMAIN = 8 # 특정 도메인(예: naver.com) 하나에 대해 동시에 보낼 수 있는 최대 요청 수입니다. ( 아무리 이 값을 높여도 전체 한도인 CONCURRENT_REQUESTS를 넘을 수는 없습니다 )
# DOWNLOAD_DELAY = 0.5 # 기본 지연 시간을 0.5초로 설정
RANDOMIZE_DOWNLOAD_DELAY = True  # 지연 시간에 무작위성을 부여 ( 설정된 DOWNLOAD_DELAY 값의 0.5배에서 1.5배 사이의 값을 무작위로 선택하여 대기 )

# Disable cookies (enabled by default)
COOKIES_ENABLED = True
COOKIES_DEBUG = False # True로 설정하면 디버깅이 편하나, 성능 저하 및 보안 문제 발생 가능

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html

#SPIDER_MIDDLEWARES = {
#    "middlewares.DonasSpiderMiddleware": 543,
#}

SPIDER_MIDDLEWARES = {
    # delay_until이 걸린 요청을 지연 재스케줄 (process_spider_output 훅이므로 SPIDER_MIDDLEWARES에 등록)
    'middlewares.DelaySchedulerMiddleware': 500,
}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html


DOWNLOADER_MIDDLEWARES = {

    # 1. IP 관리 및 프록시 할당 (가장 바깥)
    "middlewares.RateLimitedProxyMiddleware": None,  # 100

    # 2. Scrapy 기본 프록시 적용 로직
    "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": 110,

    # # 3. User-Agent 변경
    # "middlewares.RandomUserAgentMiddleware": 400,

    # # 4. Scrapy 기본 User-Agent는 무시 (RandomUserAgentMiddleware를 사용하므로)
    # "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,

    # 5. 사용자 정의 미들웨어
    "middlewares.DonasDownloaderMiddleware": None,

    # # 6. 쿠키 설정 미들웨어
    # "middlewares.RandomCookieMiddleware": None,  # 650

    # requests와 response간의 Latency 측정
    'middlewares.LatencyTrackingMiddleware': 743,

    # 7. Selenium 실행 (가장 안쪽, 모든 헤더 설정 후 실행)
    "scrapy_selenium.SeleniumMiddleware": 800,
}



# PROXY_LIST = [
#     # 'http://183.110.216.159:8090',  # 첫 번째 프록시 IP
#     # 'https://175.208.236.55:8007',  # 두 번째 프록시 IP
#     'http://userId:password@203.0.113.3:8888', # 인증이 필요한 프록시
#     # ... 필요한 만큼 추가
# ]


# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
ITEM_PIPELINES = {
   "pipelines.LoadItemPipeline": 100
}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
# AUTOTHROTTLE_ENABLED = True  # 서버의 응답 속도에 맞춰 지연 시간을 스스로 조절합니다.
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5  # 수집을 시작할 때 첫 번째 요청에 적용할 초기 대기 시간입니다. ( 첫인상 )
# The maximum download delay to be set in case of high latencies
# AUTOTHROTTLE_MAX_DELAY = 60  # 서버 응답이 아무리 늦어져도 최대 이 시간까지만 기다리겠다는 상한선입니다.  ( 인내심의 한계 )
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0  # 서버 한 대당 평균적으로 유지하고 싶은 동시 요청 수 ( 적정 인원 수 ) ( AutoThrottle의 핵심 ) 상황 봐가면서 유지하고 싶은 이상적인 통화 수
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False  # AutoThrottle이 속도를 어떻게 조절하고 있는지 로그로 보여줄지 여부 ( CCTV )



# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"
HTTPERROR_ALLOW_ALL = True  # 모든 응답 상태 허용
# HTTPERROR_ALLOWED_CODES = [404, 500, 502, 503] # 404 및 주요 서버 에러 허용


# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8-sig"

# 1. Selenium 드라이버 이름 지정
SELENIUM_DRIVER_NAME = 'chrome'

# 2. WebDriver 실행 파일 경로 지정 (PATH 환경 변수 사용 시 None)
# ⭐️ (PATH 환경 변수를 사용한 경우)
SELENIUM_DRIVER_EXECUTABLE_PATH = None

# ⭐️ (절대 경로를 문자열로 지정)
# SELENIUM_DRIVER_EXECUTABLE_PATH = 'D:/python/portfolio/donas/resources/drivers/chromedriver/chromedriver_143_0_7499_40_64.exe'


# 4. 브라우저 옵션
SELENIUM_DRIVER_ARGUMENTS = [
    # 일부 시스템에서 발생 가능한 샌드박스 오류 방지 (특히 Linux)
    '--no-sandbox',
    # GPU 사용 불가 환경에서 오류 방지
    '--disable-gpu',
    # 서버나 백그라운드에서 실행할 경우 'headless'를 추가합니다.
    # '--headless',
]