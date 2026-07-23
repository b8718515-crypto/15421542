"""
=========================================================
  4라인 설비 알람 TOP5 대시보드 (최종본)
  - 정비팀용 · L2 알람 이력 기반
  - 인코딩 / 구분자 / 스킵행 자동 감지
  - 발생빈도 + 누적지속시간 가중치 스코어링
=========================================================
"""

import io
from pathlib import Path

import pandas as pd
import streamlit as st

# ─────────────────────────────────────────
# 0. 페이지 설정
# ─────────────────────────────────────────
st.set_page_config(
    page_title="4라인 설비 알람 TOP5 대시보드",
    page_icon="🔧",
    layout="wide",
)

st.title("🔧 4라인 설비 알람 TOP5 대시보드")
st.caption("정비팀용 · L2 알람 이력 기반 · 발생빈도 + 누적지속시간 스코어링")

# ─────────────────────────────────────────
# 1. CSV 안전 로드 (인코딩 · 구분자 · 스킵행 자동 탐색)
# ─────────────────────────────────────────
ENCODINGS = ["utf-8-sig", "utf-8", "cp949", "euc-kr", "latin1"]
SEPARATORS = [",", "\t", ";", "|"]


def _try_read(source, encoding, sep, skiprows=0):
    """단일 조합으로 CSV 읽기 시도"""
    kwargs = dict(
        encoding=encoding,
        sep=sep,
        skiprows=skiprows,
        engine="python",       # 관대한 파서
        on_bad_lines="skip",   # 이상한 줄 건너뜀
    )
    if isinstance(source, (str, Path)):
        return pd.read_csv(source, **kwargs)
    return pd.read_csv(io.BytesIO(source), **kwargs)


def read_csv_safe(source, name: str = "") -> pd.DataFrame:
    """
    인코딩 + 구분자 + 스킵행 조합을 자동 탐색.
    가장 컬럼 수가 많은(=제대로 파싱된) 결과를 채택.
    """
    raw = None
    if not isinstance(source, (str, Path)):
        raw = source.read()

    best_df = None
    best_info = ""

    for enc in ENCODINGS:
        for sep in SEPARATORS:
            for skip in range(0, 10):
                try:
                    target = raw if raw is not None else source
                    df = _try_read(target, enc, sep, skip)
                    if df.shape[1] >= 2 and len(df) >= 3:
                        if best_df is None or df.shape[1] > best_df.shape[1]:
                            best_df = df
                            best_info = (
                                f"enc={enc}, sep={repr(sep)}, skiprows={skip}"
                            )
                except Exception:
                    continue

    if best_df is None:
        raise ValueError(f"{name} 파일 형식을 인식할 수 없습니다.")

    st.sidebar.caption(f"📌 {name} → {best_info}")
    return best_df


# ─────────────────────────────────────────
# 2. 사이드바 - 데이터 소스 선택
# ─────────────────────────────────────────
st.sidebar.header("📁 데이터 소스")

data_source = st.sidebar.radio(
    "데이터 로드 방식",
    ["data/ 폴더에서 자동 로드", "직접 업로드"],
)

TARGET_FILES = ["4A.csv", "4B.csv", "4C.csv", "4X.csv"]
dfs: dict[str, pd.DataFrame] = {}

# ① data/ 폴더에서 자동 로드
if data_source == "data/ 폴더에서 자동 로드":
    data_dir = Path("data")
    if not data_dir.exists():
        st.warning("⚠️ 저장소 루트에 `data/` 폴더가 없습니다.")
    else:
        for fname in TARGET_FILES:
            fpath = data_dir / fname
            if not fpath.exists():
                st.sidebar.warning(f"⚠️ {fname} 없음")
                continue
            try:
                dfs[fname] = read_csv_safe(fpath, fname)
                st.sidebar.success(
                    f"✅ {fname} ({len(dfs[fname])}행 × {dfs[fname].shape[1]}열)"
                )
            except Exception as e:
                st.sidebar.error(f"❌ {fname}: {e}")

# ② 직접 업로드
else:
    uploaded_files = st.sidebar.file_uploader(
        "CSV 업로드 (여러 개 가능)",
        type=["csv", "txt"],
        accept_multiple_files=True,
    )
    if uploaded_files:
        for uf in uploaded_files:
            try:
                dfs[uf.name] = read_csv_safe(uf, uf.name)
                st.sidebar.success(
                    f"✅ {uf.name} ({len(dfs[uf.name])}행 × {dfs[uf.name].shape[1]}열)"
                )
            except Exception as e:
                st.sidebar.error(f"❌ {uf.name}: {e}")

