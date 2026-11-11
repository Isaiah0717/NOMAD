import sys
from pathlib import Path

import pandas as pd

SRC_FOLDER = Path(__file__).resolve().parents[1]

if str(SRC_FOLDER) not in sys.path:
    sys.path.insert(0, str(SRC_FOLDER))

from database import get_database_connection

REVIEW_STATUSES = (
    "UNREVIEWED",
    "CONFIRMED",
    "REJECTED",
)


def run_query(query, parameters=None):
    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters or {})

            columns = [column.name for column in cursor.description]
            rows = cursor.fetchall()

    return pd.DataFrame(rows, columns=columns)


def normalize_event_types(event_types):
    """
    None or empty means all domains.
    A single string becomes a one-item list.
    """

    if not event_types:
        return None

    if isinstance(event_types, str):
        return [event_types]

    return list(event_types)


def event_type_filter(event_types, column="ev.event_type"):
    """
    column must be an application-controlled SQL identifier,
    never text supplied by a user.
    """

    event_types = normalize_event_types(event_types)

    if event_types is None:
        return "TRUE", {}

    return (
        f"{column} = ANY(%(event_types)s)",
        {"event_types": event_types},
    )


def get_event_types():
    query = """
        SELECT event_type, COUNT(*) AS event_count
        FROM events
        GROUP BY event_type
        ORDER BY event_count DESC;
    """

    return run_query(query)


def get_system_metrics():
    query = """
        SELECT
            (SELECT COUNT(*) FROM events) AS observed_events,
            (
                SELECT COUNT(*)
                FROM events
                WHERE event_type = 'AI_EVENT'
            ) AS ai_events,
            (
                SELECT COUNT(*)
                FROM events
                WHERE event_type = 'WORLD_EVENT'
            ) AS world_events,
            (SELECT COUNT(*) FROM entities) AS canonical_entities,
            (SELECT COUNT(*) FROM event_entities) AS entity_mentions,
            (SELECT COUNT(*) FROM entity_relationships) AS relationships,
            (SELECT MAX(ingested_at) FROM events) AS last_ingested_at;
    """

    return run_query(query).iloc[0].to_dict()


def get_entity_index(limit=500, event_types=None):
    condition, parameters = event_type_filter(event_types)

    query = f"""
        SELECT
            en.entity_id,
            en.entity_name,
            en.entity_type,
            COUNT(DISTINCT ee.event_id) AS event_count,
            MIN(ev.event_time) AS first_observed_at,
            MAX(ev.event_time) AS last_observed_at
        FROM entities en
        JOIN event_entities ee
            ON ee.entity_id = en.entity_id
        JOIN events ev
            ON ev.event_id = ee.event_id
        WHERE {condition}
        GROUP BY
            en.entity_id,
            en.entity_name,
            en.entity_type
        ORDER BY
            event_count DESC,
            en.entity_name
        LIMIT %(limit)s;
    """

    return run_query(query, {"limit": limit, **parameters})


def get_top_relationships(
    limit=150,
    min_co_occurrence=2,
    event_types=None,
):
    if normalize_event_types(event_types) is None:
        query = """
            SELECT
                r.entity_id_a,
                a.entity_name AS entity_a,
                a.entity_type AS type_a,
                r.entity_id_b,
                b.entity_name AS entity_b,
                b.entity_type AS type_b,
                r.co_occurrence_count,
                r.first_observed_at,
                r.last_observed_at
            FROM entity_relationships r
            JOIN entities a
                ON a.entity_id = r.entity_id_a
            JOIN entities b
                ON b.entity_id = r.entity_id_b
            WHERE r.co_occurrence_count >= %(min_co_occurrence)s
            ORDER BY
                r.co_occurrence_count DESC,
                r.last_observed_at DESC
            LIMIT %(limit)s;
        """

        return run_query(
            query,
            {
                "limit": limit,
                "min_co_occurrence": min_co_occurrence,
            },
        )

    condition, parameters = event_type_filter(event_types)

    query = f"""
        WITH mentions AS (
            SELECT DISTINCT
                ee.event_id,
                ee.entity_id,
                ev.event_time
            FROM event_entities ee
            JOIN events ev
                ON ev.event_id = ee.event_id
            WHERE {condition}
        ),
        pairs AS (
            SELECT
                m1.entity_id AS entity_id_a,
                m2.entity_id AS entity_id_b,
                COUNT(DISTINCT m1.event_id) AS co_occurrence_count,
                MIN(m1.event_time) AS first_observed_at,
                MAX(m1.event_time) AS last_observed_at
            FROM mentions m1
            JOIN mentions m2
                ON m2.event_id = m1.event_id
               AND m1.entity_id < m2.entity_id
            GROUP BY
                m1.entity_id,
                m2.entity_id
            HAVING COUNT(DISTINCT m1.event_id) >= %(min_co_occurrence)s
        )
        SELECT
            p.entity_id_a,
            a.entity_name AS entity_a,
            a.entity_type AS type_a,
            p.entity_id_b,
            b.entity_name AS entity_b,
            b.entity_type AS type_b,
            p.co_occurrence_count,
            p.first_observed_at,
            p.last_observed_at
        FROM pairs p
        JOIN entities a
            ON a.entity_id = p.entity_id_a
        JOIN entities b
            ON b.entity_id = p.entity_id_b
        ORDER BY
            p.co_occurrence_count DESC,
            p.last_observed_at DESC
        LIMIT %(limit)s;
    """

    return run_query(
        query,
        {
            "limit": limit,
            "min_co_occurrence": min_co_occurrence,
            **parameters,
        },
    )


