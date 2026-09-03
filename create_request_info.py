import db_conn
import os
import json
import utility
import customized_settings

# build_manifest.py도 이 쿼리로 request_info.json을 생성하므로 여기 한 곳에서만 관리한다.
ACTIVE_BLUEPRINT_QUERY = (
    "select seq_no, titles, spiders, urls, callback_urls, conditions, needs_cleaning "
    "from tb_blueprint where active = True"
)

def map_blueprints_to_request_info(blueprint_list):
    """
    DB row(리스트 내 딕셔너리)를 request_info.json 스키마로 매핑합니다.
    파일을 쓰지 않는 순수 함수 — build_manifest.py 등 다른 스크립트가 재사용합니다.
    """
    request_info_setting_list = []

    for request_info in blueprint_list:
        # 1. 기본 설정 딕셔너리 로드
        settings = customized_settings.get_request_settings()

        # 2. DB에서 가져온 데이터 매핑 (딕셔너리 키 접근)
        settings["seq_no"] = request_info.get("seq_no")
        settings["title"] = request_info.get("titles")  # DB 컬럼명이 titles인 경우
        settings["url"] = request_info.get("urls")
        settings["callback_url"] = request_info.get("callback_urls")
        settings["conditions"] = utility.transform_to_json(request_info.get("conditions"))

        settings["spiders"] = request_info.get("spiders")
        # settings["auth"] = request_info.get("auth")
        settings["needs_cleaning"] = request_info.get("needs_cleaning")
        request_info_setting_list.append(settings)

    return request_info_setting_list

def create_request_info_setting_file(blueprint_list, save_file_nm):
    """
    수집 정보 설정 파일을 생성합니다.
    blueprint_list: 리스트 내 딕셔너리 형태의 데이터
    """
    request_info_setting_list = map_blueprints_to_request_info(blueprint_list)

    save_path_local = os.path.join(os.getcwd(), f"{save_file_nm}.json")
    with open(save_path_local, "w", encoding="utf-8") as f:
        json.dump(request_info_setting_list, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":

    db_env = db_conn.get_params("PostgreSQL")
    blueprint_list = db_conn.read_db_data(db_env, ACTIVE_BLUEPRINT_QUERY)
    # 데이터가 리스트 형태인지 확인 후 진행
    if isinstance(blueprint_list, list):
        request_info_setting_list = create_request_info_setting_file(blueprint_list, "request_info")
    else:
        print("❌ 데이터 로드 실패: 반환된 데이터가 리스트 형태가 아닙니다.")