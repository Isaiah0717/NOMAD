import logging


def transform_posts_for_curated(records):
    curated_posts = []

    for record in records:
        curated_post = {
            "post_id": record["post_id"],
            "user_id": record["user_id"],
            "title": record["title"].strip(),
            "body": record["body"].strip(),
        }

        curated_posts.append(curated_post)

    logging.info(
        "Transformed %s record(s) for curated posts.",
        len(curated_posts),
    )

    return curated_posts
