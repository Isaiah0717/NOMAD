import json
import logging

from database import get_database_connection

INSERT_RAW_API_SQL = """
    INSERT INTO raw_api_data (
        pipeline_name,
        source_name,
        payload
    )
    VALUES (
        %(pipeline_name)s,
        %(source_name)s,
        %(payload)s
    );
"""


def insert_raw_api_payload(
    pipeline_name,
    source_name,
    payload,
):
    raw_record = {
        "pipeline_name": pipeline_name,
        "source_name": source_name,
        "payload": json.dumps(payload),
    }

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                INSERT_RAW_API_SQL,
                raw_record,
            )

    logging.info(
        "Stored raw API payload for pipeline '%s'.",
        pipeline_name,
    )
