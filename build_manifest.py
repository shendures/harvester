"""
고객 배포용 exe에 PyInstaller --add-data로 포함해야 할 파일 목록(매니페스트)을 산출합니다.

request_info.json은 매 실행마다 DB(tb_blueprint, active=True)를 조회해 새로 생성합니다 —
로컬에 미리 준비해두는 파일이 아닙니다. 이번 빌드에 어떤 고객을 포함할지는 DB에서 해당
고객의 active 플래그를 켜두는 것으로 결정합니다(create_request_info.py와 동일한 쿼리·매핑
로직을 재사용 — ACTIVE_BLUEPRINT_QUERY, map_blueprints_to_request_info() 참고).

그 다음 (1) seq_no별 render/login/refine 규칙 파일과 (2) 고정 아이콘 자산
(combine-harvester.ico, icon/)을 찾아 스테이징 폴더에 모으고, build-exe.ps1이 그대로
PyInstaller --add-data 인자로 변환할 수 있는 JSON 파일로 저장합니다.

render/login/refine 파일의 실제 위치는 conf.CustomModuleStorage.resolve_path()를 그대로
재사용합니다 — 앱 런타임과 다른 판별 규칙을 이 스크립트가 따로 갖지 않도록 하기 위함입니다.
"""
import argparse
import json
import os
import shutil
import sys

import db_conn
from conf import CustomModuleStorage
from create_request_info import ACTIVE_BLUEPRINT_QUERY, map_blueprints_to_request_info

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
KINDS = ("render", "login", "refine")


def fail(message: str) -> None:
    print(f"오류: {message}", file=sys.stderr)
    sys.exit(1)


def fetch_active_blueprints() -> tuple:
    """DB(tb_blueprint, active=True)를 조회해 (request_info_list, seq_nos)를 반환합니다.

    DB 접속정보를 못 읽거나 조회 결과가 비면 즉시 중단합니다 — db_conn.read_db_data()는
    연결 실패와 "active인 행이 진짜로 0건"을 구분하지 않고 똑같이 빈 리스트를 반환하므로,
    둘 다 조용히 넘기지 않고 명확한 오류로 멈추는 쪽을 택했습니다.
    """
    try:
        db_env = db_conn.get_params("PostgreSQL")
    except Exception as e:
        fail(
            f"DB 접속 정보를 읽지 못했습니다: {e}\n"
            "이 빌드 머신의 env/database.ini에 [PostgreSQL] 섹션(대소문자 정확히 일치)이 "
            "올바르게 구성되어 있는지 확인하세요."
        )

    print("DB에서 active 블루프린트를 조회하는 중입니다...")
    blueprint_rows = db_conn.read_db_data(db_env, ACTIVE_BLUEPRINT_QUERY)
    if not blueprint_rows:
        fail(
            "DB에서 active=True인 블루프린트를 하나도 가져오지 못했습니다. "
            "DB 연결 실패이거나 실제로 active인 데이터가 0건일 수 있습니다 — "
            "tb_blueprint를 직접 조회해 원인을 확인한 뒤 다시 시도하세요."
        )

    request_info_list = map_blueprints_to_request_info(blueprint_rows)
    seq_nos = []
    for i, blueprint in enumerate(request_info_list):
        if not blueprint.get("seq_no"):
            fail(f"DB에서 가져온 {i}번째 블루프린트에 seq_no가 없습니다.")
        seq_nos.append(blueprint["seq_no"])
    return request_info_list, seq_nos


def write_request_info(request_info_list: list, request_info_path: str) -> None:
    with open(request_info_path, "w", encoding="utf-8") as f:
        json.dump(request_info_list, f, ensure_ascii=False, indent=4)


