# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html
# useful for handling different item types with a single interface
from itemadapter import ItemAdapter

import csv
import os
# from pymongo import MongoClient
import json
import utility

class DonasPipeline:
    def process_item(self, item, spider):
        return item

class LoadItemPipeline:

    def process_item(self, item, spider):
        # Item을 딕셔너리로 변환
        item_dict = dict(item)

        # GUI가 인식할 수 있도록 JSON 형태로 출력
        print(f"RESULT_INFO:{json.dumps(item_dict["result_info"], ensure_ascii=False)}")
        return item

class CsvExportPipeline:

    def __init__(self):
        # 모든 CSV 파일 핸들(File Handle)을 저장할 딕셔너리
        self.files = {}
        # 모든 CSV writer 객체를 저장할 딕셔너리
        self.writers = {}
        # 현재 작업 디렉토리를 가져옵니다.
        self.base_path = utility.resource_path()
        # 데이터가 저장될 하위 디렉토리 이름
        self.output_dir = 'extract_data'

    def set_default_savedir(self):
        # 기본값 저장 경로
        output_full_path = os.path.join(self.base_path, self.output_dir)
        if not os.path.exists(output_full_path):
            os.mkdir(output_full_path)

    # 저장할 파일에 쓰기할 데이터 정보
    def create_write_info(self, item_dict):

        data = item_dict.get('data', item_dict)

        if item_dict["collect_info"]["gubun"] == "local":
            # 데이터 저장할 폴더 생성
            self.set_default_savedir()
            file_name = item_dict.get('extract_names')
            output_full_path = f"{self.base_path}/{self.output_dir}/{file_name}"
            delimiter = ","

        elif item_dict["collect_info"]["gubun"] == "deploy":
            file_path = item_dict["collect_info"]["extract"]["file"]["file_path"]
            file_name = item_dict["collect_info"]["extract"]["file"]["file_name"]
            output_full_path = file_path + "/" + file_name
            delimiter = item_dict["collect_info"]["extract"]["file"]["file_delimiter"]

        return {"output_full_path": output_full_path, "file_name":file_name, "delimiter": delimiter, "data": data, "columns":list(data.keys()) }

    def _initialize_file_writer(self, file_write_info):
        """특정 파일 키에 대한 파일 핸들과 CSV Writer를 초기화합니다."""
        try:
            # 파일을 엽니다. 이 파일 핸들을 self.files에 저장하여 close_spider에서 닫습니다.
            file_handle = open(f"{file_write_info["output_full_path"]}.csv", 'w', newline='',
                               encoding='utf-8-sig')  # utf-8-sig는 엑셀에서 한글 깨짐 방지에 유용합니다.

            self.files[file_write_info["file_name"]] = file_handle

            # CSV DictWriter를 생성하고 헤더를 작성합니다.
            writer = csv.DictWriter(file_handle, fieldnames=file_write_info["columns"], delimiter=file_write_info["delimiter"])
            writer.writeheader()
            self.writers[file_write_info["file_name"]] = writer

        except Exception as e:
            # 파일 열기/작성 중 오류 발생 시 로깅
            print(f"❌ Error initializing CSV for {file_write_info["file_name"]}: {e}")

    def process_item(self, item, spider):

        item_dict = dict(item)

        file_write_info = self.create_write_info(item_dict)

        # # 1. 파일명을 결정할 키를 가져옵니다.
        # # 이 키가 Item에 없으면 파일을 만들 수 없으므로 경고를 남기고 아이템을 반환합니다.
        # # file_name_key = item_dict.get('clct_name')
        # if not file_write_info["file_name"]:
        #     spider.logger.warning("❌ Item에 'file_name' 필드가 없어 CSV 파일명을 결정할 수 없습니다.")
        #     return item

        # 2. 파일 핸들과 Writer가 초기화되었는지 확인합니다.
        # 해당 'file_name_key'에 대한 파일이 아직 열리지 않았다면 초기화합니다.
        if file_write_info["file_name"] not in self.writers:
            self._initialize_file_writer(file_write_info)

        # 3. 데이터 적재
        # 실제 CSV에 작성할 데이터 (data 필드)
        # data_to_write = item_dict.get('data', item_dict)  # 'data' 필드가 없으면 전체 item을 사용

        # 해당 파일의 writer를 사용하여 데이터를 작성합니다.
        self.writers[file_write_info["file_name"]].writerow(file_write_info["data"])

        return item

    def close_spider(self, spider):
        # 스파이더가 종료될 때, 열려 있는 모든 파일 핸들을 닫습니다.
        for file_handle in self.files.values():
            file_handle.close()

        spider.logger.info(f"✅ CSV Export Pipeline: {len(self.files)}개의 파일이 성공적으로 닫혔습니다.")


