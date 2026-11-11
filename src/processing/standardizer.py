def standardize_customer(record):
    return {
        "customer_id": int(record["customer_id"]),
        "name": record["name"].strip(),
        "city": record["city"].strip(),
        "total_spent": float(record["total_spent"]),
    }


def standardize_customers(records):
    standardized = []

    for row_number, record in enumerate(records, start=1):
        try:
            standardized.append(standardize_customer(record))
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError(
                f"Row {row_number} failed standardization: {error}"
            ) from error

    return standardized
