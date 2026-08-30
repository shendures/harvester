# layout/multi/monitor.py

from copy import deepcopy

from ..single import MonitorPageSingle


class MonitorPageMulti(MonitorPageSingle):
    """
    단일과 동일하되 무인 판정에 "배치 실행"을 추가 — 배치 도중 블로킹
    모달이 떠서 다음 순번이 시작되지 못하는 것을 방지합니다.
    (preprocess() 본체는 MonitorPageSingle에서 그대로 상속받고,
    이 클래스는 _SILENT_JOBS 판정 기준값만 오버라이드합니다.)
    """

    _SILENT_JOBS = ("스케줄 실행", "배치 실행")

    def __init__(self, blueprint_info: dict):
        self.blueprint_info = deepcopy(blueprint_info)
        super().__init__()

    def _active_blueprint_info(self) -> dict:
        return self.blueprint_info
