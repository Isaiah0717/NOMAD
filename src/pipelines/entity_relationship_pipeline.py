import logging

from database import get_database_connection
from storage.pipeline_run_repository import (
    start_pipeline_run,
    complete_pipeline_run,
    fail_pipeline_run,
)

COUNT_SOURCE_QUERY = """
    SELECT
        COUNT(*) AS mention_count,
        COUNT(DISTINCT ee.event_id) AS event_count
    FROM event_entities ee
    JOIN events e
        ON e.event_id = ee.event_id
    WHERE e.event_type = ANY(%(event_types)s);
"""


CLEAR_RELATIONSHIPS_QUERY = """
    TRUNCATE TABLE entity_relationships;
"""


BUILD_RELATIONSHIPS_QUERY = """
    INSERT INTO entity_relationships (
        entity_id_a,
        entity_id_b,
        co_occurrence_count,
        first_observed_at,
        last_observed_at
    )
    SELECT
        ee1.entity_id AS entity_id_a,
        ee2.entity_id AS entity_id_b,
        COUNT(DISTINCT ee1.event_id) AS co_occurrence_count,
        MIN(e.event_time) AS first_observed_at,
        MAX(e.event_time) AS last_observed_at
    FROM event_entities ee1
    JOIN event_entities ee2
        ON ee1.event_id = ee2.event_id
       AND ee1.entity_id < ee2.entity_id
    JOIN events e
        ON e.event_id = ee1.event_id
    WHERE e.event_type = ANY(%(event_types)s)
    GROUP BY
        ee1.entity_id,
        ee2.entity_id
    HAVING COUNT(DISTINCT ee1.event_id) >= %(min_co_occurrence)s;
"""


TOP_RELATIONSHIPS_QUERY = """
    SELECT
        a.entity_name,
        b.entity_name,
        r.co_occurrence_count
    FROM entity_relationships r
    JOIN entities a
        ON a.entity_id = r.entity_id_a
    JOIN entities b
        ON b.entity_id = r.entity_id_b
    ORDER BY
        r.co_occurrence_count DESC,
        r.last_observed_at DESC
    LIMIT %(top_n)s;
"""


def process_entity_relationships(pipeline_definition):
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

    min_co_occurrence = parameters.get(
        "min_co_occurrence",
        1,
    )

    top_n = parameters.get(
        "top_n",
        10,
    )

    run_id = start_pipeline_run(
        "INTELLIGENCE",
        source_name,
        pipeline_name,
    )

    records_read = 0
    records_loaded = 0

    try:
        logging.info(
            "Starting entity relationship build for event types: %s",
            ", ".join(event_types),
        )

        with get_database_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    COUNT_SOURCE_QUERY,
                    {
                        "event_types": event_types,
                    },
                )

                mention_count, event_count = cursor.fetchone()

                records_read = mention_count

                logging.info(
                    "Relationship source: %s entity mention(s) across %s event(s).",
                    mention_count,
                    event_count,
                )

                cursor.execute(CLEAR_RELATIONSHIPS_QUERY)

                cursor.execute(
                    BUILD_RELATIONSHIPS_QUERY,
                    {
                        "event_types": event_types,
                        "min_co_occurrence": min_co_occurrence,
                    },
                )

                records_loaded = cursor.rowcount

                cursor.execute(
                    TOP_RELATIONSHIPS_QUERY,
                    {
                        "top_n": top_n,
                    },
                )

                top_relationships = cursor.fetchall()

            connection.commit()

        for entity_a, entity_b, count in top_relationships:
            logging.info(
                "Relationship | %s <-> %s | shared_events=%s",
                entity_a,
                entity_b,
                count,
            )

        complete_pipeline_run(
            run_id,
            records_read,
            records_loaded,
            records_valid=records_loaded,
            records_rejected=0,
            quality_score=100.0,
        )

        logging.info(
            "Entity relationship build completed | "
            "mentions=%s | "
            "relationships=%s | "
            "min_co_occurrence=%s",
            records_read,
            records_loaded,
            min_co_occurrence,
        )

    except Exception as error:
        logging.error(
            "Entity relationship pipeline failed: %s",
            error,
        )

        fail_pipeline_run(
            run_id,
            records_read,
            error,
        )

        raise