def get_entity_neighborhood(entity_id, limit=40, event_types=None):
    if normalize_event_types(event_types) is None:
        query = """
            SELECT
                CASE
                    WHEN r.entity_id_a = %(entity_id)s
                        THEN r.entity_id_b
                    ELSE r.entity_id_a
                END AS neighbor_id,
                n.entity_name AS neighbor_name,
                n.entity_type AS neighbor_type,
                r.co_occurrence_count,
                r.first_observed_at,
                r.last_observed_at
            FROM entity_relationships r
            JOIN entities n
                ON n.entity_id = CASE
                    WHEN r.entity_id_a = %(entity_id)s
                        THEN r.entity_id_b
                    ELSE r.entity_id_a
                END
            WHERE r.entity_id_a = %(entity_id)s
               OR r.entity_id_b = %(entity_id)s
            ORDER BY
                r.co_occurrence_count DESC,
                r.last_observed_at DESC
            LIMIT %(limit)s;
        """

        return run_query(
            query,
            {
                "entity_id": entity_id,
                "limit": limit,
            },
        )

    condition, parameters = event_type_filter(event_types)

    query = f"""
        WITH mentions AS (
            SELECT DISTINCT
                ee.event_id,
                ee.entity_id,
                ev.event_time
            FROM event_entities ee
            JOIN events ev
                ON ev.event_id = ee.event_id
            WHERE {condition}
        )
        SELECT
            m2.entity_id AS neighbor_id,
            n.entity_name AS neighbor_name,
            n.entity_type AS neighbor_type,
            COUNT(DISTINCT m1.event_id) AS co_occurrence_count,
            MIN(m1.event_time) AS first_observed_at,
            MAX(m1.event_time) AS last_observed_at
        FROM mentions m1
        JOIN mentions m2
            ON m2.event_id = m1.event_id
           AND m2.entity_id <> m1.entity_id
        JOIN entities n
            ON n.entity_id = m2.entity_id
        WHERE m1.entity_id = %(entity_id)s
        GROUP BY
            m2.entity_id,
            n.entity_name,
            n.entity_type
        ORDER BY
            co_occurrence_count DESC,
            last_observed_at DESC
        LIMIT %(limit)s;
    """

    return run_query(
        query,
        {
            "entity_id": entity_id,
            "limit": limit,
            **parameters,
        },
    )


def get_entity_events(entity_id, limit=15, event_types=None):
    condition, parameters = event_type_filter(event_types)

    query = f"""
        SELECT
            ev.event_id,
            ev.event_time,
            ev.source,
            ev.event_type,
            ev.title,
            ev.source_url,
            ee.extraction_method,
            ee.confidence
        FROM event_entities ee
        JOIN events ev
            ON ev.event_id = ee.event_id
        WHERE ee.entity_id = %(entity_id)s
          AND {condition}
        ORDER BY ev.event_time DESC
        LIMIT %(limit)s;
    """

    return run_query(
        query,
        {
            "entity_id": entity_id,
            "limit": limit,
            **parameters,
        },
    )


