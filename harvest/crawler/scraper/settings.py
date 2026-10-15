BOT_NAME = "harvester"

SPIDER_MODULES = ["harvest.crawler.scraper.spiders"]
NEWSPIDER_MODULE = "harvest.crawler.scraper.spiders"

ADDONS = {}

ROBOTSTXT_OBEY = True

CONCURRENT_REQUESTS = 32
CONCURRENT_REQUESTS_PER_DOMAIN = 8
RANDOMIZE_DOWNLOAD_DELAY = True

COOKIES_ENABLED = True
COOKIES_DEBUG = False # True로 설정하면 디버깅이 편하나, 성능 저하 및 보안 문제 발생 가능

# Disable Telnet Console (enabled by default) — 이 앱은 콘솔 접속 기능을 쓰지
# 않는데 켜져 있으면 수집마다 로컬 포트(6023 등)를 열어 불필요한 Windows
# 방화벽 허용 알림을 유발함
TELNETCONSOLE_ENABLED = False

SPIDER_MIDDLEWARES = {
    # delay_until이 걸린 요청을 지연 재스케줄 (process_spider_output 훅이므로 SPIDER_MIDDLEWARES에 등록)
    'harvest.crawler.scraper.middlewares.DelaySchedulerMiddleware': 500,
}

DOWNLOADER_MIDDLEWARES = {

    # 1. IP 관리 및 프록시 할당 (가장 바깥)
    "harvest.crawler.scraper.middlewares.RateLimitedProxyMiddleware": None,  # 100

    # 2. Scrapy 기본 프록시 적용 로직
    "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": 110,

    'harvest.crawler.scraper.middlewares.LatencyTrackingMiddleware': 743,
}

ITEM_PIPELINES = {
   "harvest.crawler.scraper.pipelines.LoadItemPipeline": 100
}

HTTPERROR_ALLOW_ALL = True

FEED_EXPORT_ENCODING = "utf-8-sig"
