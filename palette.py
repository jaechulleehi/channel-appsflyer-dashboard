"""색·금액 포맷의 단일 소스. **의존성 없음**(streamlit도 pandas도 안 씀).

화면(app_config.py)과 정적 차트(eda_charts.py)가 둘 다 여기서 가져간다.
이 파일이 없던 시절엔 채널 색이 세 곳에 하드코딩돼 있어서 같은 채널이
화면마다 다른 색으로 나왔다. 여기만 고치면 전부 따라온다.
"""

# 색맹 안전 팔레트 — 파랑/주황이 1순위 쌍. 빨강↔초록 조합은 쓰지 않는다
# (남성 8%가 적록색약이라 그 둘만으로는 구분이 안 된다).
CHANNEL_COLOR = {"구글": "#4C72B0", "메타": "#DD8452", "네이버": "#55A868"}

BLUE, ORANGE, GREEN, RED, PURPLE = "#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3"
GREY_MUTED = "#B0B0B0"
COLOR_GOOD, COLOR_BAD, COLOR_MUTED = GREEN, RED, GREY_MUTED

DEFAULT_TARGET = {"roas": 800.0, "cpa": 8000.0}


def won(v: float) -> str:
    """**합계 금액**을 한국식 단위로 축약. 비용·매출처럼 자릿수가 큰 값 전용.

    단가(CPA/CPC/CPM/AOV)에는 쓰지 말 것 — ₩10,995가 "₩1만"이 돼서
    목표 ₩8,000과 비교가 안 된다. 그런 값은 won_exact()를 쓴다.
    """
    if abs(v) >= 1e8:
        return f"₩{v / 1e8:.1f}억"
    if abs(v) >= 1e4:
        return f"₩{v / 1e4:,.0f}만"
    return f"₩{v:,.0f}"


def won_exact(v: float) -> str:
    """**단가**를 자릿수 그대로. 목표치와 눈으로 비교해야 하므로 축약하지 않는다."""
    return f"₩{v:,.0f}"
