"""
Tests for the user-defined paper-trading setup:
    * user_data/strategies/EmaRsiPaperStrategy.py
    * user_data/config_paper_100usdt.json

They run fully offline (exchange is mocked, data comes from tests/testdata).
"""

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from freqtrade.configuration.config_validation import validate_config_schema
from freqtrade.configuration.load_config import load_config_file
from freqtrade.data import history
from freqtrade.data.history import get_timerange
from freqtrade.enums import RunMode
from freqtrade.exceptions import OperationalException
from freqtrade.optimize.backtesting import Backtesting
from freqtrade.resolvers import StrategyResolver
from tests.conftest import EXMS, patch_exchange


ROOT = Path(__file__).parents[2]
STRATEGY_PATH = ROOT / "user_data" / "strategies"
PAPER_CONFIG = ROOT / "user_data" / "config_paper_100usdt.json"
STRATEGY_NAME = "EmaRsiPaperStrategy"


@pytest.fixture
def paper_conf(default_conf_usdt):
    conf = deepcopy(default_conf_usdt)
    conf.update(
        {
            "strategy": STRATEGY_NAME,
            "strategy_path": str(STRATEGY_PATH),
            "dry_run": True,
            "dry_run_wallet": 100,
            "stake_amount": "unlimited",
            "max_open_trades": 3,
            "tradable_balance_ratio": 0.99,
            "trading_mode": "spot",
            "margin_mode": "",
        }
    )
    conf.pop("minimal_roi", None)
    conf.pop("stoploss", None)
    conf.pop("timeframe", None)
    return conf


def _load_strategy(conf):
    return StrategyResolver.load_strategy(conf)


# --- Configuration safety ------------------------------------------------------------


def test_paper_config_is_safe():
    conf = load_config_file(str(PAPER_CONFIG))

    assert conf["dry_run"] is True
    assert conf["dry_run_wallet"] == 100
    assert conf["stake_currency"] == "USDT"
    # No private API credentials.
    assert conf["exchange"]["key"] == ""
    assert conf["exchange"]["secret"] == ""
    assert "password" not in conf["exchange"]
    assert "uid" not in conf["exchange"]
    # Spot only, no leverage / futures.
    assert conf["trading_mode"] == "spot"
    assert conf.get("margin_mode", "") == ""
    assert "liquidation_buffer" not in conf
    # No remote control surface exposed.
    assert conf["telegram"]["enabled"] is False
    assert not conf.get("api_server", {}).get("enabled", False)
    assert conf["force_entry_enable"] is False


def test_paper_config_matches_schema():
    conf = load_config_file(str(PAPER_CONFIG))
    # Raises ValidationError on an invalid configuration.
    validate_config_schema(conf)


# --- Strategy -----------------------------------------------------------------------


def test_strategy_loads_with_safe_defaults(paper_conf):
    strategy = _load_strategy(paper_conf)

    assert strategy.__class__.__name__ == STRATEGY_NAME
    assert strategy.can_short is False
    assert strategy.stoploss == -0.05
    assert strategy.timeframe == "1h"
    assert strategy.startup_candle_count == 200
    assert (
        strategy.leverage(
            pair="BTC/USDT",
            current_time=datetime.now(UTC),
            current_rate=100.0,
            proposed_leverage=10.0,
            max_leverage=20.0,
            entry_tag=None,
            side="long",
        )
        == 1.0
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"runmode": RunMode.LIVE, "dry_run": False},
        {"runmode": RunMode.DRY_RUN, "dry_run": False},
        {"runmode": RunMode.DRY_RUN, "trading_mode": "futures"},
    ],
)
def test_bot_start_refuses_unsafe_modes(paper_conf, overrides):
    paper_conf.update(overrides)
    strategy = _load_strategy(paper_conf)
    with pytest.raises(OperationalException):
        strategy.bot_start()


