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
# ===================================================f======
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    
    .dashboard-header {
        background: linear-gradient(90deg, #1C1F26 0%, #1A1D26 100%);
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
    .kpi-sub { display: none; }
    
    .section-header {
        color: #8B92A0;
        font-size: 13px;
        letter-spacing: 1px;
        font-weight: 600;
        margin-top: 20px;
        margin-bottom: 10px;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background-color: #8B92A0;
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
        background-color: #2A2E37 !important;
        color: #1A1D26 !important;
        font-weight: 700;
    }
    
    .stDataFrame {
        background-color: #1C1F26;
        border-radius: 8px;
    }
    
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
# 사이드바 (가중치 슬라이더 제거)
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
# 컬럼 자동 감지 (지속시간 불필요 → 알람명/발생시간만 있어도 OK)
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

# 알람명이 있는 행만 유효 데이터로 사용
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

# ===== 라인별 분포 카드 스타일 (전체 요약 카드와 동일 톤) =====
st.markdown("""
<style>
/* 마커가 포함된 컨테이너 = 라인별 분포 카드 */
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div > div > .dist-card-marker) {
    background-color: #1A1D26 !important;   /* ← 전체 요약과 동일 (Streamlit 기본 배경) */
    border: 1px solid #262730 !important;   /* ← 얇은 다크 보더 */
    border-radius: 10px !important;
    padding: 20px 25px !important;
    min-height: 560px;
}

/* 카드 내부의 컬럼 wrapper 배경은 투명 처리 */
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > div > div > .dist-card-marker) 
    background-color: #1A1D26 !important;   /* ← 회색빛 네이비로 변경 ⭐ */
    border: 1px solid #2A2E3A !important;   /* ← 테두리도 살짝 밝게 */
    border-radius: 10px !important;
    padding: 20px 25px !important;
    min-height: auto;
}
</style>
""", unsafe_allow_html=True)


col_left, col_right = st.columns(2)

# ---------- 왼쪽: 라인별 알람 분포 ----------
with col_left:
    with st.container(border=True):
        # 카드 식별 마커 (CSS 선택자용)
        st.markdown('<div class="dist-card-marker"></div>', unsafe_allow_html=True)
        st.markdown(
            "<div style='color:#FAFAFA; font-size:16px; font-weight:700; margin-bottom:5px; margin-top:-15px;'>"
            "라인별 알람 분포</div>",
            unsafe_allow_html=True
        )

        line_dist = df_valid.groupby("라인").size().reset_index(name="건수")
        line_dist["라인_라벨"] = line_dist["라인"].map(LINE_LABELS)
        line_dist["색상"] = line_dist["라인"].map(LINE_COLORS)

        fig_dist = go.Figure(go.Pie(
            labels=line_dist["라인_라벨"],
            values=line_dist["건수"],
            hole=0.55,
            marker=dict(colors=line_dist["색상"].tolist()),
            textinfo="label+percent",
            textposition="inside",
            textfont=dict(size=15, color="black"),
            sort=True,
            direction="clockwise",
        ))
        fig_dist.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=370,
            margin=dict(l=10, r=10, t=10, b=10),
            showlegend=True,
            legend=dict(
                orientation="v",
                yanchor="middle", y=0.5,
                xanchor="left", x=1.05,
                font=dict(color="white", size=18),
            ),
            annotations=[dict(
                text=f"<b>{line_dist['건수'].sum():,}</b><br>"
                     f"<span style='font-size:12px;color:#8B92A0;'>전체</span>",
                font=dict(size=22, color="white"),
                showarrow=False,
                x=0.5, y=0.5,
            )],
        )
        st.plotly_chart(fig_dist, use_container_width=True, key="line_dist_donut")


# ---------- 오른쪽: 라인별 비율 ----------
with col_right:
    with st.container(border=True):
        # 카드 식별 마커
        st.markdown('<div class="dist-card-marker"></div>', unsafe_allow_html=True)
        st.markdown(
            "<div style='color:#FAFAFA; font-size:16px; font-weight:700; margin-bottom:-10px; margin-top:-20px;'>"
            "라인별 비율 (알람 건수 기준)</div>",
            unsafe_allow_html=True
        )

        line_summary = df_valid.groupby("라인").size().reset_index(name="건수")
        line_order = ["4A", "4B", "4C", "4X"]
        line_summary["_order"] = line_summary["라인"].map({v: i for i, v in enumerate(line_order)})
        line_summary = line_summary.sort_values("_order").drop(columns="_order").reset_index(drop=True)
        total = line_summary["건수"].sum()

        donut_cols = st.columns(len(line_summary))
        for dcol, (_, row) in zip(donut_cols, line_summary.iterrows()):
            with dcol:
                pct = round(row["건수"] / total * 100, 1)
                color = LINE_COLORS.get(row["라인"], "#8B92A0")
                line_label = LINE_LABELS.get(row["라인"], row["라인"])

                fig = go.Figure(go.Pie(
                    values=[pct, 100 - pct],
                    hole=0.72,
                    marker=dict(
                        colors=[color, "#2A2E37"],
                        line=dict(color="rgba(0,0,0,0)", width=0),
                    ),
                    showlegend=False,
                    textinfo="none",
                    hoverinfo="skip",
                    sort=False,
                    direction="clockwise",
                    rotation=0,
                ))
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    height=345,
                    margin=dict(l=10, r=10, t=25, b=25),
                    annotations=[dict(
                        text=f"<b>{pct}%</b>",
                        x=0.5, y=0.5,
                        font=dict(size=18, color="white"),
                        showarrow=False,
                    )],
                )
                st.plotly_chart(fig, use_container_width=True, key=f"mini_donut_{row['라인']}")
                st.markdown(
                    f"<div style='text-align:center; margin-top:-35px;'>"
                    f"<span style='color:{color};font-weight:700;font-size:18px;'>{line_label}</span>"
                    f"<br><span style='color:#8B92A0;font-size:18px;'>{row['건수']:,} 건</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )



# =========================================================
# 🔄 집계: 발생빈도만 사용
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
        render_kpi_card("알람 건수", f"{len(data):,} 건", "", "cyan")
    with b:
        render_kpi_card("고유 알람", f"{data['알람명'].nunique():,} 종", "", "green")

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
    apply_dark_theme(fig, height=450)
    fig.update_layout(title=f"{title} - 발생빈도 TOP {top_n}")
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
