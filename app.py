"""
4라인 설비 알람 TOP5 대시보드
- 정비팀용 · L2 알람 이력 기반
- 발생빈도 + 누적지속시간 스코어링
"""

import io
from pathlib import Path

import pandas as pd
import streamlit as st

# ─────────────────────────────────────────
# 페이지 기본 설정
# ─────────────────────────────────────────
st.set_page_config(
    page_title="4라인 설비 알람 TOP5 대시보드",
    page_icon="🔧",
    layout="wide",
)

st.title("🔧 4라인 설비 알람 TOP5 대시보드")
st.caption("정비팀용 · L2 알람 이력 기반 · 발생빈도 + 누적지속시간 스코어링")

# ─────────────────────────────────────────
# CSV 안전 로드 함수 (인코딩 자동 감지)
# ─────────────────────────────────────────
ENCODINGS = ["utf-8-sig", "utf-8", "cp949", "euc-kr", "latin1"]


def read_csv_safe(source, name: str = "") -> pd.DataFrame:
    """여러 인코딩을 순서대로 시도해서 CSV 로드"""
    # 파일 경로인 경우
    if isinstance(source, (str, Path)):
        for enc in ENCODINGS:
            try:
                return pd.read_csv(source, encoding=enc)
            except UnicodeDecodeError:
                continue
            except Exception as e:
                raise RuntimeError(f"{name} 읽기 오류: {e}")
        raise UnicodeDecodeError("all", b"", 0, 1, f"{name} 인코딩 인식 실패")

    # 업로드된 파일(BytesIO)인 경우
    raw = source.read()
    for enc in ENCODINGS:
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("all", b"", 0, 1, f"{name} 인코딩 인식 실패")


# ─────────────────────────────────────────
# 사이드바 - 데이터 소스 선택
# ─────────────────────────────────────────
st.sidebar.header("📁 데이터 소스")

data_source = st.sidebar.radio(
    "데이터를 어디서 불러올까요?",
    ["data/ 폴더에서 자동 로드", "직접 업로드"],
)

TARGET_FILES = ["4A.csv", "4B.csv", "4C.csv", "4X.csv"]
dfs: dict[str, pd.DataFrame] = {}

# ─────────────────────────────────────────
# ① data/ 폴더에서 자동 로드
# ─────────────────────────────────────────
if data_source == "data/ 폴더에서 자동 로드":
    data_dir = Path("data")

    if not data_dir.exists():
        st.warning("⚠️ `data/` 폴더가 없습니다. 저장소 루트에 `data/` 폴더를 만들고 CSV를 넣어주세요.")
    else:
        for fname in TARGET_FILES:
            fpath = data_dir / fname
            if not fpath.exists():
                st.sidebar.warning(f"⚠️ {fname} 없음")
                continue
            try:
                dfs[fname] = read_csv_safe(fpath, fname)
                st.sidebar.success(f"✅ {fname} 로드 ({len(dfs[fname])}행)")
            except Exception as e:
                st.sidebar.error(f"❌ {fname}: {e}")

# ─────────────────────────────────────────
# ② 직접 업로드
# ─────────────────────────────────────────
else:
    uploaded_files = st.sidebar.file_uploader(
        "CSV 파일 업로드 (여러 개 가능)",
        type="csv",
        accept_multiple_files=True,
    )
    if uploaded_files:
        for uf in uploaded_files:
            try:
                dfs[uf.name] = read_csv_safe(uf, uf.name)
                st.sidebar.success(f"✅ {uf.name} 로드 ({len(dfs[uf.name])}행)")
            except Exception as e:
                st.sidebar.error(f"❌ {uf.name}: {e}")

# ─────────────────────────────────────────
# 데이터가 없으면 안내 후 종료
# ─────────────────────────────────────────
if not dfs:
    st.info(
        "📌 데이터가 없습니다.\n\n"
        "- 사이드바에서 CSV를 업로드하거나\n"
        "- 저장소 루트의 `data/` 폴더에 `4A.csv`, `4B.csv`, `4C.csv`, `4X.csv` 를 두세요."
    )
    st.stop()

# ─────────────────────────────────────────
# 분석 파라미터 (사이드바)
# ─────────────────────────────────────────
st.sidebar.header("⚙️ 분석 설정")

