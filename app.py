# app.py
# 정비팀용 · L2 알람 이력 기반 · 발생빈도 + 누적지속시간(발생~해제) 스코어링

import io
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
    return file_bytes[:2] == b"PK"


@st.cache_data(show_spinner=False)
def load_xlsx_all_sheets(file_bytes: bytes) -> dict:
    with io.BytesIO(file_bytes) as bio:
        xls = pd.ExcelFile(bio, engine="openpyxl")
        sheets = {name: xls.parse(name) for name in xls.sheet_names}
    return sheets


def guess_column(columns, keywords):
    lowered = {c: str(c).lower().replace(" ", "") for c in columns}
    for kw in keywords:
        kw_norm = kw.lower().replace(" ", "")
        for orig, low in lowered.items():
            if kw_norm in low:
                return orig
    return None


def robust_to_datetime(series: pd.Series) -> pd.Series:
    """
    다양한 형식을 순차적으로 시도하여 datetime으로 변환.
    - datetime 객체는 그대로
    - 엑셀 시리얼 숫자 (예: 45632.354)
    - 표준 문자열 (자동 파싱)
    - '2024-11-15 08:23:41', '2024/11/15 8:23', 
      '241115 082341', '2024년 11월 15일 08:23:41' 등
    """
    # 이미 datetime 계열이면 그대로
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    # 1) 숫자형 → 엑셀 시리얼 날짜로 해석 시도
    if pd.api.types.is_numeric_dtype(series):
        try:
            # 엑셀 기준: 1899-12-30 + n일
            return pd.to_datetime(series, unit="D", origin="1899-12-30", errors="coerce")
        except Exception:
            pass

    # 2) 문자열로 캐스팅 후 정리
    s = series.astype(str).str.strip()
    # 한글 날짜 표기 제거/치환
    s = (
        s.str.replace("년", "-", regex=False)
         .str.replace("월", "-", regex=False)
         .str.replace("일", " ", regex=False)
         .str.replace("시", ":", regex=False)
         .str.replace("분", ":", regex=False)
         .str.replace("초", "",  regex=False)
         .str.replace(".", "-", regex=False)  # 2024.11.15 → 2024-11-15
         .str.strip()
         .str.rstrip(":")
    )

    # 3) 일반 파싱 (자동 추론)
    out = pd.to_datetime(s, errors="coerce")
    if out.notna().sum() > 0:
        return out

    # 4) 흔한 포맷 순차 시도
    fmts = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y%m%d %H%M%S",
        "%Y%m%d%H%M%S",
        "%y%m%d %H%M%S",
        "%y-%m-%d %H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]
    for f in fmts:
        out = pd.to_datetime(s, format=f, errors="coerce")
        if out.notna().sum() > 0:
            return out

    # 모두 실패 → NaT
    return pd.to_datetime(pd.Series([None] * len(s)), errors="coerce")


def compute_duration_minutes(df: pd.DataFrame, start_col: str, end_col: str):
    """발생시간과 해제시간의 차이를 분(minute) 단위로 반환. 디버그 정보도 함께."""
    start = robust_to_datetime(df[start_col])
    end   = robust_to_datetime(df[end_col])

    delta_min = (end - start).dt.total_seconds() / 60.0

    debug = {
        "start_parsed": int(start.notna().sum()),
        "end_parsed":   int(end.notna().sum()),
        "both_parsed":  int((start.notna() & end.notna()).sum()),
        "positive":     int((delta_min > 0).sum()),
        "negative":     int((delta_min < 0).sum()),
        "zero":         int((delta_min == 0).sum()),
        "start_sample": df[start_col].dropna().astype(str).head(3).tolist(),
        "end_sample":   df[end_col].dropna().astype(str).head(3).tolist(),
        "start_parsed_sample": start.dropna().astype(str).head(3).tolist(),
        "end_parsed_sample":   end.dropna().astype(str).head(3).tolist(),
    }

    delta_min = delta_min.where(delta_min >= 0, other=0).fillna(0)
    return delta_min, debug


