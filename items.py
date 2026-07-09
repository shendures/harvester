# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy
from scrapy.loader import ItemLoader
from itemloaders.processors import TakeFirst, Identity


class DefaultItem(scrapy.Item):
    # define the fields for your item here like:
    # name = scrapy.Field()
    pass


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


class StoreItem(scrapy.Item):
    # 딕셔너리 객체들을 담을 리스트 필드
    # Identity()를 사용하여 입력된 딕셔너리를 가공하지 않고(문자열 변환 방지)
    # 그대로 리스트에 쌓이도록 설정합니다.
    data = scrapy.Field(
        input_processor=Identity(),
        output_processor=Identity()
    )


class DonasBatchItem(scrapy.Item):
    # 모니터링 탭용 (한 번만 전송됨)
    response = scrapy.Field()
    collect_info = scrapy.Field()

    # 데이터 테이블용 (딕셔너리 리스트)
    # Identity()를 사용하여 리스트 구조를 유지합니다. ( scrapy.Field()만 했을 경우 이중 리스트가 되는 것을 방지하기 위함. )
    # 만약 result가 [{'a': 1}, {'b': 2}]인 리스트라면 ItemLoader에 그냥 넣었을 때 내부적으로 [[{'a': 1}, {'b': 2}]] 처럼 이중 리스트가 되버림
    data_list = scrapy.Field(
        input_processor=Identity(),
        output_processor=Identity()
    )