@pytest.mark.parametrize("runmode", [RunMode.DRY_RUN, RunMode.BACKTEST, RunMode.HYPEROPT])
def test_bot_start_allows_simulation(paper_conf, runmode):
    paper_conf["runmode"] = runmode
    strategy = _load_strategy(paper_conf)
    strategy.bot_start()


def _synthetic_ohlcv(prices: np.ndarray) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(prices), freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "date": dates,
            "open": prices,
            "high": prices * 1.002,
            "low": prices * 0.998,
            "close": prices,
            "volume": 100.0,
        }
    )


def test_signals_on_trend_reversals(paper_conf):
    strategy = _load_strategy(paper_conf)
    # Down-trend, then up-trend, then down-trend again, with mild noise so RSI stays moderate.
    rng = np.random.default_rng(42)
    trend = np.concatenate(
        [np.linspace(100, 80, 150), np.linspace(80, 95, 150), np.linspace(95, 75, 150)]
    )
    prices = trend + rng.normal(0, 0.6, len(trend))
    df = _synthetic_ohlcv(prices)

    df = strategy.advise_indicators(df, {"pair": "BTC/USDT"})
    for col in ("ema_fast", "ema_slow", "rsi"):
        assert col in df.columns
    df = strategy.advise_entry(df, {"pair": "BTC/USDT"})
    df = strategy.advise_exit(df, {"pair": "BTC/USDT"})

    entries = df[df["enter_long"] == 1]
    exits = df[df["exit_long"] == 1]
    assert len(entries) >= 1
    assert len(exits) >= 1
    assert set(entries["enter_tag"]) == {"ema_cross_up"}
    # Every entry happens while EMA fast is above EMA slow.
    assert (entries["ema_fast"] > entries["ema_slow"]).all()
    # The first entry happens during the up-trend section.
    assert 150 <= entries.index[0] < 300
    # No short signals.
    assert "enter_short" not in df.columns or df["enter_short"].fillna(0).eq(0).all()


def test_no_entry_without_volume(paper_conf):
    strategy = _load_strategy(paper_conf)
    trend = np.concatenate([np.linspace(100, 80, 150), np.linspace(80, 95, 150)])
    df = _synthetic_ohlcv(trend)
    df["volume"] = 0.0
    df = strategy.advise_entry(
        strategy.advise_indicators(df, {"pair": "BTC/USDT"}), {"pair": "BTC/USDT"}
    )
    assert df["enter_long"].fillna(0).eq(0).all()


# --- Offline backtest (engine integration) ------------------------------------------


def test_offline_backtest_with_fees_and_100usdt_wallet(paper_conf, mocker, testdatadir):
    paper_conf.update(
        {
            "runmode": RunMode.BACKTEST,
            "timeframe": "5m",
            "fee": 0.001,
            "datadir": testdatadir,
            "exchange": {
                **paper_conf["exchange"],
                "pair_whitelist": ["BTC/USDT", "XRP/USDT"],
            },
        }
    )
    patch_exchange(mocker)
    mocker.patch(f"{EXMS}.get_min_pair_stake_amount", return_value=0.00001)
    mocker.patch(f"{EXMS}.get_max_pair_stake_amount", return_value=float("inf"))
    mocker.patch(f"{EXMS}.get_pair_base_currency", lambda _, x: x.split("/")[0])

    backtesting = Backtesting(paper_conf)
    backtesting._set_strategy(backtesting.strategylist[0])
    data = history.load_data(
        datadir=testdatadir, timeframe="5m", pairs=["BTC/USDT", "XRP/USDT"], fill_up_missing=True
    )
    processed = backtesting.strategy.advise_all_indicators(data)
    min_date, max_date = get_timerange(processed)

    result = backtesting.backtest(processed=processed, start_date=min_date, end_date=max_date)
    trades = result["results"]

    # 100 USDT wallet, of which 99 % is tradable (tradable_balance_ratio = 0.99).
    assert backtesting.wallets.get_starting_balance() == pytest.approx(99.0)
    # The engine must stay within the fictive wallet and apply fees on both sides.
    if not trades.empty:
        assert (trades["stake_amount"] <= 100).all()
        assert (trades["fee_open"] == 0.001).all()
        assert (trades["fee_close"] == 0.001).all()
        assert (trades["leverage"] == 1.0).all()
        assert not trades["is_short"].any()


