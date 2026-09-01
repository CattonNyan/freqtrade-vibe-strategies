"""Multi-timeframe trend-following strategy with dynamic trailing stoploss."""

from datetime import datetime
from pandas import DataFrame
import talib.abstract as ta

from freqtrade.persistence import Trade
from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    merge_informative_pair,
)
from technical import qtpylib


class MultiTimeframeAtrStrategy(IStrategy):
    """
    Multi-timeframe strategy combining:
    - 1h informative timeframe for macro trend direction (EMA 50 / EMA 200)
    - 5m base timeframe for entry timing and momentum (EMA, RSI, Volume)
    - Dynamic break-even and profit-securing custom stoploss
    """

    INTERFACE_VERSION = 3

    timeframe = "5m"
    informative_timeframe = "1h"

    can_short = False
    process_only_new_candles = True
    startup_candle_count = 799

    # Minimal ROI table
    minimal_roi = {
        "0": 0.05,
        "30": 0.03,
        "60": 0.015,
        "120": 0.0,
    }

    # Base stoploss fallback
    stoploss = -0.08
    use_custom_stoploss = True

    # Indicators & strategy hyperparameters
    buy_rsi = IntParameter(40, 60, default=48, space="buy", optimize=True)
    sell_rsi = IntParameter(65, 85, default=70, space="sell", optimize=True)

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
        "entry": "GTC",
        "exit": "GTC",
    }

    def informative_pairs(self):
        """Define pairs and timeframes to download and cache."""
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, self.informative_timeframe) for pair in pairs]
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # --- Base Timeframe (5m) Indicators ---
        dataframe["ema_20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(20).mean().shift(1)

        # --- Informative Timeframe (1h) Indicators ---
        if self.dp:
            informative = self.dp.get_pair_dataframe(
                pair=metadata["pair"], timeframe=self.informative_timeframe
            )
            informative["ema_50"] = ta.EMA(informative, timeperiod=50)
            informative["ema_200"] = ta.EMA(informative, timeperiod=200)
            informative["rsi"] = ta.RSI(informative, timeperiod=14)

            dataframe = merge_informative_pair(
                dataframe,
                informative,
                self.timeframe,
                self.informative_timeframe,
                ffill=True,
            )
        else:
            # Fallback for standalone dry/test runs without dataprovider
            dataframe[f"ema_50_{self.informative_timeframe}"] = dataframe["ema_50"]
            dataframe[f"ema_200_{self.informative_timeframe}"] = ta.EMA(dataframe, timeperiod=200)
            dataframe[f"rsi_{self.informative_timeframe}"] = dataframe["rsi"]

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        macro_ema_50 = dataframe[f"ema_50_{self.informative_timeframe}"]
        macro_ema_200 = dataframe[f"ema_200_{self.informative_timeframe}"]
        macro_rsi = dataframe[f"rsi_{self.informative_timeframe}"]

        macro_bullish = (macro_ema_50 > macro_ema_200) & (macro_rsi > 45)

        entry_condition = (
            macro_bullish
            & (dataframe["close"] > dataframe["ema_20"])
            & (dataframe["ema_20"] > dataframe["ema_50"])
            & qtpylib.crossed_above(dataframe["rsi"], self.buy_rsi.value)
            & (dataframe["volume"] > dataframe["volume_mean_20"])
            & (dataframe["volume"] > 0)
        )

        dataframe.loc[
            entry_condition,
            ["enter_long", "enter_tag"],
        ] = (1, "mtf_trend_pullback_entry")

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

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float | None:
        """
        Dynamic trailing stoploss with break-even protection:
        1. When profit >= 3%, secure at least 1.5% profit.
        2. When profit >= 1.5%, move stoploss to break-even (+0.3% to cover fees).
        3. Below 1.5%, standard base stoploss applies.
        """
        if current_profit >= 0.03:
            return 0.015 - current_profit
        if current_profit >= 0.015:
            return 0.003 - current_profit
        return None
