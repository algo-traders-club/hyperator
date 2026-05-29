Got it. Here's the PRD — written to be both a real engineering document and a teachable artifact. Students download it in Lesson 4 and refer back to it forever.

I'm formatting it as a standalone markdown document you can save as `PRD.md` in the Hyperator repo root and also export as PDF for the Skool downloadable resource.

---

```markdown
# Hyperator — Product Requirements Document

**Version:** 1.0
**Last updated:** May 2026
**Maintainer:** Algo Traders Club
**Repo:** github.com/algotradersclub/hyperator
**License:** MIT

---

## 1. Philosophy

### 1.1 What Hyperator is

Hyperator is the simplest possible Hyperliquid trading bot that does something real.

It is one Python file (`hyperator.py`) plus one strategy file (`strategy.py`), running an async loop that fetches market data from Hyperliquid via CCXT, runs a strategy function, checks a small set of risk gates, and either executes a trade or logs the rejection. Every signal, every trade, and every rejection is written to a local SQLite database.

The whole thing is under 250 lines of Python. Two dependencies. Two files. One database. One config.

It runs on Hyperliquid testnet by default, in dry-run mode by default, so you can't accidentally lose money the first time you run it.

### 1.2 What Hyperator is NOT

Hyperator is deliberately not a lot of things. Knowing what it isn't is as important as knowing what it is.

- **Not a framework.** No plugins, no abstractions, no inversion of control. Read it top to bottom and you understand the whole thing.
- **Not a backtester.** Forward-only. If you want backtests, fork it and add them.
- **Not a market-making bot.** No order book modeling, no inventory management, no quote-and-cancel logic. It places taker-priced limit orders, period.
- **Not a multi-asset, multi-strategy, multi-exchange engine.** One strategy, one asset, one exchange.
- **Not a production trading system.** It's a teaching artifact. Production-grade equivalents live in ATC's paid Track A curriculum.
- **Not "the bot that will make you rich."** It's the bot that will make you _literate._ What you build on top of it is your responsibility.

### 1.3 The "read it in a single sitting" promise

Every architectural decision in Hyperator is in service of one goal: a competent Python developer should be able to read the entire codebase from top to bottom in 30-45 minutes and understand every line.

This means:

- No classes unless absolutely necessary (CCXT clients are the exception)
- No async machinery beyond what `asyncio.sleep` requires
- No dependency injection
- No design patterns named after gangs of four
- No "future-proofing" for features that don't exist yet
- Comments where intent isn't obvious from code

If you find yourself reaching for `abstractmethod`, `Protocol`, or `metaclass`, stop. Hyperator is wrong for that. Look at ATC's paid Track A reference implementation instead.

### 1.4 Who Hyperator is for

Hyperator is for:

- Developers with 2+ years of Python experience who are new to crypto trading
- Crypto traders who can read code but haven't built a bot
- Anyone evaluating whether to invest time in learning Hyperliquid development
- ATC members starting the curriculum
- Educators teaching algorithmic trading

Hyperator is **not** for:

- Complete programming beginners (you'll be lost)
- People looking for "the trading bot that prints money" (it doesn't exist)
- Production deployers (use Track A's Keeper for that)
- Anyone who can't articulate what `async def` does

### 1.5 The position in the ATC curriculum

Hyperator is the **free public on-ramp** to the Algo Traders Club curriculum. It is intentionally complete on its own — you can clone it, run it, modify it, and never pay ATC a cent. That's the point.

What Hyperator gives you is the _vocabulary_ and _muscle memory_ to evaluate the paid tracks. After Hyperator, you know:

- What "running a trading bot on Hyperliquid" actually feels like
- Whether you enjoy the work
- Where Hyperator stops being enough

The three ATC tracks pick up exactly where Hyperator stops:

| Track                     | Picks up Hyperator and adds                                      | Gated to      |
| ------------------------- | ---------------------------------------------------------------- | ------------- |
| **Track A: The Operator** | Risk manager, strategy plugins, CLI, OpenClaw, deployment, OpSec | Standard tier |
| **Track B: The Curator**  | The vault that pays the Keeper. Solidity, ERC-4626, on-chain     | Premium tier  |
| **Track C: The Builder**  | Portfolio of vaults, HIP-3 markets, institutional ops            | VIP cohort    |

If you finish Hyperator and want more, you know which door to walk through.

---

## 2. Architecture

### 2.1 The five-stage tick cycle

Hyperator's main loop runs five stages in order, every N seconds (default 60):
```

┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ FETCH │ → │ STRATEGY │ → │ RISK │ → │ EXECUTE │ → │ LOG │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
market data Signal or None approve/deny place order SQLite
candles, pos. (or dry-run)

```

1. **Fetch** — pull recent candles and current position from Hyperliquid via CCXT
2. **Strategy** — call the strategy function; it returns `Signal | None`
3. **Risk** — pass the signal through three gates (position size, max positions, dry-run state)
4. **Execute** — if approved and not dry-run, place a limit order via CCXT; otherwise log the intent
5. **Log** — write the signal, the decision, and (if any) the order to SQLite

Every iteration writes at least one row to the database, even if nothing happens. The database is the history of the bot's mind.

### 2.2 File structure

```

hyperator/
├── src/
│ ├── hyperator.py # the main loop + risk + execute + log (≤180 lines)
│ ├── strategy.py # the strategy function (≤40 lines)
│ └── config.py # env vars and constants (≤30 lines)
├── data/
│ └── hyperator.db # SQLite, created on first run
├── .env.example # template for HYPERLIQUID_API_KEY etc.
├── pyproject.toml # UV-managed dependencies
├── README.md
├── PRD.md # this document
├── LICENSE # MIT
└── CONTRIBUTING.md

````

The three Python files live in `src/` for organization. No `tests/` (yet — see §7), no `utils/`. Two real source files (`hyperator.py` + `strategy.py`), run with `uv run python src/hyperator.py`.

### 2.3 Dependencies

Hyperator depends on exactly two third-party libraries:

- **`ccxt`** — unified exchange API; provides the Hyperliquid client
- **`python-dotenv`** — loads `.env` config (could be inlined but adds clarity)

Optional accelerators (recommended but not required):

- **`coincurve`** — drop-in ECDSA backend; ~900x faster signing. Without it, signing is pure-Python and slow.
- **`orjson`** — faster JSON parsing for large Hyperliquid responses

Standard library: `sqlite3`, `asyncio`, `datetime`, `logging`, `os`, `signal`.

No FastAPI. No SQLAlchemy. No pydantic. No Typer. No Rich. Those are Track A territory.

### 2.4 The Signal dataclass (minimal)

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class Signal:
    side: Literal["buy", "sell", "close"]
    size: float          # in base asset units
    reason: str          # human-readable, logged to DB
    price_hint: float | None = None  # optional limit price suggestion
````

That's the whole interface between strategy and the rest of the bot. A strategy returns `Signal | None`. The loop does the rest.

### 2.5 The strategy function (the only "extension point")

```python
def generate_signal(
    candles: list[dict],
    current_position: dict | None,
) -> Signal | None:
    """Return a Signal or None based on candles and current position."""
    ...
```

That's the entire strategy API. A pure function. No state. No classes. No plugin registry. If you want to change the strategy, edit this function.

The reference implementation is a 20-period simple moving average crossover. It is chosen for **legibility**, not performance. Do not expect it to be profitable. It is the "hello world" of trading strategies.

### 2.6 The risk manager (three gates)

Hyperator has exactly three risk checks:

1. **Position size cap** — reject if `size > MAX_POSITION_USD / price`
2. **Max open positions** — reject if `current_positions >= MAX_OPEN_POSITIONS` (default: 1)
3. **Dry-run gate** — if `DRY_RUN=true`, log the intent but skip execution

That's it. No drawdown tracking, no daily loss limit, no cooldowns. Those are Track A.

The risk manager is a single function (~20 lines) that returns `(approved: bool, reason: str)`. Every rejection is logged with the reason.

### 2.7 The SQLite schema

Three tables, all created on first run:

```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY,
    ts TIMESTAMP NOT NULL,
    side TEXT NOT NULL,
    size REAL NOT NULL,
    reason TEXT NOT NULL,
    approved BOOLEAN NOT NULL,
    rejection_reason TEXT
);

CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    signal_id INTEGER REFERENCES signals(id),
    ts TIMESTAMP NOT NULL,
    side TEXT NOT NULL,
    size REAL NOT NULL,
    price REAL NOT NULL,
    order_id TEXT,
    status TEXT NOT NULL
);

CREATE TABLE bot_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

`bot_state` is a key-value store for things like `last_tick_at`, `last_signal_id`, `starting_balance`. Read on startup to enable basic crash recovery.

WAL mode is enabled to allow concurrent reads (so you can query the DB with `sqlite3` CLI while the bot is running).

---

## 3. The Two Safety Switches

Hyperator has exactly two boolean environment variables that control whether real money is at risk:

### 3.1 `DRY_RUN`

- **Default: `true`**
- When `true`: signals are generated and logged, but no orders are placed. The bot "trades" entirely in the database.
- When `false`: signals that pass risk checks are sent to Hyperliquid as real orders.

### 3.2 `TESTNET`

- **Default: `true`**
- When `true`: the bot connects to `api.hyperliquid-testnet.xyz`. Testnet HYPE has no real value.
- When `false`: the bot connects to `api.hyperliquid.xyz`. Real mainnet. Real money.

### 3.3 The four-state matrix

| `TESTNET` | `DRY_RUN` | What happens                    | Risk                                |
| --------- | --------- | ------------------------------- | ----------------------------------- |
| `true`    | `true`    | Testnet, no orders placed       | **Zero** — the safe default         |
| `true`    | `false`   | Testnet, real orders on testnet | Zero — testnet HYPE is worthless    |
| `false`   | `true`    | Mainnet, no orders placed       | Zero — but be careful with API keys |
| `false`   | `false`   | Mainnet, real orders placed     | **REAL** — actual money at risk     |

The fourth state is the only one that can lose you money. The bot's logs make the active state extremely loud on startup:

```
========================================
  HYPERATOR STARTING
  TESTNET: true | DRY_RUN: true
  Risk: NONE — safe configuration
========================================
```

vs.

```
========================================
  ⚠️  HYPERATOR STARTING
  TESTNET: false | DRY_RUN: false
  Risk: REAL MONEY ON MAINNET
  Sleeping 10s — Ctrl+C to abort