def get_relationship_evidence(
    entity_id_a,
    entity_id_b,
    limit=15,
    event_types=None,
):
    condition, parameters = event_type_filter(event_types)

    query = f"""
        SELECT DISTINCT
            ev.event_id,
            ev.event_time,
            ev.source,
            ev.title,
            ev.source_url
        FROM event_entities ee1
        JOIN event_entities ee2
            ON ee2.event_id = ee1.event_id
        JOIN events ev
            ON ev.event_id = ee1.event_id
        WHERE ee1.entity_id = %(entity_id_a)s
          AND ee2.entity_id = %(entity_id_b)s
          AND {condition}
        ORDER BY ev.event_time DESC
        LIMIT %(limit)s;
    """

    return run_query(
        query,
        {
            "entity_id_a": entity_id_a,
            "entity_id_b": entity_id_b,
            "limit": limit,
            **parameters,
        },
    )


def get_recent_events(limit=25, per_type=5, event_types=None):
    condition, parameters = event_type_filter(
        event_types,
        column="event_type",
    )

    query = f"""
        SELECT
            event_id,
            event_time,
            event_type,
            source,
            title,
            location_name,
            severity
        FROM (
            SELECT
                event_id,
                event_time,
                event_type,
                source,
                title,
                location_name,
                severity,
                ROW_NUMBER() OVER (
                    PARTITION BY event_type
                    ORDER BY event_time DESC
                ) AS type_rank
            FROM events
            WHERE {condition}
        ) ranked
        WHERE type_rank <= %(per_type)s
        ORDER BY event_time DESC
        LIMIT %(limit)s;
    """

    return run_query(
        query,
        {
            "limit": limit,
            "per_type": per_type,
            **parameters,
        },
    )


# ------------------------------------------------------------
# CORTEX incident queue and review
# ------------------------------------------------------------


def validate_positive_integer(value, field_name):
    """
    Accept integer-like values, including pandas/numpy integers,
    but reject booleans, strings, fractions, and non-positive values.
    """

    import operator

    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer.")

    try:
        result = operator.index(value)
    except TypeError as error:
        raise ValueError(f"{field_name} must be a positive integer.") from error

    if result <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")

    return result


def validate_review_status(status):
    if status not in REVIEW_STATUSES:
        raise ValueError("Review status must be UNREVIEWED, CONFIRMED, or REJECTED.")

    return status


def incident_domain_filter(event_types):
    """
    A candidate belongs in a domain queue if at least one of its
    supporting observations matches that domain.

    Queue counts and evidence counts still describe the full group.
    """

    condition, parameters = event_type_filter(event_types)

    return (
        f"""
        EXISTS (
            SELECT 1
            FROM cortex_incident_events scope_link
            JOIN events ev
                ON ev.event_id = scope_link.event_id
            WHERE scope_link.incident_id = ci.incident_id
              AND {condition}
        )
        """,
        parameters,
    )


def get_cortex_metrics(event_types=None):
    condition, parameters = incident_domain_filter(event_types)

    query = f"""
        SELECT
            COUNT(*) AS candidate_incidents,
            COUNT(*) FILTER (
                WHERE ci.review_status = 'UNREVIEWED'
            ) AS unreviewed_incidents,
            COUNT(*) FILTER (
                WHERE ci.review_status = 'CONFIRMED'
            ) AS confirmed_incidents,
            COUNT(*) FILTER (
                WHERE ci.review_status = 'REJECTED'
            ) AS rejected_incidents
        FROM cortex_incidents ci
        WHERE {condition};
    """

    return run_query(query, parameters).iloc[0].to_dict()


def get_cortex_incidents(
    limit=100,
    review_status=None,
    event_types=None,
):
    limit = validate_positive_integer(limit, "limit")

    if limit > 1000:
        raise ValueError("limit must be 1000 or less.")

    condition, parameters = incident_domain_filter(event_types)
    status_condition = "TRUE"

    if review_status is not None:
        validate_review_status(review_status)
        status_condition = "ci.review_status = %(review_status)s"
        parameters["review_status"] = review_status

    query = f"""
        SELECT
            ci.incident_id,
            ci.candidate_key,
            ci.cortex_version,
            ci.review_status,
            ci.title,
            ci.match_score,
            ci.mean_pair_score,
            ci.core_entities,
            ci.sources,
            ci.first_published_at,
            ci.last_published_at,
            ci.created_at,
            ci.updated_at,
            (
                SELECT COUNT(*)
                FROM cortex_incident_events evidence
                WHERE evidence.incident_id = ci.incident_id
            ) AS evidence_count
        FROM cortex_incidents ci
        WHERE {condition}
          AND {status_condition}
        ORDER BY
            CASE ci.review_status
                WHEN 'UNREVIEWED' THEN 0
                WHEN 'CONFIRMED' THEN 1
                ELSE 2
            END,
            ci.last_published_at DESC,
            ci.incident_id DESC
        LIMIT %(limit)s;
    """

    return run_query(query, {"limit": limit, **parameters})


