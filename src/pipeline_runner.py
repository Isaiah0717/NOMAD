import json
import logging
import time
from pathlib import Path

PIPELINE_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "pipeline_definitions" / "pipelines.json"
)


REQUIRED_PIPELINE_FIELDS = (
    "name",
    "pipeline_type",
    "enabled",
    "source_type",
    "raw_storage",
    "destination",
)


STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_FAILED = "FAILED"
STATUS_DISABLED = "DISABLED"
STATUS_INVALID = "INVALID_DEFINITION"
STATUS_NO_EXECUTOR = "NO_EXECUTOR"


def load_pipeline_configuration():
    if not PIPELINE_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Pipeline configuration not found: {PIPELINE_CONFIG_PATH}"
        )

    with PIPELINE_CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as config_file:
        configuration = json.load(config_file)

    pipelines = configuration.get("pipelines")

    if not isinstance(pipelines, list):
        raise ValueError("Pipeline configuration must contain a 'pipelines' list.")

    return pipelines


def validate_pipeline_definition(pipeline_definition):
    if not isinstance(pipeline_definition, dict):
        raise ValueError("Pipeline definition must be a JSON object.")

    missing_fields = [
        field for field in REQUIRED_PIPELINE_FIELDS if field not in pipeline_definition
    ]

    if missing_fields:
        raise ValueError(
            "Pipeline definition is missing required field(s): "
            + ", ".join(missing_fields)
        )

    if not isinstance(pipeline_definition["enabled"], bool):
        raise ValueError(
            f"Pipeline '{pipeline_definition['name']}' "
            "'enabled' must be true or false."
        )

    if not isinstance(pipeline_definition["raw_storage"], bool):
        raise ValueError(
            f"Pipeline '{pipeline_definition['name']}' "
            "'raw_storage' must be true or false."
        )


def validate_weather_pipeline(pipeline_definition):
    pipeline_name = pipeline_definition["name"]

    if "source_name" not in pipeline_definition:
        raise ValueError(f"Pipeline '{pipeline_name}' is missing 'source_name'.")

    parameters = pipeline_definition.get("parameters")

    if not isinstance(parameters, dict):
        raise ValueError(
            f"Pipeline '{pipeline_name}' must contain a 'parameters' object."
        )

    required_parameters = (
        "location_name",
        "latitude",
        "longitude",
    )

    missing_parameters = [
        parameter for parameter in required_parameters if parameter not in parameters
    ]

    if missing_parameters:
        raise ValueError(
            f"Pipeline '{pipeline_name}' is missing parameter(s): "
            + ", ".join(missing_parameters)
        )


def validate_generic_api_pipeline(pipeline_definition):
    pipeline_name = pipeline_definition["name"]

    required_fields = (
        "source_name",
        "url",
    )

    missing_fields = [
        field for field in required_fields if field not in pipeline_definition
    ]

    if missing_fields:
        raise ValueError(
            f"Pipeline '{pipeline_name}' is missing API field(s): "
            + ", ".join(missing_fields)
        )


def validate_earthquake_pipeline(pipeline_definition):
    pipeline_name = pipeline_definition["name"]

    if "source_name" not in pipeline_definition:
        raise ValueError(f"Pipeline '{pipeline_name}' is missing 'source_name'.")

    if pipeline_definition["destination"] != "events":
        raise ValueError(
            f"Pipeline '{pipeline_name}' must use the 'events' destination."
        )


def validate_ai_news_pipeline(pipeline_definition):
    pipeline_name = pipeline_definition["name"]

    if "source_name" not in pipeline_definition:
        raise ValueError(f"Pipeline '{pipeline_name}' is missing 'source_name'.")

    if pipeline_definition["destination"] != "events":
        raise ValueError(
            f"Pipeline '{pipeline_name}' must use the 'events' destination."
        )


def validate_argus_pipeline(pipeline_definition):
    pipeline_name = pipeline_definition["name"]

    if "source_name" not in pipeline_definition:
        raise ValueError(f"Pipeline '{pipeline_name}' is missing 'source_name'.")

    if pipeline_definition["destination"] != "events":
        raise ValueError(
            f"Pipeline '{pipeline_name}' must use the 'events' destination."
        )


