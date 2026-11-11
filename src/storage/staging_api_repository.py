import json
import logging

from database import get_database_connection

INSERT_STAGING_SQL = """
    INSERT INTO staging_api_records (
        pipeline_name,
        source_name,
        record
    )
    VALUES (
        %(pipeline_name)s,
        %(source_name)s,
        %(record)s
    );
"""


INSERT_QUARANTINE_SQL = """
    INSERT INTO quarantined_api_records (
        pipeline_name,
        source_name,
        reason,
        record
    )
    VALUES (
        %(pipeline_name)s,
        %(source_name)s,
        %(reason)s,
        %(record)s
    );
"""


def insert_staging_records(
    pipeline_name,
    source_name,
    records,
):
    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            for record in records:
                cursor.execute(
                    INSERT_STAGING_SQL,
                    {
                        "pipeline_name": pipeline_name,
                        "source_name": source_name,
                        "record": json.dumps(record),
                    },
                )

    logging.info(
        "Loaded %s valid record(s) into staging.",
        len(records),
    )


def insert_quarantined_records(
    pipeline_name,
    source_name,
    rejected_records,
):
    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            for rejected_record in rejected_records:
                cursor.execute(
                    INSERT_QUARANTINE_SQL,
                    {
                        "pipeline_name": pipeline_name,
                        "source_name": source_name,
                        "reason": rejected_record["reason"],
                        "record": json.dumps(rejected_record["record"]),
                    },
                )

    logging.info(
        "Loaded %s rejected record(s) into quarantine.",
        len(rejected_records),
    )