# 데이터 없으면 안내 후 종료
if not dfs:
    st.info(
        "📌 데이터가 없습니다.\n\n"
        "- 사이드바에서 CSV를 업로드하거나\n"
        "- 저장소 루트의 `data/` 폴더에 `4A.csv`, `4B.csv`, `4C.csv`, `4X.csv` 를 두세요."
    )
    st.stop()

# ─────────────────────────────────────────
# 3. 분석 파라미터
# ─────────────────────────────────────────
st.sidebar.header("⚙️ 분석 설정")

top_n = st.sidebar.slider("TOP N", 3, 20, 5)
w_count = st.sidebar.slider("발생빈도 가중치", 0.0, 1.0, 0.5, 0.1)
w_duration = 1.0 - w_count
st.sidebar.caption(f"누적지속시간 가중치: **{w_duration:.1f}**")

# ─────────────────────────────────────────
# 4. 컬럼 자동 매핑 & 분석 로직
# ─────────────────────────────────────────
def guess_column(df: pd.DataFrame, keywords: list) -> str | None:
    """컬럼명에 키워드가 포함된 첫 번째 컬럼 반환"""
    for col in df.columns:
        low = str(col).lower().replace(" ", "")
        for kw in keywords:
            if kw.lower() in low:
                return col
    return None


def analyze(df: pd.DataFrame) -> pd.DataFrame:
    """알람명 기준으로 발생빈도·누적지속시간 집계 후 스코어링"""
    alarm_col = guess_column(
        df, ["alarm", "알람", "message", "메시지", "code", "코드", "설명"]
    )
    dur_col = guess_column(
        df, ["duration", "지속", "elapsed", "time", "시간"]
    )

    if alarm_col is None:
        return pd.DataFrame()

    if dur_col is not None:
        df[dur_col] = pd.to_numeric(df[dur_col], errors="coerce").fillna(0)

    # 발생빈도
    grouped = df.groupby(alarm_col).size().reset_index(name="발생빈도")
    grouped = grouped.rename(columns={alarm_col: "알람"})

    # 누적지속시간
    if dur_col is not None:
        dur_sum = (
            df.groupby(alarm_col)[dur_col]
            .sum()
            .reset_index(name="누적지속시간")
            .rename(columns={alarm_col: "알람"})
        )
        grouped = grouped.merge(dur_sum, on="알람", how="left")
    else:
        grouped["누적지속시간"] = 0

    # 정규화 (0~1)
    def norm(s: pd.Series) -> pd.Series:
        if s.max() == s.min():
            return pd.Series([0] * len(s), index=s.index)
        return (s - s.min()) / (s.max() - s.min())

    grouped["빈도점수"] = norm(grouped["발생빈도"])
    grouped["지속점수"] = norm(grouped["누적지속시간"])
    grouped["종합점수"] = (
        (w_count * grouped["빈도점수"] + w_duration * grouped["지속점수"]) * 100
    ).round(1)

    return grouped.sort_values("종합점수", ascending=False).reset_index(drop=True)


# ─────────────────────────────────────────
# 5. 라인별 탭 화면
# ─────────────────────────────────────────
tabs = st.tabs([f"📊 {name}" for name in dfs.keys()])

for tab, (name, df) in zip(tabs, dfs.items()):
    with tab:
        st.subheader(f"📊 {name} — 총 {len(df):,}건 · {df.shape[1]}개 컬럼")

        # 원본 미리보기
        with st.expander("🔍 원본 데이터 미리보기 (상위 20행)"):
            st.dataframe(df.head(20), use_container_width=True)
            st.write("**컬럼 목록:**", list(df.columns))

        # 분석
        result = analyze(df.copy())

        if result.empty:
            st.warning(
                "⚠️ 알람 관련 컬럼을 찾지 못했습니다. 위 컬럼 목록을 확인해주세요."
            )
            continue

        top = result.head(top_n)

        # KPI 카드
        c1, c2, c3 = st.columns(3)
        c1.metric("알람 종류", f"{len(result):,}")
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
        st.bar_chart(top.set_index("알람")[["종합점수"]])

        # 다운로드 버튼
        csv_bytes = top.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label=f"⬇️ {name} TOP{top_n} 결과 다운로드 (CSV)",
            data=csv_bytes,
            file_name=f"{name.replace('.csv', '')}_TOP{top_n}.csv",
            mime="text/csv",
        )

# ─────────────────────────────────────────
# 6. 푸터
# ─────────────────────────────────────────
st.markdown("---")
st.caption("© POSCO FUTURE M · 정비팀 대시보드 · Streamlit powered")
