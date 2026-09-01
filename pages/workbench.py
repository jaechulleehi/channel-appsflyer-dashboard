"""워크벤치 — 주 1~2회 앉아서 파고드는 화면.

브리핑이 "정상이면 침묵"이라면 여기는 반대로 다 보여준다.
탭은 METRICS.md의 지표 계층을 따라간다: 퍼널(어디서 새나) → 예산(어디 쓸까)
→ 소재(뭘 갈까) → 추이(언제부터).

추이 탭은 날짜가 2일 미만이면 **탭 자체를 만들지 않는다.** 기존 앱은 "그릴 수 없다"고
경고해놓고 점 3개짜리 빈 차트를 그렸는데, 빈 차트는 없는 것만 못하다.
"""

import altair as alt
import pandas as pd
import streamlit as st

from app_config import (
    COLOR_MUTED,
    DEFAULT_TARGET,
    channel_scale,
    get_data,
    load_targets,
    won,
    won_exact,
)
from marketing_data import agg_by

df = get_data()
if df.empty:
    st.error("`*_channel.csv` / `*_appsflyer.csv`를 찾지 못했습니다.")
    st.stop()

channels = sorted(df["채널"].dropna().unique())
targets = load_targets(channels)
n_days = df["일"].dt.date.nunique()

# --- 사이드바 필터 -----------------------------------------------------------
with st.sidebar:
    st.markdown("### 필터")
    sel_ch = st.multiselect("채널", channels, default=channels)
    groups = sorted(df["그룹"].dropna().unique())
    sel_gr = st.multiselect("타겟 그룹", groups, default=groups)
    if n_days >= 2:
        dmin, dmax = df["일"].min().date(), df["일"].max().date()
        sel_dates = st.slider("기간", min_value=dmin, max_value=dmax, value=(dmin, dmax))
    else:
        sel_dates = None

f = df[df["채널"].isin(sel_ch) & df["그룹"].isin(sel_gr)]
if sel_dates:
    f = f[(f["일"].dt.date >= sel_dates[0]) & (f["일"].dt.date <= sel_dates[1])]

if f.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다. 필터를 넓혀보세요.")
    st.stop()

unmatched = f[f["_merge"] != "both"]

st.markdown("# 워크벤치")
st.caption(f"{len(f)}행 · 채널 {len(sel_ch)}개 · 그룹 {len(sel_gr)}개")

if not unmatched.empty:
    with st.expander(f":material/warning: 조인 안 된 행 {len(unmatched)}개 — 열어서 확인"):
        st.caption(
            "일·캠페인·그룹·소재·채널 조합이 한쪽 파일에만 있는 행입니다. "
            "집계에는 포함돼 있으니, 많으면 원본 CSV의 표기 차이를 확인하세요."
        )
        st.dataframe(
            unmatched[["일", "채널", "캠페인", "그룹", "소재", "_merge"]],
            hide_index=True, use_container_width=True,
        )

TAB_NAMES = ["퍼널", "예산", "소재"] + (["추이"] if n_days >= 2 else [])
tabs = dict(zip(TAB_NAMES, st.tabs(TAB_NAMES)))

