"""정비팀 관점 TOP5 분석 (설비중분류 기준)"""
import pandas as pd
from sklearn.preprocessing import MinMaxScaler


def compute_top5(df: pd.DataFrame,
                 w_freq: float = 0.5,
                 w_dur: float = 0.5,
                 top_n: int = 5) -> pd.DataFrame:
    """
    설비중분류(equipment_group) 단위 TOP N 산출

    Score = w_freq * norm(발생빈도) + w_dur * norm(누적지속시간)
    """
    if df.empty:
        return pd.DataFrame()

    agg = df.groupby("equipment_group").agg(
        freq=("start_time", "count"),
        total_duration_sec=("duration_sec", "sum"),
        max_duration_sec=("duration_sec", "max"),
    ).reset_index()

    if len(agg) == 1:
        agg["score"] = 1.0
        agg["freq_n"] = 1.0
        agg["dur_n"] = 1.0
    else:
        scaler = MinMaxScaler()
        norm = scaler.fit_transform(agg[["freq", "total_duration_sec"]])
        agg["freq_n"] = norm[:, 0]
        agg["dur_n"] = norm[:, 1]
        agg["score"] = w_freq * agg["freq_n"] + w_dur * agg["dur_n"]

    # 보기 좋은 단위 변환
    agg["total_duration_min"] = (agg["total_duration_sec"] / 60).round(1)
    agg["max_duration_min"] = (agg["max_duration_sec"] / 60).round(1)

    return (
        agg.sort_values("score", ascending=False)
           .head(top_n)
           .reset_index(drop=True)
    )


def hourly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """시간대별 알람 발생 건수 (0~23시)"""
    if df.empty:
        return pd.DataFrame(columns=["hour", "count"])
    tmp = df.copy()
    tmp["hour"] = tmp["start_time"].dt.hour
    return tmp.groupby("hour").size().reset_index(name="count")
