import logging
from ingestion.weather_api_reader import read_weather_api
from ingestion.weather_adapter import adapt_weather_response
from storage.raw_weather_repository import insert_raw_weather_payload
from storage.weather_repository import upsert_weather_observation
from storage.pipeline_run_repository import (
    start_pipeline_run,
    complete_pipeline_run,
    fail_pipeline_run,
)


def validate_weather_observation(observation, validation_config):
    """
    Checks an adapted weather observation against the rules in pipelines.json.
    Returns a list of problems. An empty list means the observation passed.
    """
    problems = []
    field_rules = validation_config.get("field_rules", {})

    for field_name, rules in field_rules.items():
        value = observation.get(field_name)

        if value is None:
            problems.append(f"{field_name} is missing")
            continue

        if not isinstance(value, (int, float)) or isinstance(value, bool):
            problems.append(f"{field_name} is not a number (got {value!r})")
            continue

        if "min" in rules and value < rules["min"]:
            problems.append(f"{field_name}={value} is below min {rules['min']}")

        if "max" in rules and value > rules["max"]:
            problems.append(f"{field_name}={value} is above max {rules['max']}")

    return problems


def process_weather_api(pipeline_definition):
    pipeline_name = pipeline_definition["name"]
    source_name = pipeline_definition["source_name"]
    parameters = pipeline_definition["parameters"]
    validation_config = pipeline_definition.get("validation", {})

    location_name = parameters["location_name"]
    latitude = parameters["latitude"]
    longitude = parameters["longitude"]

    logging.info(
        "Starting weather ingestion for %s.",
        location_name,
    )

    run_id = start_pipeline_run(
        "WEATHER_API",
        source_name,
        pipeline_name,
    )

    records_read = 0

    try:
        weather_data = read_weather_api(
            latitude,
            longitude,
        )
        records_read = 1
        logging.info("Weather API returned current conditions.")

        if pipeline_definition["raw_storage"]:
            insert_raw_weather_payload(
                source_name,
                weather_data,
            )

        observation = adapt_weather_response(
            weather_data,
            location_name,
        )
        logging.info(
            "Adapted weather observation for %s.",
            location_name,
        )

        problems = validate_weather_observation(
            observation,
            validation_config,
        )

        if problems:
            for problem in problems:
                logging.warning(
                    "Weather observation rejected: %s",
                    problem,
                )

            complete_pipeline_run(
                run_id,
                records_read,
                0,
                records_valid=0,
                records_rejected=1,
                quality_score=0.0,
            )

            logging.warning(
                "Weather pipeline run %s completed with a rejected observation. "
                "Nothing was written to weather_observations.",
                run_id,
            )
            return

        upsert_weather_observation(observation)

        complete_pipeline_run(
            run_id,
            records_read,
            1,
            records_valid=1,
            records_rejected=0,
            quality_score=100.0,
        )

        logging.info(
            "Weather pipeline run %s completed successfully.",
            run_id,
        )
        logging.info(
            "Weather captured: %s°F, "
            "feels like %s°F, humidity %s%%, "
            "wind %s mph.",
            observation["temperature_f"],
            observation["apparent_temperature_f"],
            observation["relative_humidity"],
            observation["wind_speed_mph"],
        )

    except ValueError as error:
        logging.error(
            "Weather API data problem: %s",
            error,
        )
        fail_pipeline_run(
            run_id,
            records_read,
            error,
        )
        raise

    except Exception as error:
        logging.error(
            "Unexpected weather API failure: %s",
            error,
        )
        fail_pipeline_run(
            run_id,
            records_read,
            error,
        )
        raise
