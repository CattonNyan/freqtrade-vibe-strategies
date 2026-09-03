"""Conservative dry-run starter strategy for Freqtrade."""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, IntParameter
from technical import qtpylib


class KoreanStarterStrategy(IStrategy):
    """
    보수적 15분봉 시작 전략 (Conservative Trend Starter Strategy).

    - 진입 조건: Close > EMA(200/20), EMA(20) > EMA(50), RSI 상향돌파, ADX > 20, 완료봉 거래량 돌파
    - 청산 조건: RSI > 70 과매수, EMA(20/50) 데드크로스, ROI 테이블
    - 리스크 관리: -8% 손절, 트레일링 스탑(+2.5% 도달 시 +1% 추적), 3대 보호장치
    """

    INTERFACE_VERSION = 3

    can_short = False
    timeframe = "15m"
    process_only_new_candles = True
    startup_candle_count = 799

    minimal_roi = {
        "0": 0.03,
        "60": 0.015,
        "180": 0.0,
    }

    stoploss = -0.08
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.025
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    buy_rsi = IntParameter(35, 55, default=45, space="buy", optimize=True)
    buy_adx = IntParameter(15, 35, default=20, space="buy", optimize=True)
    sell_rsi = IntParameter(60, 80, default=70, space="sell", optimize=True)

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
        dataframe["ema_20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(20).mean().shift(1)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["ema_200"])
                & (dataframe["close"] > dataframe["ema_20"])
                & (dataframe["ema_20"] > dataframe["ema_50"])
                & qtpylib.crossed_above(dataframe["rsi"], self.buy_rsi.value)
                & (dataframe["adx"] > self.buy_adx.value)
                & (dataframe["volume"] > dataframe["volume_mean_20"])
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "trend_rsi_volume")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        has_volume = dataframe["volume"] > 0
        rsi_exit = qtpylib.crossed_above(dataframe["rsi"], self.sell_rsi.value)
        trend_exit = qtpylib.crossed_below(dataframe["ema_20"], dataframe["ema_50"])

        dataframe["exit_tag"] = ""
        dataframe.loc[
            (rsi_exit | trend_exit) & has_volume,
            "exit_long",
        ] = 1
        dataframe.loc[rsi_exit & has_volume, "exit_tag"] += "rsi_overbought "
        dataframe.loc[trend_exit & has_volume, "exit_tag"] += "ema_bearish_cross "
        return dataframe
