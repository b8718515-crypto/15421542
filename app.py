# app.py
# 정비팀용 · L2 알람 이력 기반 · 발생빈도 + 누적지속시간(발생~해제) 스코어링
# --------------------------------------------------------------------
# - data/ 폴더의 xlsx 파일(4A/4B/4C/4X 등)을 탭으로 표시
# - 각 시트의 컬럼을 자동 추정 (알람 / 발생시간 / 해제시간)
# - 지속시간 = 해제시간 - 발생시간 (분 단위)
# - 발생빈도 & 누적지속시간을 Min-Max 정규화 후 가중합 → 종합점수
# --------------------------------------------------------------------

import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="L2 알람 TOP 스코어링",
    page_icon="🚨",
    layout="wide",
)

st.caption("정비팀용 · L2 알람 이력 기반 · 발생빈도 + 누적지속시간 스코어링")

# ============================================================
# 유틸리티
# ============================================================
DATA_DIR = Path("data")

ALARM_KEYWORDS = ["알람", "알람명", "메시지", "message", "alarm", "code", "코드", "내용"]
START_KEYWORDS = ["발생시간", "발생일시", "발생", "start", "시작", "on time", "occur"]
END_KEYWORDS   = ["해제시간", "해제일시", "해제", "복구", "종료", "end", "off time", "clear", "recover"]


def is_xlsx(file_bytes: bytes) -> bool:
    """xlsx 파일 시그니처(PK) 확인."""
    return file_bytes[:2] == b"PK"


@st.cache_data(show_spinner=False)
def load_xlsx_all_sheets(file_bytes: bytes) -> dict:
    """xlsx 바이트를 받아 모든 시트를 dict로 반환."""
    with io.BytesIO(file_bytes) as bio:
        xls = pd.ExcelFile(bio, engine="openpyxl")
        sheets = {name: xls.parse(name) for name in xls.sheet_names}
    return sheets


def guess_column(columns, keywords):
    """컬럼 이름 리스트에서 keywords와 부분일치하는 컬럼 찾기."""
    lowered = {c: str(c).lower().replace(" ", "") for c in columns}
    for kw in keywords:
        kw_norm = kw.lower().replace(" ", "")
        for orig, low in lowered.items():
            if kw_norm in low:
                return orig
    return None


def compute_duration_minutes(df: pd.DataFrame, start_col: str, end_col: str) -> pd.Series:
    """발생시간과 해제시간의 차이를 분(minute) 단위로 반환."""
    start = pd.to_datetime(df[start_col], errors="coerce")
    end   = pd.to_datetime(df[end_col],   errors="coerce")
    delta_min = (end - start).dt.total_seconds() / 60.0
    # 음수/NaN은 0으로 처리 (역전되거나 결측인 경우)
    delta_min = delta_min.where(delta_min >= 0, other=0).fillna(0)
    return delta_min


def minmax_norm(s: pd.Series) -> pd.Series:
    """Min-Max 정규화 (0~1). 분모가 0이면 전부 0."""
    lo, hi = s.min(), s.max()
    if pd.isna(lo) or pd.isna(hi) or hi == lo:
        return pd.Series([0.0] * len(s), index=s.index)
    return (s - lo) / (hi - lo)


# ============================================================
# 데이터 소스 결정 (data/ 폴더 또는 업로드)
# ============================================================
st.sidebar.header("📁 데이터 소스")

uploaded_files = st.sidebar.file_uploader(
    "xlsx 업로드 (미업로드 시 data/ 폴더 사용)",
    type=["xlsx"],
    accept_multiple_files=True,
)

file_map: dict[str, bytes] = {}  # {표시이름: bytes}

if uploaded_files:
    for uf in uploaded_files:
        file_map[uf.name] = uf.getvalue()
else:
    if DATA_DIR.exists():
        for p in sorted(DATA_DIR.glob("*.xlsx")):
            file_map[p.name] = p.read_bytes()

if not file_map:
    st.warning("📂 `data/` 폴더에 xlsx 파일을 넣거나, 좌측에서 업로드해주세요.")
    st.stop()

# ============================================================
# 사이드바 - 스코어링 파라미터
# ============================================================
st.sidebar.header("⚙️ 스코어링 설정")

top_n = st.sidebar.slider("TOP N", min_value=3, max_value=30, value=8, step=1)

w_count = st.sidebar.slider(
    "발생빈도 가중치",
    min_value=0.0, max_value=1.0, value=0.5, step=0.05,
    help="0에 가까울수록 지속시간 중시, 1에 가까울수록 발생횟수 중시",
)
w_dur = 1.0 - w_count
st.sidebar.caption(f"→ 누적지속시간 가중치 = **{w_dur:.2f}**")

# ============================================================
# 파일별 탭
# ============================================================
tab_names = list(file_map.keys())
tabs = st.tabs([f"📊 {n}" for n in tab_names])

