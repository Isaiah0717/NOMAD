import logging


def standardize_generic_records(
    records,
    standardization_rules,
):
    rename_fields = standardization_rules.get(
        "rename_fields",
        {},
    )

    standardized_records = []

    for record in records:
        standardized_record = {}

        for field_name, value in record.items():
            standardized_field_name = rename_fields.get(
                field_name,
                field_name,
            )

            standardized_record[standardized_field_name] = value

        standardized_records.append(standardized_record)

    logging.info(
        "Standardized %s record(s).",
        len(standardized_records),
    )

    return standardized_records
