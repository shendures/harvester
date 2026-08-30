# layout/multi/toolbar.py

from conf import BlueprintStorage
from ..single import GlobalToolbarSingle


class GlobalToolbarMulti(GlobalToolbarSingle):
    """
    단일과 동일한 구성이지만, method 라벨을 인스턴스 속성으로 보관해
    activate_blueprint()로 활성 블루프린트 전환 시 갱신할 수 있게 합니다.
    (_build() 본체는 GlobalToolbarSingle에서 그대로 상속받고, 이 클래스는
    라벨/URL 값 계산과 라벨 위젯 후처리 훅 2개만 오버라이드합니다 —
    구 layout_multi.py의 _build() 42줄 전체 복붙 오버라이드를 대체합니다.)
    """

    def _toolbar_display_info(self):
        info = BlueprintStorage().read()
        return (info.get("conditions") or {}).get("method") or "", info.get("url") or ""

    def _configure_method_label(self, label):
        # 2개 이상 선택 시 빈 값으로 바뀌는데, 폭을 고정해두지 않으면 라벨이
        # 줄어들면서 옆 URL 입력창이 왼쪽으로 밀려온다 — 최장 메서드
        # 문자열("OPTIONS") 기준으로 폭을 고정해 빈 값이어도 자리를 유지한다.
        label.setFixedWidth(60)

    def activate_blueprint(self, blueprint_info: dict) -> None:
        """활성 블루프린트 전환 시 상단 method 라벨/URL 입력창만 갱신합니다."""
        self._method_label.setText(
            (blueprint_info.get("conditions") or {}).get("method") or "")
        self.url_input.setText(blueprint_info.get("url") or "")
        self.url_input.setCursorPosition(0)
