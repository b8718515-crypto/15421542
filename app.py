import re
import os
from pathlib import Path
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
st.caption("라인별(4A/4B/4C/4X) TOP · 전체 TOP · 누적지속시간(시간+분) · 종합점수 기반 분석")


# =========================================================
# 공용 데이터 폴더 (모든 사용자가 공유)
# =========================================================
# ⭐ app.py 파일이 있는 위치 기준으로 절대경로 고정
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

LINES = ["4A", "4B", "4C", "4X"]



# =========================================================
# 유틸: 견고한 datetime 파서
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
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
        "%Y%m%d %H%M%S", "%Y%m%d%H%M%S",
    ]
    for f in fmts:
        out = pd.to_datetime(s, format=f, errors="coerce")
        if out.notna().sum() > 0:
            return out

    return pd.to_datetime(pd.Series([None] * len(s)), errors="coerce")


# =========================================================
# 유틸
# =========================================================
def seconds_to_hm(total_seconds: float) -> str:
    if pd.isna(total_seconds) or total_seconds < 0:
        return "0시간 0분"
    total_seconds = int(total_seconds)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    return f"{h:,}시간 {m}분"


def detect_line(text: str) -> str:
    if not isinstance(text, str):
        return "미분류"
    t = text.upper()
    for ln in LINES:
        if re.search(rf"4[\s_\-]*{ln[1]}", t):
            return ln
    return "미분류"


def read_file_path(path: Path) -> pd.DataFrame:
    name = path.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(path)
    else:
        return pd.read_excel(path)


# =========================================================
# 캐시된 로더 (파일이 바뀌지 않으면 재사용)
# =========================================================
@st.cache_data(show_spinner=False)
def load_all_files(file_signatures: tuple) -> pd.DataFrame:
    """file_signatures: ((파일명, mtime, size), ...) — 변경 감지용"""
    frames = []
    for name, _, _ in file_signatures:
        p = DATA_DIR / name
        if not p.exists():
            continue
        try:
            d = read_file_path(p)
            d["_파일명"] = name
            frames.append(d)
        except Exception:
            pass
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def get_file_signatures():
    sigs = []
    for p in sorted(DATA_DIR.glob("*")):
        if p.is_file() and p.suffix.lower() in [".xlsx", ".xls", ".csv"]:
            st_ = p.stat()
            sigs.append((p.name, st_.st_mtime, st_.st_size))
    return tuple(sigs)


# =========================================================
# 사이드바 — 파일 관리
# =========================================================
with st.sidebar:
    st.header("📂 공유 파일 관리")
    st.caption("업로드한 파일은 **서버에 저장**되어 모든 사용자가 함께 봅니다.")

        # 파일 업로드 → 서버에 저장
    new_files = st.file_uploader(
        "파일 업로드 (여러 개 가능)",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
        key="uploader",
    )
    if new_files:
        saved_count = 0
        errors = []
        for f in new_files:
            try:
                save_path = DATA_DIR / f.name
                data = f.getbuffer()
                with open(save_path, "wb") as out:
                    out.write(data)
                # 저장 검증
                if save_path.exists() and save_path.stat().st_size > 0:
                    saved_count += 1
                else:
                    errors.append(f"{f.name}: 저장 실패(0바이트)")
            except Exception as e:
                errors.append(f"{f.name}: {e}")

        if saved_count > 0:
            st.success(f"✅ {saved_count}개 파일 저장 완료")
        if errors:
            for msg in errors:
                st.error(msg)

        st.cache_data.clear()
        st.rerun()

