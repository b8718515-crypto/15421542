import re
import os
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go


# =========================================================
# 페이지 기본 설정
# =========================================================
st.set_page_config(
    page_title="알람 분석 대시보드",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================================================
# 🎨 커스텀 CSS (다크 테마 + 청록 액센트)
# =========================================================
st.markdown("""
<style>
    /* 전체 배경 */
    .stApp {
        background-color: #0E1117;
    }
    
    /* 타이틀 영역 */
    .dashboard-header {
        background: linear-gradient(90deg, #1C1F26 0%, #0E1117 100%);
        padding: 20px 30px;
        border-radius: 10px;
        border-left: 4px solid #00E5FF;
        margin-bottom: 20px;
    }
    .dashboard-title {
        color: #FAFAFA;
        font-size: 28px;
        font-weight: 700;
        margin: 0;
    }
    .dashboard-subtitle {
        color: #8B92A0;
        font-size: 13px;
        margin-top: 5px;
    }
    
    /* KPI 카드 */
    .kpi-card {
        background-color: #1C1F26;
        padding: 20px;
        border-radius: 10px;
        border-left: 3px solid #00E5FF;
        height: 110px;
    }
    .kpi-card-orange { border-left-color: #FF6B35; }
    .kpi-card-green  { border-left-color: #00E676; }
    .kpi-card-yellow { border-left-color: #FFD600; }
    .kpi-card-purple { border-left-color: #B388FF; }
    
    .kpi-label {
        color: #8B92A0;
        font-size: 12px;
        letter-spacing: 0.5px;
        font-weight: 600;
    }
    .kpi-value {
        color: #FAFAFA;
        font-size: 28px;
        font-weight: 700;
        margin-top: 8px;
    }
    .kpi-sub {
        display: none;
    }
    
    /* 섹션 헤더 */
    .section-header {
        color: #8B92A0;
        font-size: 13px;
        letter-spacing: 1px;
        font-weight: 600;
        margin-top: 20px;
        margin-bottom: 10px;
    }
    
    /* 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background-color: #1C1F26;
        padding: 5px;
        border-radius: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        color: #8B92A0;
        border-radius: 6px;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #00E5FF !important;
        color: #0E1117 !important;
        font-weight: 700;
    }
    
    /* 데이터프레임 */
    .stDataFrame {
        background-color: #1C1F26;
        border-radius: 8px;
    }
    
    /* 구분선 숨김 */
    hr { border-color: #2A2E37; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# 대시보드 헤더
# =========================================================
st.markdown("""
<div class="dashboard-header">
    <div class="dashboard-title">🚨 알람 발생 이력 분석 대시보드</div>
    <div class="dashboard-subtitle">라인별(대입경A/대입경B/단결정/열처리) TOP · 전체 TOP · 누적지속시간 · 종합점수 기반 분석</div>
</div>
""", unsafe_allow_html=True)


# =========================================================
# 공용 데이터 폴더
# =========================================================
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

LINES = ["4A", "4B", "4C", "4X"]

# 🆕 라인 표시용 한글 라벨
LINE_LABELS = {
    "4A": "4라인 대입경A",
    "4B": "4라인 대입경B",
    "4C": "4라인 단결정",
    "4X": "4라인 열처리",
    "미분류": "미분류",
}

# 라인별 색상 (다크 테마 어울림)
LINE_COLORS = {
    "4A": "#00E5FF",   # cyan
    "4B": "#00E676",   # green
    "4C": "#FFD600",   # yellow
    "4X": "#FF6B35",   # orange
    "미분류": "#8B92A0",
}

# 🆕 한글 라벨 기반 색상 매핑 (차트용)
LINE_COLORS_LABEL = {LINE_LABELS[k]: v for k, v in LINE_COLORS.items()}


# Plotly 다크 테마 공통 레이아웃
def apply_dark_theme(fig, height=400):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#1C1F26",
        plot_bgcolor="#1C1F26",
        font=dict(color="#FAFAFA", size=11),
        height=height,
        margin=dict(l=20, r=20, t=50, b=20),
        title_font=dict(size=14, color="#FAFAFA"),
        xaxis=dict(gridcolor="#2A2E37", zerolinecolor="#2A2E37"),
        yaxis=dict(gridcolor="#2A2E37", zerolinecolor="#2A2E37"),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#2A2E37"),
    )
    return fig


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


def render_kpi_card(label, value, sub="", accent="cyan"):
    """커스텀 KPI 카드 렌더링"""
    color_class = {
        "cyan": "",
        "orange": "kpi-card-orange",
        "green": "kpi-card-green",
        "yellow": "kpi-card-yellow",
        "purple": "kpi-card-purple",
    }.get(accent, "")
    dot_color = {
        "cyan": "#00E5FF",
        "orange": "#FF6B35",
        "green": "#00E676",
        "yellow": "#FFD600",
        "purple": "#B388FF",
    }.get(accent, "#00E5FF")
    
    st.markdown(f"""
    <div class="kpi-card {color_class}">
        <div class="kpi-label"><span style="color:{dot_color};">●</span> {label}</div>
        <div class="kpi-value">{value}</div>
        <div class="kpi-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


# =========================================================
# 캐시된 로더
# =========================================================
@st.cache_data(show_spinner=False)
def load_all_files(file_signatures: tuple) -> pd.DataFrame:
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
# 사이드바
# =========================================================
with st.sidebar:
    st.markdown("### 📂 공유 파일 관리")
    st.caption("업로드한 파일은 **서버에 저장**되어 모든 사용자가 함께 봅니다.")

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

    st.markdown("#### 🗂️ 저장된 파일")
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
    st.markdown("#### ⚙️ 종합점수 가중치")
    w1 = st.slider("발생빈도 가중치", 0.0, 1.0, 0.5, 0.05)
    w2 = 1.0 - w1
    st.caption(f"지속시간(시간) 가중치: **{w2:.2f}**")

    st.markdown("---")
    top_n = st.number_input("TOP N 표시", min_value=3, max_value=30, value=8, step=1)


# =========================================================
# 데이터 로드
# =========================================================
signatures = get_file_signatures()

if not signatures:
    st.info("👈 좌측에서 알람 이력 파일을 업로드하세요. 업로드된 파일은 서버에 저장되어 공유됩니다.")
    st.stop()

df_raw = load_all_files(signatures)

# =========================================================
# 컬럼 자동 감지
# =========================================================
cols = [c for c in df_raw.columns.tolist() if c != "_파일명"]

def _guess(keywords, default=None):
    for c in cols:
        for k in keywords:
            if k in str(c):
                return c
    return default if default is not None else (cols[0] if cols else None)

col_alarm = _guess(["알람", "Alarm", "MSG", "메시지"])
col_start = _guess(["발생", "시작", "Start", "On"])
col_end   = _guess(["해제", "종료", "End", "Off", "복구"])

# =========================================================
# 데이터 정제
# =========================================================
df = df_raw[[col_alarm, col_start, col_end, "_파일명"]].copy()
df.columns = ["알람명", "발생시간", "해제시간", "파일명"]
df["라인"] = df["파일명"].apply(detect_line)
df["발생시간"] = robust_to_datetime(df["발생시간"])
df["해제시간"] = robust_to_datetime(df["해제시간"])
df["지속시간_초"] = (df["해제시간"] - df["발생시간"]).dt.total_seconds()

df_valid = df.dropna(subset=["발생시간", "해제시간"]).copy()
df_valid = df_valid[df_valid["지속시간_초"] > 0]

if len(df_valid) == 0:
    st.error("유효한 지속시간 데이터가 없습니다.")
    st.stop()


# =========================================================
# 🎯 상단 KPI 카드 (5개)
# =========================================================
st.markdown('<div class="section-header">━━ 전체 요약</div>', unsafe_allow_html=True)

total_sec = df_valid["지속시간_초"].sum()
unresolved = df["해제시간"].isna().sum()

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    render_kpi_card("전체 알람", f"{len(df_valid):,} 건", "", "cyan")
with k2:
    render_kpi_card("고유 알람", f"{df_valid['알람명'].nunique():,} 종", "", "green")
with k3:
    render_kpi_card("누적 지속시간", seconds_to_hm(total_sec), "", "yellow")
with k4:
    render_kpi_card("평균 지속시간", seconds_to_hm(df_valid["지속시간_초"].mean()), "", "orange")
with k5:
    render_kpi_card("활성 라인", f"{df_valid['라인'].nunique()} 개", "", "purple")


# =========================================================
# 🎯 중단: 라인별 파이 + 라인별 도넛
# =========================================================
st.markdown('<div class="section-header">━━ 라인별 분포</div>', unsafe_allow_html=True)

col_left, col_right = st.columns([1.3, 1.7])

with col_left:
    # 라인별 알람 건수 - 도넛 차트
    line_counts = df_valid.groupby("라인").size().reset_index(name="건수")
    line_counts["라인표시"] = line_counts["라인"].map(LINE_LABELS)  # 🆕 한글 라벨
    
    fig = go.Figure(go.Pie(
        labels=line_counts["라인표시"],
        values=line_counts["건수"],
        hole=0.6,
        marker=dict(colors=[LINE_COLORS.get(l, "#8B92A0") for l in line_counts["라인"]]),
        textinfo="label+percent",
        textfont=dict(color="white", size=11),
    ))
    fig.update_layout(
        title="라인별 알람 분포",
        annotations=[dict(text=f"<b>{len(df_valid):,}</b><br><span style='font-size:11px;color:#8B92A0'>전체</span>",
                          font=dict(size=20, color="white"), showarrow=False)]
    )
    apply_dark_theme(fig, height=380)
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    # 라인별 요약 - 미니 도넛
    st.markdown("**라인별 비율 (알람 건수 기준)**")
    line_summary = df_valid.groupby("라인").size().reset_index(name="건수")
    total = line_summary["건수"].sum()
    
    donut_cols = st.columns(len(line_summary))
    for dcol, (_, row) in zip(donut_cols, line_summary.iterrows()):
        with dcol:
            pct = round(row["건수"] / total * 100, 1)
            color = LINE_COLORS.get(row["라인"], "#8B92A0")
            line_label = LINE_LABELS.get(row["라인"], row["라인"])  # 🆕 한글 라벨
            
            fig = go.Figure(go.Pie(
                values=[pct, 100 - pct],
                hole=0.75,
                marker=dict(colors=[color, "#2A2E37"]),
                showlegend=False,
                textinfo="none",
                sort=False,
            ))
            fig.update_layout(
                paper_bgcolor="#1C1F26",
                height=180,
                margin=dict(l=0, r=0, t=10, b=0),
                annotations=[dict(text=f"<b>{pct}%</b>",
                                  font=dict(size=18, color="white"), showarrow=False)],
            )
            st.plotly_chart(fig, use_container_width=True, key=f"mini_donut_{row['라인']}")
            st.markdown(
                f"<center><span style='color:{color};font-weight:600;font-size:12px;'>{line_label}</span>"
                f"<br><small style='color:#8B92A0'>{row['건수']:,} 건</small></center>",
                unsafe_allow_html=True
            )


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


def render_top(title: str, data: pd.DataFrame, key_prefix: str, accent_color="#00E5FF"):
    if len(data) == 0:
        st.warning(f"⚠️ **{title}** : 유효 데이터 없음")
        return
    agg = build_agg(data)
    top_df = agg.head(top_n).copy()
    top_df.index = top_df.index + 1

    sec_sum = data["지속시간_초"].sum()

    a, b, c = st.columns(3)
    with a:
        render_kpi_card("알람 건수", f"{len(data):,} 건", "", "cyan")
    with b:
        render_kpi_card("고유 알람", f"{data['알람명'].nunique():,} 종", "", "green")
    with c:
        render_kpi_card("누적 지속시간", seconds_to_hm(sec_sum), "", "yellow")

    st.markdown(f"#### 🏆 {title} - TOP {top_n}")
    st.dataframe(
        top_df[["알람명", "발생빈도", "누적지속시간(시간+분)",
                "누적지속시간_시간", "종합점수"]],
        use_container_width=True,
    )

    t1, t2, t3 = st.tabs(["📊 발생빈도", "⏱️ 누적지속시간", "⭐ 종합점수"])
    with t1:
        fig = px.bar(top_df.sort_values("발생빈도"),
                     x="발생빈도", y="알람명", orientation="h",
                     text="발생빈도",
                     color_discrete_sequence=[accent_color])
        fig.update_traces(textposition="outside")
        apply_dark_theme(fig, height=450)
        st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_freq")
    with t2:
        fig = px.bar(top_df.sort_values("누적지속시간_시간"),
                     x="누적지속시간_시간", y="알람명", orientation="h",
                     text="누적지속시간(시간+분)",
                     labels={"누적지속시간_시간": "누적지속시간 (h)"},
                     color_discrete_sequence=["#FFD600"])
        fig.update_traces(textposition="outside")
        apply_dark_theme(fig, height=450)
        st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_dur")
    with t3:
        fig = px.bar(top_df.sort_values("종합점수"),
                     x="종합점수", y="알람명", orientation="h",
                     text="종합점수",
                     color_discrete_sequence=["#B388FF"])
        fig.update_traces(textposition="outside")
        apply_dark_theme(fig, height=450)
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
st.markdown('<div class="section-header">━━ 라인별 상세 분석</div>', unsafe_allow_html=True)

tab_all, tab_4a, tab_4b, tab_4c, tab_4x, tab_cmp = st.tabs(
    ["🌐 전체", "🅰️ 4라인 대입경A", "🅱️ 4라인 대입경B", "🅲 4라인 단결정", "❎ 4라인 열처리", "📊 라인 비교"]
)

with tab_all:
    render_top("전체", df_valid, "all", "#00E5FF")
with tab_4a:
    render_top("4라인 대입경A", df_valid[df_valid["라인"] == "4A"], "4a", LINE_COLORS["4A"])
with tab_4b:
    render_top("4라인 대입경B", df_valid[df_valid["라인"] == "4B"], "4b", LINE_COLORS["4B"])
with tab_4c:
    render_top("4라인 단결정", df_valid[df_valid["라인"] == "4C"], "4c", LINE_COLORS["4C"])
with tab_4x:
    render_top("4라인 열처리", df_valid[df_valid["라인"] == "4X"], "4x", LINE_COLORS["4X"])

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
    line_summary["라인명"] = line_summary["라인"].map(LINE_LABELS)  # 🆕

    st.dataframe(
        line_summary[["라인명", "알람건수", "고유알람수", "누적지속시간", "평균지속시간"]],
        use_container_width=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(line_summary, x="라인명", y="알람건수",
                     text="알람건수", color="라인명",
                     color_discrete_map=LINE_COLORS_LABEL)
        fig.update_traces(textposition="outside")
        apply_dark_theme(fig, height=380)
        fig.update_layout(title="라인별 알람 건수")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(line_summary, x="라인명", y="누적지속시간_시간",
                     text="누적지속시간", color="라인명",
                     labels={"누적지속시간_시간": "누적지속시간 (h)"},
                     color_discrete_map=LINE_COLORS_LABEL)
        fig.update_traces(textposition="outside")
        apply_dark_theme(fig, height=380)
        fig.update_layout(title="라인별 누적지속시간")
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
    comp["라인명"] = comp["라인"].map(LINE_LABELS)  # 🆕

    fig1 = px.bar(comp, x="알람명", y="발생빈도", color="라인명",
                  barmode="stack", color_discrete_map=LINE_COLORS_LABEL)
    fig1.update_layout(xaxis_tickangle=-30, title=f"전체 TOP {top_n} 알람 - 라인별 발생빈도")
    apply_dark_theme(fig1, height=500)
    st.plotly_chart(fig1, use_container_width=True)

    fig2 = px.bar(comp, x="알람명", y="누적지속시간_시간", color="라인명",
                  barmode="stack",
                  labels={"누적지속시간_시간": "누적지속시간 (h)"},
                  color_discrete_map=LINE_COLORS_LABEL)
    fig2.update_layout(xaxis_tickangle=-30, title=f"전체 TOP {top_n} 알람 - 라인별 누적지속시간(h)")
    apply_dark_theme(fig2, height=500)
    st.plotly_chart(fig2, use_container_width=True)
