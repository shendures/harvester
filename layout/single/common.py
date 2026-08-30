# layout/single/common.py
# Single 전용 전역(blueprint/request_info)과, Single/Multi 결과 컬럼 산출
# 중복(구 layout_single.py:530-534/889-893 ≈ layout_multi.py:41-56)을
# 통합하기 위한 ActiveBlueprintMixin.

from conf import BlueprintStorage
from ..common import result_columns_from_blueprint

blueprint = BlueprintStorage()  # 수집 정보 클래스
request_info = blueprint.read()  # 수집 정보


class ActiveBlueprintMixin:
    """DashboardPageSingle/MonitorPageSingle이 공유하는 "활성 블루프린트" 훅.

    Single은 전역 request_info를 그대로 반환하는 기본 구현을 쓰고,
    layout.multi의 DashboardPageMulti/MonitorPageMulti는 이 훅 하나만
    (self.blueprint_info를 반환하도록) 오버라이드한다 — 그러면
    _get_result_columns()는 별도 오버라이드 없이 상속만으로 재사용된다.
    """

    def _active_blueprint_info(self) -> dict:
        return request_info

    def _get_result_columns(self):
        return result_columns_from_blueprint(self._active_blueprint_info())
