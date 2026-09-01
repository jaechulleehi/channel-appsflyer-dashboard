"""브리핑 — 아침 30초용.

설계 원칙: **정상이면 침묵한다.** 이상이 없으면 한 줄로 끝나야 30초가 성립한다.
탐색 기능은 일부러 넣지 않는다. 그건 워크벤치의 일이다.

델타 표기 규칙: st.metric의 delta는 문자열의 **첫 글자**로 방향을 판단한다.
"목표 800% 대비 -253%p"처럼 앞에 텍스트가 붙으면 부호를 못 읽어서 미달인데도
초록 위쪽 화살표가 나온다(기존 앱의 버그). 반드시 `+`/`-`로 시작시키고,
설명은 help=로 뺀다. CPA처럼 낮을수록 좋은 지표는 delta_color="inverse".
"""

import datetime as dt

import pandas as pd
import streamlit as st

from app_config import (
    DEFAULT_TARGET,
    SPIKE_THRESHOLD,
    get_data,
    get_duplicate_report,
    load_targets,
    save_targets,
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

dates = sorted(df["일"].dropna().unique())
latest, prev = dates[-1], (dates[-2] if len(dates) >= 2 else None)
n_days = len(dates)

today_df = df[df["일"] == latest]
prev_df = df[df["일"] == prev] if prev is not None else None


# =============================================================================
# 이상 신호 — 데이터가 쌓일수록 규칙이 자동으로 강해진다
# =============================================================================
def build_alerts() -> list[dict]:
    alerts: list[dict] = []
    by_ch = agg_by(today_df, ["채널"])

    # 1. 목표 대비 (1일치만 있어도 판정 가능)
    for _, r in by_ch.iterrows():
        t = targets.get(r["채널"], DEFAULT_TARGET)
        if r["ROAS"] < t["roas"]:
            alerts.append({
                "level": "높음",
                "title": f"{r['채널']} ROAS {r['ROAS']:,.0f}%",
                "detail": f"목표 {t['roas']:,.0f}% 대비 {r['ROAS'] - t['roas']:+,.0f}%p · 비용 {won(r['비용'])}",
            })
        if r["구매"] > 0 and r["CPA"] > t["cpa"]:
            alerts.append({
                "level": "보통",
                "title": f"{r['채널']} CPA {won_exact(r['CPA'])}",
                "detail": f"목표 {won_exact(t['cpa'])} 대비 {r['CPA'] - t['cpa']:+,.0f}원",
            })

    # 2. 돈은 쓰는데 구매가 0 — 날짜 수와 무관하게 항상 검사
    by_cmp = agg_by(today_df, ["채널", "캠페인"])
    for _, r in by_cmp[(by_cmp["비용"] > 0) & (by_cmp["구매"] == 0)].iterrows():
        alerts.append({
            "level": "높음",
            "title": f"{r['캠페인']} 구매 0건",
            "detail": f"비용 {won(r['비용'])} 소진 · 클릭 {r['클릭']:,.0f}회",
        })

    # 3. 전일 대비 급변 (2일 이상 쌓였을 때만)
    if prev_df is not None:
        cur, old = agg_by(today_df, ["채널"]), agg_by(prev_df, ["채널"])
        cmp_df = cur.merge(old, on="채널", suffixes=("", "_전일"))
        for _, r in cmp_df.iterrows():
            for metric, label, worse_when in (("ROAS", "ROAS", "down"), ("비용", "비용", "up")):
                base = r[f"{metric}_전일"]
                if not base:
                    continue
                change = (r[metric] - base) / base
                bad = change <= -SPIKE_THRESHOLD if worse_when == "down" else change >= SPIKE_THRESHOLD
                if bad:
                    alerts.append({
                        "level": "높음" if worse_when == "down" else "보통",
                        "title": f"{r['채널']} {label} 전일 대비 {change * 100:+,.0f}%",
                        "detail": f"{base:,.0f} → {r[metric]:,.0f}",
                    })

    # 4. N일 연속 목표 미달 (7일 이상 쌓였을 때만 — 그 전엔 표본이 부족)
    if n_days >= 7:
        daily = agg_by(df, ["일", "채널"])
        for ch in channels:
            hist = daily[daily["채널"] == ch].sort_values("일", ascending=False)
            t = targets.get(ch, DEFAULT_TARGET)
            streak = 0
            for _, r in hist.iterrows():
                if r["ROAS"] < t["roas"]:
                    streak += 1
                else:
                    break
            if streak >= 3:
                alerts.append({
                    "level": "높음",
                    "title": f"{ch} {streak}일 연속 목표 미달",
                    "detail": f"목표 ROAS {t['roas']:,.0f}%",
                })

    order = {"높음": 0, "보통": 1}
    return sorted(alerts, key=lambda a: order[a["level"]])


# =============================================================================
# 헤더 — 기준일과 데이터 신선도
# =============================================================================
latest_date = pd.Timestamp(latest).date()
gap = (dt.date.today() - latest_date).days
freshness = "최신" if gap <= 1 else f"오늘로부터 {gap}일 전"

st.markdown(f"# 브리핑 · {latest_date}")
st.caption(f"{freshness} · 데이터 {n_days}일치 · {len(today_df)}행")

dup = get_duplicate_report()
if dup:
    st.error(
        f":material/error: **중복 키 발견** — "
        + ", ".join(f"{k} {len(v)}행" for k, v in dup.items())
        + ". 조인이 부풀려져 **아래 숫자를 믿으면 안 됩니다.** "
        "같은 날짜·캠페인·그룹·소재 조합이 두 번 들어와 있습니다."
    )
    for label, rows in dup.items():
        with st.expander(f"{label} 중복 행 보기"):
            st.dataframe(rows, hide_index=True, use_container_width=True)

# =============================================================================
# 전체 KPI — 기존 앱에 없던 것. 채널별만 있어서 "오늘 전체 어땠나"를 못 봤다.
# =============================================================================
cur = agg_by(today_df, ["일"]).iloc[0]
old = agg_by(prev_df, ["일"]).iloc[0] if prev_df is not None else None


def delta_of(metric: str, unit: str = "%") -> str | None:
    """전일 대비 변화율. 반드시 +/- 로 시작하는 문자열을 반환한다(§모듈 docstring)."""
    if old is None or not old[metric]:
        return None
    change = (cur[metric] - old[metric]) / old[metric] * 100
    return f"{change:+.1f}{unit}"


kpis = st.columns(5, border=True)
with kpis[0]:
    st.metric("비용", won(cur["비용"]), delta_of("비용"),
              delta_color="off", help="전일 대비 증감률")
with kpis[1]:
    st.metric("구매매출", won(cur["구매매출"]), delta_of("구매매출"),
              help="전일 대비 증감률")
with kpis[2]:
    st.metric("ROAS", f"{cur['ROAS']:,.0f}%", delta_of("ROAS"),
              help="구매매출 ÷ 비용 · 전일 대비 증감률")
with kpis[3]:
    st.metric("CPA", won_exact(cur["CPA"]), delta_of("CPA"), delta_color="inverse",
              help="비용 ÷ 구매 · 낮을수록 좋으므로 상승이 빨강")
with kpis[4]:
    st.metric("CTR", f"{cur['CTR']:.2f}%", delta_of("CTR"),
              help="클릭 ÷ 노출 · 전일 대비 증감률")

if prev_df is None:
    st.caption(
        ":material/info: 데이터가 1일치라 전일 대비 증감을 계산할 수 없습니다. "
        "다음 날 CSV가 들어오면 위 카드에 자동으로 표시됩니다."
    )

st.divider()

# =============================================================================
# 이상 신호 — 없으면 한 줄로 끝난다
# =============================================================================
alerts = build_alerts()

if not alerts:
    st.success(
        f":material/check_circle: **이상 없음** — 채널 {len(channels)}개 모두 목표 달성, "
        "구매 0건 캠페인 없음."
    )
else:
    high = sum(1 for a in alerts if a["level"] == "높음")
    st.markdown(f"### 이상 신호 {len(alerts)}건" + (f" · 긴급 {high}건" if high else ""))
    for a in alerts:
        icon = ":material/error:" if a["level"] == "높음" else ":material/warning:"
        box = st.error if a["level"] == "높음" else st.warning
        box(f"{icon} **{a['title']}** — {a['detail']}")

st.divider()

# =============================================================================
# 채널 요약 — 이상 신호의 맥락. 표 하나로 끝낸다.
# =============================================================================
st.markdown("### 채널 요약")
by_ch = agg_by(today_df, ["채널"]).sort_values("ROAS", ascending=False)
by_ch["목표 ROAS"] = by_ch["채널"].map(lambda c: targets.get(c, DEFAULT_TARGET)["roas"])
by_ch["달성"] = by_ch.apply(
    lambda r: "✅ 달성" if r["ROAS"] >= r["목표 ROAS"] else "❌ 미달", axis=1
)

st.dataframe(
    by_ch[["채널", "달성", "ROAS", "목표 ROAS", "CPA", "CTR", "비용", "구매", "구매매출"]],
    hide_index=True,
    use_container_width=True,
    column_config={
        "달성": st.column_config.TextColumn("목표", help="ROAS가 목표 이상인지"),
        "ROAS": st.column_config.NumberColumn("ROAS(%)", format="%.0f"),
        "목표 ROAS": st.column_config.NumberColumn("목표(%)", format="%.0f"),
        "CPA": st.column_config.NumberColumn("CPA(원)", format="localized"),
        "CTR": st.column_config.NumberColumn("CTR(%)", format="%.2f"),
        "비용": st.column_config.NumberColumn("비용(원)", format="localized"),
        "구매": st.column_config.NumberColumn(format="localized"),
        "구매매출": st.column_config.NumberColumn("구매매출(원)", format="localized"),
    },
)

with st.expander(":material/tune: 채널별 목표치 설정"):
    with st.form("targets_form"):
        cols = st.columns(len(channels))
        new_targets = {}
        for col, ch in zip(cols, channels):
            with col:
                st.markdown(f"**{ch}**")
                new_targets[ch] = {
                    "roas": st.number_input("목표 ROAS(%)", value=float(targets[ch]["roas"]),
                                            step=50.0, key=f"roas_{ch}"),
                    "cpa": st.number_input("목표 CPA(원)", value=float(targets[ch]["cpa"]),
                                           step=500.0, key=f"cpa_{ch}"),
                }
        if st.form_submit_button(":material/save: 저장"):
            save_targets(new_targets)
            st.cache_data.clear()
            st.rerun()

st.caption("더 파고들려면 왼쪽에서 **워크벤치**로 이동하세요.")
