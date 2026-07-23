import re
import pandas as pd
import streamlit as st
import plotly.express as px


# =========================================================
# 페이지 기본 설정
# =========================================================
st.set_page_config(
    page_title="알람 분석 대시보드",
    page_icon="🚨",
    layout="wide",
)

st.title("🚨 알람 발생 이력 분석 대시보드")
st.caption("발생빈도 · 누적지속시간(시간+분) · 종합점수 기반 TOP 알람 분석")


# =========================================================
# 유틸: 견고한 datetime 파서 (오전/오후 지원)
# =========================================================
def robust_to_datetime(series: pd.Series) -> pd.Series:
    """
    다양한 형식을 순차적으로 시도하여 datetime으로 변환.
    - datetime 객체는 그대로
    - 엑셀 시리얼 숫자 (예: 45632.354)
    - 한글 '오전/오후' 표기 지원 (예: '2026-07-22 오후 10:39:52')
    - 표준 문자열 자동 파싱
    """
    # 이미 datetime 계열이면 그대로
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    # 1) 숫자형 → 엑셀 시리얼 날짜
    if pd.api.types.is_numeric_dtype(series):
        try:
            return pd.to_datetime(series, unit="D", origin="1899-12-30", errors="coerce")
        except Exception:
            pass

    # 2) 문자열 캐스팅
    s = series.astype(str).str.strip()

    # 3) 한글 날짜 표기 정리
    s = (
        s.str.replace("년", "-", regex=False)
         .str.replace("월", "-", regex=False)
         .str.replace("일", " ", regex=False)
         .str.replace("시", ":", regex=False)
         .str.replace("분", ":", regex=False)
         .str.replace("초", "",  regex=False)
    )

    # 4) 오전/오후 처리 (핵심)
    def convert_ampm(text: str) -> str:
        if not isinstance(text, str):
            return text
        m = re.search(r"(오전|오후)\s*(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
        if not m:
            return text
        ampm, hh, mm, ss = m.group(1), int(m.group(2)), m.group(3), m.group(4) or "00"
        if ampm == "오후" and hh != 12:
            hh += 12
        elif ampm == "오전" and hh == 12:
            hh = 0
        new_time = f"{hh:02d}:{mm}:{ss}"
        return re.sub(r"(오전|오후)\s*\d{1,2}:\d{2}(?::\d{2})?", new_time, text)

    s = s.map(convert_ampm)

    # 5) 점(.) → 하이픈, 공백 정리
    s = s.str.replace(".", "-", regex=False).str.strip()
    s = s.str.replace(r"\s+", " ", regex=True)
    s = s.str.rstrip(":-")

    # 6) 자동 파싱
    out = pd.to_datetime(s, errors="coerce")
    if out.notna().sum() > 0:
        return out

    # 7) 흔한 포맷 순차 시도
    fmts = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y%m%d %H%M%S",
        "%Y%m%d%H%M%S",
    ]
    for f in fmts:
        out = pd.to_datetime(s, format=f, errors="coerce")
        if out.notna().sum() > 0:
            return out

    return pd.to_datetime(pd.Series([None] * len(s)), errors="coerce")


# =========================================================
# 유틸: 초 → "N시간 M분" 문자열
# =========================================================
def seconds_to_hm(total_seconds: float) -> str:
    """초 단위 값을 '시간 분' 문자열로 변환."""
    if pd.isna(total_seconds) or total_seconds < 0:
        return "0시간 0분"
    total_seconds = int(total_seconds)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    return f"{h:,}시간 {m}분"


# =========================================================
# 사이드바: 파일 업로드 & 옵션
# =========================================================
with st.sidebar:
    st.header("⚙️ 설정")
    uploaded = st.file_uploader(
        "알람 이력 파일 업로드 (Excel/CSV)",
        type=["xlsx", "xls", "csv"],
    )

    st.markdown("---")
    st.subheader("종합점수 가중치")
    w1 = st.slider("발생빈도 가중치", 0.0, 1.0, 0.5, 0.05)
    w2 = 1.0 - w1
    st.caption(f"지속시간(시간) 가중치: **{w2:.2f}**")

    st.markdown("---")
    top_n = st.number_input("TOP N 표시", min_value=3, max_value=30, value=8, step=1)


