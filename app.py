"""4라인 설비 알람 TOP5 대시보드 (정비팀용)"""
import streamlit as st
import pandas as pd
import plotly.express as px

from src.data_loader import load_all_alarms, load_alarm_file, filter_data
from src.analyzer import compute_top5, hourly_trend
from src.report import to_excel, to_pdf

st.set_page_config(page_title="4라인 알람 TOP5", page_icon="🔧", layout="wide")

st.title("🔧 4라인 설비 알람 TOP5 대시보드")
st.caption("정비팀용 · L2 알람 이력 기반 · 발생빈도 + 누적지속시간 스코어링")

# ─── 데이터 로드 ───
st.sidebar.header("📁 데이터")
uploaded_files = st.sidebar.file_uploader(
    "알람 CSV 업로드 (4A, 4B, 4C, 4X)",
    type=["csv"],
    accept_multiple_files=True,
)

if uploaded_files:
    dfs = []
    for f in uploaded_files:
        try:
            tmp = load_alarm_file(f, source_name=f.name.replace(".csv", ""))
            dfs.append(tmp)
        except Exception as e:
            st.warning(f"{f.name} 로드 실패: {e}")
    df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
else:
    df = load_all_alarms("data")

if df.empty:
    st.error("데이터가 없습니다. 사이드바에서 CSV를 업로드하거나 `data/` 폴더에 파일을 두세요.")
    st.stop()

# ─── 필터 ───
st.sidebar.header("🔎 필터")
line_options = ["전체"] + sorted(df["line_name"].dropna().unique().tolist())
line_sel = st.sidebar.selectbox("공정라인명", line_options)

eq_pool = df if line_sel == "전체" else df[df["line_name"] == line_sel]
eq_options = ["전체"] + sorted(eq_pool["equipment_group"].dropna().unique().tolist())
eq_sel = st.sidebar.selectbox("설비중분류", eq_options)

date_min = df["start_time"].min().date()
date_max = df["start_time"].max().date()
target_date = st.sidebar.date_input(
    "조회일자 (1일 기준)",
    value=date_max,
    min_value=date_min,
    max_value=date_max,
)

st.sidebar.header("⚖️ 스코어 가중치")
w_freq = st.sidebar.slider("발생빈도 가중치", 0.0, 1.0, 0.5, 0.1)
w_dur = round(1.0 - w_freq, 2)
st.sidebar.caption(f"누적지속시간 가중치: **{w_dur}**")

# ─── 필터링 ───
filtered = filter_data(df, line_sel, eq_sel, target_date)

# ─── KPI ───
col1, col2, col3, col4 = st.columns(4)
col1.metric("총 알람 건수", f"{len(filtered):,} 건")
col2.metric("설비중분류 종류", f"{filtered['equipment_group'].nunique()} 종")
col3.metric("총 지속시간(분)", f"{filtered['duration_sec'].sum()/60:,.1f}")
avg_dur = filtered['duration_sec'].mean() if len(filtered) else 0
col4.metric("평균 지속시간(초)", f"{avg_dur:,.1f}")

st.divider()

# ─── TOP5 ───
st.subheader(f"🏆 TOP 5 설비중분류 알람 ({target_date})")
top5 = compute_top5(filtered, w_freq=w_freq, w_dur=w_dur, top_n=5)

if top5.empty:
    st.warning("해당 조건에 데이터가 없습니다.")
else:
    display = top5[[
        "equipment_group", "freq", "total_duration_min",
        "max_duration_min", "score"
    ]].copy()
    display.columns = ["설비중분류", "발생빈도", "누적시간(분)", "최대지속(분)", "스코어"]
    display.index = display.index + 1
    display.index.name = "순위"

    st.dataframe(
        display.style.format({
            "스코어": "{:.3f}",
            "누적시간(분)": "{:.1f}",
            "최대지속(분)": "{:.1f}",
        }),
        use_container_width=True,
    )

    # ─── 차트 ───
    c1, c2 = st.columns(2)
    with c1:
        fig1 = px.bar(
            top5, x="equipment_group", y="freq",
            title="발생 빈도 (건)",
            labels={"equipment_group": "설비중분류", "freq": "발생 건수"},
            color="freq", color_continuous_scale="Blues",
        )
        st.plotly_chart(fig1, use_container_width=True)
    with c2:
        fig2 = px.bar(
            top5, x="equipment_group", y="total_duration_min",
            title="누적 지속시간 (분)",
            labels={"equipment_group": "설비중분류", "total_duration_min": "누적 분"},
            color="total_duration_min", color_continuous_scale="Reds",
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ─── 시간대별 추이 ───
    st.subheader("📈 시간대별 발생 추이 (0~23시)")
    trend = hourly_trend(filtered)
    if not trend.empty:
        fig3 = px.line(trend, x="hour", y="count", markers=True,
                       labels={"hour": "시간대", "count": "발생 건수"})
        fig3.update_xaxes(dtick=1)
        st.plotly_chart(fig3, use_container_width=True)

    # ─── 원본 이력 ───
    with st.expander("📋 필터된 원본 알람 이력 보기"):
        show_cols = ["start_time", "end_time", "duration_str",
                     "line_name", "equipment_group", "source"]
        show_cols = [c for c in show_cols if c in filtered.columns]
        st.dataframe(
            filtered[show_cols].sort_values("start_time", ascending=False),
            use_container_width=True, height=400,
        )

    # ─── 다운로드 ───
    st.divider()
    st.subheader("📥 리포트 다운로드")
    d1, d2 = st.columns(2)
    report_df = display.reset_index()
    with d1:
        st.download_button(
            "📊 Excel 다운로드",
            data=to_excel(report_df),
            file_name=f"alarm_top5_{target_date}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with d2:
        st.download_button(
            "📄 PDF 다운로드",
            data=to_pdf(report_df, title=f"4라인 알람 TOP5 ({target_date})"),
            file_name=f"alarm_top5_{target_date}.pdf",
            mime="application/pdf",
        )
