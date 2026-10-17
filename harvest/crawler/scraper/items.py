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

        super().add_value(field_name, value, *processors, **kw)
