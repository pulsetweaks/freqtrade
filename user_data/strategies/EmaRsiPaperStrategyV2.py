"""
EmaRsiPaperStrategyV2 - second iteration of EmaRsiPaperStrategy, for paper trading only.

Why a V2
--------
Backtest of V1 (Binance spot, 1h, 2025-01-09 -> 2026-10-29, fee 0.1 %, 100 USDT wallet):
    * total -41.75 % (market change -25.61 %), 598 trades,
    * the ``ema_cross_down`` exit closed 340 trades, 339 of them at a loss (-154 USDT),
    * roughly 29 USDT paid in fees (29 038 USDT traded).

Changes compared to V1 (hypotheses to be measured, NOT proven improvements):
    1. The ``ema_cross_down`` exit signal is removed. Trades exit through the ROI table,
       the stoploss or an overbought RSI only.
    2. Long-term trend filter: only enter when close > EMA 200, to trade less often
       and avoid buying during down-trends.

Logic (spot, long only, no leverage)
------------------------------------
Entry ("enter_long"), all conditions on a closed candle:
    1. ema_fast (EMA 20) crosses above ema_slow (EMA 50),
    2. close > ema_trend (EMA 200),
    3. rsi (RSI 14) < buy_rsi_max (default 70),
    4. volume > 0.

Exit ("exit_long"): rsi > sell_rsi_min (default 80).
Plus minimal_roi and stoploss -5 %, handled by the Freqtrade engine.

Safety guard
------------
``bot_start`` refuses to run in live mode or in a non-spot trading mode.
"""

from datetime import datetime

import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.enums import RunMode
from freqtrade.exceptions import OperationalException
from freqtrade.strategy import IntParameter, IStrategy


class EmaRsiPaperStrategyV2(IStrategy):
    INTERFACE_VERSION = 3

    # Spot only - no shorting, no leverage.
    can_short: bool = False

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

    process_only_new_candles = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # EMA 200 needs a long warm-up period to be stable.
    startup_candle_count: int = 400

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

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
                "EmaRsiPaperStrategyV2 is restricted to backtesting and dry-run. "
                "Set `dry_run: true` in your configuration."
            )
        if self.config.get("trading_mode", "spot") != "spot":
            raise OperationalException("EmaRsiPaperStrategyV2 only supports spot trading.")

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
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                qtpylib.crossed_above(dataframe["ema_fast"], dataframe["ema_slow"])
                & (dataframe["close"] > dataframe["ema_trend"])
                & (dataframe["rsi"] < self.buy_rsi_max.value)
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "ema_cross_up_trend")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] > self.sell_rsi_min.value) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"],
        ] = (1, "rsi_overbought")
        return dataframe
