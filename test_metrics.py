"""지표 계산 회귀 테스트.

UI는 테스트하지 않는다 — 눈으로 보는 게 빠르고 정확하다.
여기서 지키는 건 **계산이 조용히 틀어지는 것**뿐이다.

실행: python3 -m pytest test_metrics.py -v
"""

import pandas as pd
import pytest

from marketing_data import agg_by, duplicate_key_report, load_and_merge, normalize

TOL = 0.5  # 반올림 누적 허용 오차


@pytest.fixture(scope="module")
def df():
    merged = load_and_merge()
    assert not merged.empty, "CSV를 못 읽었다"
    return merged


@pytest.fixture(scope="module")
def total(df):
    return agg_by(df.assign(_전체="전체"), ["_전체"]).iloc[0]


# =============================================================================
# 조인 — 여기가 깨지면 나머지 숫자는 다 무의미하다
# =============================================================================


def test_모든_행이_조인된다(df):
    """엑셀 가공본(2025.1.1 형식 날짜 등)이 들어와도 키가 맞아야 한다."""
    assert (df["_merge"] == "both").all(), (
        f"조인 실패 {(df['_merge'] != 'both').sum()}행 — 날짜 형식이나 표기 차이 의심"
    )


def test_중복키가_없다():
    """중복 키는 조인을 에러 없이 팬아웃시켜 모든 숫자를 부풀린다."""
    report = duplicate_key_report()
    assert not report, f"중복 키 발견: { {k: len(v) for k, v in report.items()} }"


