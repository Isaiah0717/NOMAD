from src.database import get_database_connection


def upsert_entity(entity):
    query = """
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

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, entity)

            entity_id = cursor.fetchone()[0]

        connection.commit()

    return entity_id


def link_entity_to_event(
    event_id,
    entity_id,
    extraction_method,
    confidence,
):
    query = """
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

    parameters = {
        "event_id": event_id,
        "entity_id": entity_id,
        "extraction_method": extraction_method,
        "confidence": confidence,
    }

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                parameters,
            )

        connection.commit()
