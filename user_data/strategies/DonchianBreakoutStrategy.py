"""
DonchianBreakoutStrategy (V3) - trend-following breakout, for backtesting and dry-run only.

Logic (spot, long only, no leverage, 1h candles)
------------------------------------------------
Entry ("enter_long") on a closed candle:
    1. close > highest high of the previous 50 days (Donchian breakout),
    2. BTC/USDT close > its 100-day SMA (market regime filter),
    3. volume > 0.

Exit:
    * close < lowest low of the previous 5 days (exit signal),
    * stoploss -12 %.
No ROI table: winners are left running until the 5-day low breaks.

Research summary (offline Freqtrade backtests, Binance spot 1h, 10 pairs, fee 0.1 %,
100 USDT wallet, max_open_trades 5) - measured results, not a promise:
    * Parameters were chosen on 2022-2025 as the centre of a stable region
      (entry 40-60 days, exit 3-7 days), not as the single best cell.
    * Per year: 2022 (from April) -5.58 %, 2023 +65.28 %, 2024 +105.9 %, 2025 -3.77 %.
    * Holdout 2026-01-01 -> 2026-10-29 (never used for tuning): -2.12 %,
      market change -23.04 %, max drawdown 9.96 %.
    * No lookahead bias found by `freqtrade lookahead-analysis`.
It makes money in up-trending markets and aims to lose little in down-trending ones.

Safety guard
------------
``bot_start`` refuses to run in live mode or in a non-spot trading mode.
"""

from datetime import datetime

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.enums import RunMode
from freqtrade.exceptions import OperationalException
from freqtrade.strategy import IntParameter, IStrategy, merge_informative_pair


CANDLES_PER_DAY = 24


class DonchianBreakoutStrategy(IStrategy):
    INTERFACE_VERSION = 3

    can_short: bool = False

    timeframe = "1h"

    # No take-profit: exits come from the 5-day low or the stoploss.
    minimal_roi = {"0": 100}

    stoploss = -0.12
    trailing_stop = False

    process_only_new_candles = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # 100 days of 1h candles (BTC 100-day SMA). Stays below the 2499 candles
    # Binance can provide at bot start-up in dry-run.
    startup_candle_count: int = 100 * CANDLES_PER_DAY

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    }

    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    entry_days = IntParameter(40, 60, default=50, space="buy", optimize=False)
    exit_days = IntParameter(3, 7, default=5, space="sell", optimize=False)
    btc_sma_days = IntParameter(50, 100, default=100, space="buy", optimize=False)

    def bot_start(self, **kwargs) -> None:
        """
        Safety guard: refuse anything other than simulation on spot markets.
        """
        runmode = self.config.get("runmode")
        if runmode == RunMode.LIVE or (
            runmode == RunMode.DRY_RUN and not self.config.get("dry_run", False)
        ):
            raise OperationalException(
                "DonchianBreakoutStrategy is restricted to backtesting and dry-run. "
                "Set `dry_run: true` in your configuration."
            )
        if self.config.get("trading_mode", "spot") != "spot":
            raise OperationalException("DonchianBreakoutStrategy only supports spot trading.")

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

    def informative_pairs(self):
        return [("BTC/USDT", self.timeframe)]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Previous candles only (shift(1)): the current candle never sees itself.
        dataframe["donchian_high"] = (
            dataframe["high"].rolling(self.entry_days.value * CANDLES_PER_DAY).max().shift(1)
        )
        dataframe["donchian_low"] = (
            dataframe["low"].rolling(self.exit_days.value * CANDLES_PER_DAY).min().shift(1)
        )

        btc = self.dp.get_pair_dataframe("BTC/USDT", self.timeframe)[["date", "close"]].copy()
        btc["btc_sma"] = ta.SMA(btc["close"], timeperiod=self.btc_sma_days.value * CANDLES_PER_DAY)
        btc["btc_bullish"] = btc["close"] > btc["btc_sma"]
        dataframe = merge_informative_pair(
            dataframe, btc[["date", "btc_bullish"]], self.timeframe, self.timeframe, ffill=True
        )
        dataframe["btc_bullish"] = (
            dataframe[f"btc_bullish_{self.timeframe}"].fillna(False).astype(bool)
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["donchian_high"])
            & dataframe["btc_bullish"]
            & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"],
        ] = (1, "donchian_breakout")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] < dataframe["donchian_low"]) & (dataframe["volume"] > 0),
            ["exit_long", "exit_tag"],
        ] = (1, "donchian_low")
        return dataframe