def validate_entity_extraction_pipeline(pipeline_definition):
    pipeline_name = pipeline_definition["name"]

    if "source_name" not in pipeline_definition:
        raise ValueError(f"Pipeline '{pipeline_name}' is missing 'source_name'.")

    if pipeline_definition["destination"] != "event_entities":
        raise ValueError(
            f"Pipeline '{pipeline_name}' must use "
            f"'event_entities' as its destination."
        )

    parameters = pipeline_definition.get("parameters")

    if not isinstance(parameters, dict):
        raise ValueError(
            f"Pipeline '{pipeline_name}' must contain a 'parameters' object."
        )

    event_types = parameters.get("event_types")

    if not isinstance(event_types, list) or not event_types:
        raise ValueError(
            f"Pipeline '{pipeline_name}' must contain " f"at least one event type."
        )


def validate_cortex_pipeline(pipeline_definition):
    pipeline_name = pipeline_definition["name"]

    source_name = pipeline_definition.get("source_name")

    if not isinstance(source_name, str) or not source_name.strip():
        raise ValueError(
            f"Pipeline '{pipeline_name}' must contain " "a non-empty 'source_name'."
        )

    if pipeline_definition["source_type"] != "intelligence":
        raise ValueError(
            f"Pipeline '{pipeline_name}' must use " "'intelligence' as its source_type."
        )

    if pipeline_definition["destination"] != "cortex_incidents":
        raise ValueError(
            f"Pipeline '{pipeline_name}' must use "
            "'cortex_incidents' as its destination."
        )

    parameters = pipeline_definition.get("parameters")

    if not isinstance(parameters, dict):
        raise ValueError(
            f"Pipeline '{pipeline_name}' must contain a 'parameters' object."
        )

    event_types = parameters.get("event_types")

    if (
        not isinstance(event_types, list)
        or not event_types
        or any(
            not isinstance(event_type, str) or not event_type.strip()
            for event_type in event_types
        )
    ):
        raise ValueError(
            f"Pipeline '{pipeline_name}' must contain "
            "a non-empty 'event_types' list of non-empty strings."
        )

    print_diagnostics = parameters.get("print_diagnostics", False)

    if not isinstance(print_diagnostics, bool):
        raise ValueError(
            f"Pipeline '{pipeline_name}' 'print_diagnostics' " "must be true or false."
        )


def validate_entity_relationship_pipeline(pipeline_definition):
    pipeline_name = pipeline_definition["name"]

    if "source_name" not in pipeline_definition:
        raise ValueError(f"Pipeline '{pipeline_name}' is missing 'source_name'.")

    if pipeline_definition["destination"] != "entity_relationships":
        raise ValueError(
            f"Pipeline '{pipeline_name}' must use "
            f"'entity_relationships' as its destination."
        )

    parameters = pipeline_definition.get("parameters")

    if not isinstance(parameters, dict):
        raise ValueError(
            f"Pipeline '{pipeline_name}' must contain a 'parameters' object."
        )

    event_types = parameters.get("event_types")

    if not isinstance(event_types, list) or not event_types:
        raise ValueError(
            f"Pipeline '{pipeline_name}' must contain " f"at least one event type."
        )

    min_co_occurrence = parameters.get("min_co_occurrence", 1)

    if (
        not isinstance(min_co_occurrence, int)
        or isinstance(min_co_occurrence, bool)
        or min_co_occurrence < 1
    ):
        raise ValueError(
            f"Pipeline '{pipeline_name}' 'min_co_occurrence' "
            f"must be an integer of 1 or more."
        )

    top_n = parameters.get("top_n", 10)

    if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n < 1:
        raise ValueError(
            f"Pipeline '{pipeline_name}' 'top_n' must be an integer of 1 or more."
        )


def validate_pulse_pipeline(pipeline_definition):
    pipeline_name = pipeline_definition["name"]

    source_name = pipeline_definition.get("source_name")

    if not isinstance(source_name, str) or not source_name.strip():
        raise ValueError(
            f"Pipeline '{pipeline_name}' must contain " "a non-empty 'source_name'."
        )

    if pipeline_definition["source_type"] != "intelligence":
        raise ValueError(
            f"Pipeline '{pipeline_name}' must use " "'intelligence' as its source_type."
        )

    if pipeline_definition["destination"] != "events":
        raise ValueError(
            f"Pipeline '{pipeline_name}' must use " "'events' as its destination."
        )

    parameters = pipeline_definition.get("parameters")

    if not isinstance(parameters, dict):
        raise ValueError(
            f"Pipeline '{pipeline_name}' must contain " "a 'parameters' object."
        )

    save_events = parameters.get("save_events", True)

    if not isinstance(save_events, bool):
        raise ValueError(
            f"Pipeline '{pipeline_name}' 'save_events' " "must be true or false."
        )

    fail_on_rejected = parameters.get(
        "fail_on_rejected",
        True,
    )

    if not isinstance(fail_on_rejected, bool):
        raise ValueError(
            f"Pipeline '{pipeline_name}' 'fail_on_rejected' " "must be true or false."
        )


