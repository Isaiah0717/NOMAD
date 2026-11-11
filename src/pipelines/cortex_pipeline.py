"""
Run CORTEX analysis and persist unreviewed candidate incidents.

Only entity-supported groups are saved.
TEXT_REVIEW pairs remain diagnostic output.

Candidate counts represent groups processed, not newly inserted rows.
Original observations in events are never deleted or merged.
"""

import logging
import sys
from pathlib import Path

SRC_FOLDER = Path(__file__).resolve().parents[1]

if str(SRC_FOLDER) not in sys.path:
    sys.path.insert(0, str(SRC_FOLDER))

from intelligence.cortex import (
    CORTEX_VERSION,
    build_incidents,
    find_matches,
    load_events,
    print_report,
)
from storage.incident_repository import save_candidate_incidents
from storage.pipeline_run_repository import (
    start_pipeline_run,
    complete_pipeline_run,
    fail_pipeline_run,
)


def process_cortex(pipeline_definition):
    pipeline_name = pipeline_definition["name"]
    source_name = pipeline_definition["source_name"]

    parameters = pipeline_definition.get("parameters", {})
    event_types = parameters.get("event_types", ["WORLD_EVENT"])

    if (
        not isinstance(event_types, list)
        or not event_types
        or any(not isinstance(value, str) or not value.strip() for value in event_types)
    ):
        raise ValueError("CORTEX requires a non-empty event_types list of strings.")

    if pipeline_definition.get("destination") != "cortex_incidents":
        raise ValueError("CORTEX destination must be 'cortex_incidents'.")

    print_diagnostics = parameters.get("print_diagnostics", False)

    if not isinstance(print_diagnostics, bool):
        raise ValueError("print_diagnostics must be true or false.")

    run_id = start_pipeline_run(
        "INTELLIGENCE",
        source_name,
        pipeline_name,
    )

    records_read = 0
    candidates_saved = False

    try:
        logging.info(
            "CORTEX analyzing extracted observations | types=%s | version=%s",
            ", ".join(event_types),
            CORTEX_VERSION,
        )

        events = load_events(event_types=event_types)
        records_read = len(events)

        pairs = find_matches(events)
        incidents = build_incidents(pairs)

        matched_pairs = sum(pair["is_match"] for pair in pairs)
        text_review_pairs = sum(pair["text_review"] for pair in pairs)

        logging.info(
            "CORTEX analysis | observations=%s | retained_pairs=%s | "
            "matched_pairs=%s | text_review_pairs=%s | candidate_groups=%s",
            records_read,
            len(pairs),
            matched_pairs,
            text_review_pairs,
            len(incidents),
        )

        if print_diagnostics:
            print_report(events, pairs, incidents)

        saved = save_candidate_incidents(
            incidents,
            cortex_version=CORTEX_VERSION,
        )
        candidates_saved = True

        grouped_event_ids = {
            member["event_id"]
            for incident in incidents
            for member in incident["members"]
        }

        # Use observation units consistently in pipeline_runs:
        # read = observations analyzed
        # valid = observations successfully analyzed
        # loaded = observations represented in saved candidate groups
        #
        # Unmatched observations are not invalid or rejected.
        complete_pipeline_run(
            run_id,
            records_read,
            len(grouped_event_ids),
            records_valid=records_read,
            records_rejected=0,
            quality_score=100.0 if records_read else 0.0,
        )

        logging.info(
            "CORTEX persistence completed | "
            "candidates_processed=%s | evidence_links_processed=%s | "
            "grouped_observations=%s | incident_ids=%s",
            saved["candidates_processed"],
            saved["evidence_links_processed"],
            len(grouped_event_ids),
            saved["incident_ids"],
        )

        logging.info(
            "CORTEX scores measure heuristic similarity, not accuracy. "
            "New candidates are UNREVIEWED; existing review decisions "
            "are preserved. Text-review pairs were not saved."
        )

        return {
            "observations_analyzed": records_read,
            "matched_pairs": matched_pairs,
            "text_review_pairs": text_review_pairs,
            "candidate_groups": len(incidents),
            "grouped_observations": len(grouped_event_ids),
            **saved,
        }

    except Exception as error:
        logging.exception("CORTEX pipeline failed.")

        if candidates_saved:
            logging.warning(
                "Candidate persistence already committed before the failure. "
                "An identical-membership rerun updates existing candidates."
            )

        try:
            fail_pipeline_run(
                run_id,
                records_read,
                error,
            )
        except Exception:
            logging.exception("Could not record the CORTEX pipeline failure.")

        raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    result = process_cortex(
        {
            "name": "cortex",
            "pipeline_type": "cortex",
            "enabled": True,
            "source_type": "intelligence",
            "source_name": "CORTEX Incident Analysis",
            "raw_storage": False,
            "destination": "cortex_incidents",
            "parameters": {
                "event_types": ["WORLD_EVENT"],
                "print_diagnostics": False,
            },
        }
    )

    print("\nCORTEX SAVED ANALYSIS")
    print("====================")

    for name, value in result.items():
        print(f"{name}: {value}")
