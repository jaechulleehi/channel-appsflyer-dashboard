"""채널 x 앱스플라이어 데이터 로더 (streamlit 비의존).

`streamlit_app.py`의 load_and_merge와 같은 규칙을 쓰되, streamlit 없이도 돌아가게
분리했다. 정적 차트 스크립트(eda_charts.py)와 시각화 앱(viz_streamlit.py)이 공유한다.

조인 키: 일 + 캠페인 + 그룹 + 소재 + 채널  (CLAUDE.md 참조)
"""

import glob
import os

import pandas as pd

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

SOURCE_TO_CHANNEL = {
    "googleadwords_int": "구글",
    "Facebook Ads": "메타",
    "naver_search": "네이버",
}

JOIN_KEYS = ["일", "캠페인", "그룹", "소재"]
NUMERIC_COLS = ["노출", "클릭", "비용", "회원가입", "구매", "구매매출"]
TEXT_KEYS = ["캠페인", "그룹", "소재", "채널", "미디어소스"]


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """엑셀 가공 흔적(인덱스 열, vlookup 중복 열, 2025.1.1 날짜, #N/A)을 걷어낸다."""
    df = df.rename(columns=lambda c: str(c).strip())
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df = df.loc[:, ~df.columns.str.contains(r"\.\d+$", regex=True)]

    df["일"] = pd.to_datetime(
        df["일"].astype(str).str.strip().str.replace(".", "-", regex=False),
        errors="coerce",
    )
    for key in TEXT_KEYS:
        if key in df.columns:
            df[key] = df[key].astype(str).str.strip()
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "", regex=False), errors="coerce"
            )
    return df


CACHE_DIR = os.path.join(DATA_DIR, ".cache")


