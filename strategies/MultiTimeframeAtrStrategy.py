"""Multi-timeframe trend-following strategy with dynamic trailing stoploss."""

from __future__ import annotations

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
    다중 타임프레임 추세 추종 및 동적 커스텀 스탑로스 5분봉 전략.

    - 상위 추세 (1시간봉): EMA(50) > EMA(200) 및 RSI(14) > 45 정배열 매크로 강세장
    - 진입 조건 (5분봉): Close > EMA(20), EMA(20) > EMA(50), RSI 상향돌파, 완료봉 거래량 돌파
    - 청산 조건: RSI > 70 과매수, EMA(20/50) 데드크로스, ROI 테이블
    - 리스크 관리: -8% 기본 손절, 3대 보호장치, 수익률 연동 동적 커스텀 스탑로스
      (수익률 >= 3% 시 1.5% 확보 후 추가 이익 50% 트레일링, 수익률 >= 1.5% 시 본전+0.3% 수수료 방어)

    Multi-timeframe strategy combining:
    - 1h informative timeframe for macro trend direction (EMA 50 / EMA 200, RSI > 45)
    - 5m base timeframe for entry timing and momentum (EMA 20/50, RSI pullback, Volume)
    - Dynamic break-even and profit-securing custom stoploss (profit >= 3% secure 1.5%, profit >= 1.5% break-even)

    The class name is retained for configuration compatibility. The current
    stoploss uses profit thresholds and does not depend on ATR.
    Note: Requires sufficient 1h historical candles (>= 200 candles) for macro EMA 200 convergence.
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

    can_short: bool = False
    position_adjustment_enable: bool = False

    use_exit_signal = True
    exit_profit_only = False
    exit_profit_offset: float = 0.0
    ignore_roi_if_entry_signal = False

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
        "stoploss_on_exchange_interval": 60,
        "stoploss_on_exchange_limit_ratio": 0.99,
    }

    order_time_in_force = {
        "entry": "gtc",
        "exit": "gtc",
    }

    plot_config = {
        "main_plot": {
            "ema_20": {"color": "blue"},
            "ema_50": {"color": "orange"},
            "ema_50_1h": {"color": "cyan"},
            "ema_200_1h": {"color": "magenta"},
        },
        "subplots": {
            "RSI": {
                "rsi": {"color": "purple"},
                "rsi_1h": {"color": "yellow"},
            },
        },
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

    def version(self) -> str | None:
        return "1.0.0"

    def informative_pairs(self) -> list[tuple[str, str]]:
        """Define pairs and timeframes to download and cache."""
        if not getattr(self, "dp", None):
            return []
        pairs = dict.fromkeys(self.dp.current_whitelist() or [])
        return [
            (pair, self.informative_timeframe)
            for pair in pairs
            if pair
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # --- Base Timeframe (5m) Indicators ---
        dataframe["ema_20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema_50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(20).mean().shift(1)

        # --- Informative Timeframe (1h) Indicators ---
        has_informative = False
        pair = metadata.get("pair")
        if getattr(self, "dp", None) and pair:
            informative = self.dp.get_pair_dataframe(
                pair=pair, timeframe=self.informative_timeframe
            )
            if informative is not None and not informative.empty:
                informative = informative.copy()
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
        both_exit = rsi_exit & trend_exit & has_volume
        dataframe.loc[
            (rsi_exit | trend_exit) & has_volume,
            "exit_long",
        ] = 1
        dataframe.loc[rsi_exit & ~trend_exit & has_volume, "exit_tag"] = "rsi_overbought"
        dataframe.loc[trend_exit & ~rsi_exit & has_volume, "exit_tag"] = "ema_bearish_cross"
        dataframe.loc[both_exit, "exit_tag"] = (
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
