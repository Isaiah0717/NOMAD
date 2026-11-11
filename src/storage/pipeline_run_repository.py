from database import get_database_connection


def start_pipeline_run(
    source_type,
    source_name,
    pipeline_name=None,
):
    sql = """
        INSERT INTO pipeline_runs (
            source_type,
            source_name,
            pipeline_name,
            status
        )
        VALUES (%s, %s, %s, %s)
        RETURNING run_id;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    source_type,
                    source_name,
                    pipeline_name,
                    "RUNNING",
                ),
            )

            run_id = cursor.fetchone()[0]

    return run_id


def complete_pipeline_run(
    run_id,
    records_read,
    records_loaded,
    records_valid=None,
    records_rejected=None,
    quality_score=None,
):
    sql = """
        UPDATE pipeline_runs
        SET
            completed_at = NOW(),
            status = %s,
            records_read = %s,
            records_loaded = %s,
            records_valid = %s,
            records_rejected = %s,
            quality_score = %s,
            error_message = NULL
        WHERE run_id = %s;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    "SUCCESS",
                    records_read,
                    records_loaded,
                    records_valid,
                    records_rejected,
                    quality_score,
                    run_id,
                ),
            )


def fail_pipeline_run(
    run_id,
    records_read,
    error_message,
):
    sql = """
        UPDATE pipeline_runs
        SET
            completed_at = NOW(),
            status = %s,
            records_read = %s,
            records_loaded = 0,
            error_message = %s
        WHERE run_id = %s;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    "FAILED",
                    records_read,
                    str(error_message),
                    run_id,
                ),
            )