def minmax_norm(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if pd.isna(lo) or pd.isna(hi) or hi == lo:
        return pd.Series([0.0] * len(s), index=s.index)
    return (s - lo) / (hi - lo)


# ============================================================
# 데이터 소스
# ============================================================
st.sidebar.header("📁 데이터 소스")

uploaded_files = st.sidebar.file_uploader(
    "xlsx 업로드 (미업로드 시 data/ 폴더 사용)",
    type=["xlsx"],
    accept_multiple_files=True,
)

file_map: dict[str, bytes] = {}
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
# 사이드바 - 파라미터
# ============================================================
st.sidebar.header("⚙️ 스코어링 설정")
top_n = st.sidebar.slider("TOP N", 3, 30, 8, 1)
w_count = st.sidebar.slider("발생빈도 가중치", 0.0, 1.0, 0.5, 0.05,
                            help="0=지속시간 중시, 1=발생횟수 중시")
w_dur = 1.0 - w_count
st.sidebar.caption(f"→ 누적지속시간 가중치 = **{w_dur:.2f}**")

show_debug = st.sidebar.checkbox("🐞 디버그 정보 표시", value=True)

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

        default_sheet = max(sheets.items(), key=lambda kv: len(kv[1]))[0]
        sheet_names = list(sheets.keys())
        sheet_name = st.selectbox(
            "시트 선택", sheet_names,
            index=sheet_names.index(default_sheet),
            key=f"sheet_{fname}",
        )
        df = sheets[sheet_name].copy()
        st.subheader(f"📋 {fname} · [{sheet_name}] — {len(df):,}행 × {df.shape[1]}열")

        with st.expander("🔍 원본 데이터 미리보기 (상위 20행)"):
            st.dataframe(df.head(20), use_container_width=True)
            # 각 컬럼의 dtype도 표시 (문제 진단용)
            dtype_df = pd.DataFrame({
                "컬럼": df.columns,
                "dtype": [str(t) for t in df.dtypes],
                "예시값": [str(df[c].dropna().iloc[0]) if df[c].notna().any() else ""
                          for c in df.columns],
            })
            st.markdown("**컬럼별 데이터 타입 & 예시값**")
            st.dataframe(dtype_df, use_container_width=True, hide_index=True)

        # -----------------------------
        # 컬럼 선택
        # -----------------------------
        cols = list(df.columns)
        guess_alarm = guess_column(cols, ALARM_KEYWORDS) or cols[0]
        guess_start = guess_column(cols, START_KEYWORDS)
        guess_end   = guess_column(cols, END_KEYWORDS)

        c1, c2, c3 = st.columns(3)
        with c1:
            alarm_col = st.selectbox(
                "🔔 알람(그룹핑) 컬럼", cols,
                index=cols.index(guess_alarm), key=f"alarm_{fname}",
            )
        with c2:
            start_options = ["(사용 안 함)"] + cols
            start_idx = start_options.index(guess_start) if guess_start in cols else 0
            start_col = st.selectbox(
                "🕐 발생시간 컬럼", start_options,
                index=start_idx, key=f"start_{fname}",
            )
        with c3:
            end_options = ["(사용 안 함)"] + cols
            end_idx = end_options.index(guess_end) if guess_end in cols else 0
            end_col = st.selectbox(
                "🕑 해제시간 컬럼", end_options,
                index=end_idx, key=f"end_{fname}",
            )

        # -----------------------------
        # 지속시간 계산
        # -----------------------------
        use_duration = (start_col != "(사용 안 함)") and (end_col != "(사용 안 함)")

        if use_duration:
            df["_duration_min"], dbg = compute_duration_minutes(df, start_col, end_col)

            if show_debug:
                with st.expander("🐞 시간 파싱 디버그", expanded=(dbg["both_parsed"] == 0)):
                    dcol1, dcol2, dcol3, dcol4 = st.columns(4)
                    dcol1.metric("발생시간 파싱 성공", f"{dbg['start_parsed']}/{len(df)}")
                    dcol2.metric("해제시간 파싱 성공", f"{dbg['end_parsed']}/{len(df)}")
                    dcol3.metric("양쪽 다 성공", dbg["both_parsed"])
                    dcol4.metric("양의 지속시간 건수", dbg["positive"])

                    st.markdown("**원본 샘플 → 파싱 결과 샘플**")
                    st.write("발생시간(원본):", dbg["start_sample"])
                    st.write("발생시간(파싱):", dbg["start_parsed_sample"])
                    st.write("해제시간(원본):", dbg["end_sample"])
                    st.write("해제시간(파싱):", dbg["end_parsed_sample"])

            if (df["_duration_min"] > 0).sum() == 0:
                st.warning(
                    "⚠️ 발생시간/해제시간을 datetime으로 해석할 수 없거나 "
                    "모든 값이 0/음수입니다. 위 디버그 정보를 확인해주세요."
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

        agg["_n_cnt"] = minmax_norm(agg["발생빈도"])
        agg["_n_dur"] = minmax_norm(agg["누적지속시간_분"]) if use_duration else 0.0

        if use_duration and agg["누적지속시간_분"].sum() > 0:
            agg["종합점수"] = (w_count * agg["_n_cnt"] + w_dur * agg["_n_dur"]) * 100
        else:
            agg["종합점수"] = agg["_n_cnt"] * 100

        agg = agg.sort_values("종합점수", ascending=False).reset_index(drop=True)

        show_cols = [alarm_col, "발생빈도"]
        if use_duration:
            show_cols += ["누적지속시간_분"]
        show_cols += ["종합점수"]

        top_df = agg[show_cols].head(top_n).copy()
        top_df["종합점수"] = top_df["종합점수"].round(1)
        if use_duration:
            top_df["누적지속시간_분"] = top_df["누적지속시간_분"].round(1)

        st.markdown(f"### 🏆 TOP {top_n} 알람")
        st.dataframe(top_df, use_container_width=True, hide_index=True)

        chart_df = top_df.set_index(alarm_col)[["종합점수"]]
        st.bar_chart(chart_df, height=320)

        csv_bytes = agg[show_cols].to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "💾 전체 랭킹 CSV 다운로드",
            data=csv_bytes,
            file_name=f"{Path(fname).stem}_{sheet_name}_ranking.csv",
            mime="text/csv",
            key=f"dl_{fname}",
        )
