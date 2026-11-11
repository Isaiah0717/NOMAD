import logging

from database import get_database_connection
from intelligence.entity_extractor import extract_entities
from intelligence.parallax import resolve_entities
from storage.pipeline_run_repository import (
    start_pipeline_run,
    complete_pipeline_run,
    fail_pipeline_run,
)

EXTRACTION_VERSION = "GLINER_0_55_PARALLAX_V1"


ENTITY_UPSERT_QUERY = """
    INSERT INTO entities (
        entity_name,
        entity_type,
        normalized_name
    )
    VALUES (
        %(entity_name)s,
        %(entity_type)s,
        %(normalized_name)s
    )
    ON CONFLICT (normalized_name, entity_type)
    DO UPDATE SET
        entity_name = EXCLUDED.entity_name
    RETURNING entity_id;
"""


EVENT_ENTITY_UPSERT_QUERY = """
    INSERT INTO event_entities (
        event_id,
        entity_id,
        extraction_method,
        confidence
    )
    VALUES (
        %(event_id)s,
        %(entity_id)s,
        %(extraction_method)s,
        %(confidence)s
    )
    ON CONFLICT (event_id, entity_id)
    DO UPDATE SET
        extraction_method = EXCLUDED.extraction_method,
        confidence = EXCLUDED.confidence;
"""


MARK_EVENT_COMPLETE_QUERY = """
    UPDATE events
    SET
        entities_extracted_at = NOW(),
        entity_extraction_version = %(extraction_version)s
    WHERE event_id = %(event_id)s;
"""


def load_pending_events(connection, event_types):
    query = """
        SELECT
            event_id,
            title,
            description
        FROM events
        WHERE entities_extracted_at IS NULL
          AND event_type = ANY(%(event_types)s)
        ORDER BY event_time;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            {
                "event_types": event_types,
            },
        )

        rows = cursor.fetchall()

    return [
        {
            "event_id": row[0],
            "title": row[1],
            "description": row[2],
        }
        for row in rows
    ]


def process_entity_extraction(pipeline_definition):
    pipeline_name = pipeline_definition["name"]
    source_name = pipeline_definition["source_name"]

    parameters = pipeline_definition.get(
        "parameters",
        {},
    )

    event_types = parameters.get(
        "event_types",
        ["AI_EVENT"],
    )

    run_id = start_pipeline_run(
        "INTELLIGENCE",
        source_name,
        pipeline_name,
    )

    records_read = 0
    records_loaded = 0
    records_valid = 0
    records_rejected = 0

    entity_ids = {}

    relationships_created = 0
    events_with_entities = 0
    entities_extracted = 0
    entities_resolved = 0

    try:
        logging.info(
            "Starting entity extraction for event types: %s",
            ", ".join(event_types),
        )

        with get_database_connection() as connection:
            events = load_pending_events(
                connection,
                event_types,
            )

            records_read = len(events)

            logging.info(
                "Found %s event(s) awaiting entity extraction.",
                records_read,
            )

            with connection.cursor() as cursor:
                for event in events:
                    try:
                        text = " ".join(
                            part
                            for part in [
                                event["title"],
                                event["description"],
                            ]
                            if part
                        )

                        extracted_entities = extract_entities(text)

                        entities_extracted += len(extracted_entities)

                        resolved_entities = resolve_entities(extracted_entities)

                        entities_resolved += len(resolved_entities)

                        if resolved_entities:
                            events_with_entities += 1

                        for entity in resolved_entities:
                            entity_parameters = {
                                "entity_name": entity["canonical_name"],
                                "entity_type": entity["entity_type"],
                                "normalized_name": entity["normalized_name"],
                            }

                            entity_key = (
                                entity["normalized_name"],
                                entity["entity_type"],
                            )

                            entity_id = entity_ids.get(entity_key)

                            if entity_id is None:
                                cursor.execute(
                                    ENTITY_UPSERT_QUERY,
                                    entity_parameters,
                                )

                                entity_id = cursor.fetchone()[0]

                                entity_ids[entity_key] = entity_id

                            relationship_method = (
                                f"{entity['extraction_method']}"
                                f"+{entity['resolution_method']}"
                            )

                            relationship_confidence = min(
                                entity["extraction_confidence"],
                                entity["resolution_confidence"],
                            )

                            cursor.execute(
                                EVENT_ENTITY_UPSERT_QUERY,
                                {
                                    "event_id": event["event_id"],
                                    "entity_id": entity_id,
                                    "extraction_method": (relationship_method),
                                    "confidence": (relationship_confidence),
                                },
                            )

                            relationships_created += 1

                        cursor.execute(
                            MARK_EVENT_COMPLETE_QUERY,
                            {
                                "event_id": event["event_id"],
                                "extraction_version": (EXTRACTION_VERSION),
                            },
                        )

                        records_valid += 1
                        records_loaded += 1

                    except Exception as error:
                        records_rejected += 1

                        logging.warning(
                            "Entity intelligence failed " "for event %s: %s",
                            event["event_id"],
                            error,
                        )

            connection.commit()

        quality_score = (
            records_valid / records_read * 100 if records_read > 0 else 100.0
        )

        complete_pipeline_run(
            run_id,
            records_read,
            records_loaded,
            records_valid=records_valid,
            records_rejected=records_rejected,
            quality_score=quality_score,
        )

        logging.info(
            "Entity intelligence completed | "
            "events=%s | "
            "events_with_entities=%s | "
            "extracted_entities=%s | "
            "resolved_entities=%s | "
            "unique_canonical_entities=%s | "
            "relationships=%s | "
            "rejected=%s | "
            "quality=%.2f%%",
            records_read,
            events_with_entities,
            entities_extracted,
            entities_resolved,
            len(entity_ids),
            relationships_created,
            records_rejected,
            quality_score,
        )

    except Exception as error:
        logging.error(
            "Entity intelligence pipeline failed: %s",
            error,
        )

        fail_pipeline_run(
            run_id,
            records_read,
            error,
        )

        raise
