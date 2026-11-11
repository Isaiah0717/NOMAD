import logging

from ingestion.earthquake_api_reader import read_earthquake_api
from ingestion.earthquake_adapter import adapt_earthquake
from storage.event_repository import upsert_event
from storage.pipeline_run_repository import (
    start_pipeline_run,
    complete_pipeline_run,
    fail_pipeline_run,
)


def process_earthquake_api(pipeline_definition):
    pipeline_name = pipeline_definition["name"]
    source_name = pipeline_definition["source_name"]

    run_id = start_pipeline_run(
        "API",
        source_name,
        pipeline_name,
    )

    records_read = 0
    records_loaded = 0
    records_valid = 0
    records_rejected = 0

    try:
        logging.info("Fetching earthquake events from USGS.")

        earthquake_data = read_earthquake_api()
        earthquakes = earthquake_data["features"]

        records_read = len(earthquakes)

        logging.info(
            "USGS returned %s earthquake events.",
            records_read,
        )

        for earthquake in earthquakes:
            try:
                event = adapt_earthquake(earthquake)

                records_valid += 1

                upsert_event(event)

                records_loaded += 1

            except (KeyError, TypeError, ValueError) as error:
                records_rejected += 1

                logging.warning(
                    "Rejected earthquake event %s: %s",
                    earthquake.get("id", "UNKNOWN"),
                    error,
                )

        quality_score = records_valid / records_read * 100 if records_read > 0 else 0.0

        complete_pipeline_run(
            run_id,
            records_read,
            records_loaded,
            records_valid=records_valid,
            records_rejected=records_rejected,
            quality_score=quality_score,
        )

        logging.info(
            "Earthquake pipeline completed | "
            "read=%s | valid=%s | rejected=%s | loaded=%s | quality=%.2f%%",
            records_read,
            records_valid,
            records_rejected,
            records_loaded,
            quality_score,
        )

    except Exception as error:
        logging.error(
            "Earthquake pipeline failed: %s",
            error,
        )

        fail_pipeline_run(
            run_id,
            records_read,
            error,
        )

        raise
