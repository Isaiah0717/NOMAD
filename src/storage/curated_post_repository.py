import logging

from database import get_database_connection

UPSERT_CURATED_POST_SQL = """
    INSERT INTO curated_posts (
        post_id,
        user_id,
        title,
        body
    )
    VALUES (
        %(post_id)s,
        %(user_id)s,
        %(title)s,
        %(body)s
    )
    ON CONFLICT (post_id)
    DO UPDATE SET
        user_id = EXCLUDED.user_id,
        title = EXCLUDED.title,
        body = EXCLUDED.body,
        curated_at = NOW();
"""


def upsert_curated_posts(posts):
    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            for post in posts:
                cursor.execute(
                    UPSERT_CURATED_POST_SQL,
                    post,
                )

    logging.info(
        "Loaded %s record(s) into curated_posts.",
        len(posts),
    )
