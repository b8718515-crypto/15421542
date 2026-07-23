"""L2 알람 이력 로드 & 전처리 (실제 포맷 기준)"""
import re
import pandas as pd
from pathlib import Path


def parse_korean_datetime(s: str) -> pd.Timestamp:
    """'2026-07-22 오후 10:39:52' → datetime 변환"""
    if pd.isna(s) or not isinstance(s, str):
        return pd.NaT
    s = s.strip().replace("‑", "-")  # 유니코드 하이픈 정리
    s = s.replace("오전", "AM").replace("오후", "PM")
    try:
        return pd.to_datetime(s, format="%Y-%m-%d %p %I:%M:%S")
    except Exception:
        return pd.NaT


def parse_duration(s: str) -> int:
    """'0시간 02분 50초' → 초(int) 변환"""
    if pd.isna(s) or not isinstance(s, str):
        return 0
    m = re.match(r"(\d+)\s*시간\s*(\d+)\s*분\s*(\d+)\s*초", s.strip())
    if not m:
        return 0
    h, mm, ss = map(int, m.groups())
    return h * 3600 + mm * 60 + ss


def load_alarm_file(path: str, source_name: str = None) -> pd.DataFrame:
    """
    단일 알람 이력 파일 로드
    
    파일 포맷 (탭/공백 구분):
      발생시간 | 해제시간 | 지속시간 | 공정라인명 | 설비중분류
    """
    df = pd.read_csv(
        path,
        sep=r"\s{2,}|\t",   # 2칸 이상 공백 또는 탭
        engine="python",
        encoding="utf-8-sig",
    )
    df.columns = [c.strip() for c in df.columns]

    # 컬럼명 표준화
    rename_map = {
        "발생시간": "start_time",
        "해제시간": "end_time",
        "지속시간": "duration_str",
        "공정라인명": "line_name",
        "설비중분류": "equipment_group",
    }
    df = df.rename(columns=rename_map)

    # 필수 컬럼 필터
    required = ["start_time", "end_time", "duration_str", "line_name", "equipment_group"]
    df = df[[c for c in required if c in df.columns]].copy()

    # 시간 파싱
    df["start_time"] = df["start_time"].apply(parse_korean_datetime)
    df["end_time"] = df["end_time"].apply(parse_korean_datetime)
    df["duration_sec"] = df["duration_str"].apply(parse_duration)

    # 결측/이상치 제거
    df = df.dropna(subset=["start_time"]).reset_index(drop=True)

    # 데이터 출처(파일명) 태그
    if source_name:
        df["source"] = source_name

    return df


def load_all_alarms(data_dir: str = "data") -> pd.DataFrame:
    """data 폴더의 4A, 4B, 4C, 4X CSV를 모두 로드"""
    frames = []
    for p in Path(data_dir).glob("*.csv"):
        try:
            frames.append(load_alarm_file(str(p), source_name=p.stem))
        except Exception as e:
            print(f"[WARN] {p.name} 로드 실패: {e}")
    if not frames:
        return pd.DataFrame(columns=[
            "start_time", "end_time", "duration_str", "line_name",
            "equipment_group", "duration_sec", "source"
        ])
    return pd.concat(frames, ignore_index=True)


def filter_data(df: pd.DataFrame,
                line_name: str = "전체",
                equipment_group: str = "전체",
                target_date=None) -> pd.DataFrame:
    """공정라인 / 설비중분류 / 일자 필터"""
    result = df.copy()
    if line_name and line_name != "전체":
        result = result[result["line_name"] == line_name]
    if equipment_group and equipment_group != "전체":
        result = result[result["equipment_group"] == equipment_group]
    if target_date is not None:
        result = result[result["start_time"].dt.date == target_date]
    return result
