"""Reference strategy: 20-period SMA crossover (PRD sections 2.4-2.5).

Chosen for legibility, not profit. A strategy is a pure function mapping recent
candles plus the current position to a Signal or None. To change the strategy,
edit generate_signal below; nothing else in the bot needs to know how it works.
"""
from dataclasses import dataclass
from typing import Literal

import config

SMA_PERIOD = 20


@dataclass
class Signal:
    """A trade intent produced by the strategy (PRD section 2.4)."""

    side: Literal["buy", "sell", "close"]
    size: float                      # position size in base asset units
    reason: str                      # human-readable, logged to the database
    price_hint: float | None = None  # optional limit price suggestion


def generate_signal(candles: list, current_position: dict | None) -> Signal | None:
    """Return a Signal, or None when the strategy wants to do nothing.

    The signal fires on a simple moving-average crossover: go long when the
    latest close crosses above the 20-period SMA, and close the position when
    the close crosses back below it.
    """
    # One extra candle is needed to compare the previous bar against the prior SMA.
    if len(candles) < SMA_PERIOD + 1:
        return None

    # A ccxt OHLCV row is [timestamp, open, high, low, close, volume].
    closes = [candle[4] for candle in candles]
    price = closes[-1]
    sma = sum(closes[-SMA_PERIOD:]) / SMA_PERIOD
    prev_sma = sum(closes[-SMA_PERIOD - 1:-1]) / SMA_PERIOD
    size = config.MAX_POSITION_USD / price

    crossed_up = closes[-2] <= prev_sma and price > sma
    crossed_down = closes[-2] >= prev_sma and price < sma

    if crossed_up and not current_position:
        return Signal("buy", size, f"close {price:.2f} crossed above SMA{SMA_PERIOD}", price)
    if crossed_down and current_position:
        return Signal("close", size, f"close {price:.2f} crossed below SMA{SMA_PERIOD}", price)
    return None
