import logging

from ingestion.api_reader import read_api

from processing.generic_validator import validate_generic_records
from processing.generic_standardizer import standardize_generic_records
from processing.post_transformer import transform_posts_for_curated
from processing.quality_analyzer import analyze_data_quality

from storage.raw_api_repository import insert_raw_api_payload
from storage.staging_api_repository import (
    insert_staging_records,
    insert_quarantined_records,
)
from storage.curated_post_repository import upsert_curated_posts
from storage.pipeline_run_repository import (
    start_pipeline_run,
    complete_pipeline_run,
    fail_pipeline_run,
)


def process_generic_api(pipeline_definition):
    pipeline_name = pipeline_definition["name"]
    source_name = pipeline_definition["source_name"]
    url = pipeline_definition["url"]
    raw_storage = pipeline_definition["raw_storage"]

    validation_rules = pipeline_definition.get(
        "validation",
        {},
    )

    standardization_rules = pipeline_definition.get(
        "standardization",
        {},
    )

    logging.info(
        "Starting generic API pipeline '%s' from %s.",
        pipeline_name,
        source_name,
    )

    run_id = start_pipeline_run(
        "API",
        source_name,
        pipeline_name,
    )

    records_read = 0

    try:
        data = read_api(url)

        if isinstance(data, list):
            records = data
        else:
            records = [data]

        records_read = len(records)

        logging.info(
            "Generic API '%s' returned %s record(s).",
            source_name,
            records_read,
        )

        if raw_storage:
            insert_raw_api_payload(
                pipeline_name,
                source_name,
                data,
            )

        valid_records, rejected_records = validate_generic_records(
            records,
            validation_rules,
        )

        quality_report = analyze_data_quality(
            records_read,
            valid_records,
            rejected_records,
        )

        logging.info(
            "Data quality for '%s': %s%% | " "%s valid | %s rejected.",
            pipeline_name,
            quality_report["quality_score"],
            quality_report["valid_records"],
            quality_report["rejected_records"],
        )

        for reason, count in quality_report["failure_reasons"].items():
            logging.warning(
                "Quality failure: %s record(s) | %s",
                count,
                reason,
            )

        standardized_records = standardize_generic_records(
            valid_records,
            standardization_rules,
        )

        if standardized_records:
            insert_staging_records(
                pipeline_name,
                source_name,
                standardized_records,
            )

        if rejected_records:
            insert_quarantined_records(
                pipeline_name,
                source_name,
                rejected_records,
            )

        curated_posts = transform_posts_for_curated(
            standardized_records,
        )

        if curated_posts:
            upsert_curated_posts(curated_posts)

        logging.info(
            "Pipeline '%s': %s staged, %s quarantined, %s curated.",
            pipeline_name,
            len(standardized_records),
            len(rejected_records),
            len(curated_posts),
        )

        complete_pipeline_run(
            run_id,
            records_read,
            len(curated_posts),
            records_valid=quality_report["valid_records"],
            records_rejected=quality_report["rejected_records"],
            quality_score=quality_report["quality_score"],
        )

        logging.info(
            "Generic API pipeline run %s completed successfully.",
            run_id,
        )

    except ValueError as error:
        logging.error(
            "Generic API data problem for %s: %s",
            source_name,
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
            "Unexpected generic API failure for %s: %s",
            source_name,
            error,
        )

        fail_pipeline_run(
            run_id,
            records_read,
            error,
        )

        raise