class MongoDBPipeline:
    """
    MongoDB에 Item을 저장하는 Pipeline
    """

    def __init__(self, mongo_uri, mongo_db):
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db
        self.client = None
        self.db = None

    @classmethod
    def from_crawler(cls, crawler):
        """MongoDB 설정을 가져옴"""
        mongo_config = db_conn.get_params("mongodb")

        # db_info["extract"]["db"]

        return cls(
            mongo_uri=mongo_config['host'] + ':' + mongo_config['port'],
            mongo_db=mongo_config['database']
        )

    def open_spider(self, spider):
        """Spider가 시작될 때 MongoDB 연결"""
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[self.mongo_db]
            # spider.logger.info("✅ MongoDB 연결 성공")
        except Exception as e:
            spider.logger.error(f"❌ MongoDB 연결 실패: {e}")
            self.client = None

    def process_item(self, item, spider):
        """Item을 MongoDB에 저장"""

        # 연결 확인
        if not self.client:
            spider.logger.warning("⚠️ MongoDB 연결이 유효하지 않아 Item을 건너뜁니다.")
            return item

        try:
            # ItemAdapter를 사용하여 Item을 dict로 변환
            adapter = ItemAdapter(item)
            item_dict = dict(adapter)

            # 1. clct_names 추출
            if "user_settings" in item_dict.keys():
                clct_name = item_dict["user_settings"]["extract"]["db"]["save_data_nm"]
            else:
                clct_name = item_dict.get('clct_name')

            if not clct_name:
                spider.logger.error("❌ clct_name 필드가 Item에 없습니다. 저장 건너뜁니다.")
                return item

            # 3. 빈 딕셔너리 체크
            if not item_dict:
                spider.logger.warning(f"⚠️ '{clct_name}' 컬렉션에 저장할 데이터가 없습니다.")
                return item

            # 4. MongoDB에 저장
            collection = self.db[clct_name]

            result = collection.insert_one(item_dict["data"])

            spider.logger.info(f"✅ '{clct_name}' 컬렉션에 데이터 저장 완료 (ID: {result.inserted_id})")

        except Exception as e:
            spider.logger.error(f"❌ MongoDB 저장 실패: {e}")
            spider.logger.error(f"   Item 내용: {item}")

        return item

    def close_spider(self, spider):
        """Spider가 종료될 때 MongoDB 연결 종료"""
        if self.client:
            self.client.close()
            spider.logger.info("✅ MongoDB 연결 해제")





# class MongoDBPipeline:
#     """
#     MongoDB에 Item을 저장하는 Pipeline
#     """
#     def process_item(self, item, spider):
#         """Item을 MongoDB에 저장"""
#
#         # 수집 정보
#         collect_info = spider.collect_info
#
#         # 로컬용
#         if collect_info["gubun"] == "local":
#             mongo_config = collect_info["extract"]
#
#         # 배포용
#         elif collect_info["gubun"] == "deploy":
#             mongo_config = collect_info["extract"]["db"]
#
#         mongo_uri = mongo_config['host'] + ':' + mongo_config['port']
#         mongo_db = mongo_config['database']
#
#         try:
#             self.client = MongoClient(mongo_uri)
#             self.db = self.client[mongo_db]
#             spider.logger.info("✅ MongoDB 연결 성공")
#         except Exception as e:
#             spider.logger.error(f"❌ MongoDB 연결 실패: {e}")
#             self.client = None
#
#
#         try:
#             # ItemAdapter를 사용하여 Item을 dict로 변환
#             adapter = ItemAdapter(item)
#             item_dict = dict(adapter)
#
#
#             # 저장할 collection명
#             clct_name = mongo_config["save_data_nm"]
#
#             if not clct_name:
#                 spider.logger.error("❌ clct_name 필드가 Item에 없습니다. 저장 건너뜁니다.")
#                 return item
#
#             # 빈 딕셔너리 체크
#             if not item_dict:
#                 spider.logger.warning(f"⚠️ '{clct_name}' 컬렉션에 저장할 데이터가 없습니다.")
#                 return item
#
#             # MongoDB에 저장
#             collection = self.db[clct_name]
#
#             result = collection.insert_one(item_dict["data"])
#
#             spider.logger.info(f"✅ '{clct_name}' 컬렉션에 데이터 저장 완료 (ID: {result.inserted_id})")
#
#         except Exception as e:
#             spider.logger.error(f"❌ MongoDB 저장 실패: {e}")
#             spider.logger.error(f"   Item 내용: {item}")
#
#         return item
#
#     def close_spider(self, spider):
#         """Spider가 종료될 때 MongoDB 연결 종료"""
#         if self.client:
#             self.client.close()
#             spider.logger.info("✅ MongoDB 연결 해제")






##########################################################################################################################

