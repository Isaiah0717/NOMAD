import logging

from config import (
    ARCHIVE_FOLDER,
    FAILED_FOLDER,
    INCOMING_FOLDER,
    LOG_FOLDER,
)
from logging_setup import configure_logging
from pipeline_runner import run_configured_pipelines
from pipelines.generic_api_pipeline import process_generic_api
from ingestion.csv_reader import read_csv
from ingestion.json_reader import read_json
from ingestion.api_reader import read_api
from ingestion.api_adapter import adapt_api_users

from processing.validator import validate_records
from processing.standardizer import standardize_customers

from storage.customer_repository import upsert_customers
from storage.file_manager import move_file, save_processed_data
from storage.pipeline_run_repository import (
    start_pipeline_run,
    complete_pipeline_run,
    fail_pipeline_run,
)

from pipelines.weather_pipeline import process_weather_api
from pipelines.earthquake_pipeline import process_earthquake_api
from pipelines.ai_news_pipeline import process_ai_news
from pipelines.argus_pipeline import process_argus
from pipelines.sports_pipeline import process_sports_api
from pipelines.entity_extraction_pipeline import process_entity_extraction
from pipelines.cortex_pipeline import process_cortex
from pipelines.entity_relationship_pipeline import process_entity_relationships
from pipelines.market_pipeline import process_market_api
from pipelines.pulse_pipeline import process_pulse

CUSTOMER_API_URL = ""
CUSTOMER_API_NAME = "JSONPlaceholder"


READERS = {
    ".csv": read_csv,
    ".json": read_json,
}


def process_file(file_path):
    file_extension = file_path.suffix.lower()

    source_type = file_extension.replace(".", "").upper()
    source_name = file_path.name

    run_id = start_pipeline_run(
        source_type,
        source_name,
    )

    records_read = 0
    reader = READERS.get(file_extension)

    if reader is None:
        error_message = f"Unsupported file type: {file_extension or '(no extension)'}"

        logging.warning(error_message)

        fail_pipeline_run(
            run_id,
            records_read,
            error_message,
        )

        return False

    try:
        records = reader(file_path)
        records_read = len(records)

        logging.info(
            "Read %s record(s) from %s.",
            records_read,
            source_name,
        )

        validate_records(records)
        logging.info("Validation passed.")

        customers = standardize_customers(records)

        logging.info(
            "Standardized %s record(s).",
            len(customers),
        )

        save_processed_data(
            customers,
            file_path,
        )

        upsert_customers(customers)

        complete_pipeline_run(
            run_id,
            records_read,
            len(customers),
        )

        logging.info(
            "Pipeline run %s completed successfully.",
            run_id,
        )

    except ValueError as error:
        logging.error(
            "Data problem in %s: %s",
            source_name,
            error,
        )

        fail_pipeline_run(
            run_id,
            records_read,
            error,
        )

        return False

    except Exception as error:
        logging.error(
            "Unexpected failure in %s: %s",
            source_name,
            error,
        )

        fail_pipeline_run(
            run_id,
            records_read,
            error,
        )

        return False

    return True


def process_customer_api(pipeline_definition):
    logging.info("Starting customer API ingestion.")

    run_id = start_pipeline_run(
        "API",
        CUSTOMER_API_NAME,
    )

    records_read = 0

    try:
        api_users = read_api(CUSTOMER_API_URL)
        records_read = len(api_users)

        logging.info(
            "Customer API returned %s record(s).",
            records_read,
        )

        customers = adapt_api_users(api_users)

        logging.info(
            "Adapted %s API record(s) to NOMAD customer format.",
            len(customers),
        )

        validate_records(customers)
        logging.info("Customer API validation passed.")

        customers = standardize_customers(customers)

        logging.info(
            "Standardized %s customer API record(s).",
            len(customers),
        )

        upsert_customers(customers)

        complete_pipeline_run(
            run_id,
            records_read,
            len(customers),
        )

        logging.info(
            "Customer API pipeline run %s completed successfully.",
            run_id,
        )

    except ValueError as error:
        logging.error(
            "Customer API data problem: %s",
            error,
        )

        fail_pipeline_run(
            run_id,
            records_read,
            error,
        )

    except Exception as error:
        logging.error(
            "Unexpected customer API failure: %s",
            error,
        )

        fail_pipeline_run(
            run_id,
            records_read,
            error,
        )


def process_incoming_files(pipeline_definition):
    INCOMING_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    incoming_files = sorted(
        file
        for file in INCOMING_FOLDER.iterdir()
        if file.is_file() and not file.stem.endswith("_processed")
    )

    if not incoming_files:
        logging.info("No incoming files detected.")
        return

    logging.info(
        "Detected %s incoming file(s).",
        len(incoming_files),
    )

    for file_path in incoming_files:
        logging.info(
            "Processing file: %s",
            file_path.name,
        )

        success = process_file(file_path)

        if success:
            move_file(
                file_path,
                ARCHIVE_FOLDER,
            )
        else:
            move_file(
                file_path,
                FAILED_FOLDER,
            )


PIPELINE_REGISTRY = {
    "customer_file": process_incoming_files,
    "customer_api": process_customer_api,
    "weather": process_weather_api,
    "earthquake": process_earthquake_api,
    "api": process_generic_api,
    "ai_news": process_ai_news,
    "argus": process_argus,
    "sports": process_sports_api,
    "entity_extraction": process_entity_extraction,
    "cortex": process_cortex,
    "entity_relationships": process_entity_relationships,
    "market": process_market_api,
    "pulse": process_pulse,
}


def main():
    configure_logging(LOG_FOLDER)

    logging.info("NOMAD is online.")

    run_configured_pipelines(
        PIPELINE_REGISTRY,
    )

    logging.info("NOMAD processing complete.")


if __name__ == "__main__":
    main()
