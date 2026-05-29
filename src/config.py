"""Configuration loaded from environment variables (PRD section 4).

The defaults are the safe configuration: TESTNET and DRY_RUN are both true, so a
fresh checkout cannot place real orders until the operator opts in (PRD section 3).
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    """Parse a boolean env var; 1/true/yes (any case) is True, anything else False."""
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


# Credentials (required; their presence is validated at startup in hyperator.main).
HYPERLIQUID_API_KEY = os.getenv("HYPERLIQUID_API_KEY", "")
HYPERLIQUID_MAIN_WALLET = os.getenv("HYPERLIQUID_MAIN_WALLET", "")

# The two safety switches (PRD section 3).
TESTNET = _bool("TESTNET", True)
DRY_RUN = _bool("DRY_RUN", True)

# Market and loop settings.
SYMBOL = os.getenv("SYMBOL", "HYPE/USDC:USDC")
TIMEFRAME = os.getenv("TIMEFRAME", "1h")
TICK_INTERVAL_SECONDS = int(os.getenv("TICK_INTERVAL_SECONDS", "60"))

# Risk gates (PRD section 2.6).
MAX_POSITION_USD = float(os.getenv("MAX_POSITION_USD", "50"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "1"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Local SQLite database, created on first run.
DB_PATH = "data/hyperator.db"
