import json
import logging

from database import get_database_connection

INSERT_RAW_WEATHER_SQL = """
    INSERT INTO raw_weather_api (
        source_name,
        payload
    )
    VALUES (
        %(source_name)s,
        %(payload)s
    );
"""


def insert_raw_weather_payload(source_name, payload):
    raw_record = {
        "source_name": source_name,
        "payload": json.dumps(payload),
    }

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                INSERT_RAW_WEATHER_SQL,
                raw_record,
            )

    logging.info(
        "Stored raw weather payload from %s.",
        source_name,
    )