PIPELINE_VALIDATORS = {
    "weather": validate_weather_pipeline,
    "api": validate_generic_api_pipeline,
    "pulse": validate_pulse_pipeline,
    "earthquake": validate_earthquake_pipeline,
    "ai_news": validate_ai_news_pipeline,
    "argus": validate_argus_pipeline,
    "entity_extraction": validate_entity_extraction_pipeline,
    "cortex": validate_cortex_pipeline,
    "entity_relationships": validate_entity_relationship_pipeline,
}


def run_single_pipeline(pipeline_definition, pipeline_registry):
    """
    Runs one pipeline in isolation.
    Always returns a result dict. Never lets an exception escape,
    so one broken pipeline cannot take down the others.
    """
    pipeline_name = (
        pipeline_definition.get("name", "(unnamed)")
        if isinstance(pipeline_definition, dict)
        else "(unnamed)"
    )

    result = {
        "name": pipeline_name,
        "status": None,
        "duration_seconds": 0.0,
        "error": None,
    }

    try:
        validate_pipeline_definition(pipeline_definition)

        pipeline_type = pipeline_definition["pipeline_type"]

        pipeline_validator = PIPELINE_VALIDATORS.get(pipeline_type)

        if pipeline_validator is not None:
            pipeline_validator(pipeline_definition)

    except ValueError as error:
        logging.error(
            "Invalid pipeline definition: %s",
            error,
        )
        result["status"] = STATUS_INVALID
        result["error"] = str(error)
        return result

    pipeline_type = pipeline_definition["pipeline_type"]
    enabled = pipeline_definition["enabled"]
    source_type = pipeline_definition["source_type"]
    raw_storage = pipeline_definition["raw_storage"]
    destination = pipeline_definition["destination"]

    if not enabled:
        logging.info(
            "Pipeline '%s' is disabled.",
            pipeline_name,
        )
        result["status"] = STATUS_DISABLED
        return result

    pipeline_function = pipeline_registry.get(pipeline_type)

    if pipeline_function is None:
        logging.error(
            "No executor is registered for pipeline type '%s'.",
            pipeline_type,
        )
        result["status"] = STATUS_NO_EXECUTOR
        result["error"] = f"No executor for type '{pipeline_type}'"
        return result

    logging.info(
        "Running pipeline '%s' | " "source=%s | " "raw_storage=%s | " "destination=%s",
        pipeline_name,
        source_type,
        raw_storage,
        destination,
    )

    start_time = time.perf_counter()

    try:
        pipeline_function(pipeline_definition)
        result["status"] = STATUS_SUCCEEDED

    except Exception as error:
        logging.exception(
            "Pipeline '%s' crashed during execution. "
            "Continuing with remaining pipelines.",
            pipeline_name,
        )
        result["status"] = STATUS_FAILED
        result["error"] = str(error)

    finally:
        result["duration_seconds"] = round(
            time.perf_counter() - start_time,
            2,
        )

    logging.info(
        "Pipeline '%s' finished | status=%s | duration=%ss",
        pipeline_name,
        result["status"],
        result["duration_seconds"],
    )

    return result


def log_run_summary(results):
    logging.info("=" * 60)
    logging.info("NOMAD RUN SUMMARY")
    logging.info("=" * 60)

    for result in results:
        line = "%-22s | %-18s | %6ss"
        arguments = [
            result["name"],
            result["status"],
            result["duration_seconds"],
        ]

        if result["error"]:
            line += " | %s"
            arguments.append(result["error"])

        if result["status"] in (STATUS_FAILED, STATUS_INVALID, STATUS_NO_EXECUTOR):
            logging.warning(line, *arguments)
        else:
            logging.info(line, *arguments)

    status_counts = {}

    for result in results:
        status_counts[result["status"]] = status_counts.get(result["status"], 0) + 1

    logging.info(
        "Totals: %s",
        ", ".join(f"{status}={count}" for status, count in status_counts.items()),
    )
    logging.info("=" * 60)


def run_configured_pipelines(pipeline_registry):
    try:
        pipeline_definitions = load_pipeline_configuration()

    except (FileNotFoundError, ValueError) as error:
        logging.error(
            "Could not load pipeline configuration: %s",
            error,
        )
        return []

    logging.info(
        "Loaded %s pipeline definition(s).",
        len(pipeline_definitions),
    )

    results = []

    for pipeline_definition in pipeline_definitions:
        result = run_single_pipeline(
            pipeline_definition,
            pipeline_registry,
        )
        results.append(result)

    log_run_summary(results)

    return results