# --- V2 -----------------------------------------------------------------------------

STRATEGY_V2_NAME = "EmaRsiPaperStrategyV2"


@pytest.fixture
def v2_conf(paper_conf):
    paper_conf["strategy"] = STRATEGY_V2_NAME
    return paper_conf


def test_v2_loads_with_safe_defaults(v2_conf):
    strategy = _load_strategy(v2_conf)

    assert strategy.__class__.__name__ == STRATEGY_V2_NAME
    assert strategy.can_short is False
    assert strategy.stoploss == -0.05
    assert strategy.timeframe == "1h"
    assert strategy.startup_candle_count >= 200


@pytest.mark.parametrize(
    "overrides",
    [
        {"runmode": RunMode.LIVE, "dry_run": False},
        {"runmode": RunMode.DRY_RUN, "dry_run": False},
        {"runmode": RunMode.DRY_RUN, "trading_mode": "futures"},
    ],
)
def test_v2_bot_start_refuses_unsafe_modes(v2_conf, overrides):
    v2_conf.update(overrides)
    strategy = _load_strategy(v2_conf)
    with pytest.raises(OperationalException):
        strategy.bot_start()


def test_v2_bot_start_allows_dry_run(v2_conf):
    v2_conf["runmode"] = RunMode.DRY_RUN
    _load_strategy(v2_conf).bot_start()


def _advise_all(strategy, df):
    meta = {"pair": "BTC/USDT"}
    df = strategy.advise_indicators(df, meta)
    df = strategy.advise_entry(df, meta)
    return strategy.advise_exit(df, meta)


def test_v2_entries_only_above_long_term_trend(v2_conf):
    strategy = _load_strategy(v2_conf)
    rng = np.random.default_rng(42)
    # Long up-trend (price above EMA 200), a dip, then a recovery.
    trend = np.concatenate(
        [np.linspace(50, 100, 400), np.linspace(100, 92, 80), np.linspace(92, 110, 120)]
    )
    df = _advise_all(strategy, _synthetic_ohlcv(trend + rng.normal(0, 0.4, len(trend))))

    entries = df[df["enter_long"] == 1]
    assert len(entries) >= 1
    assert set(entries["enter_tag"]) == {"ema_cross_up_trend"}
    assert (entries["close"] > entries["ema_trend"]).all()
    assert (entries["ema_fast"] > entries["ema_slow"]).all()


def test_v2_no_entry_in_long_down_trend(v2_conf):
    strategy = _load_strategy(v2_conf)
    rng = np.random.default_rng(7)
    # Long down-trend with a short bounce: EMA 20/50 may cross up, but price stays below EMA 200.
    trend = np.concatenate([np.linspace(200, 100, 400), np.linspace(100, 108, 60)])
    df = _advise_all(strategy, _synthetic_ohlcv(trend + rng.normal(0, 0.4, len(trend))))

    assert df["enter_long"].fillna(0).eq(0).all()


def test_v2_has_no_ema_cross_down_exit(v2_conf):
    strategy = _load_strategy(v2_conf)
    rng = np.random.default_rng(42)
    trend = np.concatenate(
        [np.linspace(100, 80, 150), np.linspace(80, 95, 150), np.linspace(95, 75, 150)]
    )
    df = _advise_all(strategy, _synthetic_ohlcv(trend + rng.normal(0, 0.6, len(trend))))

    exits = df[df["exit_long"] == 1]
    assert "ema_cross_down" not in set(exits["exit_tag"].dropna())
    # Every exit signal comes from an overbought RSI.
    assert (exits["rsi"] > strategy.sell_rsi_min.value).all()
