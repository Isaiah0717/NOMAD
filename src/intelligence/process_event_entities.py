from src.database import get_database_connection

from src.intelligence.entity_extractor import extract_entities

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


def load_ai_events():
    query = """
        SELECT
            event_id,
            title,
            description
        FROM events
        WHERE event_type = 'AI_EVENT'
        ORDER BY event_time;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)

            rows = cursor.fetchall()

    return [
        {
            "event_id": row[0],
            "title": row[1],
            "description": row[2],
        }
        for row in rows
    ]


def process_all_ai_event_entities():
    events = load_ai_events()

    events_processed = 0
    events_with_entities = 0
    relationships_created = 0

    entity_ids = {}

    print("\nNOMAD BULK ENTITY EXTRACTION")
    print("============================")
    print(f"AI events loaded: {len(events)}")

    with get_database_connection() as connection:
        with connection.cursor() as cursor:

            for event in events:
                events_processed += 1

                text = " ".join(
                    part
                    for part in [
                        event["title"],
                        event["description"],
                    ]
                    if part
                )

                extracted_entities = extract_entities(text)

                if extracted_entities:
                    events_with_entities += 1

                for entity in extracted_entities:
                    entity_key = (
                        entity["normalized_name"],
                        entity["entity_type"],
                    )

                    if entity_key not in entity_ids:
                        cursor.execute(
                            ENTITY_UPSERT_QUERY,
                            entity,
                        )

                        entity_id = cursor.fetchone()[0]

                        entity_ids[entity_key] = entity_id

                    else:
                        entity_id = entity_ids[entity_key]

                    cursor.execute(
                        EVENT_ENTITY_UPSERT_QUERY,
                        {
                            "event_id": event["event_id"],
                            "entity_id": entity_id,
                            "extraction_method": entity["extraction_method"],
                            "confidence": entity["confidence"],
                        },
                    )

                    relationships_created += 1

        connection.commit()

    print(f"Events processed:       {events_processed}")
    print(f"Events with entities:   {events_with_entities}")
    print(f"Unique entities found:  {len(entity_ids)}")
    print(f"Relationships created:  {relationships_created}")

    return {
        "events_processed": events_processed,
        "events_with_entities": events_with_entities,
        "unique_entities": len(entity_ids),
        "relationships_created": relationships_created,
    }


if __name__ == "__main__":
    process_all_ai_event_entities()