# ❌ 삭제 (또는 주석 처리)
with st.expander("🐛 시간 파싱 디버그"):
    st.write(...)
    st.dataframe(...)
    # ... 등등


    # 현재 서버에 저장된 파일 목록
    st.subheader("🗂️ 저장된 파일")
    saved = get_file_signatures()
    if not saved:
        st.info("아직 저장된 파일이 없습니다.")
    else:
        for name, mtime, size in saved:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"📄 **{name}**  \n<small>{size/1024:,.0f} KB</small>",
                         unsafe_allow_html=True)
            with col2:
                if st.button("🗑️", key=f"del_{name}", help="삭제"):
                    try:
                        (DATA_DIR / name).unlink()
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

        if st.button("🧹 전체 삭제", use_container_width=True):
            for name, _, _ in saved:
                try:
                    (DATA_DIR / name).unlink()
                except Exception:
                    pass
            st.cache_data.clear()
            st.rerun()

    st.markdown("---")
    st.subheader("종합점수 가중치")
    w1 = st.slider("발생빈도 가중치", 0.0, 1.0, 0.5, 0.05)
    w2 = 1.0 - w1
    st.caption(f"지속시간(시간) 가중치: **{w2:.2f}**")

    st.markdown("---")
    top_n = st.number_input("TOP N 표시", min_value=3, max_value=30, value=8, step=1)


# =========================================================
# 데이터 로드 (서버 폴더에서)
# =========================================================
signatures = get_file_signatures()

if not signatures:
    st.info("👈 좌측에서 알람 이력 파일을 업로드하세요. 업로드된 파일은 서버에 저장되어 공유됩니다.")
    st.stop()

df_raw = load_all_files(signatures)

# ❌ 삭제 (또는 주석)
# st.subheader("📁 현재 분석 중인 파일")
# info_df = pd.DataFrame(
#     [(n, f"{s/1024:,.0f} KB") for n, _, s in signatures],
#     columns=["파일명", "크기"],
# )
# st.dataframe(info_df, use_container_width=True)
# st.success(f"✅ 총 **{len(signatures)}개 파일** · **{len(df_raw):,} 행** 분석 중")


# =========================================================
# 컬럼 자동 매핑 (UI 숨김)
# =========================================================
cols = [c for c in df_raw.columns.tolist() if c != "_파일명"]

def guess(name_candidates):
    for c in cols:
        for k in name_candidates:
            if k in str(c):
                return c
    return cols[0]

col_alarm = guess(["알람", "Alarm", "MSG"])
col_start = guess(["발생", "시작", "Start", "On"])
col_end   = guess(["해제", "종료", "End", "Off", "복구"])
line_src  = "(자동 감지 - 파일명)"   # 기본값 고정



# =========================================================
# 데이터 정제
# =========================================================
df = df_raw[[col_alarm, col_start, col_end, "_파일명"]].copy()
df.columns = ["알람명", "발생시간", "해제시간", "파일명"]

if line_src == "(자동 감지 - 파일명)":
    df["라인"] = df["파일명"].apply(detect_line)
elif line_src == "(자동 감지 - 알람명)":
    df["라인"] = df["알람명"].apply(detect_line)
else:
    df["라인"] = df_raw[line_src].apply(detect_line)

df["발생시간"] = robust_to_datetime(df["발생시간"])
df["해제시간"] = robust_to_datetime(df["해제시간"])
df["지속시간_초"] = (df["해제시간"] - df["발생시간"]).dt.total_seconds()


# =========================================================
# 라인 감지 결과
# =========================================================
st.markdown("---")
st.subheader("🏭 라인 감지 결과")
line_counts = df["라인"].value_counts().reindex(LINES + ["미분류"], fill_value=0)
cc = st.columns(len(line_counts))
for i, (ln, cnt) in enumerate(line_counts.items()):
    cc[i].metric(ln, f"{cnt:,} 건")


# =========================================================
# 파싱 디버그
# =========================================================
with st.expander("🐞 시간 파싱 디버그"):
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("발생시간 파싱 성공", f"{df['발생시간'].notna().sum()}/{len(df)}")
    d2.metric("해제시간 파싱 성공", f"{df['해제시간'].notna().sum()}/{len(df)}")
    both_ok = (df["발생시간"].notna() & df["해제시간"].notna()).sum()
    d3.metric("양쪽 다 성공", f"{both_ok}")
    d4.metric("양의 지속시간 건수", f"{(df['지속시간_초'] > 0).sum()}")


