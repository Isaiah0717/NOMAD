"""
Adapt validated daily market bars into NOMAD MARKET_EVENT records.

One logical observation per symbol and session date.

event_time uses midnight UTC as a date-only storage convention.
It is NOT an actual trade, publication, or market-close timestamp.

Daily bars can be revised by the provider. A populated Close field
does not independently prove that a session is finalized.
"""

import math
from datetime import date, datetime, time, timezone
from urllib.parse import quote

SOURCE_NAME = "Yahoo Finance via yfinance"
EVENT_TYPE = "MARKET_EVENT"

INSTRUMENT_NAMES = {
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "AAPL": "Apple",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "META": "Meta",
    "AMD": "AMD",
    "TSLA": "Tesla",
    "JPM": "JPMorgan Chase",
    "V": "Visa",
    "MA": "Mastercard",
    "CRM": "Salesforce",
    "ORCL": "Oracle",
    "WMT": "Walmart",
    "COST": "Costco",
    "HD": "Home Depot",
    "MCD": "McDonald's",
    "SPY": "SPDR S&P 500 ETF Trust",
    "QQQ": "Invesco QQQ Trust",
    "COIN": "Coinbase",
}


def require_number(record, field):
    value = record.get(field)

    if isinstance(value, bool):
        raise ValueError(f"{field} cannot be a boolean.")

    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must contain a valid number.") from None

    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite.")

    return number


def adapt_market_bar(record):
    if not isinstance(record, dict):
        raise ValueError("Market bar must be a dictionary.")

    symbol = record.get("symbol")

    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Market bar is missing its symbol.")

    symbol = symbol.strip().upper()

    if symbol not in INSTRUMENT_NAMES:
        raise ValueError(f"No configured instrument name for symbol {symbol}.")

    session_value = record.get("session_date")

    if not isinstance(session_value, str):
        raise ValueError("session_date must be an ISO date string.")

    session_date = date.fromisoformat(session_value)

    open_price = require_number(record, "open")
    high_price = require_number(record, "high")
    low_price = require_number(record, "low")
    close_price = require_number(record, "close")
    volume = require_number(record, "volume")

    if min(open_price, high_price, low_price, close_price) <= 0:
        raise ValueError("Market prices must be positive.")

    if (
        low_price > min(open_price, close_price)
        or high_price < max(open_price, close_price)
        or low_price > high_price
    ):
        raise ValueError("Market bar has inconsistent OHLC prices.")

    if volume < 0 or not volume.is_integer():
        raise ValueError("Volume must be a non-negative integer.")

    instrument_name = INSTRUMENT_NAMES[symbol]

    description = (
        f"{instrument_name} ({symbol}) daily market-bar observation "
        f"for session {session_date.isoformat()}. "
        f"Provider-reported open: {open_price:.4f} USD; "
        f"high: {high_price:.4f} USD; "
        f"low: {low_price:.4f} USD; "
        f"close: {close_price:.4f} USD; "
        f"volume: {int(volume):,} shares. "
        "Prices are unadjusted daily market values. "
        "This bar may be revised and is not a live quote. "
        "Stored event time represents the session date only, "
        "not an actual market-close timestamp."
    )

    return {
        "source": SOURCE_NAME,
        "source_event_id": (f"yfinance_{symbol}_{session_date.isoformat()}_1d"),
        "event_type": EVENT_TYPE,
        "title": (
            f"{instrument_name} ({symbol}) daily market observation "
            f"| {session_date.isoformat()}"
        ),
        "description": description,
        "event_time": datetime.combine(
            session_date,
            time.min,
            tzinfo=timezone.utc,
        ),
        "location_name": None,
        "latitude": None,
        "longitude": None,
        "severity": None,
        "source_url": (f"https://finance.yahoo.com/quote/{quote(symbol, safe='')}/"),
    }


def adapt_market_bars(records):
    valid_events = []
    rejected_records = []
    seen_ids = set()

    for record in records:
        try:
            event = adapt_market_bar(record)
            source_id = event["source_event_id"]

            if source_id in seen_ids:
                raise ValueError(f"Duplicate symbol/session observation: {source_id}")

            seen_ids.add(source_id)
            valid_events.append(event)

        except (TypeError, ValueError, OverflowError) as error:
            rejected_records.append(
                {
                    "symbol": (
                        record.get("symbol") if isinstance(record, dict) else None
                    ),
                    "session_date": (
                        record.get("session_date") if isinstance(record, dict) else None
                    ),
                    "error": str(error),
                }
            )

    return valid_events, rejected_records