top_n = st.sidebar.slider("TOP N", min_value=3, max_value=20, value=5)
w_count = st.sidebar.slider("발생빈도 가중치", 0.0, 1.0, 0.5, 0.1)
w_duration = 1.0 - w_count
st.sidebar.caption(f"누적지속시간 가중치: **{w_duration:.1f}**")

# ─────────────────────────────────────────
# 컬럼 자동 매핑 (데이터 스키마가 달라도 유연 대응)
# ─────────────────────────────────────────
def guess_column(df: pd.DataFrame, keywords: list[str]) -> str | None:
    for col in df.columns:
        col_low = str(col).lower().replace(" ", "")
        for kw in keywords:
            if kw.lower() in col_low:
                return col
    return None


def analyze(df: pd.DataFrame) -> pd.DataFrame:
    """알람명 기준으로 발생빈도·누적지속시간 집계 후 스코어링"""
    alarm_col = guess_column(df, ["alarm", "알람", "message", "메시지", "code", "코드"])
    dur_col = guess_column(df, ["duration", "지속", "elapsed", "time"])

    if alarm_col is None:
        return pd.DataFrame()

    agg_dict = {alarm_col: "count"}
    if dur_col is not None:
        # 지속시간이 문자열일 수도 있으니 숫자로 변환
        df[dur_col] = pd.to_numeric(df[dur_col], errors="coerce").fillna(0)
        agg_dict[dur_col] = "sum"

    grouped = (
        df.groupby(alarm_col)
        .agg(발생빈도=(alarm_col, "count"),
             누적지속시간=(dur_col, "sum") if dur_col else (alarm_col, "count"))
        .reset_index()
        .rename(columns={alarm_col: "알람"})
    )

    if dur_col is None:
        grouped["누적지속시간"] = 0

    # 정규화 후 스코어 계산 (0~1 → 100점 만점)
    def norm(s: pd.Series) -> pd.Series:
        if s.max() == s.min():
            return pd.Series([0] * len(s), index=s.index)
        return (s - s.min()) / (s.max() - s.min())

    grouped["빈도점수"] = norm(grouped["발생빈도"])
    grouped["지속점수"] = norm(grouped["누적지속시간"])
    grouped["종합점수"] = (
        w_count * grouped["빈도점수"] + w_duration * grouped["지속점수"]
    ) * 100
    grouped["종합점수"] = grouped["종합점수"].round(1)

    return grouped.sort_values("종합점수", ascending=False).reset_index(drop=True)


# ─────────────────────────────────────────
# 라인별 탭
# ─────────────────────────────────────────
tabs = st.tabs([f"📊 {name}" for name in dfs.keys()])

for tab, (name, df) in zip(tabs, dfs.items()):
    with tab:
        st.subheader(f"📊 {name} — 총 {len(df):,}건")

        with st.expander("🔍 원본 데이터 미리보기 (상위 20행)"):
            st.dataframe(df.head(20), use_container_width=True)

        result = analyze(df.copy())

        if result.empty:
            st.warning("⚠️ 알람 관련 컬럼을 찾지 못했습니다. 컬럼명을 확인해주세요.")
            st.write("**현재 컬럼:**", list(df.columns))
            continue

        top = result.head(top_n)

        # KPI
        c1, c2, c3 = st.columns(3)
        c1.metric("전체 알람 종류", f"{len(result):,}")
        c2.metric("총 발생 건수", f"{int(result['발생빈도'].sum()):,}")
        c3.metric("총 누적지속시간", f"{int(result['누적지속시간'].sum()):,}")

        # TOP N 표
        st.markdown(f"### 🏆 TOP {top_n} 알람")
        st.dataframe(
            top[["알람", "발생빈도", "누적지속시간", "종합점수"]],
            use_container_width=True,
            hide_index=True,
        )

        # 차트
        st.markdown("### 📈 종합점수 차트")
        chart_df = top.set_index("알람")[["종합점수"]]
        st.bar_chart(chart_df)

        # 다운로드
        csv_bytes = top.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label=f"⬇️ {name} TOP{top_n} 결과 다운로드 (CSV)",
            data=csv_bytes,
            file_name=f"{name.replace('.csv', '')}_TOP{top_n}.csv",
            mime="text/csv",
        )

# ─────────────────────────────────────────
# 푸터
# ─────────────────────────────────────────
st.markdown("---")
st.caption("© POSCO FUTURE M · 정비팀 대시보드 · Streamlit powered")
