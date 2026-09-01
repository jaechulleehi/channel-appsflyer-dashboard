"""마케팅 성과 대시보드 — 진입점.

역할별로 화면을 나눈다:
  · 브리핑   — 매일 아침 30초. 이상 없으면 한 줄로 끝난다.
  · 워크벤치 — 주 1~2회 앉아서 파고든다. 필터·드릴다운·교차분석.

두 요구가 정반대(전자는 "안 보여주기"가 미덕, 후자는 "다 보여주기"가 미덕)라
한 화면에 섞지 않는다.

pages/ 자동 감지 대신 st.navigation을 쓴다 — 파일명이 곧 메뉴명이 되지 않아서
한글 라벨·순서·아이콘을 명시적으로 제어할 수 있다.

실행: python3 -m streamlit run streamlit_app.py --server.port 8501
"""

import os

import streamlit as st

from marketing_data import DATA_DIR

st.set_page_config(
    page_title="마케팅 성과 대시보드",
    page_icon=":material/query_stats:",
    layout="wide",
)

pages = [
    st.Page("pages/briefing.py", title="브리핑",
            icon=":material/notifications_active:", default=True),
    st.Page("pages/workbench.py", title="워크벤치", icon=":material/science:"),
]

with st.sidebar:
    st.markdown("## :material/query_stats: 성과 대시보드")

nav = st.navigation(pages)

# 파일 목록은 매일 볼 정보가 아니라 문제 생겼을 때 볼 정보다 — 사이드바 맨 아래로 보낸다.
with st.sidebar:
    st.divider()
    channel_files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith("_channel.csv"))
    af_files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith("_appsflyer.csv"))
    with st.expander(f"불러온 파일 {len(channel_files) + len(af_files)}개"):
        st.caption("**channel**")
        st.code("\n".join(channel_files) or "없음", language=None)
        st.caption("**appsflyer**")
        st.code("\n".join(af_files) or "없음", language=None)
        st.caption(f"경로: `{DATA_DIR}`")

nav.run()
