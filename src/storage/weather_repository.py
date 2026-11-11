import logging

from database import get_database_connection

UPSERT_WEATHER_SQL = """
    INSERT INTO weather_observations (
        location_name,
        latitude,
        longitude,
        observed_at,
        temperature_f,
        apparent_temperature_f,
        relative_humidity,
        precipitation_inches,
        wind_speed_mph,
        weather_code
    )
    VALUES (
        %(location_name)s,
        %(latitude)s,
        %(longitude)s,
        %(observed_at)s,
        %(temperature_f)s,
        %(apparent_temperature_f)s,
        %(relative_humidity)s,
        %(precipitation_inches)s,
        %(wind_speed_mph)s,
        %(weather_code)s
    )
    ON CONFLICT (location_name, observed_at)
    DO UPDATE SET
        latitude = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        temperature_f = EXCLUDED.temperature_f,
        apparent_temperature_f = EXCLUDED.apparent_temperature_f,
        relative_humidity = EXCLUDED.relative_humidity,
        precipitation_inches = EXCLUDED.precipitation_inches,
        wind_speed_mph = EXCLUDED.wind_speed_mph,
        weather_code = EXCLUDED.weather_code;
"""


def upsert_weather_observation(observation):
    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                UPSERT_WEATHER_SQL,
                observation,
            )

    logging.info(
        "Loaded weather observation for %s into PostgreSQL.",
        observation["location_name"],
    )
