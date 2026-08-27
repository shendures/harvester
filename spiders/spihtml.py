import engine
from spiders.base import BaseExtractorSpider

class HtmlExtractorSpider(BaseExtractorSpider):

    name = "spider_html"

    def parse(self, response):
        try:
            if response.status != 200:
                self.logger.warning(f'HTTP Status {response.status} for URL: {response.url}')
                return

            root = self.request_info["conditions"]["items"]["root"]
            _items = {key: value for key, value in self.request_info["conditions"]["items"].items() if key != 'root'}

            # 데이터 생성
            selectors = response.xpath(root)
            result = engine.get_result(self.request_info, selectors, _items)

            # 데이터 처리
            loader = engine.set_item_loader(response, self.request_info, result)

            yield loader.load_item()

        except IndexError as e:
            self.logger.error('IndexError : %s at %s', e, response.url)
        except Exception as e:
            self.logger.error('Exception : %s at %s', e, response.url)


