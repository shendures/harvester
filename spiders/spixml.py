import xmltodict
import engine
import utility
from spiders.base import BaseExtractorSpider


class XmlExtractorSpider(BaseExtractorSpider):

    name = "spider_xml"

    def parse(self, response):
        try:

            if response.status != 200:
                self.logger.warning(f'HTTP Status {response.status} for URL: {response.url}')
                return

            root = self.request_info["conditions"]["items"]["root"]
            _items = {key: value for key, value in self.request_info["conditions"]["items"].items() if key != 'root'}
            xmltojson = xmltodict.parse(response.text)
            result = engine.get_result(self.request_info, utility.get_target(xmltojson, root), _items)

            # 데이터 처리
            loader = engine.set_item_loader(response, self.request_info, result)

            yield loader.load_item()


        except IndexError as e:
            self.logger.error('IndexError : %s at %s', e, response.url)
        except Exception as e:
            self.logger.error('Exception : %s at %s', e, response.url)


