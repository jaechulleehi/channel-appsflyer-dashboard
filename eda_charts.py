"""정적 EDA 차트 생성 — `data-visualization` 스킬 가이드라인 적용.

적용한 원칙 (스킬 체크리스트 기준):
  · 차트 선택은 "무엇을 보여주는가"로 결정 (랭킹→가로막대, 상관→산점도, 다변수→히트맵)
  · 제목이 데이터가 아니라 **인사이트**를 말한다 ("네이버 ROAS 4,406%" > "채널별 ROAS")
  · 색맹 안전 팔레트 (파랑/주황 기준, 빨강↔초록 대비 금지)
  · 색 없이도 읽힌다 — 값 라벨 직접 표기, 선 스타일 구분
  · 막대는 0에서 시작, 알파벳순이 아니라 값순 정렬
  · 차트 정크 제거 (위/오른쪽 축선 삭제)
  · 데이터 출처와 기간을 각 차트에 명시
  · 대체 텍스트(alt text)를 charts/ALT_TEXT.md 로 함께 생성

실행: python3 eda_charts.py  →  charts/*.png
"""

import os

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns

from marketing_data import agg_by, load_and_merge
from palette import BLUE, GREEN, GREY_MUTED as GREY, ORANGE, PURPLE, RED, won

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "charts")
TARGET_ROAS = 800.0  # streamlit_app.py의 기본 목표치와 동일

# --- 스타일 -----------------------------------------------------------------
plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({
    "figure.dpi": 150,
    "font.family": "AppleGothic",   # 한글 라벨용 (macOS 기본 탑재)
    "axes.unicode_minus": False,
    "font.size": 11,
    "axes.titlesize": 15,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "legend.fontsize": 10,
})

