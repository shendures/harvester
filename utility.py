import sys
import os
import re
import itertools
from typing import Optional, Any
from datetime import datetime as dt, timedelta
import calendar
import json

def resource_path():
    '''
    실행 프로그램이 바라보고 있는 root 경로
    '''
    if hasattr(sys, '_MEIPASS'):
        # 빌드된 .exe 실행 환경
        return sys._MEIPASS
    else:
        # 일반 .py 실행 환경
        return os.path.dirname(os.path.abspath(__file__))


def get_isin_dict(data_dict: dict, key_list: list):
    return {k: v for k, v in data_dict.items() if k in key_list}


def transform_to_json(_variable):
    # 1. 데이터 타입이 딕셔너리(dict)인 경우
    if isinstance(_variable, dict):
        print("데이터가 이미 dict 형태입니다. (Pass)")
        return _variable

    # 2. 데이터 타입이 텍스트(str)인 경우
    elif isinstance(_variable, str):
        try:
            converted_data = json.loads(_variable)
            return converted_data
        except json.JSONDecodeError:
            print("오류: 입력된 텍스트가 올바른 JSON 형식이 아닙니다.")
            return None

    # 3. 그 외의 데이터 타입인 경우
    else:
        print(f"지원하지 않는 타입입니다: {type(_variable)}")
        return _variable

def update_empty_value(value):
    # 값이 공백일 경우 None으로 반환
    if value == '':
        return None
    return value


def to_forward_slash(value):
    # 역슬래쉬(\)를 슬래쉬(/)로 변경
    return value.replace("\\", "/")


def generate_combined_urls(url_template):
    """
    URL 템플릿에서 '${page:start:step:end}' (페이지네이션) 패턴과
    '${item1,item2,...}' (목록 확장) 패턴을 모두 처리하여 URL 리스트를 생성합니다.

    Args:
        url_template (str): 패턴이 포함된 URL 문자열.

    Returns:
        list: 생성된 URL 문자열 리스트.
    """
    # 1. 페이지네이션 패턴 분석 및 URL 템플릿 처리

    # 패턴: ${page:시작 수:증가 숫자:끝 수} - 음수 포함
    page_pattern = r'(\$\{page:(-?\d+):(-?\d+):(-?\d+)\})'
    page_match = re.search(page_pattern, url_template)

    page_urls = []

    if page_match:
        # 패턴 문자열 전체: ${page:1:1:10}
        full_pattern_str = page_match.group(1)
        start = int(page_match.group(2))
        step = int(page_match.group(3))
        end = int(page_match.group(4))

        # 유효성 검사 (음수 step 처리 포함)
        if step == 0:
            print("❌ 오류: step 값은 0일 수 없습니다.")
            return []
        if (step > 0 and start > end) or (step < 0 and start < end):
            print(f"⚠️ 경고: 페이지 범위({start} to {end}, step {step})가 유효하지 않습니다.")
            return []

        # range의 stop 값 조정
        stop = end + 1 if step > 0 else end - 1

        # 페이지 리스트 생성 및 템플릿 문자열 대체
        for page_num in range(start, stop, step):
            new_url = url_template.replace(full_pattern_str, str(page_num))
            page_urls.append(new_url)

    # 패턴이 없으면 원본 템플릿 하나만 리스트에 담아 다음 단계로 전달
    if not page_urls:
        page_urls = [url_template]

    # 2. 목록 확장 패턴 분석 및 최종 URL 생성

    # 패턴: ${특정 문자1, 특정 문자2, ...}
    # 그룹 1: ${...} 전체, 그룹 2: 내부 콤마로 구분된 문자열 (서울,인천)
    list_pattern = r'(\$\{keywords:([^{}]+?)\})'

    final_urls = []

    # page_urls에 담긴 모든 URL 템플릿을 순회
    for current_url_template in page_urls:

        # 현재 템플릿에서 모든 목록 확장 패턴을 찾음
        list_matches = re.findall(list_pattern, current_url_template)

        if not list_matches:
            # 목록 확장 패턴이 없으면 최종 리스트에 추가
            final_urls.append(current_url_template)
            continue

        # 목록 확장 패턴의 모든 조합을 생성하기 위한 리스트 초기화
        substitution_data = []

        # 각 패턴 (${서울,인천})을 순회하며 치환할 문자열 리스트를 준비
        for full_match, items_str in list_matches:
            # [('서울,인천', '서울,인천'), ...]
            items_list = [item.strip() for item in items_str.split(',')]
            substitution_data.append((full_match, items_list))

        # 모든 목록 패턴의 값들 (예: ['서울', '인천'])에 대해 데카르트 곱 생성
        # (예: [('서울',), ('인천',)])
        value_combinations = itertools.product(*(item[1] for item in substitution_data))

        # 조합된 값들을 사용하여 최종 URL 생성
        for combo in value_combinations:
            temp_url = current_url_template

            # 패턴과 값의 조합을 사용하여 URL 치환
            for i in range(len(substitution_data)):
                # substitution_data[i][0]은 패턴 문자열 (${서울,인천})
                # combo[i]는 치환할 값 (서울 또는 인천)
                temp_url = temp_url.replace(substitution_data[i][0], combo[i], 1)

            final_urls.append(temp_url)

    return final_urls


