"""
PULSE: detect notable changes in stored market observations.

Signals:
    - Absolute close-to-close return >= 4%
    - Volume >= 2.5x the preceding 20 observations' average
    - New 20-session closing high with a daily return >= +2%
    - New 20-session closing low with a daily return <= -2%

All rolling baselines exclude the current observation.

Default execution is read-only.
Use --save to persist derived MARKET_EVENT records.

Limitations:
    - Existing prices are unadjusted. Splits and other corporate
      actions can produce misleading price-movement signals.
    - Baselines use available stored sessions, not an exchange calendar.
    - Daily timestamps encode session dates, not exact occurrence times.
    - These are descriptive signals, not trading recommendations.
"""

import argparse
import logging
import math
import re
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path

import pandas as pd

SRC_FOLDER = Path(__file__).resolve().parents[1]

if str(SRC_FOLDER) not in sys.path:
    sys.path.insert(0, str(SRC_FOLDER))

from database import get_database_connection
from ingestion.market_adapter import INSTRUMENT_NAMES, SOURCE_NAME
from storage.event_repository import upsert_events

PULSE_SOURCE = "PULSE Market"

RETURN_THRESHOLD = 4.0
VOLUME_THRESHOLD = 2.5
BREAKOUT_RETURN_THRESHOLD = 2.0
LOOKBACK = 20

NUMBER = r"([0-9]+(?:\.[0-9]+)?)"

BAR_PATTERN = re.compile(
    rf"Provider-reported open:\s*{NUMBER}\s*USD;\s*"
    rf"high:\s*{NUMBER}\s*USD;\s*"
    rf"low:\s*{NUMBER}\s*USD;\s*"
    rf"close:\s*{NUMBER}\s*USD;\s*"
    r"volume:\s*([0-9,]+)\s*shares\."
)

ID_PATTERN = re.compile(r"^yfinance_([A-Z0-9.-]+)_(\d{4}-\d{2}-\d{2})_1d$")


