import json

class LoadItemPipeline:

    def process_item(self, item, spider):
        item_dict = dict(item)

        # GUI가 인식할 수 있도록 JSON 형태로 출력
        result_info = item_dict["result_info"]
        print(f"RESULT_INFO:{json.dumps(result_info, ensure_ascii=False)}")
        return item
