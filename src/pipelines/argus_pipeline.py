import logging

from ingestion.argus_reader import read_argus_news
from ingestion.argus_adapter import adapt_argus_article
from storage.event_repository import upsert_events
from storage.pipeline_run_repository import (
    start_pipeline_run,
    complete_pipeline_run,
    fail_pipeline_run,
)


def process_argus(pipeline_definition):
    pipeline_name = pipeline_definition["name"]
    source_name = pipeline_definition["source_name"]

    run_id = start_pipeline_run(
        "RSS",
        source_name,
        pipeline_name,
    )

    records_read = 0
    records_loaded = 0
    records_valid = 0
    records_rejected = 0

    try:
        logging.info("ARGUS fetching world news from %s.", source_name)

        articles = read_argus_news()

        records_read = len(articles)

        logging.info("ARGUS received %s article(s).", records_read)

        events = []
        seen_ids = set()

        for article in articles:
            try:
                event = adapt_argus_article(article)

                event_key = (event["source"], event["source_event_id"])

                if event_key in seen_ids:
                    records_rejected += 1
                    logging.warning(
                        "ARGUS duplicate ID skipped: %s",
                        event["source_event_id"],
                    )
                    continue

                seen_ids.add(event_key)
                events.append(event)
                records_valid += 1

            except (KeyError, TypeError, ValueError) as error:
                records_rejected += 1

                logging.warning(
                    "ARGUS rejected article '%s': %s",
                    article.get("title", "UNKNOWN"),
                    error,
                )

        records_loaded = upsert_events(events)

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
            "ARGUS completed | read=%s | valid=%s | rejected=%s | "
            "loaded=%s | quality=%.2f%%",
            records_read,
            records_valid,
            records_rejected,
            records_loaded,
            quality_score,
        )

    except Exception as error:
        logging.error("ARGUS pipeline failed: %s", error)

        fail_pipeline_run(
            run_id,
            records_read,
            error,
        )

        raise
