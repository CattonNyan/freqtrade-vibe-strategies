"""Multi-timeframe trend-following strategy with dynamic trailing stoploss."""

from datetime import datetime
from pandas import DataFrame
import talib.abstract as ta

from freqtrade.persistence import Trade
from freqtrade.strategy import (
    IStrategy,
    IntParameter,
    merge_informative_pair,
    stoploss_from_open,
)
from technical import qtpylib


class MultiTimeframeAtrStrategy(IStrategy):
    """
    Multi-timeframe strategy combining:
    - 1h informative timeframe for macro trend direction (EMA 50 / EMA 200, RSI > 45)
    - 5m base timeframe for entry timing and momentum (EMA 20/50, RSI pullback, Volume)
    - Dynamic break-even and profit-securing custom stoploss (profit >= 3% secure 1.5%, profit >= 1.5% break-even)

    The class name is retained for configuration compatibility. The current
    stoploss uses profit thresholds and does not depend on ATR.
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

    def informative_pairs(self) -> list[tuple[str, str]]:
        """Define pairs and timeframes to download and cache."""
        if not getattr(self, "dp", None):
            return []
        pairs = self.dp.current_whitelist()
        return [(pair, self.informative_timeframe) for pair in pairs]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # --- Base Timeframe (5m) Indicators ---
        dataframe["ema_20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(20).mean().shift(1)

        # --- Informative Timeframe (1h) Indicators ---
        has_informative = False
        if getattr(self, "dp", None):
            informative = self.dp.get_pair_dataframe(
                pair=metadata["pair"], timeframe=self.informative_timeframe
            )
            if informative is not None and not informative.empty:
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
                has_informative = True

        if not has_informative:
            # Suppress entries when the informative timeframe cannot be loaded.
            # Reusing 5m indicators here would misrepresent them as 1h signals.
            dataframe[f"ema_50_{self.informative_timeframe}"] = float("nan")
            dataframe[f"ema_200_{self.informative_timeframe}"] = float("nan")
            dataframe[f"rsi_{self.informative_timeframe}"] = float("nan")

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["enter_long"] = 0
        dataframe["enter_tag"] = ""
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
        # Avoid panic selling in deeply oversold conditions where a relief bounce is likely
        trend_exit = qtpylib.crossed_below(dataframe["ema_20"], dataframe["ema_50"]) & (
            dataframe["rsi"] > 35
        )

        dataframe["exit_long"] = 0
        dataframe["exit_tag"] = ""
        dataframe.loc[
            (rsi_exit | trend_exit) & has_volume,
            "exit_long",
        ] = 1
        dataframe.loc[rsi_exit & has_volume, "exit_tag"] = "rsi_overbought"
        dataframe.loc[trend_exit & has_volume, "exit_tag"] = "ema_bearish_cross"
        dataframe.loc[rsi_exit & trend_exit & has_volume, "exit_tag"] = (
            "rsi_overbought+ema_bearish_cross"
        )
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
        1. When profit >= 3%, secure at least 1.5% profit and trail 50% of additional gains.
        2. When profit >= 1.5%, move stoploss to break-even (+0.3% to cover fees).
        3. Below 1.5%, standard base stoploss applies.
        """
        if current_profit >= 0.03:
            secured_profit = 0.015 + (current_profit - 0.03) * 0.5
            return stoploss_from_open(
                secured_profit,
                current_profit,
                is_short=trade.is_short,
                leverage=trade.leverage,
            )
        if current_profit >= 0.015:
            return stoploss_from_open(
                0.003,
                current_profit,
                is_short=trade.is_short,
                leverage=trade.leverage,
            )
        return None
