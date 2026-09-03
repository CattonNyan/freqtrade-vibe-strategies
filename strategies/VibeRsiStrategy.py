"""Simple RSI and EMA trend-following strategy for Freqtrade."""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy
from technical import qtpylib


class VibeRsiStrategy(IStrategy):
    """
    RSI 과매도 회복 및 EMA 추세 추종 5분봉 전략.

    - 진입 조건: RSI(14) > 30 상향 돌파, EMA(20) > EMA(50), Close > EMA(20)
    - 청산 조건: RSI(14) > 70 과매수, EMA(20) < EMA(50) 데드크로스, ROI 테이블
    - 리스크 관리: -5% 고정 손절, Cooldown/StoplossGuard/MaxDrawdown 보호장치
    """

    INTERFACE_VERSION = 3

    timeframe = "5m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 199

    minimal_roi = {
        "0": 0.04,
        "30": 0.02,
        "60": 0.01,
    }

    stoploss = -0.05
    trailing_stop = False

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "emergency_exit": "market",
        "force_entry": "market",
        "force_exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    order_time_in_force = {
        "entry": "gtc",
        "exit": "gtc",
    }

    @property
    def protections(self) -> list[dict]:
        return [
            {"method": "CooldownPeriod", "stop_duration": 60},
            {
                "method": "StoplossGuard",
                "lookback_period": 43200,
                "trade_limit": 2,
                "stop_duration": 10080,
                "required_profit": 0.0,
                "only_per_pair": False,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period": 86400,
                "trade_limit": 8,
                "stop_duration": 20160,
                "max_allowed_drawdown": 0.05,
                "calculation_mode": "equity",
            },
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                qtpylib.crossed_above(dataframe["rsi"], 30)
                & (dataframe["ema20"] > dataframe["ema50"])
                & (dataframe["close"] > dataframe["ema20"])
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "rsi_recovery_with_trend")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        has_volume = dataframe["volume"] > 0
        rsi_exit = qtpylib.crossed_above(dataframe["rsi"], 70)
        trend_exit = qtpylib.crossed_below(dataframe["ema20"], dataframe["ema50"])

        dataframe["exit_tag"] = ""
        dataframe.loc[
            (rsi_exit | trend_exit) & has_volume,
            "exit_long",
        ] = 1
        dataframe.loc[rsi_exit & has_volume, "exit_tag"] += "rsi_overbought "
        dataframe.loc[trend_exit & has_volume, "exit_tag"] += "ema_bearish_cross "
        return dataframe
