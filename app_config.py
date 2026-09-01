"""앱 전역 설정 — 색·목표치·포맷터·캐시된 데이터 접근.

이 파일이 생긴 이유: 채널 색과 목표치가 streamlit_app.py / viz_streamlit.py /
eda_charts.py 세 곳에 각각 하드코딩돼 있어서 같은 채널이 화면마다 다른 색으로 나왔다.
여기 한 곳만 고치면 전부 따라오게 한다.

marketing_data.py는 streamlit 비의존으로 유지한다(정적 차트 스크립트가 쓰므로).
streamlit에 의존하는 캐시 래퍼는 이 파일에 둔다.
"""

import json
import os

import altair as alt
import pandas as pd
import streamlit as st

from marketing_data import DATA_DIR, duplicate_key_report, load_and_merge
from palette import (  # noqa: F401  — 화면 모듈들이 여기서 가져다 쓴다
    CHANNEL_COLOR,
    COLOR_BAD,
    COLOR_GOOD,
    COLOR_MUTED,
    DEFAULT_TARGET,
    won,
    won_exact,
)

TARGETS_PATH = os.path.join(DATA_DIR, "targets.json")

# 색·금액 포맷은 palette.py가 단일 소스다 (streamlit 비의존 → 정적 차트도 같은 값을 쓴다).
# 여기서는 재수출만 한다.

# 이상 신호 임계값
SPIKE_THRESHOLD = 0.30  # 전일 대비 ±30% 이상 변동이면 신호


def channel_scale() -> alt.Scale:
    """Altair 색 스케일. 데이터에 없는 채널이 섞여도 순서가 안 흔들리게 domain 고정."""
    return alt.Scale(domain=list(CHANNEL_COLOR), range=list(CHANNEL_COLOR.values()))


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


@st.cache_data(ttl=600)
def get_data() -> pd.DataFrame:
    """두 페이지가 공유하는 캐시. 같은 함수 객체를 import하므로 캐시도 공유된다."""
    return load_and_merge()


@st.cache_data(ttl=600)
def get_duplicate_report() -> dict:
    return duplicate_key_report()


def load_targets(channels: list[str]) -> dict:
    saved = {}
    if os.path.exists(TARGETS_PATH):
        with open(TARGETS_PATH, encoding="utf-8") as fp:
            saved = json.load(fp)
    return {ch: saved.get(ch, DEFAULT_TARGET.copy()) for ch in channels}


def save_targets(targets: dict) -> None:
    with open(TARGETS_PATH, "w", encoding="utf-8") as fp:
        json.dump(targets, fp, ensure_ascii=False, indent=2)