# =========================================================
# 유효 데이터
# =========================================================
df_valid = df.dropna(subset=["발생시간", "해제시간"]).copy()
df_valid = df_valid[df_valid["지속시간_초"] > 0]

if len(df_valid) == 0:
    st.error("유효한 지속시간 데이터가 없습니다.")
    st.stop()


# =========================================================
# 전체 KPI
# =========================================================
st.markdown("---")
st.subheader("📊 전체 요약")

total_sec = df_valid["지속시간_초"].sum()
k1, k2, k3, k4 = st.columns(4)
k1.metric("총 알람 건수", f"{len(df_valid):,} 건")
k2.metric("고유 알람 종류", f"{df_valid['알람명'].nunique():,} 종")
k3.metric("총 누적지속시간", seconds_to_hm(total_sec))
k4.metric("평균 지속시간", seconds_to_hm(df_valid["지속시간_초"].mean()))


# =========================================================
# 집계 & 렌더 함수
# =========================================================
def build_agg(data: pd.DataFrame) -> pd.DataFrame:
    if len(data) == 0:
        return pd.DataFrame(columns=["알람명", "발생빈도", "누적지속시간(시간+분)",
                                     "누적지속시간_시간", "종합점수"])
    agg = data.groupby("알람명").agg(
        발생빈도=("알람명", "count"),
        누적지속_초=("지속시간_초", "sum"),
    ).reset_index()
    agg["누적지속시간_시간"] = (agg["누적지속_초"] / 3600).round(2)
    agg["누적지속시간(시간+분)"] = agg["누적지속_초"].apply(seconds_to_hm)

    def minmax(s):
        if s.max() == s.min():
            return pd.Series([0] * len(s), index=s.index)
        return (s - s.min()) / (s.max() - s.min())

    agg["_f"] = minmax(agg["발생빈도"])
    agg["_d"] = minmax(agg["누적지속시간_시간"])
    agg["종합점수"] = (agg["_f"] * w1 + agg["_d"] * w2).round(4)
    return agg.sort_values("종합점수", ascending=False).reset_index(drop=True)


def render_top(title: str, data: pd.DataFrame, key_prefix: str):
    if len(data) == 0:
        st.warning(f"⚠️ **{title}** : 유효 데이터 없음")
        return
    agg = build_agg(data)
    top_df = agg.head(top_n).copy()
    top_df.index = top_df.index + 1

    sec_sum = data["지속시간_초"].sum()
    a, b, c = st.columns(3)
    a.metric("알람 건수", f"{len(data):,} 건")
    b.metric("고유 알람", f"{data['알람명'].nunique():,} 종")
    c.metric("누적지속시간", seconds_to_hm(sec_sum))

    st.markdown(f"#### 🏆 {title} - TOP {top_n}")
    st.dataframe(
        top_df[["알람명", "발생빈도", "누적지속시간(시간+분)",
                "누적지속시간_시간", "종합점수"]],
        use_container_width=True,
    )

    t1, t2, t3 = st.tabs(["발생빈도", "누적지속시간", "종합점수"])
    with t1:
        fig = px.bar(top_df.sort_values("발생빈도"),
                     x="발생빈도", y="알람명", orientation="h",
                     text="발생빈도", title=f"{title} - 발생빈도 TOP {top_n}")
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_freq")
    with t2:
        fig = px.bar(top_df.sort_values("누적지속시간_시간"),
                     x="누적지속시간_시간", y="알람명", orientation="h",
                     text="누적지속시간(시간+분)",
                     title=f"{title} - 누적지속시간 TOP {top_n}",
                     labels={"누적지속시간_시간": "누적지속시간 (h)"})
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_dur")
    with t3:
        fig = px.bar(top_df.sort_values("종합점수"),
                     x="종합점수", y="알람명", orientation="h",
                     text="종합점수", title=f"{title} - 종합점수 TOP {top_n}")
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_score")

    csv = agg[["알람명", "발생빈도", "누적지속시간(시간+분)",
               "누적지속시간_시간", "종합점수"]].to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        f"📥 {title} 집계 CSV 다운로드",
        data=csv, file_name=f"알람_TOP_{title}.csv",
        mime="text/csv", key=f"{key_prefix}_dl",
    )


