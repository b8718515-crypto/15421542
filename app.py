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
# 🎨 커스텀 CSS
# =========================================================
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    
    .dashboard-header {
        background: linear-gradient(90deg, #1C1F26 0%, #0E1117 100%);
        padding: 20px 30px;
        border-radius: 16px;
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
    
    /* 기본(큰) KPI 카드 - 상단 요약용 */
    .kpi-card {
        background-color: #1C1F26;
        padding: 20px;
        border-radius: 16px;
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
    .kpi-sub { display: none; }
    
    /* 작은 KPI 카드 - 라인별 상세용 */
    .kpi-card-sm {
        background-color: #1C1F26;
        padding: 8px 16px;
        border-radius: 14px;
        border-left: 3px solid #00E5FF;
        height: 52px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .kpi-card-sm.sm-orange { border-left-color: #FF6B35; }
    .kpi-card-sm.sm-green  { border-left-color: #00E676; }
    .kpi-card-sm.sm-yellow { border-left-color: #FFD600; }
    .kpi-card-sm.sm-purple { border-left-color: #B388FF; }
    
    .kpi-sm-label {
        color: #8B92A0;
        font-size: 11px;
        font-weight: 600;
    }
    .kpi-sm-value {
        color: #FAFAFA;
        font-size: 16px;
        font-weight: 700;
    }
    
    .section-header {
        color: #8B92A0;
        font-size: 13px;
        letter-spacing: 1px;
        font-weight: 600;
        margin-top: 20px;
        margin-bottom: 10px;
    }
    
    /* ✨ 탭 라운드 - 고급화 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: #1C1F26;
        padding: 8px;
        border-radius: 14px;
        border: 1px solid #2A2E37;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        color: #8B92A0;
        border-radius: 10px;
        padding: 10px 20px;
        transition: all 0.25s ease;
        font-weight: 500;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background-color: rgba(0, 229, 255, 0.08);
        color: #FAFAFA;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #00E5FF 0%, #00B8D4 100%) !important;
        color: #0E1117 !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 12px rgba(0, 229, 255, 0.35),
                    0 0 0 1px rgba(0, 229, 255, 0.2);
        transform: translateY(-1px);
    }
    /* 탭 하이라이트 밑줄 제거 */
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: transparent !important;
    }
    .stTabs [data-baseweb="tab-border"] {
        background-color: transparent !important;
    }
    
    /* 데이터프레임 라운드 */
    .stDataFrame {
        background-color: #1C1F26;
        border-radius: 14px;
        overflow: hidden;
    }
    
    /* Plotly 차트 컨테이너 라운드 */
    .js-plotly-plot, .plot-container {
        border-radius: 16px !important;
        overflow: hidden;
    }
    
    /* 버튼 라운드 */
    .stButton>button, .stDownloadButton>button {
        border-radius: 10px;
    }
    
    /* 파일 업로더 라운드 */
    .stFileUploader > div {
        border-radius: 14px;
    }
    
    /* ✨ 라인별 비율 미니 도넛 카드 */
    .mini-donut-card {
        background-color: #1C1F26;
        border-radius: 16px;
        padding: 14px 12px 24px 12px;
        border: 1px solid #2A2E37;
        margin-bottom: 8px;
    }
    .mini-donut-label {
        text-align: center;
        font-weight: 700;
        font-size: 13px;
        margin-top: 10px;
    }
    .mini-donut-sub {
        text-align: center;
        color: #8B92A0;
        font-size: 12px;
        margin-top: 6px;
        padding-bottom: 8px;
    }
    
    hr { border-color: #2A2E37; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# 대시보드 헤더
# =========================================================
st.markdown("""
<div class="dashboard-header">
    <div class="dashboard-title">🚨 알람 발생 이력 분석 대시보드</div>
    <div class="dashboard-subtitle">라인별(대입경A/대입경B/단결정/열처리) 발생빈도 기반 TOP 분석</div>
</div>
""", unsafe_allow_html=True)


# =========================================================
# 공용 데이터 폴더
# =========================================================
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

LINES = ["4A", "4B", "4C", "4X"]

LINE_LABELS = {
    "4A": "4라인 대입경A",
    "4B": "4라인 대입경B",
    "4C": "4라인 단결정",
    "4X": "4라인 열처리",
    "미분류": "미분류",
}

LINE_COLORS = {
    "4A": "#00E5FF",
    "4B": "#00E676",
    "4C": "#FFD600",
    "4X": "#FF6B35",
    "미분류": "#8B92A0",
}

LINE_COLORS_LABEL = {LINE_LABELS[k]: v for k, v in LINE_COLORS.items()}


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


def render_kpi_card_sm(label, value, accent="cyan"):
    """작은 KPI 카드 - 라인별 상세 분석용"""
    color_class = {
        "cyan": "",
        "orange": "sm-orange",
        "green": "sm-green",
        "yellow": "sm-yellow",
        "purple": "sm-purple",
    }.get(accent, "")
    dot_color = {
        "cyan": "#00E5FF",
        "orange": "#FF6B35",
        "green": "#00E676",
        "yellow": "#FFD600",
        "purple": "#B388FF",
    }.get(accent, "#00E5FF")
    
    st.markdown(f"""
    <div class="kpi-card-sm {color_class}">
        <div class="kpi-sm-label"><span style="color:{dot_color};">●</span> {label}</div>
        <div class="kpi-sm-value">{value}</div>
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

# =========================================================
# 데이터 정제
# =========================================================
df = df_raw[[col_alarm, col_start, "_파일명"]].copy()
df.columns = ["알람명", "발생시간", "파일명"]
df["라인"] = df["파일명"].apply(detect_line)
df["발생시간"] = robust_to_datetime(df["발생시간"])

df_valid = df.dropna(subset=["알람명"]).copy()
df_valid = df_valid[df_valid["알람명"].astype(str).str.strip() != ""]

if len(df_valid) == 0:
    st.error("유효한 알람 데이터가 없습니다.")
    st.stop()


# =========================================================
# 🎯 상단 KPI 카드 (3개)
# =========================================================
st.markdown('<div class="section-header">━━ 전체 요약</div>', unsafe_allow_html=True)

k1, k2, k3 = st.columns(3)
with k1:
    render_kpi_card("전체 알람", f"{len(df_valid):,} 건", "", "cyan")
with k2:
    render_kpi_card("고유 알람", f"{df_valid['알람명'].nunique():,} 종", "", "green")
with k3:
    render_kpi_card("활성 라인", f"{df_valid['라인'].nunique()} 개", "", "purple")


# =========================================================
# 🎯 중단: 라인별 분포
# =========================================================
st.markdown('<div class="section-header">━━ 라인별 분포</div>', unsafe_allow_html=True)

col_left, col_right = st.columns([1.3, 1.7])

with col_left:
    line_counts = df_valid.groupby("라인").size().reset_index(name="건수")
    line_counts["라인표시"] = line_counts["라인"].map(LINE_LABELS)
    
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
    st.markdown("**라인별 비율 (알람 건수 기준)**")
    line_summary = df_valid.groupby("라인").size().reset_index(name="건수")
    total = line_summary["건수"].sum()
    
    donut_cols = st.columns(len(line_summary))
    for dcol, (_, row) in zip(donut_cols, line_summary.iterrows()):
        with dcol:
            pct = round(row["건수"] / total * 100, 1)
            color = LINE_COLORS.get(row["라인"], "#8B92A0")
            line_label = LINE_LABELS.get(row["라인"], row["라인"])
            
            fig = go.Figure(go.Pie(
                values=[pct, 100 - pct],
                hole=0.75,
                marker=dict(colors=[color, "#2A2E37"]),
                showlegend=False,
                textinfo="none",
                sort=False,
            ))
            # ✨ 상하 여백 균등하게 (t=20, b=20)
            fig.update_layout(
                paper_bgcolor="#1C1F26",
                plot_bgcolor="#1C1F26",
                height=200,
                margin=dict(l=10, r=10, t=20, b=20),
                annotations=[dict(text=f"<b>{pct}%</b>",
                                  font=dict(size=18, color="white"), showarrow=False)],
            )
            
            # ✨ 미니 도넛 카드 컨테이너 시작 (하단 여백 확대)
            st.markdown('<div class="mini-donut-card">', unsafe_allow_html=True)
            st.plotly_chart(fig, use_container_width=True, key=f"mini_donut_{row['라인']}")
            st.markdown(
                f"""
                <div class="mini-donut-label" style="color:{color};">{line_label}</div>
                <div class="mini-donut-sub">{row['건수']:,} 건</div>
                """,
                unsafe_allow_html=True
            )
            st.markdown('</div>', unsafe_allow_html=True)


# =========================================================
# 🔄 집계
# =========================================================
def build_agg(data: pd.DataFrame) -> pd.DataFrame:
    if len(data) == 0:
        return pd.DataFrame(columns=["알람명", "발생빈도", "비율(%)"])
    agg = data.groupby("알람명").agg(
        발생빈도=("알람명", "count"),
    ).reset_index()
    total = agg["발생빈도"].sum()
    agg["비율(%)"] = (agg["발생빈도"] / total * 100).round(2)
    return agg.sort_values("발생빈도", ascending=False).reset_index(drop=True)


def render_top(title: str, data: pd.DataFrame, key_prefix: str, accent_color="#00E5FF"):
    if len(data) == 0:
        st.warning(f"⚠️ **{title}** : 유효 데이터 없음")
        return
    agg = build_agg(data)
    top_df = agg.head(top_n).copy()
    top_df.index = top_df.index + 1

    a, b = st.columns(2)
    with a:
        render_kpi_card_sm("알람 건수", f"{len(data):,} 건", "cyan")
    with b:
        render_kpi_card_sm("고유 알람", f"{data['알람명'].nunique():,} 종", "green")

    st.markdown(f"#### 🏆 {title} - 발생빈도 TOP {top_n}")
    st.dataframe(
        top_df[["알람명", "발생빈도", "비율(%)"]],
        use_container_width=True,
    )

    # 발생빈도 막대 차트
    fig = px.bar(top_df.sort_values("발생빈도"),
                 x="발생빈도", y="알람명", orientation="h",
                 text="발생빈도",
                 color_discrete_sequence=[accent_color])
    fig.update_traces(textposition="outside")
    apply_dark_theme(fig, height=480)
    
    # ✨ 제목을 오른쪽 아래로 이동 (구석 X, 여백 있음)
    fig.update_layout(
        title=dict(
            text=f"{title} - 발생빈도 TOP {top_n}",
            x=0.92,           # 오른쪽에서 약간 안쪽
            xanchor="right",
            y=0.05,           # 아래쪽에서 약간 위
            yanchor="bottom",
            font=dict(size=13, color="#8B92A0"),
        ),
        margin=dict(l=40, r=60, t=40, b=70),  # 하단·우측 여백 확대
    )
    st.plotly_chart(fig, use_container_width=True, key=f"{key_prefix}_freq")

    csv = agg[["알람명", "발생빈도", "비율(%)"]].to_csv(index=False).encode("utf-8-sig")
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
    ).reset_index()
    line_summary["라인명"] = line_summary["라인"].map(LINE_LABELS)

    st.dataframe(
        line_summary[["라인명", "알람건수", "고유알람수"]],
        use_container_width=True,
    )

    fig = px.bar(line_summary, x="라인명", y="알람건수",
                 text="알람건수", color="라인명",
                 color_discrete_map=LINE_COLORS_LABEL)
    fig.update_traces(textposition="outside")
    apply_dark_theme(fig, height=380)
    fig.update_layout(title="라인별 알람 건수")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### 🔍 전체 TOP 알람의 라인별 분포")
    overall_top = build_agg(df_valid).head(top_n)["알람명"].tolist()
    comp = (
        df_valid[df_valid["알람명"].isin(overall_top)]
        .groupby(["알람명", "라인"])
        .agg(발생빈도=("알람명", "count"))
        .reset_index()
    )
    comp["라인명"] = comp["라인"].map(LINE_LABELS)

    fig1 = px.bar(comp, x="알람명", y="발생빈도", color="라인명",
                  barmode="stack", color_discrete_map=LINE_COLORS_LABEL)
    fig1.update_layout(xaxis_tickangle=-30, title=f"전체 TOP {top_n} 알람 - 라인별 발생빈도")
    apply_dark_theme(fig1, height=500)
    st.plotly_chart(fig1, use_container_width=True)
