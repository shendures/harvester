"""
고객 배포용 exe에 PyInstaller --add-data로 포함해야 할 파일 목록(매니페스트)을 산출합니다.

request_info.json의 내용을 근거로 (1) seq_no별 render/login/refine 규칙 파일과
(2) 고정 아이콘 자산(combine-harvester.ico, icon/)을 찾아 스테이징 폴더에 모으고,
build-exe.ps1이 그대로 PyInstaller --add-data 인자로 변환할 수 있는 JSON 파일로 저장합니다.

render/login/refine 파일의 실제 위치는 conf.CustomModuleStorage.resolve_path()를 그대로
재사용합니다 — 앱 런타임과 다른 판별 규칙을 이 스크립트가 따로 갖지 않도록 하기 위함입니다.

request_info.json 자체는 conf.BlueprintStorage를 쓰지 않고 이 스크립트가 직접 검증합니다.
BlueprintStorage는 파일이 없거나 깨져도 조용히 기본값으로 폴백하는 런타임 전용 설계라
(conf.py BlueprintStorage._load() 참고), 실패를 숨기지 않고 즉시 중단해야 하는 빌드
스크립트의 요구와 맞지 않기 때문입니다.
"""
import argparse
import json
import os
import shutil
import sys

from conf import CustomModuleStorage

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
KINDS = ("render", "login", "refine")


def fail(message: str) -> None:
    print(f"오류: {message}", file=sys.stderr)
    sys.exit(1)


def load_seq_nos(request_info_path: str) -> list:
    """request_info.json을 읽어 담긴 블루프린트들의 seq_no 목록을 반환합니다.
    파일이 없거나, JSON이 아니거나, 블루프린트에 seq_no가 없으면 즉시 중단합니다."""
    if not os.path.isfile(request_info_path):
        fail(f"request_info.json이 없습니다: {request_info_path}")

    with open(request_info_path, "r", encoding="utf-8") as f:
        raw_text = f.read()
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as e:
        fail(f"request_info.json 파싱 실패: {e}")

    blueprints = raw if isinstance(raw, list) else [raw]
    if not blueprints:
        fail("request_info.json에 블루프린트가 하나도 없습니다.")

    seq_nos = []
    for i, blueprint in enumerate(blueprints):
        if not isinstance(blueprint, dict) or not blueprint.get("seq_no"):
            fail(f"request_info.json의 {i}번째 블루프린트에 seq_no가 없습니다.")
        seq_nos.append(blueprint["seq_no"])
    return seq_nos


def validate_seq_no_selection(actual_seq_nos: list, requested_seq_nos: list) -> None:
    """--seq-no로 지정한 값이 request_info.json의 실제 seq_no 집합과 정확히 일치하는지
    확인합니다 — 잘못된 고객 조합으로 패키징하는 실수를 빌드 시점에 막기 위함입니다."""
    actual = sorted(set(actual_seq_nos))
    requested = sorted(set(requested_seq_nos))
    if actual != requested:
        fail(
            f"request_info.json의 seq_no 목록({', '.join(actual)})이 "
            f"--seq-no({', '.join(requested)})와 다릅니다. "
            "다른 고객 파일이 섞여 들어갈 위험이 있어 중단합니다."
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
    actual_seq_nos = load_seq_nos(request_info_path)
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
        help="배포할 고객의 seq_no(생략 시 request_info.json에서 자동 감지)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    request_info_path = os.path.join(REPO_ROOT, "request_info.json")

    manifest = build_manifest(request_info_path, args.staging_dir, args.seq_no)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
