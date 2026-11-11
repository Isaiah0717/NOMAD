from config import REQUIRED_CUSTOMER_FIELDS


def validate_records(records):
    if not records:
        raise ValueError("The file contains no records.")

    for row_number, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"Row {row_number} is not a valid record.")

        missing_fields = REQUIRED_CUSTOMER_FIELDS - set(record.keys())

        if missing_fields:
            raise ValueError(
                f"Row {row_number} missing required fields: {sorted(missing_fields)}"
            )
