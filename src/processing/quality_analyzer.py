from collections import Counter


def analyze_data_quality(
    records_read,
    valid_records,
    rejected_records,
):
    valid_count = len(valid_records)
    rejected_count = len(rejected_records)

    if records_read == 0:
        quality_score = 100.0
    else:
        quality_score = round(
            (valid_count / records_read) * 100,
            2,
        )

    failure_reasons = Counter(
        rejected_record["reason"] for rejected_record in rejected_records
    )

    return {
        "records_read": records_read,
        "valid_records": valid_count,
        "rejected_records": rejected_count,
        "quality_score": quality_score,
        "failure_reasons": dict(failure_reasons),
    }