# =========================================================
# 라인별 TOP + 전체 TOP
# =========================================================
st.markdown("---")
st.subheader("🏭 라인별 · 전체 TOP 분석")

tab_all, tab_4a, tab_4b, tab_4c, tab_4x, tab_cmp = st.tabs(
    ["🌐 전체", "🅰️ 4A", "🅱️ 4B", "🅲 4C", "❎ 4X", "📊 라인 비교"]
)

with tab_all:
    render_top("전체", df_valid, "all")
with tab_4a:
    render_top("4A 라인", df_valid[df_valid["라인"] == "4A"], "4a")
with tab_4b:
    render_top("4B 라인", df_valid[df_valid["라인"] == "4B"], "4b")
with tab_4c:
    render_top("4C 라인", df_valid[df_valid["라인"] == "4C"], "4c")
with tab_4x:
    render_top("4X 라인", df_valid[df_valid["라인"] == "4X"], "4x")

with tab_cmp:
    st.markdown("#### 📊 라인별 요약")
    line_summary = df_valid.groupby("라인").agg(
        알람건수=("알람명", "count"),
        고유알람수=("알람명", "nunique"),
        누적지속_초=("지속시간_초", "sum"),
    ).reset_index()
    line_summary["누적지속시간"] = line_summary["누적지속_초"].apply(seconds_to_hm)
    line_summary["평균지속시간"] = (
        line_summary["누적지속_초"] / line_summary["알람건수"]
    ).apply(seconds_to_hm)
    line_summary["누적지속시간_시간"] = (line_summary["누적지속_초"] / 3600).round(2)

    st.dataframe(
        line_summary[["라인", "알람건수", "고유알람수", "누적지속시간", "평균지속시간"]],
        use_container_width=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(line_summary, x="라인", y="알람건수",
                     text="알람건수", title="라인별 알람 건수", color="라인")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(line_summary, x="라인", y="누적지속시간_시간",
                     text="누적지속시간", title="라인별 누적지속시간",
                     labels={"누적지속시간_시간": "누적지속시간 (h)"}, color="라인")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### 🔍 전체 TOP 알람의 라인별 분포")
    overall_top = build_agg(df_valid).head(top_n)["알람명"].tolist()
    comp = (
        df_valid[df_valid["알람명"].isin(overall_top)]
        .groupby(["알람명", "라인"])
        .agg(발생빈도=("알람명", "count"),
             누적지속_초=("지속시간_초", "sum"))
        .reset_index()
    )
    comp["누적지속시간_시간"] = (comp["누적지속_초"] / 3600).round(2)

    fig1 = px.bar(comp, x="알람명", y="발생빈도", color="라인",
                  title=f"전체 TOP {top_n} 알람 - 라인별 발생빈도", barmode="stack")
    fig1.update_layout(xaxis_tickangle=-30, height=500)
    st.plotly_chart(fig1, use_container_width=True)

    fig2 = px.bar(comp, x="알람명", y="누적지속시간_시간", color="라인",
                  title=f"전체 TOP {top_n} 알람 - 라인별 누적지속시간(h)",
                  barmode="stack", labels={"누적지속시간_시간": "누적지속시간 (h)"})
    fig2.update_layout(xaxis_tickangle=-30, height=500)
    st.plotly_chart(fig2, use_container_width=True)