def get_cortex_incident_evidence(incident_id):
    """
    Return all supporting observations for one candidate.

    No domain filter or top-N limit: reviewers need the entire
    saved group's evidence, not a partial view.
    """

    incident_id = validate_positive_integer(
        incident_id,
        "incident_id",
    )

    query = """
        SELECT
            ev.event_id,
            ev.event_time,
            ev.event_type,
            ev.source,
            ev.title,
            ev.description,
            ev.source_url,
            ev.location_name,
            ev.entity_extraction_version,
            cie.linked_at,
            ARRAY(
                SELECT DISTINCT
                    en.entity_name || ' [' || en.entity_type || ']'
                FROM event_entities ee
                JOIN entities en
                    ON en.entity_id = ee.entity_id
                WHERE ee.event_id = ev.event_id
                ORDER BY
                    en.entity_name || ' [' || en.entity_type || ']'
            ) AS entities
        FROM cortex_incident_events cie
        JOIN events ev
            ON ev.event_id = cie.event_id
        WHERE cie.incident_id = %(incident_id)s
        ORDER BY ev.event_time, ev.event_id;
    """

    return run_query(query, {"incident_id": incident_id})


def update_cortex_review_status(
    incident_id,
    new_status,
    expected_status,
):
    """
    Persist a human review decision.

    CONFIRMED means the reviewer accepts the observation grouping,
    not that every source claim has been independently verified.

    expected_status prevents a stale page from overwriting a
    different current status.

    This function must NOT be cached.
    It changes only review_status and updated_at.
    """

    incident_id = validate_positive_integer(
        incident_id,
        "incident_id",
    )
    validate_review_status(new_status)
    validate_review_status(expected_status)

    if new_status == expected_status:
        raise ValueError("Choose a different status from the current status.")

    query = """
        UPDATE cortex_incidents
        SET
            review_status = %(new_status)s,
            updated_at = NOW()
        WHERE incident_id = %(incident_id)s
          AND review_status = %(expected_status)s
        RETURNING
            incident_id,
            review_status,
            updated_at;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "incident_id": incident_id,
                    "new_status": new_status,
                    "expected_status": expected_status,
                },
            )

            row = cursor.fetchone()

            if row is None:
                raise ValueError(
                    "The candidate no longer exists or its review "
                    "status changed. Refresh the queue before retrying."
                )

        connection.commit()

    return {
        "incident_id": row[0],
        "review_status": row[1],
        "updated_at": row[2],
    }


if __name__ == "__main__":
    metrics = get_system_metrics()

    print("NOMAD MEMORY ACCESS TEST")
    print("-" * 40)

    for name, value in metrics.items():
        print(f"{name:<22} {value}")

    print()
    print("EVENT TYPES")
    print(get_event_types())

    print()
    print("TOP ENTITIES (ALL DOMAINS)")
    print(get_entity_index(limit=5)[["entity_name", "entity_type", "event_count"]])

    print()
    print("TOP ENTITIES (WORLD_EVENT ONLY)")
    print(
        get_entity_index(limit=10, event_types="WORLD_EVENT")[
            ["entity_name", "entity_type", "event_count"]
        ]
    )

    print()
    print("TOP RELATIONSHIPS (WORLD_EVENT ONLY)")
    print(
        get_top_relationships(
            limit=10,
            min_co_occurrence=1,
            event_types="WORLD_EVENT",
        )[["entity_a", "entity_b", "co_occurrence_count"]]
    )

    print()
    print("CORTEX METRICS")
    print(get_cortex_metrics())

    print()
    print("CORTEX CANDIDATE QUEUE")

    incidents = get_cortex_incidents(limit=10)

    print(
        incidents[
            [
                "incident_id",
                "review_status",
                "match_score",
                "evidence_count",
                "title",
            ]
        ]
    )

    if not incidents.empty:
        first_id = int(incidents.iloc[0]["incident_id"])

        print()
        print(f"CORTEX EVIDENCE FOR INCIDENT {first_id}")

        print(
            get_cortex_incident_evidence(first_id)[
                ["event_id", "source", "event_time", "title", "entities"]
            ]
        )

    print()
    print("Read-only test complete. No review statuses were changed.")