def validate_seq_no_selection(actual_seq_nos: list, requested_seq_nos: list) -> None:
    """--seq-no로 지정한 값이 모두 DB에서 가져온 active seq_no 목록에 포함되는지
    확인합니다(부분집합 검사). DB의 active 전체를 그대로 쓰는 것 자체가 목적이므로,
    --seq-no는 포함 대상을 고르는 필터가 아니라 "기대한 고객이 실제로 이번 빌드에
    포함됐는지" 검증하는 용도입니다 — 예를 들어 다중 사이트 고객인데 사이트 하나를
    active로 켜는 걸 깜빡한 경우를 빌드 시점에 잡아냅니다."""
    missing = sorted(set(requested_seq_nos) - set(actual_seq_nos))
    if missing:
        fail(
            f"--seq-no로 지정한 값 중 DB의 active 목록에 없는 seq_no가 있습니다: "
            f"{', '.join(missing)} (DB에서 가져온 active seq_no: {', '.join(sorted(actual_seq_nos))}). "
            "해당 고객이 tb_blueprint에서 active=False로 되어 있지 않은지 확인하세요."
        )


def stage_custom_rules(seq_nos: list, staging_dir: str) -> list:
    """seq_no별 render/login/refine 규칙 파일을 staging_dir로 모으고,
    PyInstaller --add-data 항목({"src", "dest"} 딕셔너리) 목록으로 반환합니다."""
    storage = CustomModuleStorage()
    add_data = []
    any_found = False

    for seq_no in seq_nos:
        seq_has_file = False
        for kind in KINDS:
            src = storage.resolve_path(seq_no, kind)
            if not os.path.isfile(src):
                continue
            dest_dir = os.path.join(staging_dir, kind)
            os.makedirs(dest_dir, exist_ok=True)
            staged_path = os.path.join(dest_dir, f"{seq_no}.py")
            shutil.copy2(src, staged_path)
            print(f"포함: {kind}\\{seq_no}.py")
            add_data.append({"src": staged_path, "dest": kind})
            seq_has_file = True
            any_found = True
        if not seq_has_file:
            print(f"경고: seq_no={seq_no}에 해당하는 규칙 파일이 없습니다(render/login/refine 모두).")

    if not any_found:
        print("경고: 어떤 seq_no에도 규칙 파일이 없습니다. 커스텀 규칙 없이 빌드를 계속합니다.")

    return add_data


def build_manifest(request_info_path: str, staging_dir: str, requested_seq_nos: list) -> dict:
    request_info_list, actual_seq_nos = fetch_active_blueprints()
    write_request_info(request_info_list, request_info_path)
    print(
        f"request_info.json을 DB 기준으로 갱신했습니다 (active {len(actual_seq_nos)}건: "
        f"{', '.join(actual_seq_nos)})"
    )

    if requested_seq_nos:
        validate_seq_no_selection(actual_seq_nos, requested_seq_nos)

    # request_info.json 원본과 고정 아이콘 자산(combine-harvester.ico, icon/)은
    # 고객 콘텐츠와 무관하게 항상 포함한다.
    add_data = [
        {"src": request_info_path, "dest": "."},
        {"src": os.path.join(REPO_ROOT, "combine-harvester.ico"), "dest": "."},
        {"src": os.path.join(REPO_ROOT, "icon"), "dest": "icon"},
    ]
    add_data.extend(stage_custom_rules(actual_seq_nos, staging_dir))

    return {"seq_nos": actual_seq_nos, "add_data": add_data}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="고객 배포용 exe에 포함할 --add-data 목록을 산출합니다.")
    parser.add_argument("--out", required=True, help="매니페스트 JSON을 저장할 경로")
    parser.add_argument("--staging-dir", required=True, help="seq_no별 규칙 파일을 모을 스테이징 폴더")
    parser.add_argument(
        "--seq-no", nargs="+", default=[],
        help="이번 빌드에 반드시 포함되어야 할 고객 seq_no 검증용(복수 가능, 생략 시 검증 "
             "생략). DB에서 가져온 active 블루프린트 전체가 항상 포함되며, 이 값은 포함 "
             "대상을 고르는 필터가 아니라 지정한 seq_no가 실제로 active 목록에 있는지 "
             "확인하는 안전장치입니다.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    request_info_path = os.path.join(REPO_ROOT, "request_info.json")

    manifest = build_manifest(request_info_path, args.staging_dir, args.seq_no)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