def strip_junk(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def source_note(fig, df) -> None:
    d = df["일"].dt.date
    period = f"{d.min()}" if d.min() == d.max() else f"{d.min()} ~ {d.max()}"
    fig.text(
        0.01, 0.01,
        f"출처: *_channel.csv × *_appsflyer.csv 조인 (일·캠페인·그룹·소재·채널) · 기간: {period}",
        fontsize=8, color="#666666",
    )


# =============================================================================
# 1. 채널별 ROAS 랭킹 — 관계: "랭킹" → 가로 막대
# =============================================================================
def chart_channel_roas(df, alts):
    by_ch = agg_by(df, ["채널"]).sort_values("ROAS")
    fig, ax = plt.subplots(figsize=(10, 5))

    # 스토리를 색으로: 목표 달성은 파랑, 미달은 주황 하나만 강조
    colors = [BLUE if v >= TARGET_ROAS else ORANGE for v in by_ch["ROAS"]]
    bars = ax.barh(by_ch["채널"], by_ch["ROAS"], color=colors, height=0.6)

    for bar, (_, r) in zip(bars, by_ch.iterrows()):
        ax.text(bar.get_width() + 60, bar.get_y() + bar.get_height() / 2,
                f"{r['ROAS']:,.0f}%  (비용 {won(r['비용'])})",
                va="center", fontsize=10)

    ax.axvline(TARGET_ROAS, color="#444444", linestyle="--", linewidth=1.3)
    # 막대 사이 빈 공간에 둔다 — 위쪽은 제목과, 아래쪽은 눈금 라벨과 겹친다
    ax.text(TARGET_ROAS * 1.06, len(by_ch) - 1.5, f"목표 {TARGET_ROAS:,.0f}%",
            fontsize=9, color="#444444", va="center")

    best, worst = by_ch.iloc[-1], by_ch.iloc[0]
    ax.set_title(
        f"{best['채널']}가 ROAS {best['ROAS']:,.0f}%로 1위, "
        f"{worst['채널']}는 {worst['ROAS']:,.0f}%로 목표 미달",
        loc="left", pad=14,
    )
    ax.set_xlabel("ROAS (%) — 구매매출 ÷ 비용")
    ax.set_xlim(0, by_ch["ROAS"].max() * 1.28)  # 막대는 항상 0에서 시작
    strip_junk(ax)
    source_note(fig, df)
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    plt.savefig(f"{OUT_DIR}/1_채널_ROAS_랭킹.png", dpi=150, bbox_inches="tight")
    plt.close()

    alts.append(
        f"**1_채널_ROAS_랭킹.png** — 채널 3개의 ROAS 가로 막대. "
        f"{best['채널']} {best['ROAS']:,.0f}%, "
        + ", ".join(f"{r['채널']} {r['ROAS']:,.0f}%" for _, r in by_ch.iloc[:-1][::-1].iterrows())
        + f". 목표선 {TARGET_ROAS:,.0f}% 기준 {(by_ch['ROAS'] < TARGET_ROAS).sum()}개 채널 미달."
    )


# =============================================================================
# 2. 캠페인별 비용 vs ROAS — 관계: "상관(2변수)+3번째 변수" → 버블 차트
# =============================================================================
def chart_budget_quadrant(df, alts):
    by_cmp = agg_by(df, ["채널", "캠페인"])
    by_cmp = by_cmp[by_cmp["비용"] > 0]
    med_cost = by_cmp["비용"].median()

    fig, ax = plt.subplots(figsize=(11, 6.5))
    markers = {"구글": "o", "메타": "s", "네이버": "^"}  # 색 없이도 구분되게 마커 분리
    palette = {"구글": BLUE, "메타": ORANGE, "네이버": GREEN}

    for ch, g in by_cmp.groupby("채널"):
        ax.scatter(g["비용"], g["ROAS"], s=g["구매"] * 6 + 40,
                   color=palette[ch], marker=markers.get(ch, "o"),
                   alpha=0.75, edgecolor="white", linewidth=1.2, label=ch)

    # ROAS가 547%~16,000%로 30배 퍼져 있다. 선형 축이면 하위 캠페인이 전부 바닥에
    # 뭉개져 비교가 불가능해서 로그 축을 쓴다 (비율 지표라 로그가 자연스럽다).
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, p: f"{y:,.0f}%"))

    ax.axvline(med_cost, color=GREY, linestyle="--", linewidth=1.2)
    ax.axhline(TARGET_ROAS, color=GREY, linestyle="--", linewidth=1.2)

    win = by_cmp[(by_cmp["비용"] < med_cost) & (by_cmp["ROAS"] >= TARGET_ROAS)]
    lose = by_cmp[(by_cmp["비용"] >= med_cost) & (by_cmp["ROAS"] < TARGET_ROAS)]

    # 라벨은 액션 대상(증액/감액 후보)에만 — 전부 달면 겹쳐서 못 읽는다.
    for _, r in pd.concat([win, lose]).iterrows():
        ax.annotate(r["캠페인"].replace("_", " "), (r["비용"], r["ROAS"]),
                    textcoords="offset points", xytext=(0, 16),
                    ha="center", fontsize=8.5, color="#333333", fontweight="bold")

    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    ax.text(xmin + (med_cost - xmin) * 0.5, ymax * 0.55, "증액 후보\n비용↓ 효율↑",
            fontsize=9.5, color=GREEN, fontweight="bold", ha="center")
    ax.text(med_cost + (xmax - med_cost) * 0.5, ymin * 1.5, "감액 후보\n비용↑ 효율↓",
            fontsize=9.5, color=RED, fontweight="bold", ha="center")
    ax.text(med_cost, ymax * 0.97, f" 비용 중앙값 {won(med_cost)}",
            fontsize=8.5, color="#666666", va="top")
    ax.text(xmax * 0.995, TARGET_ROAS * 1.08, f"목표 ROAS {TARGET_ROAS:,.0f}% ",
            fontsize=8.5, color="#666666", ha="right")

    ax.set_title(
        f"증액 후보 {len(win)}개 · 감액 후보 {len(lose)}개 — 비용 중앙값 {won(med_cost)} 기준",
        loc="left", pad=14,
    )
    ax.set_xlabel("비용 (원)")
    ax.set_ylabel("ROAS (%) — 로그 스케일")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: won(x)))
    leg = ax.legend(title="채널", loc="lower left", frameon=True, labelspacing=1.1)
    for handle in leg.legend_handles:  # 범례 마커는 고정 크기로 (버블 크기와 혼동 방지)
        handle.set_sizes([70])
    ax.text(0.012, 0.30, "버블 크기 = 구매 건수", transform=ax.transAxes,
            fontsize=8.5, color="#666666")
    strip_junk(ax)
    source_note(fig, df)
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    plt.savefig(f"{OUT_DIR}/2_예산_사분면.png", dpi=150, bbox_inches="tight")
    plt.close()

    alts.append(
        f"**2_예산_사분면.png** — 캠페인 {len(by_cmp)}개의 비용(x) 대비 ROAS(y) 산점도, "
        f"버블 크기는 구매 건수. 비용 중앙값 {won(med_cost)}과 목표 ROAS {TARGET_ROAS:,.0f}%로 "
        f"사분면 분할. 좌상단(증액 후보) {len(win)}개: "
        + (", ".join(win["캠페인"]) if len(win) else "없음") + "."
    )


