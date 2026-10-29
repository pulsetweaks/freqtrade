"""
EmaRsiPaperStrategy - simple, documented trend-following strategy for paper trading.

Purpose
-------
Starting point for backtesting and dry-run (paper trading) with a fictive 100 USDT wallet.
It is NOT a proven profitable strategy: only measured backtest / dry-run results can tell.

Logic (spot, long only, no leverage)
------------------------------------
Indicators:
    * ema_fast (EMA 20) / ema_slow (EMA 50): trend direction.
    * rsi (RSI 14): avoid buying when the market is already overbought.

Entry ("enter_long"), all conditions on a closed candle:
    1. ema_fast crosses above ema_slow (start of an up-trend),
    2. rsi < buy_rsi_max (default 70),
    3. volume > 0 (exclude empty candles).

Exit ("exit_long"), any of:
    * ema_fast crosses below ema_slow (trend reversal),
    * rsi > sell_rsi_min (default 80).

Risk management (handled by the Freqtrade engine, not re-implemented here):
    * stoploss -5 %,
    * minimal_roi table (take-profit decreasing over time).

Safety guard
------------
``bot_start`` refuses to run in live mode or in a non-spot trading mode, so this strategy
can only be used for backtesting, hyperopt and dry-run.
"""

from datetime import datetime

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.enums import RunMode
from freqtrade.exceptions import OperationalException
from freqtrade.strategy import IntParameter, IStrategy


class EmaRsiPaperStrategy(IStrategy):
    INTERFACE_VERSION = 3

    # Spot only - no shorting, no leverage.
    can_short: bool = False

    # Default timeframe. Can be overridden with --timeframe on the command line.
    timeframe = "1h"

    # Take-profit table: {minutes since entry: minimal profit ratio}.
    minimal_roi = {
        "0": 0.08,
        "720": 0.04,
        "1440": 0.02,
        "2880": 0,
    }

    stoploss = -0.05
    trailing_stop = False

    # Only evaluate signals on closed candles (avoids repainting).
    process_only_new_candles = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # EMA 50 needs a warm-up period to be stable (see `freqtrade recursive-analysis`).
    startup_candle_count: int = 200

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    # Hyperoptable parameters (optional - defaults are used for backtesting / dry-run).
    buy_rsi_max = IntParameter(55, 80, default=70, space="buy", optimize=True)
    sell_rsi_min = IntParameter(70, 90, default=80, space="sell", optimize=True)

    def bot_start(self, **kwargs) -> None:
        """
        Safety guard: refuse anything other than simulation on spot markets.
        """
        runmode = self.config.get("runmode")
        if runmode == RunMode.LIVE or (
            runmode == RunMode.DRY_RUN and not self.config.get("dry_run", False)
        ):
            raise OperationalException(
                "EmaRsiPaperStrategy is restricted to backtesting and dry-run. "
                "Set `dry_run: true` in your configuration."
            )
        if self.config.get("trading_mode", "spot") != "spot":
            raise OperationalException("EmaRsiPaperStrategy only supports spot trading.")

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        # Never use leverage.
        return 1.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                qtpylib.crossed_above(dataframe["ema_fast"], dataframe["ema_slow"])
                & (dataframe["rsi"] < self.buy_rsi_max.value)
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "ema_cross_up")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                qtpylib.crossed_below(dataframe["ema_fast"], dataframe["ema_slow"])
                & (dataframe["volume"] > 0)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "ema_cross_down")
        dataframe.loc[
            (dataframe["rsi"] > self.sell_rsi_min.value) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"],
        ] = (1, "rsi_overbought")
        return dataframe