# =========================================================
# 파일 읽기
# =========================================================
if uploaded is None:
    st.info("👈 좌측에서 알람 이력 파일을 업로드하세요.")
    st.stop()

try:
    if uploaded.name.lower().endswith(".csv"):
        df_raw = pd.read_csv(uploaded)
    else:
        df_raw = pd.read_excel(uploaded)
except Exception as e:
    st.error(f"파일을 읽을 수 없습니다: {e}")
    st.stop()

st.success(f"✅ 파일 로드 완료: **{uploaded.name}** ({len(df_raw):,} 행)")


# =========================================================
# 컬럼 매핑
# =========================================================
st.subheader("🔧 컬럼 매핑")
cols = df_raw.columns.tolist()

def guess(name_candidates):
    for c in cols:
        for k in name_candidates:
            if k in str(c):
                return c
    return cols[0]

c1, c2, c3 = st.columns(3)
with c1:
    col_alarm = st.selectbox("알람명 컬럼", cols,
                             index=cols.index(guess(["알람", "알람명", "Alarm", "MSG"]))
                             if guess(["알람", "알람명", "Alarm", "MSG"]) in cols else 0)
with c2:
    col_start = st.selectbox("발생시간 컬럼", cols,
                             index=cols.index(guess(["발생", "시작", "Start", "On"]))
                             if guess(["발생", "시작", "Start", "On"]) in cols else 0)
with c3:
    col_end = st.selectbox("해제시간 컬럼", cols,
                           index=cols.index(guess(["해제", "종료", "End", "Off", "복구"]))
                           if guess(["해제", "종료", "End", "Off", "복구"]) in cols else 0)


# =========================================================
# 데이터 정제
# =========================================================
df = df_raw[[col_alarm, col_start, col_end]].copy()
df.columns = ["알람명", "발생시간", "해제시간"]

df["발생시간"] = robust_to_datetime(df["발생시간"])
df["해제시간"] = robust_to_datetime(df["해제시간"])

# 지속시간 (초 단위)
df["지속시간_초"] = (df["해제시간"] - df["발생시간"]).dt.total_seconds()


# =========================================================
# 원본 미리보기 & 파싱 디버그
# =========================================================
with st.expander("🔍 원본 데이터 미리보기 (상위 20행)"):
    st.dataframe(df_raw.head(20), use_container_width=True)

with st.expander("🐞 시간 파싱 디버그"):
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("발생시간 파싱 성공", f"{df['발생시간'].notna().sum()}/{len(df)}")
    d2.metric("해제시간 파싱 성공", f"{df['해제시간'].notna().sum()}/{len(df)}")
    both_ok = (df["발생시간"].notna() & df["해제시간"].notna()).sum()
    d3.metric("양쪽 다 성공", f"{both_ok}")
    d4.metric("양의 지속시간 건수", f"{(df['지속시간_초'] > 0).sum()}")

    st.markdown("**원본 샘플 → 파싱 결과 샘플**")
    st.write("발생시간(원본):", df_raw[col_start].astype(str).head(3).tolist())
    st.write("발생시간(파싱):", df["발생시간"].head(3).astype(str).tolist())
    st.write("해제시간(원본):", df_raw[col_end].astype(str).head(3).tolist())
    st.write("해제시간(파싱):", df["해제시간"].head(3).astype(str).tolist())


# =========================================================
# 유효 데이터만 필터링
# =========================================================
df_valid = df.dropna(subset=["발생시간", "해제시간"]).copy()
df_valid = df_valid[df_valid["지속시간_초"] > 0]

