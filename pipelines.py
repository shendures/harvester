# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html
# useful for handling different item types with a single interface
import json

class LoadItemPipeline:

    def process_item(self, item, spider):
        # Item을 딕셔너리로 변환
        item_dict = dict(item)

        # GUI가 인식할 수 있도록 JSON 형태로 출력
        print(f"RESULT_INFO:{json.dumps(item_dict["result_info"], ensure_ascii=False)}")
        return item
