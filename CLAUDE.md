# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A local working folder for performance-marketing EDA: daily channel-spend CSVs and AppsFlyer
attribution CSVs are dropped in here, joined, and turned into dashboards. No build/lint/test
tooling — this is a data + reporting workspace, not an application.

## Files

- `*_channel.csv` — media channel report (impressions/clicks/cost). One file per day,
  named `YYYY-MM-DD_channel.csv`.
- `*_appsflyer.csv` — AppsFlyer attribution report (clicks/signups/purchases/revenue). Same
  date-prefixed naming: `YYYY-MM-DD_appsflyer.csv`.
- `streamlit_app.py` — live dashboard. Globs **all** `*_channel.csv` / `*_appsflyer.csv` in this
  folder at load time (`@st.cache_data(ttl=600)`), so dropping in a new day's pair and refreshing
  picks it up automatically — no code change needed.
- `dashboard.html` — static snapshot report generated from the same join logic. Data is baked into
  the HTML at generation time; re-run the generation step after new dates are added (see below).
- `.claude/launch.json` — preview server config (`python3 -m streamlit run streamlit_app.py`,
  port 8501). Use `python3 -m streamlit`, not the bare `streamlit` binary — it isn't on PATH here.

## Running

```bash
python3 -m streamlit run streamlit_app.py --server.port 8501
```

To regenerate `dashboard.html` after adding new dated CSVs, re-run the same aggregation logic
used in `streamlit_app.py`'s `load_and_merge()` and dump into the `dashboard.html` template's
`__DATA_JSON__` placeholder (see how it was built — inline Python computing `by_channel` /
`by_campaign` / `by_creative` aggregates, then string-replacing into the HTML `<script>` block).

## Join logic (the core thing to preserve)

Join key across both files: **일(date) + 캠페인 + 그룹 + 소재** + 채널 (channel name, after mapping).

`appsflyer` uses "미디어소스" (media source) instead of "채널"; it must be mapped before joining:

| appsflyer 미디어소스   | channel 채널 |
|-------------------------|--------------|
| `googleadwords_int`     | 구글          |
| `Facebook Ads`          | 메타          |
| `naver_search`          | 네이버        |

**New channel checklist:** adding a 4th channel (e.g. TikTok) means updating this mapping in
*both* `streamlit_app.py` (`SOURCE_TO_CHANNEL`) and the `dashboard.html` generation script —
there is no single shared source of truth for it yet.

Known schema asymmetry: `channel` has 노출(impressions) and 비용(cost); `appsflyer` does not.
`channel` and `appsflyer` both report 회원가입/구매/구매매출 but from different attribution
logic — the merge suffixes these `_channel` / `_af`. Dashboards currently use the `_channel`
suffixed columns as the source of truth for conversions/revenue (media-side report), not `_af`.
If that's wrong for your use case, decide explicitly rather than silently mixing sources.

The join is `how="outer"` with `indicator=True` — unmatched rows are surfaced as a warning/count,
not dropped silently. Investigate unmatched rows before trusting aggregate totals.

## Metric definitions in use

- CTR = 클릭 / 노출 (channel-side)
- CVR = 구매 / 클릭 (channel-side, click-based — not impression-based)
- CPA = 비용 / 구매
- ROAS = 구매매출 / 비용 × 100 (%)

These are computed metrics, not sourced from either CSV directly — confirm this matches your
team's definitions before reporting numbers externally (e.g. some teams define CVR against
signups, not purchases).

## ⚠️ Not yet defined — needed before scaling this past ad-hoc use

These require domain knowledge only the marketing team has; do not infer or invent them:

1. **소재(creative) naming convention.** Observed pattern in current data looks like
   `{타입}_{테마}_{시즌}_{AB버전}_v{번호}` (e.g. `VID_플러스멤버십_겨울_A_v1`,
   타입 ∈ {VID, IMG, CRS, TXT}) — **this is inferred from 1 day of sample data, not confirmed.**
   If this is the real convention, document the allowed values for each segment (creative type
   codes, whether AB suffix is always present, version numbering rules) so parsing logic can be
   built on it instead of regex-guessed.
2. **캠페인 코드 convention.** Observed: `{채널코드}_CMP_{번호}_{목적}` (e.g.
   `GGL_CMP_01_플러스가입`) — same caveat, needs confirmation + the full list of valid 목적 values.
3. **그룹(targeting group) taxonomy.** Observed values: 논타겟, 유사타겟, 리마케팅, VIP, 윈백.
   Confirm this is the complete/stable list before hardcoding it anywhere (e.g. for grouping or
   filtering UI).
4. **File replacement policy.** If a day's data is re-uploaded (correction), does the new file
   overwrite the old `YYYY-MM-DD_*.csv`, or do corrections need a different naming/versioning
   scheme? Currently the loader just globs by filename, so a same-named file silently overwrites.
