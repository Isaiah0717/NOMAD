import logging

from ingestion.ai_news_reader import read_ai_news
from ingestion.ai_news_adapter import adapt_ai_news
from storage.event_repository import upsert_events
from storage.pipeline_run_repository import (
    start_pipeline_run,
    complete_pipeline_run,
    fail_pipeline_run,
)


def process_ai_news(pipeline_definition):
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
        logging.info(
            "Fetching AI news events from %s.",
            source_name,
        )

        articles = read_ai_news()

        records_read = len(articles)

        logging.info(
            "AI news feed returned %s article(s).",
            records_read,
        )

        events = []

        for article in articles:
            try:
                event = adapt_ai_news(article)

                events.append(event)
                records_valid += 1

            except (KeyError, TypeError, ValueError) as error:
                records_rejected += 1

                logging.warning(
                    "Rejected AI news event '%s': %s",
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
            "AI news pipeline completed | "
            "read=%s | valid=%s | rejected=%s | "
            "loaded=%s | quality=%.2f%%",
            records_read,
            records_valid,
            records_rejected,
            records_loaded,
            quality_score,
        )

    except Exception as error:
        logging.error(
            "AI news pipeline failed: %s",
            error,
        )

        fail_pipeline_run(
            run_id,
            records_read,
            error,
        )

        raise
