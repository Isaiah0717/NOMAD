from database import get_database_connection

EVENT_UPSERT_QUERY = """
    INSERT INTO events (
        source,
        source_event_id,
        event_type,
        title,
        description,
        event_time,
        location_name,
        latitude,
        longitude,
        severity,
        source_url
    )
    VALUES (
        %(source)s,
        %(source_event_id)s,
        %(event_type)s,
        %(title)s,
        %(description)s,
        %(event_time)s,
        %(location_name)s,
        %(latitude)s,
        %(longitude)s,
        %(severity)s,
        %(source_url)s
    )
    ON CONFLICT (source, source_event_id)
    DO UPDATE SET
        title = EXCLUDED.title,
        description = EXCLUDED.description,
        event_time = EXCLUDED.event_time,
        location_name = EXCLUDED.location_name,
        latitude = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        severity = EXCLUDED.severity,
        source_url = EXCLUDED.source_url;
"""


def upsert_event(event):
    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                EVENT_UPSERT_QUERY,
                event,
            )

        connection.commit()


def upsert_events(events):
    if not events:
        return 0

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                EVENT_UPSERT_QUERY,
                events,
            )

        connection.commit()

    return len(events)


if __name__ == "__main__":
    from src.ingestion.earthquake_api_reader import read_earthquake_api
    from src.ingestion.earthquake_adapter import adapt_earthquake

    earthquake_data = read_earthquake_api()

    first_earthquake = earthquake_data["features"][0]

    event = adapt_earthquake(first_earthquake)

    upsert_event(event)

    print(f"NOMAD stored event: " f"{event['source_event_id']} | " f"{event['title']}")
