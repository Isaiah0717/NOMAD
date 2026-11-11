"""
Read daily market bars through yfinance.

No API key.
No database writes.

Rows missing required OHLCV values are skipped.
A session date is preserved as a date, not misrepresented
as an exact market-close timestamp.
"""

import logging
import math

import pandas as pd
import yfinance as yf

DEFAULT_SYMBOLS = [
    "MSFT",
    "NVDA",
    "AAPL",
    "GOOGL",
    "AMZN",
    "META",
    "AMD",
    "TSLA",
    "JPM",
    "V",
    "MA",
    "CRM",
    "ORCL",
    "WMT",
    "COST",
    "HD",
    "MCD",
    "SPY",
    "QQQ",
    "COIN",
]

REQUIRED_FIELDS = (
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
)


def read_market_bars(symbols=None):
    symbols = DEFAULT_SYMBOLS if symbols is None else symbols

    if isinstance(symbols, str):
        symbols = [symbols]

    if not isinstance(symbols, (list, tuple)) or not symbols:
        raise ValueError("Provide a non-empty list of symbols.")

    if any(not isinstance(symbol, str) or not symbol.strip() for symbol in symbols):
        raise ValueError("Every symbol must be a non-empty string.")

    symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols))

    logging.info(
        "Downloading daily market bars for %s symbols.",
        len(symbols),
    )

    data = yf.download(
        symbols,
        period="1y",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    if data is None or data.empty:
        raise RuntimeError("Market download returned no data.")

    records = []
    skipped_rows = 0
    missing_symbols = []

    for symbol in symbols:
        if isinstance(data.columns, pd.MultiIndex):
            if symbol not in data.columns.get_level_values(-1):
                missing_symbols.append(symbol)
                continue

            frame = data.xs(
                symbol,
                axis=1,
                level=-1,
            )
        else:
            if len(symbols) != 1:
                raise ValueError(
                    "Unexpected market column structure " "for a multi-symbol download."
                )

            frame = data

        if any(field not in frame.columns for field in REQUIRED_FIELDS):
            missing_symbols.append(symbol)
            continue

        symbol_records = 0

        for session_date, row in frame.iterrows():
            values = {}

            for field in REQUIRED_FIELDS:
                value = row[field]

                if pd.isna(value):
                    break

                number = float(value)

                if not math.isfinite(number):
                    break

                values[field] = number

            if len(values) != len(REQUIRED_FIELDS):
                skipped_rows += 1
                continue

            open_price = values["Open"]
            high_price = values["High"]
            low_price = values["Low"]
            close_price = values["Close"]
            volume = values["Volume"]

            if (
                min(open_price, high_price, low_price, close_price) <= 0
                or volume < 0
                or not volume.is_integer()
                or low_price > min(open_price, close_price)
                or high_price < max(open_price, close_price)
                or low_price > high_price
            ):
                skipped_rows += 1
                continue

            records.append(
                {
                    "symbol": symbol,
                    "session_date": pd.Timestamp(session_date).date().isoformat(),
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": int(volume),
                }
            )

            symbol_records += 1

        if symbol_records == 0:
            missing_symbols.append(symbol)

    missing_symbols = sorted(set(missing_symbols))

    if not records:
        raise RuntimeError("No usable market bars remained after validation.")

    logging.info(
        "Market reader completed | usable_bars=%s | "
        "skipped_rows=%s | symbols_without_usable_data=%s",
        len(records),
        skipped_rows,
        ", ".join(missing_symbols) or "none",
    )

    return {
        "records": records,
        "skipped_rows": skipped_rows,
        "missing_symbols": missing_symbols,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    result = read_market_bars()

    print("\nNOMAD MARKET READER")
    print("===================")
    print(f"Usable daily bars: {len(result['records'])}")
    print(f"Skipped rows: {result['skipped_rows']}")
    print(f"Symbols without usable data: {result['missing_symbols']}")

    print("\nLATEST USABLE BAR PER SYMBOL")

    latest = {}

    for record in result["records"]:
        symbol = record["symbol"]

        if (
            symbol not in latest
            or record["session_date"] > latest[symbol]["session_date"]
        ):
            latest[symbol] = record

    for symbol in sorted(latest):
        record = latest[symbol]

        print(
            f"{symbol:<6} "
            f"{record['session_date']} | "
            f"close={record['close']:.2f} | "
            f"volume={record['volume']:,}"
        )