def read_cached(csv_path: str) -> pd.DataFrame:
    """CSV를 normalize한 결과를 Parquet으로 캐시해두고 재사용한다.

    CSV는 그대로 드롭존으로 남긴다 — 매체에서 받는 게 CSV라 워크플로를 바꿀 수 없다.
    대신 두 번째 로드부터는 Parquet을 읽는다. 실측(626만 행 기준):
      CSV 10.6s / Parquet 3.3s, 파일 크기는 989MB → 129MB.

    부수 효과가 더 중요할 수 있다 — Parquet은 dtype을 보존하므로
    `2025.1.1` 날짜나 `#N/A` 같은 엑셀 가공 사고가 캐시 단계에서 한 번만 처리된다.

    CSV가 더 새로우면(수정·재업로드) 캐시를 무시하고 다시 만든다.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    stem = os.path.basename(csv_path).removesuffix(".csv")
    pq_path = os.path.join(CACHE_DIR, f"{stem}.parquet")

    if os.path.exists(pq_path) and os.path.getmtime(pq_path) >= os.path.getmtime(csv_path):
        return pd.read_parquet(pq_path)

    df = normalize(pd.read_csv(csv_path))
    try:
        df.to_parquet(pq_path, index=False, compression="zstd")
    except Exception:
        # 캐시 쓰기 실패는 치명적이지 않다 — 원본으로 계속 간다.
        pass
    return df


def load_and_merge(data_dir: str = DATA_DIR) -> pd.DataFrame:
    channel_files = sorted(glob.glob(os.path.join(data_dir, "*_channel.csv")))
    appsflyer_files = sorted(glob.glob(os.path.join(data_dir, "*_appsflyer.csv")))
    if not channel_files or not appsflyer_files:
        return pd.DataFrame()

    # normalize는 read_cached 안에서 파일당 한 번만 돈다.
    channel_df = pd.concat([read_cached(f) for f in channel_files], ignore_index=True)
    appsflyer_df = pd.concat([read_cached(f) for f in appsflyer_files], ignore_index=True)
    appsflyer_df["채널"] = (
        appsflyer_df["미디어소스"].map(SOURCE_TO_CHANNEL).fillna(appsflyer_df["미디어소스"])
    )

    merged = channel_df.merge(
        appsflyer_df,
        on=JOIN_KEYS + ["채널"],
        how="outer",
        suffixes=("_channel", "_af"),
        indicator=True,
    )
    for col in ["노출", "클릭_channel", "비용", "회원가입_channel", "구매_channel", "구매매출_channel"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    merged["소재타입"] = merged["소재"].str.split("_").str[0]
    return merged


def duplicate_key_report(data_dir: str = DATA_DIR) -> dict:
    """조인 **전에** 중복 키를 잡는다.

    같은 키가 두 번 있으면 outer join이 에러 없이 팬아웃해서 모든 숫자가 배로 뛴다.
    (실측: 중복 5배인 522만 행 입력 → 2,610만 행 조인 결과, 경고 한 줄 없음)
    보정본을 `2025-01-01_channel_v2.csv`로 올리는 순간 바로 터지는 시나리오다.

    반환: {"channel": 중복행 DataFrame, "appsflyer": ...} — 깨끗하면 빈 dict.
    """
    report = {}
    for label, pattern in (("channel", "*_channel.csv"), ("appsflyer", "*_appsflyer.csv")):
        files = sorted(glob.glob(os.path.join(data_dir, pattern)))
        if not files:
            continue
        df = pd.concat([read_cached(f) for f in files], ignore_index=True)
        source_key = "채널" if "채널" in df.columns else "미디어소스"
        keys = JOIN_KEYS + [source_key]
        dup = df[df.duplicated(subset=keys, keep=False)].sort_values(keys)
        if not dup.empty:
            report[label] = dup[keys + [c for c in NUMERIC_COLS if c in dup.columns]]
    return report


# 원시 변수(합산 가능) — 항상 이걸 먼저 합산한 뒤 비율을 다시 계산한다.
BASE_METRICS = ["노출", "클릭", "비용", "회원가입", "구매", "구매매출"]

# 파생 지표(합산 불가) — 계층별 분류. METRICS.md 참조.
FUNNEL_RATES = ["CTR", "가입률", "가입구매율", "CVR"]      # 단계 전환율
UNIT_COSTS = ["CPM", "CPC", "CPS", "CPA"]                 # 단계 단가
OUTCOME = ["AOV", "ROAS", "순이익"]                        # 최종 성과


def _div(a: pd.Series, b: pd.Series) -> pd.Series:
    """0 나누기를 0으로 처리. 분모가 0이면 '측정 불가'지 '0'이 아니지만,
    집계 표에서 inf/NaN이 튀는 것보다 낫다고 보고 0으로 채운다."""
    return (a / b).replace([float("inf"), float("-inf")], 0).fillna(0)


def agg_by(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """키 기준으로 원시 변수를 합산한 뒤 파생 지표를 **재계산**한다.

    핵심: 비율 지표는 절대 평균내지 않는다. 채널별 CTR을 단순평균하면 3.94%지만
    실제 전체 CTR은 2.76%다 (노출 가중치가 무시되기 때문). 그래서 합산 → 재계산 순서.

    지표 계층과 분해식은 METRICS.md 참조.
    """
    out = df.groupby(keys, as_index=False).agg(
        노출=("노출", "sum"),
        클릭=("클릭_channel", "sum"),
        비용=("비용", "sum"),
        회원가입=("회원가입_channel", "sum"),
        구매=("구매_channel", "sum"),
        구매매출=("구매매출_channel", "sum"),
    )

    # 1단계 — 퍼널 전환율 (노출 → 클릭 → 가입 → 구매)
    out["CTR"] = (_div(out["클릭"], out["노출"]) * 100).round(2)
    out["가입률"] = (_div(out["회원가입"], out["클릭"]) * 100).round(2)
    out["가입구매율"] = (_div(out["구매"], out["회원가입"]) * 100).round(2)
    out["CVR"] = (_div(out["구매"], out["클릭"]) * 100).round(2)

    # 1단계 — 단계별 단가
    out["CPM"] = (_div(out["비용"], out["노출"]) * 1000).round(0)
    out["CPC"] = _div(out["비용"], out["클릭"]).round(0)
    out["CPS"] = _div(out["비용"], out["회원가입"]).round(0)  # 가입 1건 단가
    out["CPA"] = _div(out["비용"], out["구매"]).round(0)

    # 2단계 — 최종 성과
    out["AOV"] = _div(out["구매매출"], out["구매"]).round(0)   # 객단가
    out["ROAS"] = (_div(out["구매매출"], out["비용"]) * 100).round(1)
    out["순이익"] = (out["구매매출"] - out["비용"]).round(0)

    return out
