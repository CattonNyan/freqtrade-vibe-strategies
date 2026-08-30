"""Simple RSI and EMA trend-following strategy for Freqtrade."""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class VibeRsiStrategy(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "5m"
    can_short = False
    process_only_new_candles = True
    startup_candle_count = 60

    minimal_roi = {
        "0": 0.04,
        "30": 0.02,
        "60": 0.01,
    }

    stoploss = -0.05
    trailing_stop = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["rsi"] < 30)
                & (dataframe["ema20"] > dataframe["ema50"])
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            ((dataframe["rsi"] > 70) & (dataframe["volume"] > 0)),
            "exit_long",
        ] = 1
        return dataframe
