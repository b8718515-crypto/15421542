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
st.caption("여러 파일 업로드 지원 · 발생빈도 · 누적지속시간(시간+분) · 종합점수 기반 TOP 알람 분석")


# =========================================================
# 유틸: 견고한 datetime 파서 (오전/오후 지원)
# =========================================================
def robust_to_datetime(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    if pd.api.types.is_numeric_dtype(series):
        try:
            return pd.to_datetime(series, unit="D", origin="1899-12-30", errors="coerce")
        except Exception:
            pass

    s = series.astype(str).str.strip()

    s = (
        s.str.replace("년", "-", regex=False)
         .str.replace("월", "-", regex=False)
         .str.replace("일", " ", regex=False)
         .str.replace("시", ":", regex=False)
         .str.replace("분", ":", regex=False)
         .str.replace("초", "",  regex=False)
    )

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
    s = s.str.replace(".", "-", regex=False).str.strip()
    s = s.str.replace(r"\s+", " ", regex=True)
    s = s.str.rstrip(":-")

    out = pd.to_datetime(s, errors="coerce")
    if out.notna().sum() > 0:
        return out

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
# 유틸: 초 → "N시간 M분"
# =========================================================
def seconds_to_hm(total_seconds: float) -> str:
    if pd.isna(total_seconds) or total_seconds < 0:
        return "0시간 0분"
    total_seconds = int(total_seconds)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    return f"{h:,}시간 {m}분"


# =========================================================
# 유틸: 파일 읽기
# =========================================================
def read_file(file) -> pd.DataFrame:
    name = file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(file)
    else:
        return pd.read_excel(file)


# =========================================================
# 사이드바
# =========================================================
with st.sidebar:
    st.header("⚙️ 설정")
    uploaded_files = st.file_uploader(
        "알람 이력 파일 업로드 (여러 개 가능)",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,  # ✅ 다중 업로드
    )

    st.markdown("---")
    st.subheader("종합점수 가중치")
    w1 = st.slider("발생빈도 가중치", 0.0, 1.0, 0.5, 0.05)
    w2 = 1.0 - w1
    st.caption(f"지속시간(시간) 가중치: **{w2:.2f}**")

    st.markdown("---")
    top_n = st.number_input("TOP N 표시", min_value=3, max_value=30, value=8, step=1)


# =========================================================
# 파일 읽기 & 병합
# =========================================================
if not uploaded_files:
    st.info("👈 좌측에서 알람 이력 파일을 **하나 이상** 업로드하세요.")
    st.stop()

raw_frames = []
file_info = []
for f in uploaded_files:
    try:
        d = read_file(f)
        d["_파일명"] = f.name
        raw_frames.append(d)
        file_info.append((f.name, len(d), None))
    except Exception as e:
        file_info.append((f.name, 0, str(e)))

# 파일별 로드 결과 표시
st.subheader("📁 업로드된 파일")
info_df = pd.DataFrame(file_info, columns=["파일명", "행 수", "오류"])
st.dataframe(info_df, use_container_width=True)

if not raw_frames:
    st.error("읽을 수 있는 파일이 없습니다.")
    st.stop()

# 컬럼이 다를 수 있으므로 outer 병합
df_raw = pd.concat(raw_frames, ignore_index=True, sort=False)
st.success(f"✅ 총 {len(uploaded_files)}개 파일 병합 완료 · 총 **{len(df_raw):,} 행**")


# =========================================================
# 컬럼 매핑 (병합된 df 기준)
# =========================================================
st.subheader("🔧 컬럼 매핑")
cols = [c for c in df_raw.columns.tolist() if c != "_파일명"]

def guess(name_candidates):
    for c in cols:
        for k in name_candidates:
            if k in str(c):
                return c
    return cols[0]

c1, c2, c3 = st.columns(3)
with c1:
    g = guess(["알람", "알람명", "Alarm", "MSG"])
    col_alarm = st.selectbox("알람명 컬럼", cols,
                             index=cols.index(g) if g in cols else 0)
with c2:
    g = guess(["발생", "시작", "Start", "On"])
    col_start = st.selectbox("발생시간 컬럼", cols,
                             index=cols.index(g) if g in cols else 0)
with c3:
    g = guess(["해제", "종료", "End", "Off", "복구"])
    col_end = st.selectbox("해제시간 컬럼", cols,
                           index=cols.index(g) if g in cols else 0)


# =========================================================
# 데이터 정제
# =========================================================
df = df_raw[[col_alarm, col_start, col_end, "_파일명"]].copy()
df.columns = ["알람명", "발생시간", "해제시간", "파일명"]

df["발생시간"] = robust_to_datetime(df["발생시간"])
df["해제시간"] = robust_to_datetime(df["해제시간"])
df["지속시간_초"] = (df["해제시간"] - df["발생시간"]).dt.total_seconds()


# =========================================================
# 파일 필터
# =========================================================
st.markdown("---")
st.subheader("🔎 파일 필터")
all_files = sorted(df["파일명"].unique().tolist())
selected_files = st.multiselect(
    "분석에 포함할 파일 선택",
    options=all_files,
    default=all_files,
)
df = df[df["파일명"].isin(selected_files)]


# =========================================================
# 파싱 디버그
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


# =========================================================
# 유효 데이터만
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
st.subheader("📊 전체 요약 지표")

total_sec = df_valid["지속시간_초"].sum()
k1, k2, k3, k4 = st.columns(4)
k1.metric("총 알람 건수", f"{len(df_valid):,} 건")
k2.metric("고유 알람 종류", f"{df_valid['알람명'].nunique():,} 종")
k3.metric("총 누적지속시간", seconds_to_hm(total_sec))
k4.metric("평균 지속시간", seconds_to_hm(df_valid["지속시간_초"].mean()))


# =========================================================
# 파일별 요약
# =========================================================
st.markdown("---")
st.subheader("📁 파일별 요약")

file_summary = df_valid.groupby("파일명").agg(
    알람건수=("알람명", "count"),
    고유알람수=("알람명", "nunique"),
    누적지속_초=("지속시간_초", "sum"),
).reset_index()
file_summary["누적지속시간"] = file_summary["누적지속_초"].apply(seconds_to_hm)
file_summary["평균지속시간"] = (file_summary["누적지속_초"] / file_summary["알람건수"]).apply(seconds_to_hm)
file_summary = file_summary[["파일명", "알람건수", "고유알람수", "누적지속시간", "평균지속시간"]]

st.dataframe(file_summary, use_container_width=True)


# =========================================================
# 알람별 집계
# =========================================================
agg = df_valid.groupby("알람명").agg(
    발생빈도=("알람명", "count"),
    누적지속_초=("지속시간_초", "sum"),
).reset_index()

agg["누적지속시간_시간"] = (agg["누적지속_초"] / 3600).round(2)
agg["누적지속시간(시간+분)"] = agg["누적지속_초"].apply(seconds_to_hm)

def minmax(s):
    if s.max() == s.min():
        return pd.Series([0] * len(s), index=s.index)
    return (s - s.min()) / (s.max() - s.min())

agg["_freq_norm"] = minmax(agg["발생빈도"])
agg["_dur_norm"] = minmax(agg["누적지속시간_시간"])
agg["종합점수"] = (agg["_freq_norm"] * w1 + agg["_dur_norm"] * w2).round(4)

agg_sorted = agg.sort_values("종합점수", ascending=False).reset_index(drop=True)


# =========================================================
# TOP N
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

tab1, tab2, tab3, tab4 = st.tabs(["발생빈도", "누적지속시간(h)", "종합점수", "파일별 비교"])

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

with tab4:
    # 파일별 × 알람 TOP 비교 (스택 막대)
    top_alarms = top_df["알람명"].tolist()
    comp = (
        df_valid[df_valid["알람명"].isin(top_alarms)]
        .groupby(["파일명", "알람명"])
        .agg(발생빈도=("알람명", "count"),
             누적지속_초=("지속시간_초", "sum"))
        .reset_index()
    )
    comp["누적지속시간_시간"] = (comp["누적지속_초"] / 3600).round(2)

    fig = px.bar(
        comp, x="알람명", y="발생빈도", color="파일명",
        title=f"파일별 TOP {top_n} 알람 발생빈도 비교",
        barmode="group",
    )
    fig.update_layout(height=500, xaxis_tickangle=-30)
    st.plotly_chart(fig, use_container_width=True)

    fig2 = px.bar(
        comp, x="알람명", y="누적지속시간_시간", color="파일명",
        title=f"파일별 TOP {top_n} 알람 누적지속시간(h) 비교",
        barmode="group",
        labels={"누적지속시간_시간": "누적지속시간 (h)"},
    )
    fig2.update_layout(height=500, xaxis_tickangle=-30)
    st.plotly_chart(fig2, use_container_width=True)


# =========================================================
# 다운로드
# =========================================================
st.markdown("---")
st.subheader("💾 결과 다운로드")

download_df = agg_sorted[["알람명", "발생빈도", "누적지속시간(시간+분)",
                          "누적지속시간_시간", "종합점수"]]

col_a, col_b = st.columns(2)
with col_a:
    csv1 = download_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 알람별 집계 CSV",
        data=csv1,
        file_name="알람_분석_결과.csv",
        mime="text/csv",
    )
with col_b:
    csv2 = file_summary.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 파일별 요약 CSV",
        data=csv2,
        file_name="파일별_요약.csv",
        mime="text/csv",
    )
