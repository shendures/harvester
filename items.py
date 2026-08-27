# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy
from scrapy.loader import ItemLoader
from itemloaders.processors import TakeFirst


class DonasItem(scrapy.Item):
    """동적으로 필드를 추가할 수 있는 Item 클래스"""

    def __setitem__(self, key, value):
        """필드가 없으면 자동으로 생성"""
        if key not in self.fields:
            self.fields[key] = scrapy.Field()
        super().__setitem__(key, value)

class DonasItemLoader(ItemLoader):
    """동적 Item과 함께 사용하는 ItemLoader"""

    default_item_class = DonasItem

    # 기본적으로 리스트의 첫 번째 값만 반환
    default_output_processor = TakeFirst()

    def add_value(self, field_name, value, *processors, **kw):
        """
        필드가 없으면 자동으로 생성하고 값을 추가

        Args:
            field_name: 필드명 (컬럼명)
            value: 추가할 값
        """
        if field_name not in self.item.fields:
            self.item.fields[field_name] = scrapy.Field(output_processor=TakeFirst())
        else:
            self.item.fields[field_name] = scrapy.Field()

        # 부모 클래스의 add_value 호출
        super().add_value(field_name, value, *processors, **kw)