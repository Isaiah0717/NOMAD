"""
Persistence for CORTEX candidate incident groups.

Only entity-supported candidate groups are saved here.
TEXT_REVIEW pairs are not saved as incident groups.

Candidate identity is based on:
    CORTEX version + sorted member event IDs.

The same membership updates the same candidate.
Changed membership creates a different candidate snapshot.

This repository does not delete or merge source events.
"""

import hashlib
import json
import math
from datetime import datetime

from database import get_database_connection

INCIDENT_UPSERT_QUERY = """
    INSERT INTO cortex_incidents (
        candidate_key,
        cortex_version,
        title,
        match_score,
        mean_pair_score,
        core_entities,
        sources,
        first_published_at,
        last_published_at
    )
    VALUES (
        %(candidate_key)s,
        %(cortex_version)s,
        %(title)s,
        %(match_score)s,
        %(mean_pair_score)s,
        %(core_entities)s,
        %(sources)s,
        %(first_published_at)s,
        %(last_published_at)s
    )
    ON CONFLICT (candidate_key)
    DO UPDATE SET
        title = EXCLUDED.title,
        match_score = EXCLUDED.match_score,
        mean_pair_score = EXCLUDED.mean_pair_score,
        core_entities = EXCLUDED.core_entities,
        sources = EXCLUDED.sources,
        first_published_at = EXCLUDED.first_published_at,
        last_published_at = EXCLUDED.last_published_at,
        updated_at = NOW()
    RETURNING incident_id;
"""


EVENT_LINK_QUERY = """
    INSERT INTO cortex_incident_events (
        incident_id,
        event_id
    )
    VALUES (
        %(incident_id)s,
        %(event_id)s
    )
    ON CONFLICT (incident_id, event_id)
    DO NOTHING;
"""


def validate_score(value, field_name):
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number, not a boolean.")

    try:
        score = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a number.") from error

    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError(f"{field_name} must be finite and between 0 and 1.")

    return score


def validate_time(value, field_name):
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime.")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone.")

    return value


def prepare_candidate(incident, cortex_version):
    members = list(incident.get("members") or [])

    if len(members) < 2:
        raise ValueError("A candidate incident must contain at least two observations.")

    event_ids = []

    for member in members:
        event_id = member.get("event_id")

        if not isinstance(event_id, int) or isinstance(event_id, bool) or event_id <= 0:
            raise ValueError("Each member must have a positive integer event_id.")

        event_ids.append(event_id)

    if len(set(event_ids)) != len(event_ids):
        raise ValueError("A candidate incident contains duplicate event IDs.")

    ordered_members = sorted(
        members,
        key=lambda member: (
            validate_time(member.get("event_time"), "event_time"),
            member["event_id"],
        ),
    )

    title = str(ordered_members[0].get("title") or "").strip()

    if not title:
        raise ValueError("The earliest observation must have a title.")

    first_published = ordered_members[0]["event_time"]
    last_published = ordered_members[-1]["event_time"]

    # Derive these from members rather than trusting duplicate metadata.
    sources = sorted(
        {str(member.get("source") or "UNKNOWN") for member in ordered_members}
    )

    entity_counts = {}

    for member in ordered_members:
        for name in set(member.get("entities") or ()):
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Entity names must be non-empty strings.")

            entity_counts[name] = entity_counts.get(name, 0) + 1

    core_entities = sorted(
        (name for name, count in entity_counts.items() if count >= 2),
        key=lambda name: (-entity_counts[name], name),
    )

    identity = json.dumps(
        {
            "cortex_version": cortex_version,
            "event_ids": sorted(event_ids),
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    candidate_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()

    return {
        "candidate_key": candidate_key,
        "cortex_version": cortex_version,
        # Representative article title, not a generated factual summary.
        "title": title,
        "match_score": validate_score(
            incident.get("match_score"),
            "match_score",
        ),
        "mean_pair_score": validate_score(
            incident.get("mean_pair_score"),
            "mean_pair_score",
        ),
        "core_entities": core_entities,
        "sources": sources,
        "first_published_at": first_published,
        "last_published_at": last_published,
        "event_ids": sorted(event_ids),
    }


def save_candidate_incidents(incidents, cortex_version):
    """
    Save one analysis batch atomically.

    If any write fails, roll back the entire batch.
    Existing human review statuses are preserved on repeat runs.

    Returns processed candidate/link counts, not new-row counts.
    """

    if (
        not isinstance(cortex_version, str)
        or not cortex_version.strip()
        or len(cortex_version) > 50
    ):
        raise ValueError(
            "cortex_version must be a non-empty string of at most 50 characters."
        )

    candidates = [prepare_candidate(incident, cortex_version) for incident in incidents]

    keys = [candidate["candidate_key"] for candidate in candidates]

    if len(set(keys)) != len(keys):
        raise ValueError("The batch contains duplicate candidate memberships.")

    if not candidates:
        return {
            "candidates_processed": 0,
            "evidence_links_processed": 0,
            "incident_ids": [],
        }

    incident_ids = []
    evidence_links_processed = 0

    with get_database_connection() as connection:
        try:
            with connection.cursor() as cursor:
                for candidate in candidates:
                    cursor.execute(
                        INCIDENT_UPSERT_QUERY,
                        candidate,
                    )

                    incident_id = cursor.fetchone()[0]
                    incident_ids.append(incident_id)

                    for event_id in candidate["event_ids"]:
                        cursor.execute(
                            EVENT_LINK_QUERY,
                            {
                                "incident_id": incident_id,
                                "event_id": event_id,
                            },
                        )

                        evidence_links_processed += 1

            connection.commit()

        except Exception:
            connection.rollback()
            raise

    return {
        "candidates_processed": len(candidates),
        "evidence_links_processed": evidence_links_processed,
        "incident_ids": incident_ids,
    }
