from PyQt6.QtCore import QStandardPaths

def set_desktop_dir():

    try:
        desktop_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        if not desktop_dir:
            default_file_path = './output/'
        else:
            default_file_path_slash = desktop_dir.replace('\\', '/')
            if not default_file_path_slash.endswith('/'):
                default_file_path = default_file_path_slash + '/'
            else:
                default_file_path = default_file_path_slash
    except Exception:
        default_file_path = './output/'

    return default_file_path

def get_request_settings():
    return {
                'seq_no': None,
                'title': None,
                'url':None,
                'callback_url': None,
                'conditions': None,
                'spiders': None,
            }

def get_task_settings():
    return {
        'delay': 0.5,
        'threads': 8,
        'timeout': 10,
        'retry': 3
    }

def get_render_safety_limits():
    return {
        'max_threads': 2,
        'min_delay': 1.0,
    }

def get_output_settings():
    return {
            'extract': {
                        'file': {
                            'enabled': True,
                            'file_path': QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation),
                            'file_name': 'untitled0',
                            'file_format': 'CSV',
                            'file_encoding': 'UTF-8 BOM',
                            'file_delimiter': ',',
                            'is_open_save_path': True
                        },
                        'db': {
                            'enabled': False,
                            'db_env': "MySQL",
                            'host': "localhost",
                            'port': "3306",
                            'database': None,
                            'schema': None,
                            'user': None,
                            'password': None,
                            'save_data_nm': None
                        },
                        'auto_save': False,
                        'auto_save_source': 'raw'
                    }
            }

def get_schedule_settings():

    task_info = {}
    task_info.update(get_task_settings())
    task_info.update(get_output_settings())

    task_info["schedule"] = {
                                'enabled': False,
                                'schedule_nm': None,
                                'interval': None,  # 매일(daily), 주간(weekly), 월간(monthly), 일일(specific)
                                'run_at': None,
                                'exec_str': None,
                                'schedule_save_type': None
                            }
    return task_info

def set_ip_settings(request_info):

    if "proxy" not in request_info.keys() or not request_info["proxy"]["enabled"]:
        return None

    # GUI 프록시 테이블 행(dict: host/port/protocol/enabled)을
    # Scrapy request.meta['proxy']가 요구하는 URL 문자열로 변환
    ip_list = []
    for row in request_info["proxy"]["ip_list"]:
        if isinstance(row, dict):
            if not row.get("enabled", True):
                continue
            protocol = str(row.get("protocol", "http")).lower()
            ip_list.append(f"{protocol}://{row['host']}:{row['port']}")
        else:
            ip_list.append(row)

    proxy_req_info = {}
    proxy_req_info["ip_list"] = ip_list
    proxy_req_info["allow_ip_cnts"] = request_info["proxy"]["allow_ip_cnts"]
    # 이전에 저장된 schedule_info에는 rotate 키가 없을 수 있어 기본값(True=무작위)으로 보완
    proxy_req_info["rotate"] = request_info["proxy"].get("rotate", True)

    return proxy_req_info


def set_downloader_middlewares(request_info):

    downloader_middlewares = {}

    if "proxy" in request_info.keys():

        if request_info["proxy"]["enabled"]:
            downloader_middlewares["scraper.middlewares.RateLimitedProxyMiddleware"] = 100

        elif not request_info["proxy"]["enabled"]:
            downloader_middlewares["scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware"] = 110

    else:
        downloader_middlewares["scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware"] = 110

    if request_info["user_agent"]:
        downloader_middlewares["scraper.middlewares.RandomUserAgentMiddleware"] = 400
    else:
        downloader_middlewares["scraper.middlewares.RandomUserAgentMiddleware"] = None

    if request_info["cookie"]:
        downloader_middlewares["scraper.middlewares.RandomCookieMiddleware"] = 650
    else:
        downloader_middlewares["scraper.middlewares.RandomCookieMiddleware"] = None

    downloader_middlewares["scraper.middlewares.LatencyTrackingMiddleware"] = 743

    return downloader_middlewares


