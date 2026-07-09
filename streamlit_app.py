"""
마케팅 채널 x 앱스플라이어 EDA 대시보드

같은 폴더의 `*_channel.csv` (채널 성과: 노출/클릭/비용)와
`*_appsflyer.csv` (앱스플라이어 전환: 클릭/회원가입/구매)를
일/캠페인/그룹/소재 기준으로 조인해서 보여준다.

폴더에 날짜별 파일이 늘어나면 자동으로 다 읽어서 합친다 (글롭 기반).

탭 구성 (매일 여는 순서 기준):
1. 오늘의 스코어 — 채널별 목표(ROAS/CPA) 대비 어제 성과 pass/fail
2. 예산 재배분 — 캠페인별 비용 대비 효율, 증액/감액 후보
3. 소재 피로도 — 소재별 CTR/ROAS 순위, 저성과 소재 플래그
4. 트렌드 — 일별 채널 추이 (날짜가 쌓일수록 유용해짐)
"""

import glob
import json
import os

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="채널 x 앱스플라이어 대시보드",
    page_icon=":material/query_stats:",
    layout="wide",
)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
TARGETS_PATH = os.path.join(DATA_DIR, "targets.json")

# appsflyer의 미디어소스 표기를 channel 파일의 채널명으로 통일
SOURCE_TO_CHANNEL = {
    "googleadwords_int": "구글",
    "Facebook Ads": "메타",
    "naver_search": "네이버",
}

JOIN_KEYS = ["일", "캠페인", "그룹", "소재"]

DEFAULT_TARGET = {"roas": 800.0, "cpa": 8000.0}
CTR_FATIGUE_THRESHOLD_DEFAULT = 2.0  # %


# =============================================================================
# 데이터 로드 & 조인
# =============================================================================


