import logging

from intelligence.pulse import (
    adapt_detection,
    detect_market_changes,
    load_market_history,
)
from storage.event_repository import upsert_events


def process_pulse(pipeline_definition):
    """
    Detect notable changes in stored original market observations.

    PULSE reads only provider-originated market bars, so derived
    PULSE events cannot feed back into PULSE detection.

    Saving is controlled by the pipeline definition.
    """

    parameters = pipeline_definition.get("parameters", {})
    save_events = parameters.get("save_events", True)
    fail_on_rejected = parameters.get("fail_on_rejected", True)

    logging.info("Starting PULSE market-change detection.")

    rows = load_market_history()

    if not rows:
        logging.info("PULSE found no original market observations to analyze.")
        return

    detections, rejected, bars_analyzed = detect_market_changes(rows)

    logging.info(
        "PULSE analyzed %s usable market bar(s), "
        "rejected %s record(s), and detected %s notable change(s).",
        bars_analyzed,
        len(rejected),
        len(detections),
    )

    for rejection in rejected:
        logging.warning(
            "PULSE rejected market event %s: %s",
            rejection["event_id"],
            rejection["error"],
        )

    if rejected and fail_on_rejected:
        raise RuntimeError(
            "PULSE stopped because one or more historical market "
            "records could not be parsed. Missing observations could "
            "distort rolling baselines."
        )

    if not save_events:
        logging.info(
            "PULSE is configured for read-only execution. "
            "No derived events were written."
        )
        return

    if not detections:
        logging.info("PULSE found no notable market changes to persist.")
        return

    events = [adapt_detection(detection) for detection in detections]

    processed = upsert_events(events)

    logging.info(
        "PULSE saved/upserted %s derived MARKET_EVENT record(s).",
        processed,
    )