def load_market_history():
    """
    Read only original daily-bar observations.

    Filtering by source prevents PULSE from analyzing
    its own derived output.
    """

    query = """
        SELECT
            event_id,
            source_event_id,
            description,
            source_url
        FROM events
        WHERE event_type = 'MARKET_EVENT'
          AND source = %(source)s
        ORDER BY source_event_id;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"source": SOURCE_NAME},
            )
            return cursor.fetchall()


def parse_stored_bar(row):
    event_id, source_event_id, description, source_url = row

    identity = ID_PATTERN.fullmatch(str(source_event_id))

    if identity is None:
        raise ValueError("Unexpected daily-bar source identifier.")

    symbol, session_text = identity.groups()

    if symbol not in INSTRUMENT_NAMES:
        raise ValueError(f"Unknown instrument: {symbol}")

    session_date = date.fromisoformat(session_text)

    match = BAR_PATTERN.search(description or "")

    if match is None:
        raise ValueError("Could not read stored market-bar description.")

    open_price, high, low, close = (float(value) for value in match.groups()[:4])

    volume = int(match.group(5).replace(",", ""))

    if not all(
        math.isfinite(value) and value > 0
        for value in (
            open_price,
            high,
            low,
            close,
        )
    ):
        raise ValueError("Prices must be finite and positive.")

    if low > min(open_price, close) or high < max(open_price, close) or low > high:
        raise ValueError("Inconsistent market-bar prices.")

    if volume < 0:
        raise ValueError("Volume cannot be negative.")

    return {
        "event_id": int(event_id),
        "source_event_id": source_event_id,
        "symbol": symbol,
        "session_date": session_date,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "source_url": source_url,
    }


def detect_market_changes(rows):
    bars = []
    rejected = []

    for row in rows:
        try:
            bars.append(parse_stored_bar(row))

        except (
            TypeError,
            ValueError,
            OverflowError,
        ) as error:
            rejected.append(
                {
                    "event_id": row[0],
                    "error": str(error),
                }
            )

    if not bars:
        return [], rejected, 0

    frame = pd.DataFrame(bars)

    if frame.duplicated(["symbol", "session_date"]).any():
        raise ValueError(
            "Duplicate symbol/session bars found. "
            "Resolve them before calculating PULSE signals."
        )

    detections = []

    for symbol, group in frame.groupby(
        "symbol",
        sort=True,
    ):
        group = group.sort_values("session_date").copy()

        # The current session is excluded from
        # every baseline calculation.
        previous_close = group["close"].shift(1)
        previous_volume = group["volume"].shift(1)

        group["previous_close"] = previous_close
        group["previous_session"] = group["session_date"].shift(1)

        group["return_pct"] = ((group["close"] / previous_close) - 1) * 100

        group["average_volume"] = previous_volume.rolling(
            LOOKBACK,
            min_periods=LOOKBACK,
        ).mean()

        group["previous_high"] = previous_close.rolling(
            LOOKBACK,
            min_periods=LOOKBACK,
        ).max()

        group["previous_low"] = previous_close.rolling(
            LOOKBACK,
            min_periods=LOOKBACK,
        ).min()

        for _, row in group.iterrows():
            signals = []

            return_pct = row["return_pct"]
            average_volume = row["average_volume"]
            previous_high = row["previous_high"]
            previous_low = row["previous_low"]

            volume_ratio = None

            # Strong standalone price movement.
            if pd.notna(return_pct) and abs(return_pct) >= RETURN_THRESHOLD:
                signals.append("close-to-close move " f"{return_pct:+.2f}%")

            # Strong standalone volume anomaly.
            if pd.notna(average_volume) and average_volume > 0:
                volume_ratio = row["volume"] / average_volume

                if volume_ratio >= VOLUME_THRESHOLD:
                    signals.append(
                        f"volume {volume_ratio:.2f}x "
                        f"preceding {LOOKBACK}-session average"
                    )

            # A high alone is not enough.
            # It must be accompanied by meaningful
            # positive daily movement.
            if (
                pd.notna(previous_high)
                and pd.notna(return_pct)
                and row["close"] > previous_high
                and return_pct >= BREAKOUT_RETURN_THRESHOLD
            ):
                signals.append(f"new {LOOKBACK}-session closing high")

            # A low alone is not enough.
            # It must be accompanied by meaningful
            # negative daily movement.
            if (
                pd.notna(previous_low)
                and pd.notna(return_pct)
                and row["close"] < previous_low
                and return_pct <= -BREAKOUT_RETURN_THRESHOLD
            ):
                signals.append(f"new {LOOKBACK}-session closing low")

            if not signals:
                continue

            detections.append(
                {
                    "symbol": symbol,
                    "name": INSTRUMENT_NAMES[symbol],
                    "session_date": (row["session_date"]),
                    "previous_session": (row["previous_session"]),
                    "close": float(row["close"]),
                    "volume": int(row["volume"]),
                    "return_pct": (float(return_pct) if pd.notna(return_pct) else None),
                    "volume_ratio": (
                        float(volume_ratio) if volume_ratio is not None else None
                    ),
                    "signals": signals,
                    "evidence_event_id": int(row["event_id"]),
                    "evidence_source_id": (row["source_event_id"]),
                    "source_url": (row["source_url"]),
                }
            )

    detections.sort(
        key=lambda item: (
            item["session_date"],
            len(item["signals"]),
            abs(item["return_pct"] or 0.0),
        ),
        reverse=True,
    )

    return (
        detections,
        rejected,
        len(bars),
    )


def adapt_detection(detection):
    symbol = detection["symbol"]
    session_date = detection["session_date"]
    name = detection["name"]

    # Stable derived identity:
    # one PULSE event per instrument/session.
    source_event_id = f"pulse_{symbol}_" f"{session_date.isoformat()}_1d"

    signal_text = "; ".join(detection["signals"])

    description = (
        f"{name} ({symbol}) triggered PULSE "
        f"market-change rules for session "
        f"{session_date.isoformat()}: "
        f"{signal_text}. "
        f"Provider-reported close: "
        f"{detection['close']:.4f} USD. "
        f"Volume: "
        f"{detection['volume']:,} shares. "
        f"Evidence: stored event "
        f"{detection['evidence_event_id']} "
        f"({detection['evidence_source_id']}). "
        f"Rules: absolute close-to-close return "
        f"at least {RETURN_THRESHOLD:.1f}%; "
        f"volume at least "
        f"{VOLUME_THRESHOLD:.1f}x the preceding "
        f"{LOOKBACK}-session average; "
        f"or a new {LOOKBACK}-session closing "
        f"high/low accompanied by at least "
        f"{BREAKOUT_RETURN_THRESHOLD:.1f}% "
        f"movement in the breakout direction. "
        "Rolling baselines exclude the current "
        "session and use available stored "
        "observations."
    )

    if detection["return_pct"] is not None:
        description += (
            " Return comparison uses the "
            "previous available session, "
            f"{detection['previous_session']}."
        )

    description += (
        " Prices are unadjusted; corporate "
        "actions can distort signals. "
        "This is a descriptive PULSE trigger, "
        "not verified news, a causal explanation, "
        "or a trading recommendation. "
        "Event time represents the session date "
        "only."
    )

    return {
        "source": PULSE_SOURCE,
        "source_event_id": source_event_id,
        "event_type": "MARKET_EVENT",
        "title": (
            f"{name} ({symbol}): " f"{signal_text} | " f"{session_date.isoformat()}"
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
        "source_url": (detection["source_url"]),
    }


def print_report(
    detections,
    rejected,
    bars_analyzed,
    limit,
):
    detection_rate = 100.0 * len(detections) / bars_analyzed if bars_analyzed else 0.0

    print("\nPULSE - MARKET CHANGE DETECTION")
    print("==============================")
    print(f"Usable stored bars:       " f"{bars_analyzed}")
    print(f"Unusable stored records:  " f"{len(rejected)}")
    print(f"Flagged symbol/sessions:  " f"{len(detections)}")
    print(f"Detection rate:           " f"{detection_rate:.2f}%")
    print(f"Showing latest:           " f"{min(limit, len(detections))}")

    print("\nRule triggers describe market movement, " "not economic cause.")
    print("Unadjusted prices can generate " "corporate-action artifacts.")

    for detection in detections[:limit]:
        print(
            f"\n{detection['session_date']} | "
            f"{detection['name']} "
            f"({detection['symbol']})"
        )

        for signal in detection["signals"]:
            print(f"  - {signal}")

        print(
            f"  Close: "
            f"{detection['close']:.4f} USD | "
            f"Volume: "
            f"{detection['volume']:,}"
        )

        print(f"  Evidence event: " f"{detection['evidence_event_id']}")

    for rejection in rejected[:10]:
        print(f"\nSKIPPED event " f"{rejection['event_id']}: " f"{rejection['error']}")


def main():
    parser = argparse.ArgumentParser(
        description=("Detect meaningful market changes " "in NOMAD's stored history.")
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help=("Persist derived PULSE " "MARKET_EVENT records."),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help=("Number of detections printed, " "not a persistence limit."),
    )

    arguments = parser.parse_args()

    if not (1 <= arguments.limit <= 500):
        parser.error("--limit must be between " "1 and 500.")

    logging.basicConfig(
        level=logging.INFO,
        format=("%(asctime)s | " "%(levelname)s | " "%(message)s"),
    )

    rows = load_market_history()

    if not rows:
        raise RuntimeError("No original Yahoo Finance " "market observations found.")

    (
        detections,
        rejected,
        bars_analyzed,
    ) = detect_market_changes(rows)

    print_report(
        detections,
        rejected,
        bars_analyzed,
        arguments.limit,
    )

    if arguments.save:
        if rejected:
            raise RuntimeError(
                "Save stopped because some "
                "historical records could not "
                "be parsed. Review the skipped "
                "records first because missing "
                "bars could distort baselines."
            )

        events = [adapt_detection(detection) for detection in detections]

        processed = upsert_events(events)

        print(f"\nSaved/upserted " f"{processed} PULSE " f"market events.")

        print("Original daily observations " "were preserved.")

        print(
            "Existing derived PULSE events "
            "are not automatically retracted "
            "if revised historical data later "
            "stops triggering a rule."
        )

    else:
        print("\nREAD-ONLY RUN: nothing written " "to PostgreSQL.")

        print("Use --save only after inspecting " "the detected changes.")


if __name__ == "__main__":
    main()