# =============================================================================
# 퍼널 — ROAS 분해. METRICS.md의 항등식을 실제로 쓰는 화면.
# =============================================================================
with tabs["퍼널"]:
    st.markdown("### ROAS 분해")
    st.caption("ROAS = AOV × CVR × CTR × (1000 ÷ CPM) — 어느 인자가 무너졌는지 본다")

    overall = agg_by(f.assign(_전체="전체"), ["_전체"]).iloc[0]
    pick = st.selectbox("채널 선택", sel_ch, index=0)
    row = agg_by(f[f["채널"] == pick], ["채널"]).iloc[0]

    def factor(label: str, value: str, metric: str, inverse: bool = False, help_: str = ""):
        base = overall[metric]
        pct = (row[metric] - base) / base * 100 if base else 0
        st.metric(label, value, f"{pct:+.0f}%",
                  delta_color="inverse" if inverse else "normal",
                  help=help_ or f"전체 평균 {base:,.0f} 대비", border=True)

    cols = st.columns(4)
    with cols[0]:
        factor("AOV (객단가)", won_exact(row["AOV"]), "AOV", help_="구매매출 ÷ 구매 · 전체 평균 대비")
    with cols[1]:
        factor("CVR (구매전환)", f"{row['CVR']:.2f}%", "CVR", help_="구매 ÷ 클릭 · 전체 평균 대비")
    with cols[2]:
        factor("CTR", f"{row['CTR']:.2f}%", "CTR", help_="클릭 ÷ 노출 · 전체 평균 대비")
    with cols[3]:
        factor("CPM", won_exact(row["CPM"]), "CPM", inverse=True,
               help_="비용 ÷ 노출 × 1000 · 낮을수록 좋으므로 상승이 빨강")

    st.info(
        f"**{pick}** ROAS **{row['ROAS']:,.0f}%** = "
        f"{won_exact(row['AOV'])} × {row['CVR']:.2f}% × {row['CTR']:.2f}% × (1000 ÷ {won_exact(row['CPM'])})"
        f"  ·  전체 평균 ROAS {overall['ROAS']:,.0f}%"
    )
    st.caption(
        "위 숫자들은 표시용으로 반올림돼 있어 손으로 곱하면 1% 이내로 어긋납니다. "
        "ROAS 값 자체는 원시 합계로 계산한 정확한 값입니다."
    )

    st.markdown("### 퍼널 단계별 전환")
    st.caption("어느 단계에서 이탈이 큰지 — 단계마다 책임 주체가 다르다")

    funnel = agg_by(f, ["채널"])
    stages = funnel.melt(
        id_vars="채널", value_vars=["CTR", "가입률", "가입구매율"],
        var_name="단계", value_name="전환율",
    )
    stage_order = ["CTR", "가입률", "가입구매율"]
    chart = (
        alt.Chart(stages)
        .mark_bar()
        .encode(
            x=alt.X("단계:N", sort=stage_order, title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("전환율:Q", title="전환율 (%)"),
            color=alt.Color("채널:N", scale=channel_scale(), title="채널"),
            xOffset=alt.XOffset("채널:N"),
            tooltip=["채널", "단계", alt.Tooltip("전환율:Q", format=".2f")],
        )
        .properties(height=300)
    )
    st.altair_chart(chart, use_container_width=True)
    st.caption(
        "CTR = 클릭÷노출 (소재 책임) · 가입률 = 가입÷클릭 (랜딩 책임) · "
        "가입구매율 = 구매÷가입 (상품·가격 책임)"
    )

    st.dataframe(
        funnel[["채널", "노출", "클릭", "회원가입", "구매",
                "CTR", "가입률", "가입구매율", "CVR", "CPM", "CPC", "CPS", "CPA", "AOV", "ROAS"]],
        hide_index=True, use_container_width=True,
        column_config={
            c: st.column_config.NumberColumn(format="localized")
            for c in ["노출", "클릭", "회원가입", "구매", "CPM", "CPC", "CPS", "CPA", "AOV"]
        } | {
            c: st.column_config.NumberColumn(f"{c}(%)", format="%.2f")
            for c in ["CTR", "가입률", "가입구매율", "CVR"]
        } | {"ROAS": st.column_config.NumberColumn("ROAS(%)", format="%.0f")},
    )

# =============================================================================
# 예산 — 비용 vs ROAS 사분면
# =============================================================================
with tabs["예산"]:
    by_cmp = agg_by(f, ["채널", "캠페인"])
    by_cmp = by_cmp[by_cmp["비용"] > 0]
    med_cost = by_cmp["비용"].median()
    avg_target = sum(targets.get(c, DEFAULT_TARGET)["roas"] for c in sel_ch) / max(len(sel_ch), 1)

    c1, c2 = st.columns([3, 1])
    with c2:
        log_scale = st.toggle("ROAS 로그 스케일", value=True,
                              help="ROAS가 수백~수만%로 퍼져 있어 선형 축이면 하위 캠페인이 바닥에 뭉칩니다")
    with c1:
        st.caption(
            f"**왼쪽 위**(비용 낮고 ROAS 높음)가 증액 후보, **오른쪽 아래**가 감액 후보입니다. "
            f"점선 = 비용 중앙값 {won(med_cost)} · 목표 ROAS {avg_target:,.0f}%"
        )

    scatter = (
        alt.Chart(by_cmp)
        .mark_circle(opacity=0.8, stroke="white", strokeWidth=1.5)
        .encode(
            x=alt.X("비용:Q", title="비용 (원)"),
            y=alt.Y("ROAS:Q", title="ROAS (%)",
                    scale=alt.Scale(type="log" if log_scale else "linear")),
            size=alt.Size("구매:Q", title="구매 건수", scale=alt.Scale(range=[80, 900])),
            color=alt.Color("채널:N", scale=channel_scale(), title="채널"),
            tooltip=["채널", "캠페인", alt.Tooltip("비용:Q", format=","),
                     alt.Tooltip("ROAS:Q", format=",.0f"),
                     alt.Tooltip("CPA:Q", format=","), "구매"],
        )
        .properties(height=400)
    )
    vline = alt.Chart(pd.DataFrame({"x": [med_cost]})).mark_rule(
        strokeDash=[5, 4], color=COLOR_MUTED).encode(x="x:Q")
    hline = alt.Chart(pd.DataFrame({"y": [avg_target]})).mark_rule(
        strokeDash=[5, 4], color=COLOR_MUTED).encode(y="y:Q")
    st.altair_chart(scatter + vline + hline, use_container_width=True)

    win = by_cmp[(by_cmp["비용"] < med_cost) & (by_cmp["ROAS"] >= avg_target)]
    lose = by_cmp[(by_cmp["비용"] >= med_cost) & (by_cmp["ROAS"] < avg_target)]
    money_cfg = {
        "비용": st.column_config.NumberColumn("비용(원)", format="localized"),
        "CPA": st.column_config.NumberColumn("CPA(원)", format="localized"),
        "ROAS": st.column_config.NumberColumn("ROAS(%)", format="%.0f"),
    }
    left, right = st.columns(2)
    with left:
        st.markdown(f"#### :material/trending_up: 증액 후보 {len(win)}개")
        st.dataframe(win[["채널", "캠페인", "비용", "CPA", "ROAS", "구매"]]
                     .sort_values("ROAS", ascending=False),
                     hide_index=True, use_container_width=True, column_config=money_cfg)
    with right:
        st.markdown(f"#### :material/trending_down: 감액 후보 {len(lose)}개")
        st.dataframe(lose[["채널", "캠페인", "비용", "CPA", "ROAS", "구매"]].sort_values("ROAS"),
                     hide_index=True, use_container_width=True, column_config=money_cfg)

# =============================================================================
# 소재 — CTR 랭킹 + 그룹×타입 히트맵
# =============================================================================
with tabs["소재"]:
    by_cr = agg_by(f, ["채널", "그룹", "소재"])
    by_cr = by_cr[by_cr["노출"] > 0].sort_values("CTR")
    median_ctr = by_cr["CTR"].median()

    low = by_cr[by_cr["CTR"] < median_ctr]
    st.caption(f"소재 {len(by_cr)}개 · CTR 중앙값 {median_ctr:.2f}% · 미만 {len(low)}개")
    only_low = st.toggle("중앙값 미만만 보기", value=False)
    view = low if only_low else by_cr

    st.dataframe(
        view[["채널", "그룹", "소재", "노출", "클릭", "CTR", "CPC", "비용", "구매", "CPA", "ROAS"]],
        hide_index=True, use_container_width=True,
        column_config={
            "노출": st.column_config.NumberColumn(format="localized"),
            "클릭": st.column_config.NumberColumn(format="localized"),
            "CTR": st.column_config.NumberColumn("CTR(%)", format="%.2f"),
            "CPC": st.column_config.NumberColumn("CPC(원)", format="localized"),
            "비용": st.column_config.NumberColumn("비용(원)", format="localized"),
            "CPA": st.column_config.NumberColumn("CPA(원)", format="localized"),
            "ROAS": st.column_config.ProgressColumn(
                "ROAS(%)", format="%.0f", min_value=0, max_value=float(by_cr["ROAS"].max())),
        },
    )

    st.markdown("### 그룹 × 소재타입")
    heat_src = agg_by(f, ["그룹", "소재타입"])
    heat = (
        alt.Chart(heat_src)
        .mark_rect()
        .encode(
            x=alt.X("소재타입:N", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("그룹:N", title=None),
            color=alt.Color("ROAS:Q", scale=alt.Scale(scheme="yelloworangered"),
                            legend=alt.Legend(title="ROAS(%)")),
            tooltip=["그룹", "소재타입", alt.Tooltip("ROAS:Q", format=",.0f"),
                     alt.Tooltip("비용:Q", format=",")],
        )
        .properties(height=260)
    )
    heat_text = heat.mark_text(fontSize=11).encode(
        text=alt.Text("ROAS:Q", format=",.0f"),
        color=alt.condition(alt.datum.ROAS > heat_src["ROAS"].max() * 0.6,
                            alt.value("white"), alt.value("black")),
    )
    st.altair_chart(heat + heat_text, use_container_width=True)
    st.caption("소재타입은 파일명 앞부분 추정값 — 팀 컨벤션 확정 전까지 참고용 (CLAUDE.md 참조)")

# =============================================================================
# 추이 — 날짜가 2일 이상일 때만 탭이 존재한다
# =============================================================================
if "추이" in tabs:
    with tabs["추이"]:
        daily = agg_by(f, ["일", "채널"])
        metric = st.selectbox("지표", ["ROAS", "비용", "CPA", "CTR", "CVR", "구매매출"], index=0)
        line = (
            alt.Chart(daily)
            .mark_line(point=True, strokeWidth=2)
            .encode(
                x=alt.X("일:T", title=None),
                y=alt.Y(f"{metric}:Q", title=metric),
                color=alt.Color("채널:N", scale=channel_scale(), title="채널"),
                strokeDash=alt.StrokeDash("채널:N", title="채널"),  # 색 없이도 구분되게
                tooltip=["일:T", "채널", alt.Tooltip(f"{metric}:Q", format=",.1f")],
            )
            .properties(height=360)
        )
        st.altair_chart(line, use_container_width=True)
        st.dataframe(
            daily[["일", "채널", "비용", "구매", "구매매출", "CTR", "CVR", "CPA", "ROAS"]],
            hide_index=True, use_container_width=True,
        )
