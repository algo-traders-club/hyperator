# Hyperator

The simplest possible Hyperliquid trading bot that does something real. It's three small Python files and two dependencies: an async-ish loop that fetches market data from Hyperliquid via [CCXT](https://github.com/ccxt/ccxt), runs a strategy function, checks a handful of risk gates, and either places an order or logs why it didn't. Every signal, trade, and rejection is written to a local SQLite database, so the DB is the full history of the bot's decisions.

It trades the **HYPE perp** (`HYPE/USDC:USDC`) by default, and it runs on **testnet in dry-run mode out of the box** — so the first time you run it, it cannot place a real order or lose real money.

## Read the PRD first

[`docs/PRD.md`](docs/PRD.md) is the source of truth for Hyperator — its philosophy, architecture, and every design decision. **Read it before changing anything or opening a PR.** This README is the front door; the PRD is the spec.

## What it is / what it isn't

Hyperator is a **teaching artifact**: a complete, readable trading bot you can clone, run, and understand top-to-bottom in one sitting.

It is deliberately **not**:

- a framework (no plugins, no abstractions, no inversion of control),
- a backtester (forward-only),
- a market-making engine (it places taker-priced limit orders, period),
- a multi-asset / multi-strategy / multi-exchange system,
- a production trading system, and
- "the bot that will make you rich" — it's the bot that will make you *literate*.

See PRD §1.2 for the full list and the reasoning.

## Quickstart

Gets you running on testnet in about ten minutes. You'll need an [API wallet](https://app.hyperliquid.xyz/API) (its private key) and your main account's wallet address.

```bash
git clone https://github.com/algo-traders-club/hyperator.git
cd hyperator
uv sync
cp .env.example .env
```

Then edit `.env` and set the two credentials:

```
HYPERLIQUID_API_KEY=<your API wallet private key>
HYPERLIQUID_MAIN_WALLET=<your main account address>
```

Run it from the repo root:

```bash
uv run python src/hyperator.py
```

The bot creates its SQLite database at `data/hyperator.db` on first run (WAL mode, so you can query it with the `sqlite3` CLI while the bot is running). Because `TESTNET` and `DRY_RUN` both default to `true`, this is completely safe — no real orders are placed.

## The two safety switches

Two boolean environment variables control whether real money is at risk. Their combination gives four states:

| `TESTNET` | `DRY_RUN` | What happens                    | Risk                                |
| --------- | --------- | ------------------------------- | ----------------------------------- |
| `true`    | `true`    | Testnet, no orders placed       | **Zero** — the safe default         |
| `true`    | `false`   | Testnet, real orders on testnet | Zero — testnet HYPE is worthless    |
| `false`   | `true`    | Mainnet, no orders placed       | Zero — but be careful with API keys |
| `false`   | `false`   | Mainnet, real orders placed     | **REAL** — actual money at risk     |

The fourth state (`TESTNET=false` + `DRY_RUN=false`) is the **only** one that can lose you money. The bot makes the active state extremely loud on startup, and the mainnet-live state sleeps 10 seconds before proceeding — the "are you sure?" moment. See PRD §3.

## Configuration

All configuration is via environment variables loaded from `.env`. The full table is in PRD §4; the ones you'll touch most:

- `TESTNET` / `DRY_RUN` — the safety switches above (both default `true`).
- `SYMBOL` — the Hyperliquid perp to trade (default `HYPE/USDC:USDC`).
- `TIMEFRAME` — candle timeframe (default `1h`).
- `MAX_POSITION_USD` — hard cap on position size in USD (default `50`).

Everything else is hardcoded by design. If you want to change it, edit the code.

## How it works

The main loop runs a five-stage tick cycle every `TICK_INTERVAL_SECONDS` (PRD §2.1):

```
FETCH → STRATEGY → RISK → EXECUTE → LOG
```

Fetch candles and the current position, run the strategy function (the reference one is a 20-period SMA crossover, chosen for legibility, not profit), pass any signal through three risk gates, place the order if approved and not in dry-run, then write the outcome to SQLite. Every tick writes at least one row.

That's spread across three files under `src/`:

- `config.py` — environment variables and constants.
- `strategy.py` — the `Signal` dataclass and `generate_signal()`, the one extension point.
- `hyperator.py` — everything else: the loop, the risk gates, execution, SQLite, and clean shutdown.

PRD §2 walks through all of it in detail.

## Where to go next

Hyperator is intentionally complete on its own — clone it, run it, modify it, and never pay a cent. That's the point. It's the free public on-ramp to the [Algo Traders Club](https://github.com/algo-traders-club) curriculum (PRD §1.5).

When you find yourself wanting something Hyperator deliberately leaves out — a risk manager with drawdown limits, a strategy plugin system, a CLI, an HTTP server, deployment, vaults — the PRD §7 deferral table is effectively the syllabus: it maps each of those to where it's taught. The three ATC tracks pick up exactly where Hyperator stops:

- **Track A — The Operator:** risk manager, strategy plugins, CLI, deployment, OpSec.
- **Track B — The Curator:** the on-chain vault that pays the bot (Solidity, ERC-4626).
- **Track C — The Builder:** portfolios of vaults, HIP-3 markets, institutional ops.

If you finish Hyperator and want more, you'll know which door to walk through.

## Contributing

Contributions are welcome but evaluated against the philosophy in PRD §8. **Accepted:** bug fixes, clearer comments and docs, better variable names, and new reference strategies in `strategy.py` *if they stay small and pure*. **Rejected:** frameworks, ORMs, DI containers, plugin systems, web UIs, multi-asset support, and "cleanups" that split the code into many files. If a feature you want belongs in Track A, build it as a fork and link it — read PRD §8 before opening a PR.

## License & disclaimer

MIT, © Algo Traders Club. See [`LICENSE`](LICENSE).

**Use at your own risk.** Hyperator is educational software. The default `TESTNET=true, DRY_RUN=true` configuration exists to prevent accidents; if you flip both switches and lose money, that's entirely your responsibility. Hyperator is not affiliated with, endorsed by, or supported by Hyperliquid Labs or the Hyper Foundation.