for tab, fname in zip(tabs, tab_names):
    with tab:
        raw = file_map[fname]

        if not is_xlsx(raw):
            st.error(f"❌ `{fname}` 은 xlsx 형식이 아닙니다.")
            continue

        try:
            sheets = load_xlsx_all_sheets(raw)
        except Exception as e:
            st.error(f"❌ `{fname}` 로드 실패: {e}")
            continue

        if not sheets:
            st.warning("시트가 없습니다.")
            continue

        # 기본 시트: 행 수가 가장 많은 시트
        default_sheet = max(sheets.items(), key=lambda kv: len(kv[1]))[0]
        sheet_names = list(sheets.keys())

        sheet_name = st.selectbox(
            "시트 선택",
            sheet_names,
            index=sheet_names.index(default_sheet),
            key=f"sheet_{fname}",
        )
        df = sheets[sheet_name].copy()
        st.subheader(f"📋 {fname} · [{sheet_name}] — {len(df):,}행 × {df.shape[1]}열")

        with st.expander("🔍 원본 데이터 미리보기 (상위 20행)"):
            st.dataframe(df.head(20), use_container_width=True)

        # -----------------------------
        # 컬럼 자동 추정
        # -----------------------------
        cols = list(df.columns)
        guess_alarm = guess_column(cols, ALARM_KEYWORDS) or cols[0]
        guess_start = guess_column(cols, START_KEYWORDS)
        guess_end   = guess_column(cols, END_KEYWORDS)

        c1, c2, c3 = st.columns(3)
        with c1:
            alarm_col = st.selectbox(
                "🔔 알람(그룹핑) 컬럼",
                cols,
                index=cols.index(guess_alarm),
                key=f"alarm_{fname}",
            )
        with c2:
            start_options = ["(사용 안 함)"] + cols
            start_idx = start_options.index(guess_start) if guess_start in cols else 0
            start_col = st.selectbox(
                "🕐 발생시간 컬럼",
                start_options,
                index=start_idx,
                key=f"start_{fname}",
            )
        with c3:
            end_options = ["(사용 안 함)"] + cols
            end_idx = end_options.index(guess_end) if guess_end in cols else 0
            end_col = st.selectbox(
                "🕑 해제시간 컬럼",
                end_options,
                index=end_idx,
                key=f"end_{fname}",
            )

        # -----------------------------
        # 지속시간 계산
        # -----------------------------
        use_duration = (start_col != "(사용 안 함)") and (end_col != "(사용 안 함)")

        if use_duration:
            df["_duration_min"] = compute_duration_minutes(df, start_col, end_col)
            valid_dur_count = (df["_duration_min"] > 0).sum()
            if valid_dur_count == 0:
                st.warning(
                    "⚠️ 발생시간/해제시간을 datetime으로 해석할 수 없거나 "
                    "모든 값이 0/음수입니다. 컬럼을 확인해주세요."
                )
        else:
            df["_duration_min"] = 0.0

        # -----------------------------
        # KPI
        # -----------------------------
        k1, k2, k3 = st.columns(3)
        k1.metric("알람 종류", f"{df[alarm_col].nunique():,}")
        k2.metric("총 발생 건수", f"{len(df):,}")
        k3.metric(
            "총 누적지속시간(분)",
            f"{df['_duration_min'].sum():,.1f}" if use_duration else "—",
        )

        # -----------------------------
        # 알람별 집계
        # -----------------------------
        agg = (
            df.groupby(alarm_col)
              .agg(발생빈도=(alarm_col, "size"),
                   누적지속시간_분=("_duration_min", "sum"))
              .reset_index()
        )

        # 정규화 & 종합점수
        agg["_n_cnt"] = minmax_norm(agg["발생빈도"])
        agg["_n_dur"] = minmax_norm(agg["누적지속시간_분"]) if use_duration else 0.0

        if use_duration:
            agg["종합점수"] = (w_count * agg["_n_cnt"] + w_dur * agg["_n_dur"]) * 100
        else:
            agg["종합점수"] = agg["_n_cnt"] * 100  # 지속시간 없으면 빈도만 반영

        agg = agg.sort_values("종합점수", ascending=False).reset_index(drop=True)

        # 표시용 컬럼 정리
        show_cols = [alarm_col, "발생빈도"]
        if use_duration:
            show_cols += ["누적지속시간_분"]
        show_cols += ["종합점수"]

        top_df = agg[show_cols].head(top_n).copy()
        top_df["종합점수"] = top_df["종합점수"].round(1)
        if use_duration:
            top_df["누적지속시간_분"] = top_df["누적지속시간_분"].round(1)

        # -----------------------------
        # TOP N 표
        # -----------------------------
        st.markdown(f"### 🏆 TOP {top_n} 알람")
        st.dataframe(top_df, use_container_width=True, hide_index=True)

        # -----------------------------
        # 차트
        # -----------------------------
        chart_df = top_df.set_index(alarm_col)[["종합점수"]]
        st.bar_chart(chart_df, height=320)

        # -----------------------------
        # 다운로드
        # -----------------------------
        csv_bytes = agg[show_cols].to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "💾 전체 랭킹 CSV 다운로드",
            data=csv_bytes,
            file_name=f"{Path(fname).stem}_{sheet_name}_ranking.csv",
            mime="text/csv",
            key=f"dl_{fname}",
        )
