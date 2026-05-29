"""Hyperator — a minimal Hyperliquid trading bot (PRD sections 2, 3, 5).

Runs a five-stage tick (FETCH -> STRATEGY -> RISK -> EXECUTE -> LOG) on a loop,
writing every decision to SQLite. The loop survives every error except invalid
credentials on startup (PRD section 5.4).
"""
import logging
import os
import signal
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone

import ccxt

import config
from strategy import Signal, generate_signal

log = logging.getLogger("hyperator")

# Set by the SIGINT/SIGTERM handlers; the loop and sleeps watch it to stop cleanly.
_shutdown = threading.Event()

# The three tables, created on first run (PRD section 2.7).
SIGNALS_TABLE = """
CREATE TABLE IF NOT EXISTS signals (
    id               INTEGER PRIMARY KEY,
    ts               TIMESTAMP NOT NULL,
    side             TEXT NOT NULL,
    size             REAL NOT NULL,
    reason           TEXT NOT NULL,
    approved         BOOLEAN NOT NULL,
    rejection_reason TEXT
)
"""

TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    id        INTEGER PRIMARY KEY,
    signal_id INTEGER REFERENCES signals(id),
    ts        TIMESTAMP NOT NULL,
    side      TEXT NOT NULL,
    size      REAL NOT NULL,
    price     REAL NOT NULL,
    order_id  TEXT,
    status    TEXT NOT NULL
)
"""

BOT_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS bot_state (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL
)
"""


def _now() -> str:
    """Current UTC time as an ISO-8601 string (used for every timestamp)."""
    return datetime.now(timezone.utc).isoformat()


def init_db() -> sqlite3.Connection:
    """Open the database, enable WAL mode, and create the tables if missing."""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    # WAL lets you query the DB with the sqlite3 CLI while the bot is running.
    conn.execute("PRAGMA journal_mode=WAL")
    for table in (SIGNALS_TABLE, TRADES_TABLE, BOT_STATE_TABLE):
        conn.execute(table)
    conn.commit()
    return conn


def log_signal(conn, sig: Signal, approved: bool, rejection: str | None) -> int:
    """Record a signal and its risk decision; return the new signal id."""
    cursor = conn.execute(
        "INSERT INTO signals (ts, side, size, reason, approved, rejection_reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (_now(), sig.side, sig.size, sig.reason, approved, rejection),
    )
    conn.commit()
    return cursor.lastrowid


def log_trade(conn, signal_id: int, sig: Signal, price: float,
              order_id: str | None, status: str) -> None:
    """Record an executed (or dry-run) order, linked back to its signal."""
    conn.execute(
        "INSERT INTO trades (signal_id, ts, side, size, price, order_id, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (signal_id, _now(), sig.side, sig.size, price, order_id, status),
    )
    conn.commit()


def set_state(conn, key: str, value: str) -> None:
    """Upsert a bot_state key (e.g. last_tick_at) to support crash recovery."""
    conn.execute(
        "INSERT INTO bot_state (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at",
        (key, value, _now()),
    )
    conn.commit()


def get_state(conn, key: str) -> str | None:
    """Read a bot_state value, or None if the key has never been written."""
    row = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def check_risk(sig: Signal, price: float, position_count: int) -> tuple[bool, str]:
    """Apply the risk gates and return (approved, rejection_reason) (PRD 2.6).

    Gates 1 and 2 can reject here; gate 3 (DRY_RUN) is applied at execution time.
    """
    if sig.size > config.MAX_POSITION_USD / price:
        return False, f"position size {sig.size} exceeds MAX_POSITION_USD"

    # New positions are capped; a "close" only reduces exposure, so it is exempt.
    if sig.side != "close" and position_count >= config.MAX_OPEN_POSITIONS:
        return False, f"already at MAX_OPEN_POSITIONS ({config.MAX_OPEN_POSITIONS})"

    return True, ""