def get_all_nested_keys(data: dict):
    """
    딕셔너리(및 중첩된 딕셔너리)의 모든 레벨에 있는 키를 재귀적으로 수집하여 리스트로 반환합니다.

    Args:
        data (dict): 처리할 딕셔너리.

    Returns:
        list: 딕셔너리의 모든 키를 포함하는 리스트.
    """
    keys_list = []

    if isinstance(data, dict):
        # 현재 레벨의 모든 키를 가져옵니다.
        for key, value in data.items():
            # 1. 현재 키를 리스트에 추가합니다.
            keys_list.append(key)

            # 2. 값(value)이 다시 딕셔너리이면, 재귀적으로 이 함수를 호출합니다.
            if isinstance(value, dict):
                # 중첩 딕셔너리에서 반환된 키들을 현재 리스트에 확장(extend)합니다.
                keys_list.extend(get_all_nested_keys(value))

    return list(set(keys_list))


def get_target(data: Any, target: str) -> Optional[Any]:
    """
    중첩된 dict/list 구조에서 target 키의 값을 찾아 반환.

    - target에 점(.)이 포함되어 있으면 경로 탐색(예: "b.a")을 수행하여 맨 마지막 값을 반환합니다.
    - target에 점(.)이 없으면, 재귀적으로 구조를 탐색하여 target 키의 첫 번째 일치 값을 반환합니다.
    """

    # 1. 경로 탐색 로직 (target에 점(.)이 포함된 경우)
    if isinstance(data, dict) and isinstance(target, str) and '.' in target:
        keys = target.split('.')
        current_node = data

        try:
            for key in keys:
                # 현재 노드가 딕셔너리가 아니면 경로 탐색 중단
                if not isinstance(current_node, dict):
                    return None

                # 다음 단계로 이동
                current_node = current_node[key]

            # 최종적으로 찾은 값 반환
            return current_node
        except KeyError:
            # 경로 중 어느 하나라도 키가 없는 경우
            return None
        except Exception:
            # 기타 예외 처리 (예: None에 접근 시도 등)
            return None

    # 2. 원본 재귀 탐색 로직 (target이 단일 키인 경우)
    results = []

    def _search(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == target:
                    results.append(value)
                _search(value)  # 계속해서 value 내부를 탐색
        elif isinstance(node, list):
            for item in node:
                _search(item)

    _search(data)

    # 원본 함수의 반환 방식: 첫 번째 결과만 반환 (리스트가 비어있으면 None 반환하여 IndexError 방지)
    return results[0] if results else None


def _calculate_next_run(schedule_info):
    """
    표준 datetime 라이브러리만을 사용하여 정확한 차기 실행 시간을 계산합니다.
    """
    now = dt.now()

    # 요일 인덱스 사전
    day_of_week_dict = {"월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3, "금요일": 4, "토요일": 5, "일요일": 6}

    # 1. 사용자가 설정한 시간 파싱 (HH:MM:SS)
    s_time_str = schedule_info.get('time', '00:00:00')
    try:
        t_obj = dt.strptime(s_time_str, '%H:%M:%S').time()
    except ValueError:
        t_obj = dt.strptime("00:00:00", '%H:%M:%S').time()

    # 2. 기준 시간을 오늘 날짜와 결합
    next_run = dt.combine(now.date(), t_obj)

    # 3. 주기 유형에 따른 상세 계산
    s_type = schedule_info.get('schedule_type')

    if s_type == 'daily':
        if next_run <= now:
            next_run += timedelta(days=1)

    elif s_type == 'weekly':
        # target_day: 0(월) ~ 6(일)
        target_day = int(day_of_week_dict.get(schedule_info["day_of_week"], 0))

        # 현재 요일과 목표 요일의 차이 계산
        days_ahead = target_day - now.weekday()

        # 오늘이 목표 요일인데 시간이 지났거나, 목표 요일이 이미 지난 경우
        if days_ahead < 0 or (days_ahead == 0 and next_run <= now):
            days_ahead += 7

        next_run = next_run + timedelta(days=days_ahead)

    elif s_type == 'monthly':
        target_day_val = int(schedule_info.get('day_of_month', 1))

        # 이번 달의 해당 날짜로 설정
        # 주의: 31일 설정 시 이번 달이 30일까지면 에러 발생 가능 -> 해당 월의 최대값으로 클램핑
        last_day_of_month = calendar.monthrange(next_run.year, next_run.month)[1]
        actual_day = min(target_day_val, last_day_of_month)
        next_run = next_run.replace(day=actual_day)

        if next_run <= now:
            # 다음 달 계산 (연도가 넘어가는 경우 포함)
            new_month = next_run.month + 1
            new_year = next_run.year
            if new_month > 12:
                new_month = 1
                new_year += 1

            # 다음 달의 마지막 날 확인 후 날짜 재설정
            last_day_next_month = calendar.monthrange(new_year, new_month)[1]
            actual_day = min(target_day_val, last_day_next_month)
            next_run = next_run.replace(year=new_year, month=new_month, day=actual_day)

    elif s_type == 'specific':
        spec_date_str = schedule_info.get('date', now.strftime('%Y-%m-%d'))
        next_run = dt.strptime(f"{spec_date_str} {s_time_str}", '%Y-%m-%d %H:%M:%S')

    return next_run


def check_lap_time(start_time):
    # 끝난 시간
    end_time = dt.now()

    # 걸린 시간
    lap = end_time - start_time
    round_lap = re.sub(r"(\.).*", "", str(lap))  # micro_seconds 제거

    print("\n")
    print("=" * 35)
    print(f'start time : {start_time.strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'End time : {end_time.strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'lap time : {round_lap}')
    print("=" * 35)
    print("\n")