if len(df_valid) == 0:
    st.error("유효한 지속시간 데이터가 없습니다. 컬럼 매핑을 확인하세요.")
    st.stop()


# =========================================================
# 상단 KPI
# =========================================================
st.markdown("---")
st.subheader("📊 요약 지표")

total_sec = df_valid["지속시간_초"].sum()
k1, k2, k3, k4 = st.columns(4)
k1.metric("총 알람 건수", f"{len(df_valid):,} 건")
k2.metric("고유 알람 종류", f"{df_valid['알람명'].nunique():,} 종")
k3.metric("총 누적지속시간", seconds_to_hm(total_sec))
k4.metric("평균 지속시간", seconds_to_hm(df_valid["지속시간_초"].mean()))


# =========================================================
# 알람별 집계
# =========================================================
agg = df_valid.groupby("알람명").agg(
    발생빈도=("알람명", "count"),
    누적지속_초=("지속시간_초", "sum"),
).reset_index()

# 시간 단위 (숫자, 차트/점수용)
agg["누적지속시간_시간"] = (agg["누적지속_초"] / 3600).round(2)

# 표시용 "N시간 M분" 문자열
agg["누적지속시간(시간+분)"] = agg["누적지속_초"].apply(seconds_to_hm)

# 종합점수 = 빈도 * w1 + 시간(h) * w2  (정규화 옵션)
# 스케일 차이가 클 수 있어 0-1 min-max 정규화 후 가중합
def minmax(s):
    if s.max() == s.min():
        return pd.Series([0] * len(s), index=s.index)
    return (s - s.min()) / (s.max() - s.min())

agg["_freq_norm"] = minmax(agg["발생빈도"])
agg["_dur_norm"] = minmax(agg["누적지속시간_시간"])
agg["종합점수"] = (agg["_freq_norm"] * w1 + agg["_dur_norm"] * w2).round(4)

agg_sorted = agg.sort_values("종합점수", ascending=False).reset_index(drop=True)


# =========================================================
# TOP N 표
# =========================================================
st.markdown("---")
st.subheader(f"🏆 TOP {top_n} 알람 (종합점수 순)")

show_cols = ["알람명", "발생빈도", "누적지속시간(시간+분)", "누적지속시간_시간", "종합점수"]
top_df = agg_sorted.head(top_n)[show_cols].copy()
top_df.index = top_df.index + 1

st.dataframe(top_df, use_container_width=True)


# =========================================================
# 차트
# =========================================================
st.markdown("---")
st.subheader("📈 시각화")

tab1, tab2, tab3 = st.tabs(["발생빈도", "누적지속시간(h)", "종합점수"])

with tab1:
    fig = px.bar(
        top_df.sort_values("발생빈도"),
        x="발생빈도", y="알람명", orientation="h",
        text="발생빈도", title=f"TOP {top_n} 발생빈도",
    )
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    plot_df = top_df.sort_values("누적지속시간_시간")
    fig = px.bar(
        plot_df,
        x="누적지속시간_시간", y="알람명", orientation="h",
        text="누적지속시간(시간+분)",
        title=f"TOP {top_n} 누적지속시간",
        labels={"누적지속시간_시간": "누적지속시간 (h)"},
    )
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)

with tab3:
    fig = px.bar(
        top_df.sort_values("종합점수"),
        x="종합점수", y="알람명", orientation="h",
        text="종합점수", title=f"TOP {top_n} 종합점수",
    )
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)


# =========================================================
# 다운로드
# =========================================================
st.markdown("---")
st.subheader("💾 결과 다운로드")

download_df = agg_sorted[["알람명", "발생빈도", "누적지속시간(시간+분)",
                          "누적지속시간_시간", "종합점수"]]

csv = download_df.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "📥 전체 알람 집계 결과 CSV 다운로드",
    data=csv,
    file_name="알람_분석_결과.csv",
    mime="text/csv",
)
