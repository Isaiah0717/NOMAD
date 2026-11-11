import logging

TYPE_MAP = {
    "integer": int,
    "string": str,
    "float": float,
    "boolean": bool,
    "list": list,
    "object": dict,
}


def validate_generic_records(
    records,
    validation_rules,
):
    required_fields = validation_rules.get(
        "required_fields",
        [],
    )

    field_types = validation_rules.get(
        "field_types",
        {},
    )

    field_rules = validation_rules.get(
        "field_rules",
        {},
    )

    valid_records = []
    rejected_records = []

    for record in records:
        missing_fields = [
            field
            for field in required_fields
            if field not in record or record[field] is None
        ]

        if missing_fields:
            rejected_records.append(
                {
                    "record": record,
                    "reason": (
                        "Missing required field(s): " + ", ".join(missing_fields)
                    ),
                }
            )
            continue

        type_errors = []

        for field, expected_type_name in field_types.items():
            if field not in record or record[field] is None:
                continue

            expected_type = TYPE_MAP.get(expected_type_name)

            if expected_type is None:
                type_errors.append(
                    f"{field}: unknown expected type " f"'{expected_type_name}'"
                )
                continue

            field_value = record[field]

            if not isinstance(field_value, expected_type):
                actual_type = type(field_value).__name__

                type_errors.append(
                    f"{field}: expected {expected_type_name}, " f"got {actual_type}"
                )

        if type_errors:
            rejected_records.append(
                {
                    "record": record,
                    "reason": "; ".join(type_errors),
                }
            )
            continue

        rule_errors = []

        for field, rules in field_rules.items():
            if field not in record or record[field] is None:
                continue

            field_value = record[field]

            if "min" in rules:
                minimum_value = rules["min"]

                if isinstance(field_value, (int, float)):
                    if field_value < minimum_value:
                        rule_errors.append(
                            f"{field}: value must be at least "
                            f"{minimum_value}, got {field_value}"
                        )

            if "max" in rules:
                maximum_value = rules["max"]

                if isinstance(field_value, (int, float)):
                    if field_value > maximum_value:
                        rule_errors.append(
                            f"{field}: value must be no more than "
                            f"{maximum_value}, got {field_value}"
                        )

            if "min_length" in rules:
                minimum_length = rules["min_length"]

                if isinstance(
                    field_value,
                    (str, list, dict),
                ):
                    if len(field_value) < minimum_length:
                        rule_errors.append(
                            f"{field}: length must be at least "
                            f"{minimum_length}, got {len(field_value)}"
                        )

            if "max_length" in rules:
                maximum_length = rules["max_length"]

                if isinstance(
                    field_value,
                    (str, list, dict),
                ):
                    if len(field_value) > maximum_length:
                        rule_errors.append(
                            f"{field}: length must be no more than "
                            f"{maximum_length}, got {len(field_value)}"
                        )

        if rule_errors:
            rejected_records.append(
                {
                    "record": record,
                    "reason": "; ".join(rule_errors),
                }
            )
            continue

        valid_records.append(record)

    logging.info(
        "Data validation complete: %s valid, %s rejected.",
        len(valid_records),
        len(rejected_records),
    )

    return valid_records, rejected_records