def run_tick(exchange, conn) -> None:
    """Run one FETCH -> STRATEGY -> RISK -> EXECUTE -> LOG cycle (PRD 2.1)."""
    # Stage 1: FETCH market data and the current position.
    try:
        candles = exchange.fetch_ohlcv(config.SYMBOL, config.TIMEFRAME, limit=30)
        positions = exchange.fetch_positions([config.SYMBOL])
    except ccxt.RateLimitExceeded:
        log.warning("rate limited (429); sleeping 30s (PRD 5.4)")
        time.sleep(30)
        return
    except (ccxt.RequestTimeout, ccxt.NetworkError) as e:
        log.warning("fetch failed, skipping tick: %s (PRD 5.4)", e)
        return

    open_positions = [p for p in positions if p.get("contracts")]
    current_position = open_positions[0] if open_positions else None

    # Stage 2: STRATEGY. A misbehaving strategy must not break the loop.
    try:
        sig = generate_signal(candles, current_position)
    except Exception:
        log.exception("strategy raised; treating as no-signal (PRD 5.4)")
        return
    if sig is None:
        return

    price = sig.price_hint or candles[-1][4]

    # Stage 3: RISK. A risk error is treated as a rejection, never a crash.
    try:
        approved, reason = check_risk(sig, price, len(open_positions))
    except Exception:
        log.exception("risk manager raised; rejecting signal (PRD 5.4)")
        approved, reason = False, "risk_error"

    # Stage 5 (decision logging): every signal and every rejection is recorded.
    signal_id = log_signal(conn, sig, approved, reason or None)
    set_state(conn, "last_signal_id", str(signal_id))
    if not approved:
        log.info("REJECT %s %s: %s", sig.side, sig.size, reason)
        return

    # Stage 4: EXECUTE. In dry-run we log the intent but place no order.
    if config.DRY_RUN:
        log.info("DRY_RUN intent: %s %s @ %s", sig.side, sig.size, price)
        log_trade(conn, signal_id, sig, price, None, "dry_run")
        return

    order_side = "buy" if sig.side == "buy" else "sell"
    params = {"reduceOnly": True} if sig.side == "close" else {}
    try:
        order = exchange.create_order(
            config.SYMBOL, "limit", order_side, sig.size, price, params
        )
        log_trade(conn, signal_id, sig, price, order.get("id"), "submitted")
        log.info("ORDER %s %s @ %s -> %s", order_side, sig.size, price, order.get("id"))
    except ccxt.BaseError as e:
        log.error("order placement failed: %s", e)
        log_trade(conn, signal_id, sig, price, None, "failed")


def _sleep_interruptible(seconds: int) -> None:
    """Sleep in one-second steps, returning early if shutdown was requested."""
    for _ in range(seconds):
        if _shutdown.is_set():
            return
        time.sleep(1)


def banner() -> None:
    """Print the active safety state loudly on startup (PRD 3.3).

    Mainnet with live orders (TESTNET=false, DRY_RUN=false) is the only state
    that risks real money; it pauses 10s so the operator can abort with Ctrl+C.
    """
    line = "=" * 40
    testnet = str(config.TESTNET).lower()
    dry_run = str(config.DRY_RUN).lower()
    live = not config.TESTNET and not config.DRY_RUN

    print(line)
    print("  \u26a0\ufe0f  HYPERATOR STARTING" if live else "  HYPERATOR STARTING")
    print(f"  TESTNET: {testnet} | DRY_RUN: {dry_run}")
    if live:
        print("  Risk: REAL MONEY ON MAINNET")
        print("  Sleeping 10s \u2014 Ctrl+C to abort")
    else:
        print("  Risk: NONE \u2014 safe configuration")
    print(line)

    if live:
        _sleep_interruptible(10)


def connect_exchange():
    """Build the CCXT client and verify the credentials, or exit 1 (PRD 5.4)."""
    exchange = ccxt.hyperliquid({
        "walletAddress": config.HYPERLIQUID_MAIN_WALLET,
        "privateKey": config.HYPERLIQUID_API_KEY,
    })
    # Sandbox mode must be set before any other call (PRD 3.2).
    if config.TESTNET:
        exchange.set_sandbox_mode(True)
    try:
        exchange.fetch_balance()
    except ccxt.AuthenticationError as e:
        log.error("invalid credentials, cannot start: %s", e)
        sys.exit(1)
    return exchange


def main() -> None:
    """Start up (PRD 5.1), run the loop (PRD 5.2), and shut down cleanly (PRD 5.3)."""
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not config.HYPERLIQUID_API_KEY or not config.HYPERLIQUID_MAIN_WALLET:
        log.error("HYPERLIQUID_API_KEY and HYPERLIQUID_MAIN_WALLET are required")
        sys.exit(1)

    signal.signal(signal.SIGINT, lambda *_: _shutdown.set())
    signal.signal(signal.SIGTERM, lambda *_: _shutdown.set())

    banner()
    conn = init_db()
    log.info("resuming; last tick at %s", get_state(conn, "last_tick_at"))
    exchange = connect_exchange()

    # Main loop (PRD 5.2): one tick, then sleep until the next interval. The tick
    # always finishes before shutdown, so an in-flight order is never abandoned.
    while not _shutdown.is_set():
        try:
            run_tick(exchange, conn)
            set_state(conn, "last_tick_at", _now())
        except Exception:
            log.exception("tick error; continuing")
        _sleep_interruptible(config.TICK_INTERVAL_SECONDS)

    conn.close()
    exchange.close()
    log.info("Hyperator stopped cleanly")
    sys.exit(0)


if __name__ == "__main__":
    main()
