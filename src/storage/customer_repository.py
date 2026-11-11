import logging

from database import get_database_connection

UPSERT_SQL = """
    INSERT INTO customers (customer_id, name, city, total_spent)
    VALUES (%(customer_id)s, %(name)s, %(city)s, %(total_spent)s)
    ON CONFLICT (customer_id) DO UPDATE SET
        name = EXCLUDED.name,
        city = EXCLUDED.city,
        total_spent = EXCLUDED.total_spent;
"""


def upsert_customers(customers):
    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(UPSERT_SQL, customers)

    logging.info("Loaded %s record(s) into PostgreSQL.", len(customers))