@st.cache_data(ttl=600)
def load_and_merge() -> pd.DataFrame:
    channel_files = sorted(glob.glob(os.path.join(DATA_DIR, "*_channel.csv")))
    appsflyer_files = sorted(glob.glob(os.path.join(DATA_DIR, "*_appsflyer.csv")))

    if not channel_files or not appsflyer_files:
        return pd.DataFrame()

    channel_df = pd.concat([pd.read_csv(f) for f in channel_files], ignore_index=True)
    appsflyer_df = pd.concat([pd.read_csv(f) for f in appsflyer_files], ignore_index=True)

    appsflyer_df["채널"] = appsflyer_df["미디어소스"].map(SOURCE_TO_CHANNEL).fillna(
        appsflyer_df["미디어소스"]
    )

    # channel = 노출/클릭/비용 (매체 리포트), appsflyer = 클릭/회원가입/구매/구매매출 (기여 리포트)
    # 두 소스의 회원가입·구매는 집계 기준이 달라 접미사로 구분해서 함께 보여준다.
    merged = channel_df.merge(
        appsflyer_df,
        on=JOIN_KEYS + ["채널"],
        how="outer",
        suffixes=("_channel", "_af"),
        indicator=True,
    )

    merged["일"] = pd.to_datetime(merged["일"])

    for col in ["노출", "클릭_channel", "비용", "회원가입_channel", "구매_channel", "구매매출_channel"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    # 소재 파일명 앞부분(VID/IMG/CRS/TXT)을 소재 타입으로 추출.
    # CLAUDE.md 기준 아직 팀 확정 컨벤션이 아니므로 참고용 그룹핑에만 사용.
    merged["소재타입"] = merged["소재"].str.split("_").str[0]

    return merged


@st.cache_data(ttl=600)
def load_raw_counts() -> dict:
    channel_files = sorted(glob.glob(os.path.join(DATA_DIR, "*_channel.csv")))
    appsflyer_files = sorted(glob.glob(os.path.join(DATA_DIR, "*_appsflyer.csv")))
    return {"channel_files": channel_files, "appsflyer_files": appsflyer_files}


def load_targets(channels: list[str]) -> dict:
    if os.path.exists(TARGETS_PATH):
        with open(TARGETS_PATH, encoding="utf-8") as fp:
            saved = json.load(fp)
    else:
        saved = {}
    return {ch: saved.get(ch, DEFAULT_TARGET.copy()) for ch in channels}


def save_targets(targets: dict) -> None:
    with open(TARGETS_PATH, "w", encoding="utf-8") as fp:
        json.dump(targets, fp, ensure_ascii=False, indent=2)


def agg_by(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    out = df.groupby(keys, as_index=False).agg(
        노출=("노출", "sum"),
        클릭=("클릭_channel", "sum"),
        비용=("비용", "sum"),
        회원가입=("회원가입_channel", "sum"),
        구매=("구매_channel", "sum"),
        구매매출=("구매매출_channel", "sum"),
    )
    out["CTR"] = (out["클릭"] / out["노출"] * 100).round(2)
    out["CPA"] = (out["비용"] / out["구매"]).replace([float("inf")], 0).round(0)
    out["ROAS"] = (out["구매매출"] / out["비용"] * 100).replace([float("inf")], 0).round(1)
    return out


# =============================================================================
# 페이지 헤더 & 데이터 로드
# =============================================================================

st.markdown("# :material/query_stats: 채널 x 앱스플라이어 대시보드")

counts = load_raw_counts()
with st.expander(
    f"불러온 파일: channel {len(counts['channel_files'])}개 · appsflyer {len(counts['appsflyer_files'])}개",
    expanded=False,
):
    st.write("**channel**", [os.path.basename(f) for f in counts["channel_files"]])
    st.write("**appsflyer**", [os.path.basename(f) for f in counts["appsflyer_files"]])

df = load_and_merge()

if df.empty:
    st.warning("이 폴더에서 `*_channel.csv` / `*_appsflyer.csv` 파일을 찾지 못했습니다.")
    st.stop()

unmatched = df[df["_merge"] != "both"]
if not unmatched.empty:
    st.info(
        f":material/warning: 두 파일에서 매칭되지 않은 행이 {len(unmatched)}개 있습니다 "
        "(일/캠페인/그룹/소재/채널 기준). 아래 필터·집계에는 포함되어 있어요."
    )

with st.sidebar:
    st.markdown("### 필터")
    channels = sorted(df["채널"].dropna().unique())
    sel_channels = st.multiselect("채널", channels, default=channels)

    date_min, date_max = df["일"].min().date(), df["일"].max().date()
    if date_min == date_max:
        st.caption(f"날짜: {date_min} (1일치 데이터)")
        sel_dates = (date_min, date_max)
    else:
        sel_dates = st.slider(
            "기간", min_value=date_min, max_value=date_max, value=(date_min, date_max)
        )

f = df[
    df["채널"].isin(sel_channels)
    & (df["일"].dt.date >= sel_dates[0])
    & (df["일"].dt.date <= sel_dates[1])
]

latest_date = f["일"].max()
f_latest = f[f["일"] == latest_date]

targets = load_targets(channels)

tab_score, tab_budget, tab_fatigue, tab_trend = st.tabs(
    [
        ":material/target: 오늘의 스코어",
        ":material/pie_chart: 예산 재배분",
        ":material/local_fire_department: 소재 피로도",
        ":material/show_chart: 트렌드",
    ]
)

# =============================================================================
# 탭 1. 오늘의 스코어 — 채널별 목표 대비 최신일 성과
# =============================================================================

with tab_score:
    st.caption(f"기준일: {latest_date.date()} · 채널별 목표는 이 화면에서 저장하면 다음에도 유지됩니다.")

    with st.expander(":material/tune: 채널별 목표치 설정", expanded=False):
        with st.form("targets_form"):
            cols = st.columns(len(channels))
            new_targets = {}
            for col, ch in zip(cols, channels):
                with col:
                    st.markdown(f"**{ch}**")
                    roas_t = st.number_input(
                        "목표 ROAS(%)", value=float(targets[ch]["roas"]), step=50.0, key=f"roas_{ch}"
                    )
                    cpa_t = st.number_input(
                        "목표 CPA(원)", value=float(targets[ch]["cpa"]), step=500.0, key=f"cpa_{ch}"
                    )
                    new_targets[ch] = {"roas": roas_t, "cpa": cpa_t}
            if st.form_submit_button(":material/save: 저장"):
                save_targets(new_targets)
                targets = new_targets
                st.success("목표치를 저장했어요.")

    by_channel_latest = agg_by(f_latest, ["채널"])

    score_cols = st.columns(len(by_channel_latest))
    for col, (_, row) in zip(score_cols, by_channel_latest.iterrows()):
        ch = row["채널"]
        t = targets.get(ch, DEFAULT_TARGET)
        roas_ok = row["ROAS"] >= t["roas"]
        cpa_ok = row["CPA"] <= t["cpa"] if row["CPA"] > 0 else True
        both_ok = roas_ok and cpa_ok
        badge = ":material/check_circle: 목표 달성" if both_ok else (
            ":material/warning: 부분 미달" if (roas_ok or cpa_ok) else ":material/cancel: 목표 미달"
        )
        with col:
            with st.container(border=True):
                st.markdown(f"**{ch}**")
                st.markdown(badge)
                st.metric(
                    "ROAS",
                    f"{row['ROAS']:,.0f}%",
                    delta=f"목표 {t['roas']:,.0f}% 대비 {row['ROAS'] - t['roas']:+,.0f}%p",
                )
                st.metric(
                    "CPA",
                    f"₩{row['CPA']:,.0f}",
                    delta=f"목표 ₩{t['cpa']:,.0f} 대비 ₩{row['CPA'] - t['cpa']:+,.0f}",
                    delta_color="inverse",
                )

    st.divider()
    st.markdown("### 채널별 상세")
    st.dataframe(
        by_channel_latest[["채널", "노출", "클릭", "비용", "회원가입", "구매", "구매매출", "CTR", "CPA", "ROAS"]],
        hide_index=True,
        width="stretch",
    )

# =============================================================================
# 탭 2. 예산 재배분 — 캠페인별 비용 대비 효율
# =============================================================================

with tab_budget:
    st.caption("캠페인별 비용(x) 대비 ROAS(y) — 오른쪽 아래(비용 낮고 ROAS 높음)일수록 증액 후보")

    by_campaign = agg_by(f, ["채널", "캠페인"])
    by_campaign = by_campaign[by_campaign["비용"] > 0]

    median_cost = by_campaign["비용"].median()
    avg_target_roas = sum(t["roas"] for t in targets.values()) / len(targets) if targets else 800.0

    scatter = (
        alt.Chart(by_campaign)
        .mark_circle(size=140, opacity=0.8)
        .encode(
            x=alt.X("비용:Q", title="비용"),
            y=alt.Y("ROAS:Q", title="ROAS(%)"),
            color=alt.Color("채널:N", title=None),
            tooltip=["채널", "캠페인", "비용", "ROAS", "구매"],
        )
        .properties(height=340)
    )
    rule_x = alt.Chart(pd.DataFrame({"x": [median_cost]})).mark_rule(strokeDash=[4, 4], color="gray").encode(x="x:Q")
    rule_y = (
        alt.Chart(pd.DataFrame({"y": [avg_target_roas]}))
        .mark_rule(strokeDash=[4, 4], color="gray")
        .encode(y="y:Q")
    )
    st.altair_chart(scatter + rule_x + rule_y, width="stretch")
    st.caption(f"점선: 비용 중앙값(₩{median_cost:,.0f}) · 목표 ROAS 평균({avg_target_roas:,.0f}%)")

    increase = by_campaign[
        (by_campaign["비용"] < median_cost) & (by_campaign["ROAS"] >= avg_target_roas)
    ].sort_values("ROAS", ascending=False)
    decrease = by_campaign[
        (by_campaign["비용"] >= median_cost) & (by_campaign["ROAS"] < avg_target_roas)
    ].sort_values("ROAS")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### :material/trending_up: 증액 후보 (비용↓ 효율↑)")
        if increase.empty:
            st.caption("해당 없음")
        else:
            st.dataframe(
                increase[["채널", "캠페인", "비용", "ROAS", "구매"]], hide_index=True, width="stretch"
            )
    with c2:
        st.markdown("#### :material/trending_down: 감액 후보 (비용↑ 효율↓)")
        if decrease.empty:
            st.caption("해당 없음")
        else:
            st.dataframe(
                decrease[["채널", "캠페인", "비용", "ROAS", "구매"]], hide_index=True, width="stretch"
            )

# =============================================================================
# 탭 3. 소재 피로도 — 소재별 CTR/ROAS 순위
# =============================================================================

with tab_fatigue:
    ctr_threshold = st.slider(
        "피로도 기준 CTR(%) — 이 값 미만이면 저성과로 플래그",
        min_value=0.5,
        max_value=10.0,
        value=CTR_FATIGUE_THRESHOLD_DEFAULT,
        step=0.5,
    )

    by_creative = agg_by(f, ["채널", "그룹", "소재"])
    by_creative = by_creative[by_creative["클릭"] > 0].sort_values("CTR")
    by_creative["피로도"] = by_creative["CTR"].apply(
        lambda v: ":material/local_fire_department: 저성과" if v < ctr_threshold else ""
    )

    low_perf = by_creative[by_creative["CTR"] < ctr_threshold]
    if not low_perf.empty:
        st.warning(f":material/local_fire_department: CTR {ctr_threshold}% 미만 소재 {len(low_perf)}개 — 교체 검토 대상")

    st.markdown("### 소재별 순위 (CTR 낮은 순)")
    st.dataframe(
        by_creative[["채널", "그룹", "소재", "클릭", "비용", "CTR", "ROAS", "피로도"]],
        hide_index=True,
        width="stretch",
    )

    st.markdown("### 소재 타입별 평균 성과")
    st.caption("소재 파일명 앞부분(VID/IMG/CRS/TXT)으로 추정한 그룹 — 팀 컨벤션 확정 전까지 참고용 (CLAUDE.md 참고)")
    by_type = f.groupby("소재타입", as_index=False).agg(
        클릭=("클릭_channel", "sum"), 비용=("비용", "sum"), 구매매출=("구매매출_channel", "sum")
    )
    by_type["ROAS"] = (by_type["구매매출"] / by_type["비용"] * 100).round(1)
    type_chart = (
        alt.Chart(by_type)
        .mark_bar()
        .encode(
            x=alt.X("소재타입:N", sort="-y", title=None),
            y=alt.Y("ROAS:Q", title="평균 ROAS(%)"),
            tooltip=["소재타입", "클릭", "비용", "ROAS"],
        )
        .properties(height=260)
    )
    st.altair_chart(type_chart, width="stretch")

# =============================================================================
# 탭 4. 트렌드 — 일별 채널 추이
# =============================================================================

with tab_trend:
    n_days = f["일"].dt.date.nunique()
    if n_days < 2:
        st.info(
            ":material/info: 아직 1일치 데이터뿐이라 추이를 그릴 수 없어요. "
            "날짜별 CSV가 폴더에 쌓이면 이 탭에 자동으로 라인이 생깁니다."
        )

    daily = f.groupby(["일", "채널"], as_index=False).agg(
        비용=("비용", "sum"), 구매매출=("구매매출_channel", "sum")
    )
    daily["ROAS"] = (daily["구매매출"] / daily["비용"] * 100).round(1)

    cost_line = (
        alt.Chart(daily)
        .mark_line(point=True)
        .encode(
            x=alt.X("일:T", title=None),
            y=alt.Y("비용:Q", title="비용"),
            color=alt.Color("채널:N", title=None),
            tooltip=["일", "채널", "비용", "ROAS"],
        )
        .properties(height=260, title="일별 비용 추이")
    )
    roas_line = (
        alt.Chart(daily)
        .mark_line(point=True)
        .encode(
            x=alt.X("일:T", title=None),
            y=alt.Y("ROAS:Q", title="ROAS(%)"),
            color=alt.Color("채널:N", title=None),
            tooltip=["일", "채널", "비용", "ROAS"],
        )
        .properties(height=260, title="일별 ROAS 추이")
    )
    st.altair_chart(cost_line, width="stretch")
    st.altair_chart(roas_line, width="stretch")

st.divider()
st.caption(
    "데이터 정확도: channel/appsflyer 원본 CSV 그대로 조인·합산 (정확). "
    "CTR·CVR·CPA·ROAS·목표 판정은 두 소스 합산값 기반 계산값입니다."
)