# =============================================================================
# 3. 그룹 × 소재타입 ROAS — 관계: "다변수 상관" → 히트맵
# =============================================================================
def chart_heatmap(df, alts):
    by = agg_by(df, ["그룹", "소재타입"])
    pivot = by.pivot_table(index="그룹", columns="소재타입", values="ROAS", aggfunc="mean")
    pivot = pivot.reindex(pivot.mean(axis=1).sort_values(ascending=False).index)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    # 순차형 데이터 → 단일 색상 그라데이션 (발산형 아님: 의미 있는 중앙값이 없다)
    sns.heatmap(pivot, annot=True, fmt=",.0f", cmap="YlOrRd", linewidths=0.6,
                linecolor="white", ax=ax,
                cbar_kws={"label": "ROAS (%)"}, annot_kws={"fontsize": 10})

    top = by.loc[by["ROAS"].idxmax()]
    ax.set_title(
        f"{top['그룹']} × {top['소재타입']} 조합이 ROAS {top['ROAS']:,.0f}%로 최고",
        loc="left", pad=14,
    )
    ax.set_xlabel("소재 타입 (파일명 앞부분 — 팀 컨벤션 미확정, 참고용)")
    ax.set_ylabel("타겟 그룹")
    ax.tick_params(axis="y", rotation=0)  # 세로로 눕힌 라벨은 읽기 어렵다
    source_note(fig, df)
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    plt.savefig(f"{OUT_DIR}/3_그룹x소재타입_히트맵.png", dpi=150, bbox_inches="tight")
    plt.close()

    alts.append(
        f"**3_그룹x소재타입_히트맵.png** — 타겟 그룹(행) × 소재 타입(열)별 평균 ROAS 히트맵. "
        f"최고는 {top['그룹']}×{top['소재타입']} {top['ROAS']:,.0f}%, "
        f"빈 칸은 해당 조합의 집행 없음."
    )


# =============================================================================
# 4. 소재별 CTR 랭킹 — 관계: "랭킹" → 가로 막대 (하위 강조)
# =============================================================================
def chart_creative_ctr(df, alts):
    by_cr = agg_by(df, ["채널", "소재"])
    by_cr = by_cr[by_cr["노출"] > 0].sort_values("CTR")
    median_ctr = by_cr["CTR"].median()
    show = by_cr.head(12)  # 하위 12개 = 교체 검토 대상

    fig, ax = plt.subplots(figsize=(10, 6.5))
    labels = [f"{r['소재'].replace('_', ' ')}  ({r['채널']})" for _, r in show.iterrows()]
    # 스토리 강조: 중앙값 미만만 주황, 나머지는 회색
    colors = [ORANGE if v < median_ctr else GREY for v in show["CTR"]]
    bars = ax.barh(labels, show["CTR"], color=colors, height=0.65)

    for bar, (_, r) in zip(bars, show.iterrows()):
        ax.text(bar.get_width() + 0.06, bar.get_y() + bar.get_height() / 2,
                f"{r['CTR']:.2f}%", va="center", fontsize=9)

    ax.axvline(median_ctr, color="#444444", linestyle="--", linewidth=1.3)
    ax.text(median_ctr, len(show) - 0.3, f" 전체 중앙값 {median_ctr:.2f}%",
            fontsize=9, color="#444444")

    below = (by_cr["CTR"] < median_ctr).sum()
    ax.set_title(
        f"소재 {len(by_cr)}개 중 {below}개가 CTR 중앙값 미만 — 하위 12개 교체 검토",
        loc="left", pad=14,
    )
    ax.set_xlabel("CTR (%) — 클릭 ÷ 노출")
    ax.set_xlim(0, show["CTR"].max() * 1.2)
    strip_junk(ax)
    source_note(fig, df)
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    plt.savefig(f"{OUT_DIR}/4_소재_CTR_하위.png", dpi=150, bbox_inches="tight")
    plt.close()

    worst = by_cr.iloc[0]
    alts.append(
        f"**4_소재_CTR_하위.png** — CTR이 낮은 소재 12개 가로 막대. "
        f"최하위는 {worst['소재']}({worst['채널']}) {worst['CTR']:.2f}%. "
        f"전체 {len(by_cr)}개 중 {below}개가 중앙값 {median_ctr:.2f}% 미만."
    )


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_and_merge()
    if df.empty:
        raise SystemExit("CSV를 찾지 못했습니다 (*_channel.csv / *_appsflyer.csv)")

    alts: list[str] = []
    chart_channel_roas(df, alts)
    chart_budget_quadrant(df, alts)
    chart_heatmap(df, alts)
    chart_creative_ctr(df, alts)

    with open(f"{OUT_DIR}/ALT_TEXT.md", "w", encoding="utf-8") as fp:
        fp.write("# 차트 대체 텍스트\n\n스크린리더·공유용 설명입니다.\n\n")
        fp.write("\n\n".join(alts) + "\n")

    n_days = df["일"].dt.date.nunique()
    print(f"차트 4개 생성 완료 → {OUT_DIR}/")
    if n_days < 2:
        print(f"참고: 데이터가 {n_days}일치라 시계열(추이) 차트는 생략했습니다.")


if __name__ == "__main__":
    main()
