"""
=========================================================
  4라인 설비 알람 TOP5 대시보드 (xlsx 전용 최종본)
  - 정비팀용 · L2 알람 이력 기반
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
# 1. Excel 로더
# ─────────────────────────────────────────
@st.cache_data(show_spinner=False)
def read_excel_safe(source, name: str = "") -> dict:
    """
    xlsx 파일을 읽어 모든 시트를 dict{시트명: DataFrame} 로 반환.
    파일 경로(str/Path) 또는 업로드 객체 모두 지원.
    """
    if isinstance(source, (str, Path)):
        with open(source, "rb") as f:
            raw = f.read()
    else:
        raw = source.read()

    # 시그니처 체크 (xlsx는 ZIP 기반이므로 'PK'로 시작)
    if raw[:2] != b"PK":
        raise ValueError(
            f"{name}: xlsx 파일이 아닙니다. (앞 4바이트: {raw[:4]!r})"
        )

    # 모든 시트 로드
    sheets = pd.read_excel(
        io.BytesIO(raw),
        engine="openpyxl",
        sheet_name=None,   # None = 모든 시트
    )
    return sheets


def pick_main_sheet(sheets: dict) -> tuple[str, pd.DataFrame]:
    """가장 행 수가 많은 시트를 대표 시트로 선정"""
    best_name, best_df = None, None
    for sname, sdf in sheets.items():
        if best_df is None or len(sdf) > len(best_df):
            best_name, best_df = sname, sdf
    return best_name, best_df


# ─────────────────────────────────────────
# 2. 사이드바 - 데이터 소스
# ─────────────────────────────────────────
st.sidebar.header("📁 데이터 소스")

data_source = st.sidebar.radio(
    "데이터 로드 방식",
    ["data/ 폴더에서 자동 로드", "직접 업로드"],
)

# 파일별 원본 시트 dict 저장
raw_sheets: dict[str, dict] = {}

if data_source == "data/ 폴더에서 자동 로드":
    data_dir = Path("data")
    if not data_dir.exists():
        st.warning("⚠️ 저장소 루트에 `data/` 폴더가 없습니다.")
    else:
        excel_files = sorted(data_dir.glob("*.xlsx"))
        # 확장자만 .csv로 되어있을 수 있으니 .csv도 시도
        excel_files += sorted(data_dir.glob("*.csv"))

        if not excel_files:
            st.sidebar.warning("⚠️ data/ 폴더에 파일이 없습니다.")

        for fpath in excel_files:
            try:
                sheets = read_excel_safe(fpath, fpath.name)
                raw_sheets[fpath.name] = sheets
                st.sidebar.success(
                    f"✅ {fpath.name} (시트 {len(sheets)}개)"
                )
            except Exception as e:
                st.sidebar.error(f"❌ {fpath.name}: {e}")

else:
    uploaded_files = st.sidebar.file_uploader(
        "xlsx 업로드 (여러 개 가능)",
        type=["xlsx", "csv"],
        accept_multiple_files=True,
    )
    if uploaded_files:
        for uf in uploaded_files:
            try:
                sheets = read_excel_safe(uf, uf.name)
                raw_sheets[uf.name] = sheets
                st.sidebar.success(f"✅ {uf.name} (시트 {len(sheets)}개)")
            except Exception as e:
                st.sidebar.error(f"❌ {uf.name}: {e}")

if not raw_sheets:
    st.info(
        "📌 데이터가 없습니다.\n\n"
        "- 사이드바에서 xlsx 파일을 업로드하거나\n"
        "- 저장소 루트의 `data/` 폴더에 `4A.xlsx`, `4B.xlsx`, `4C.xlsx`, `4X.xlsx` 를 두세요."
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
# 4. 컬럼 자동 매핑 & 분석
# ─────────────────────────────────────────
ALARM_KEYWORDS = [
    "alarm", "알람", "message", "메시지", "msg",
    "code", "코드", "설명", "description", "desc",
    "event", "이벤트", "fault", "결함", "이상",
]
DURATION_KEYWORDS = [
    "duration", "지속", "elapsed", "time", "시간", "sec", "min",
]


def guess_column(df: pd.DataFrame, keywords: list) -> str | None:
    """컬럼명 부분일치로 첫 매칭 컬럼 반환"""
    for col in df.columns:
        low = str(col).lower().replace(" ", "")
        for kw in keywords:
            if kw.lower() in low:
                return col
    return None


def analyze(
    df: pd.DataFrame,
    alarm_col: str,
    dur_col: str | None,
) -> pd.DataFrame:
    """알람별 발생빈도·누적지속시간 집계 후 스코어링"""
    df = df.copy()
    df[alarm_col] = df[alarm_col].astype(str).str.strip()
    df = df[df[alarm_col].str.len() > 0]
    df = df[df[alarm_col].str.lower() != "nan"]

    if dur_col is not None:
        df[dur_col] = pd.to_numeric(df[dur_col], errors="coerce").fillna(0)

    # 집계
    grouped = (
        df.groupby(alarm_col)
        .size()
        .reset_index(name="발생빈도")
        .rename(columns={alarm_col: "알람"})
    )

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
# 5. 라인별 탭
# ─────────────────────────────────────────
tabs = st.tabs([f"📊 {name}" for name in raw_sheets.keys()])

for tab, (fname, sheets) in zip(tabs, raw_sheets.items()):
    with tab:
        # 시트 선택
        sheet_names = list(sheets.keys())
        default_sheet, _ = pick_main_sheet(sheets)

        col_a, col_b = st.columns([1, 3])
        with col_a:
            sel_sheet = st.selectbox(
                "시트 선택",
                sheet_names,
                index=sheet_names.index(default_sheet),
                key=f"sheet_{fname}",
            )

        df = sheets[sel_sheet]
        st.subheader(f"📊 {fname} · [{sel_sheet}] — {len(df):,}행 × {df.shape[1]}열")

        # 원본 미리보기
        with st.expander("🔍 원본 데이터 미리보기 (상위 20행)"):
            st.dataframe(df.head(20), use_container_width=True)
            st.write("**컬럼 목록:**", list(df.columns))

        # 컬럼 자동 추정 + 수동 지정 UI
        auto_alarm = guess_column(df, ALARM_KEYWORDS)
        auto_dur = guess_column(df, DURATION_KEYWORDS)
        cols = list(df.columns)

        c1, c2 = st.columns(2)
        with c1:
            alarm_col = st.selectbox(
                "🚨 알람(그룹핑) 컬럼",
                cols,
                index=cols.index(auto_alarm) if auto_alarm in cols else 0,
                key=f"alarm_{fname}",
            )
        with c2:
            dur_options = ["(사용 안 함)"] + cols
            dur_idx = (
                dur_options.index(auto_dur) if auto_dur in cols else 0
            )
            dur_sel = st.selectbox(
                "⏱️ 지속시간(숫자) 컬럼",
                dur_options,
                index=dur_idx,
                key=f"dur_{fname}",
            )
            dur_col = None if dur_sel == "(사용 안 함)" else dur_sel

        # 분석
        try:
            result = analyze(df, alarm_col, dur_col)
        except Exception as e:
            st.error(f"분석 중 오류: {e}")
            continue

        if result.empty:
            st.warning("⚠️ 집계 결과가 없습니다. 컬럼 선택을 확인해주세요.")
            continue

        top = result.head(top_n)

        # KPI 카드
        k1, k2, k3 = st.columns(3)
        k1.metric("알람 종류", f"{len(result):,}")
        k2.metric("총 발생 건수", f"{int(result['발생빈도'].sum()):,}")
        k3.metric("총 누적지속시간", f"{result['누적지속시간'].sum():,.0f}")

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

        # 다운로드
        csv_bytes = top.to_csv(index=False).encode("utf-8-sig")
        base_name = fname.rsplit(".", 1)[0]
        st.download_button(
            label=f"⬇️ {base_name} TOP{top_n} 결과 다운로드 (CSV)",
            data=csv_bytes,
            file_name=f"{base_name}_{sel_sheet}_TOP{top_n}.csv",
            mime="text/csv",
        )

# ─────────────────────────────────────────
# 6. 푸터
# ─────────────────────────────────────────
st.markdown("---")
st.caption("© POSCO FUTURE M · 정비팀 대시보드 · Streamlit powered")