========================================
```

The 10-second sleep is intentional. It's the "are you sure?" moment.

---

## 4. Configuration

All configuration is via environment variables loaded from `.env`. No YAML, no TOML for config, no CLI args (yet).

| Variable                  | Default         | Notes                                          |
| ------------------------- | --------------- | ---------------------------------------------- |
| `HYPERLIQUID_API_KEY`     | —               | Your Hyperliquid API wallet private key        |
| `HYPERLIQUID_MAIN_WALLET` | —               | The main wallet the API wallet is approved for |
| `TESTNET`                 | `true`          | See §3.2                                       |
| `DRY_RUN`                 | `true`          | See §3.1                                       |
| `SYMBOL`                  | `HYPE/USDC:USDC` | The Hyperliquid perp to trade                  |
| `TIMEFRAME`               | `1h`            | Candle timeframe                               |
| `TICK_INTERVAL_SECONDS`   | `60`            | Loop interval                                  |
| `MAX_POSITION_USD`        | `50`            | Hard cap on position size in USD               |
| `MAX_OPEN_POSITIONS`      | `1`             | Hard cap on concurrent positions               |
| `LOG_LEVEL`               | `INFO`          | Python logging level                           |

Everything else is hardcoded. If you want to change it, edit the code. That's a feature, not a bug.

---

## 5. Operational behavior

### 5.1 Startup sequence

1. Load `.env`
2. Print the safety banner (§3.3) and sleep if mainnet-live
3. Connect to SQLite, create tables if missing, enable WAL mode
4. Connect to Hyperliquid via CCXT (with the right testnet/mainnet base URL)
5. Verify API key is approved for the main wallet (fail fast if not)
6. Read `bot_state` for any last-tick recovery info
7. Enter the main loop

### 5.2 The main loop

Forever:

1. Sleep until next tick boundary
2. Run the five-stage cycle (§2.1)
3. Update `bot_state.last_tick_at`
4. Catch any exception, log it, continue (do not crash the loop)

### 5.3 Shutdown

On `SIGINT` (Ctrl+C) or `SIGTERM`:

1. Stop accepting new ticks
2. Wait up to 5 seconds for the current tick to finish
3. Close the SQLite connection
4. Close the CCXT exchange connection
5. Log "Hyperator stopped cleanly"
6. Exit 0

If the current tick is mid-order-placement when shutdown is requested, the bot finishes the order placement, logs the result, then exits. **Hyperator never abandons an in-flight order.**

### 5.4 Failure modes and how Hyperator handles them

| Failure                               | Behavior                                            |
| ------------------------------------- | --------------------------------------------------- |
| Hyperliquid API timeout               | Log warning, skip tick, continue next iteration     |
| Hyperliquid API rate-limit (HTTP 429) | Log warning, sleep 30s, continue                    |
| Invalid API key on startup            | Fail fast with clear error message, exit 1          |
| SQLite write failure                  | Log error, attempt re-open, exit if persistent      |
| Strategy raises exception             | Log full traceback, treat as no-signal, continue    |
| Risk manager raises exception         | Log full traceback, **reject** the signal, continue |
| Order placement fails                 | Log the failure with full response, continue        |
| Network disconnection                 | CCXT raises; caught, logged, retried next tick      |

The principle: **the loop survives everything except invalid credentials**. A misbehaving strategy can break a tick; it cannot break the bot.

---

## 6. What "Done" looks like

Hyperator v1.0 is considered feature-complete when:

- [ ] A user can `git clone`, `uv sync`, `cp .env.example .env`, set 2 keys, and run within 10 minutes
- [ ] The bot runs continuously for 24 hours on testnet without crashing
- [ ] Every signal and every trade is logged to SQLite with no rows dropped
- [ ] The four-state safety matrix works correctly (verified by integration test)
- [ ] A reasonably competent Python developer can read the whole codebase top-to-bottom in ~30-45 minutes and understand every line (the §1.3 promise) — this readability test, not a line count, is the actual bar
- [ ] The codebase stays small enough to read in a single sitting — as a rule of thumb roughly 350-450 lines of Python across all `src/*.py` files, but this is soft guidance, not a gate

Line count is a proxy, not a target. Do NOT micro-optimize formatting, drop docstrings, or use non-standard spacing to hit a number. Standard PEP 8 — including two blank lines between top-level definitions — takes priority over line count. If the "single sitting" read starts to feel too long, the fix is fewer responsibilities, not denser code.

The hard invariants that actually keep Hyperator a teaching artifact live in §1.2, §7, and §8: exactly three source files under `src/`, exactly two third-party dependencies, and nothing from the §7 deferral table implemented here. Those stay hard. The line count never was.

Anything beyond this is out of scope for Hyperator and belongs in Track A.

---

## 7. What's deliberately deferred

These are real, useful features that **are intentionally not in Hyperator**. They live in Track A's Keeper or higher.

| Deferred feature                                     | Where it lives                         |
| ---------------------------------------------------- | -------------------------------------- |
| FastAPI HTTP server with health endpoints            | Track A, Module A3                     |
| Multi-strategy plugin system with `BaseStrategy` ABC | Track A, Module A4                     |
| Drawdown tracking and daily loss circuit breaker     | Track A, Module A5                     |
| Typer/Rich CLI with `--json`, `--dry-run`, `--yes`   | Track A, Module A6                     |
| OpenClaw integration (WhatsApp/Telegram control)     | Track A, Module A8                     |
| Render Docker deployment with persistent disk        | Track A, Module A9                     |
| API key rotation discipline                          | Track A, Module A9                     |
| Production go-live checklist and monitoring          | Track A, Module A10                    |
| Tests (unit + integration)                           | TBD; PRs welcome                       |
| Backtesting harness                                  | Out of scope, possibly a separate repo |
| Multi-asset, multi-position support                  | Track A, partially                     |
| Vault integration (Allocator role)                   | Track B                                |

The deferral table is the syllabus. Anything you wish Hyperator did but doesn't, look here to find where it's taught.

---

## 8. Contributing

Hyperator is open source under the MIT license. PRs are welcome but evaluated against the philosophy in §1.

**PRs that will be accepted:**

- Bug fixes
- Better comments and docstrings
- Clearer variable names
- Documentation improvements (especially this PRD and the README)
- New reference strategies in `strategy.py` _if they remain under 40 lines and pure_
- Performance improvements that don't add complexity

**PRs that will be rejected:**

- Adding a framework, ORM, or DI container
- Adding plugin systems
- Adding a web UI
- Adding multi-asset support
- "Cleaning up" `hyperator.py` by splitting it into many files
- Adding configuration knobs for things that should be edited in code

If a feature you want belongs in Track A, **build it as a fork** and link it from your PR description. The maintainers will likely close the PR but link to your fork from the README as a "next step" project.

---

## 9. License & disclaimer

Hyperator is released under the MIT license. See `LICENSE`.

**Use at your own risk.** Hyperator is educational software. The default `TESTNET=true, DRY_RUN=true` configuration is designed to prevent accidents. If you flip both safety switches and lose money, that is entirely your responsibility. The maintainers, Algo Traders Club, and any contributors accept no liability for losses incurred by users of this software.

Hyperliquid is a third-party platform. Hyperator is not affiliated with, endorsed by, or supported by Hyperliquid Labs or the Hyper Foundation.

---

_Hyperator is the on-ramp to the Algo Traders Club curriculum. Once you can read every line and run it confidently, you've graduated. The next door is Track A._

```

---

## Notes on what's in here and why

**The "What Hyperator is NOT" section (§1.2) is doing real work.** It defends the philosophy against scope creep. When someone PRs a FastAPI server, you point to §1.2 and §8. The PRD becomes the constitution that lets you say no without being mean.

**The four-state safety matrix (§3.3) is the most important pedagogical asset in the whole document.** Most trading-bot tutorials hand-wave about "be careful with mainnet." Hyperator names every state, marks the dangerous one in caps, and explains the 10-second sleep. This becomes the visual that students screenshot and share. It's also the foundation for the "Two Safety Switches" lesson in the course.

**The deferral table (§7) is the syllabus disguised as documentation.** Every row maps a wishlist feature to a paid track module. A student who finishes Hyperator and wants more *will* read §7 — and §7 tells them exactly where to go. It's the most natural upsell in the document because it doesn't feel like an upsell; it feels like helpful guidance.

**The PR acceptance policy (§8) defends the codebase forever.** Without it, the repo becomes a mess of contributors adding features. With it, you have written authority to close PRs while staying friendly. The "build it as a fork and we'll link to it" pattern is generous *and* protective.

**The 250-line ceiling is in §6 and is non-negotiable.** Every line you add forces you to remove one. This is the kind of constraint that makes Hyperator special. When students see a real codebase with a hard size limit, they understand that discipline is part of engineering.

**The position in the curriculum (§1.5) is explicit but soft.** It tells students the three tracks exist, but it doesn't sell them. The selling happens in Lesson 13 of the course. The PRD just plants the seed: "there's a path beyond this."

## Practical next steps

1. **Save this as `PRD.md` in the Hyperator repo root.** Make it part of the repo, not just a Skool download. Engineers will read PRDs that live next to code; they won't read PDFs they had to download.

2. **Also export as PDF for Skool.** Pandoc handles this cleanly: `pandoc PRD.md -o PRD.pdf --pdf-engine=xelatex`. Or just open in Typora / Obsidian and export. Aim for something clean and professional — this is a piece of ATC's brand.

3. **Link to the PRD prominently in the README.** First section of the README should be "Read the PRD before contributing." Sets the tone immediately.

4. **In Lesson 4 of the course, walk through §1.2 and §3.3.** Those two sections carry 80% of the philosophy. Don't try to walk through the whole PRD on camera — point to it, then highlight the two critical sections.

5. **When you write Hyperator's code, refer back to this PRD constantly.** Every architectural decision should be traceable to a numbered section. If you find yourself writing code that violates the PRD, either change the code or change the PRD — but never let them drift.

One thing to flag: the **§2.7 schema is slightly more elaborate than your original Agent Zero outline implied.** I added the `bot_state` table because the original "Crash Recovery via bot_state" lesson references it, and without it the recovery lesson doesn't work. If you want to keep the schema simpler (just `signals` and `trades`), drop `bot_state` and we'll move crash recovery entirely into Track A. Your call — I'd argue keeping it because it's only ~10 extra lines and the lesson on querying SQL is more interesting with three tables.

Want me to draft `hyperator.py` itself next, or the README, or the Skool course description for the Hyperator course?
```