def test_normalize가_엑셀_가공흔적을_걷어낸다():
    raw = pd.DataFrame({
        "Unnamed: 0": ["키1", "키2"],
        "일": ["2025.1.1", "2025-01-02"],
        "캠페인": [" A ", "B"],
        "그룹": ["논타겟", "VIP"],
        "소재": ["VID_x_v1", "IMG_y_v1"],
        "비용": ["1,000", "#N/A"],
        "구매": [1, 2],
    })
    raw["회원가입"] = [10, 20]
    out = normalize(raw)

    assert "Unnamed: 0" not in out.columns, "엑셀 인덱스 열이 남았다"
    assert out["일"].tolist() == [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-02")]
    assert out["캠페인"].tolist() == ["A", "B"], "공백이 안 잘렸다"
    assert out["비용"].iloc[0] == 1000, "천단위 콤마를 못 읽었다"
    assert pd.isna(out["비용"].iloc[1]), "#N/A가 숫자로 둔갑했다"


def test_normalize가_vlookup_중복열을_버린다():
    raw = pd.DataFrame({
        "일": ["2025-01-01"], "캠페인": ["A"], "그룹": ["논타겟"], "소재": ["VID_x_v1"],
        "구매": [5], "구매.1": [3],  # pandas가 중복 컬럼명을 이렇게 읽는다
    })
    out = normalize(raw)
    assert "구매.1" not in out.columns
    assert out["구매"].iloc[0] == 5, "원본이 아니라 vlookup 열을 남겼다"


# =============================================================================
# 지표 항등식 — METRICS.md §4
# =============================================================================


def test_ROAS_분해식(total):
    """ROAS = AOV × CVR × CTR × (1000 ÷ CPM)

    **원시 합계**로 검증한다. agg_by가 표시용으로 반올림한 값을 곱하면 오차가 누적돼
    1,243.2% 대신 1,241.4%가 나온다 — 수식이 틀린 게 아니라 반올림 때문이다.
    화면에 적힌 숫자를 손으로 곱하면 살짝 안 맞는 이유이기도 하다.
    """
    노출, 클릭, 비용 = total["노출"], total["클릭"], total["비용"]
    구매, 매출 = total["구매"], total["구매매출"]

    AOV, CVR, CTR, CPM = 매출 / 구매, 구매 / 클릭, 클릭 / 노출, 비용 / 노출 * 1000
    right = AOV * CVR * CTR * (1000 / CPM) * 100
    assert right == pytest.approx(매출 / 비용 * 100, abs=0.01)


def test_반올림_드리프트가_1퍼센트_이내다(total):
    """표시용 반올림 때문에 분해식이 정확히 맞아떨어지지 않는 폭을 고정한다.

    이 값이 커지면 화면의 분해 설명이 신뢰를 잃으므로, 자릿수를 줄일 때 여기서 잡힌다.
    """
    from_rounded = (
        total["AOV"] * (total["CVR"] / 100) * (total["CTR"] / 100) * (1000 / total["CPM"]) * 100
    )
    drift = abs(from_rounded - total["ROAS"]) / total["ROAS"]
    assert drift < 0.01, f"반올림 드리프트 {drift:.2%} — 표시 자릿수를 늘려야 한다"


def test_ROAS는_AOV나누기_CPA(total):
    assert total["AOV"] / total["CPA"] * 100 == pytest.approx(total["ROAS"], abs=TOL)


def test_CPA는_CPC나누기_CVR(total):
    assert total["CPC"] / (total["CVR"] / 100) == pytest.approx(total["CPA"], abs=5)


def test_CVR은_가입률곱하기_가입구매율(total):
    right = total["가입률"] * total["가입구매율"] / 100
    assert right == pytest.approx(total["CVR"], abs=0.05)


# =============================================================================
# 비율 지표 합산 금지 — 가장 흔한 실수
# =============================================================================


def test_비율지표는_평균내면_틀린다(df, total):
    """채널별 CTR을 단순평균하면 노출 가중치가 무시돼 값이 부풀려진다.

    이 테스트는 '평균이 틀리다'는 사실 자체를 고정한다. 누군가 agg_by를 고쳐
    가중평균 대신 산술평균을 쓰면 여기서 잡힌다.
    """
    naive = agg_by(df, ["채널"])["CTR"].mean()
    correct = total["CTR"]
    assert naive != pytest.approx(correct, abs=0.1), "가중치가 사라졌다"
    assert correct == pytest.approx(2.76, abs=0.01), "전체 CTR이 예상과 다르다"


def test_agg_by는_합산후_재계산한다(df):
    """채널별로 쪼갠 뒤 원시 변수를 다시 더하면 전체와 같아야 한다(합산 가능층)."""
    by_ch = agg_by(df, ["채널"])
    total_row = agg_by(df.assign(_전체="전체"), ["_전체"]).iloc[0]
    for col in ["노출", "클릭", "비용", "회원가입", "구매", "구매매출"]:
        assert by_ch[col].sum() == pytest.approx(total_row[col]), f"{col} 합이 안 맞는다"


def test_0나누기가_inf를_만들지_않는다(df):
    """구매 0인 행에서 CPA가 inf/NaN이 되면 집계 표 전체가 깨진다."""
    out = agg_by(df, ["채널", "그룹", "소재"])
    for col in ["CTR", "가입률", "가입구매율", "CVR", "CPM", "CPC", "CPS", "CPA", "AOV", "ROAS"]:
        assert out[col].notna().all(), f"{col}에 NaN"
        assert (out[col].abs() != float("inf")).all(), f"{col}에 inf"


# =============================================================================
# Parquet 캐시 — 여기가 틀리면 CSV를 고쳐도 옛 숫자가 나온다
# =============================================================================


def test_캐시가_CSV보다_오래되면_다시_만든다(tmp_path):
    """보정본을 덮어썼는데 캐시가 남아 있으면 조용히 옛 데이터를 보게 된다."""
    import os
    import time

    import marketing_data as md

    csv = tmp_path / "2025-01-01_channel.csv"
    csv.write_text(
        "일,채널,캠페인,그룹,소재,노출,클릭,비용,회원가입,구매,구매매출\n"
        "2025-01-01,구글,A,논타겟,VID_x_v1,100,10,1000,2,1,5000\n",
        encoding="utf-8",
    )
    orig_cache = md.CACHE_DIR
    md.CACHE_DIR = str(tmp_path / ".cache")
    try:
        first = md.read_cached(str(csv))
        assert first["비용"].iloc[0] == 1000
        assert os.path.exists(os.path.join(md.CACHE_DIR, "2025-01-01_channel.parquet"))

        # 보정본으로 덮어쓰기 (mtime이 캐시보다 새로워야 한다)
        time.sleep(0.01)
        csv.write_text(
            "일,채널,캠페인,그룹,소재,노출,클릭,비용,회원가입,구매,구매매출\n"
            "2025-01-01,구글,A,논타겟,VID_x_v1,100,10,9999,2,1,5000\n",
            encoding="utf-8",
        )
        again = md.read_cached(str(csv))
        assert again["비용"].iloc[0] == 9999, "캐시가 갱신되지 않아 옛 값이 나왔다"
    finally:
        md.CACHE_DIR = orig_cache


def test_캐시가_normalize_결과를_보존한다(tmp_path):
    """캐시를 거쳐도 엑셀 가공 흔적 제거 결과가 같아야 한다."""
    import marketing_data as md

    csv = tmp_path / "2025-01-02_channel.csv"
    csv.write_text(
        ",일,채널,캠페인,그룹,소재,노출,클릭,비용,회원가입,구매,구매매출,회원가입,구매\n"
        "키1,2025.1.2,구글,A,논타겟,VID_x_v1,100,10,\"1,000\",2,1,5000,#N/A,#N/A\n",
        encoding="utf-8",
    )
    orig = md.CACHE_DIR
    md.CACHE_DIR = str(tmp_path / ".cache")
    try:
        cold = md.read_cached(str(csv))   # CSV 경로
        warm = md.read_cached(str(csv))   # Parquet 경로
        pd.testing.assert_frame_equal(cold, warm)
        assert cold["일"].iloc[0] == pd.Timestamp("2025-01-02")
        assert cold["비용"].iloc[0] == 1000
        assert "Unnamed: 0" not in cold.columns
    finally:
        md.CACHE_DIR = orig
