"""
Coordinate market ingestion:
    reader -> adapter -> event upserts -> run tracking.

Daily observations use stable symbol/session identifiers.
Upsert counts are processed records, not necessarily new inserts.

Reader-skipped rows are reported separately because they may
represent incomplete provider bars rather than invalid events.
"""

import logging
import sys
from pathlib import Path

SRC_FOLDER = Path(__file__).resolve().parents[1]

if str(SRC_FOLDER) not in sys.path:
    sys.path.insert(0, str(SRC_FOLDER))

from ingestion.market_api_reader import (
    DEFAULT_SYMBOLS,
    read_market_bars,
)
from ingestion.market_adapter import (
    INSTRUMENT_NAMES,
    SOURCE_NAME,
    adapt_market_bars,
)
from storage.event_repository import upsert_events
from storage.pipeline_run_repository import (
    start_pipeline_run,
    complete_pipeline_run,
    fail_pipeline_run,
)


def process_market_api(pipeline_definition):
    pipeline_name = pipeline_definition["name"]
    source_name = pipeline_definition.get("source_name", SOURCE_NAME)

    if pipeline_definition.get("destination") != "events":
        raise ValueError("Market destination must be 'events'.")

    parameters = pipeline_definition.get("parameters", {})

    if not isinstance(parameters, dict):
        raise ValueError("Market parameters must be an object.")

    symbols = parameters.get("symbols", DEFAULT_SYMBOLS)

    if (
        not isinstance(symbols, list)
        or not symbols
        or any(not isinstance(symbol, str) or not symbol.strip() for symbol in symbols)
    ):
        raise ValueError("Market symbols must be a non-empty list of strings.")

    symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols))

    unknown_symbols = sorted(set(symbols) - set(INSTRUMENT_NAMES))

    if unknown_symbols:
        raise ValueError(
            "Add instrument names to market_adapter.py before "
            "requesting these symbols: " + ", ".join(unknown_symbols)
        )

    run_id = start_pipeline_run(
        "API",
        source_name,
        pipeline_name,
    )

    records_read = 0
    persistence_committed = False

    try:
        result = read_market_bars(symbols=symbols)

        records = result["records"]
        skipped_rows = result["skipped_rows"]
        missing_symbols = result["missing_symbols"]

        # Counts refer to usable bars returned by the reader.
        # Reader-skipped rows are logged separately below.
        records_read = len(records)

        logging.info(
            "Market coverage | requested_symbols=%s | "
            "symbols_with_usable_data=%s | reader_skipped_rows=%s",
            len(symbols),
            len(symbols) - len(missing_symbols),
            skipped_rows,
        )

        if missing_symbols:
            logging.warning(
                "Market download has partial symbol coverage | missing=%s",
                ", ".join(missing_symbols),
            )

        events, rejected = adapt_market_bars(records)

        for rejection in rejected:
            logging.warning(
                "Rejected market bar | symbol=%s | session=%s | error=%s",
                rejection["symbol"],
                rejection["session_date"],
                rejection["error"],
            )

        if not events:
            raise ValueError("No valid MARKET_EVENT records remained after adaptation.")

        records_loaded = upsert_events(events)
        persistence_committed = True

        quality_score = 100.0 * len(events) / records_read if records_read else 0.0

        complete_pipeline_run(
            run_id,
            records_read,
            records_loaded,
            records_valid=len(events),
            records_rejected=len(rejected),
            quality_score=quality_score,
        )

        logging.info(
            "Market pipeline completed | read=%s | valid=%s | "
            "rejected=%s | upserted=%s | adapter_quality=%.2f%%",
            records_read,
            len(events),
            len(rejected),
            records_loaded,
            quality_score,
        )

        logging.info(
            "Market observations are daily bars, not live quotes. "
            "Event timestamps encode session dates at midnight UTC, "
            "not actual trade or market-close times."
        )

        return {
            "records_read": records_read,
            "records_valid": len(events),
            "records_rejected": len(rejected),
            "records_loaded": records_loaded,
            "reader_skipped_rows": skipped_rows,
            "missing_symbols": missing_symbols,
        }

    except Exception as error:
        logging.exception("Market pipeline failed.")

        if persistence_committed:
            logging.warning(
                "Market upserts committed before the failure. "
                "A retry uses the same symbol/session identifiers."
            )

        try:
            fail_pipeline_run(
                run_id,
                records_read,
                error,
            )
        except Exception:
            logging.exception("Could not record the market pipeline failure.")

        raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    result = process_market_api(
        {
            "name": "market",
            "source_name": SOURCE_NAME,
            "destination": "events",
            "parameters": {
                "symbols": DEFAULT_SYMBOLS,
            },
        }
    )

    print("\nNOMAD MARKET INGESTION")
    print("======================")

    for name, value in result.items():
        print(f"{name}: {value}")
