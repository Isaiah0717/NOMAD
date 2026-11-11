import json


def read_json(file_path):
    try:
        with file_path.open("r", encoding="utf-8") as json_file:
            data = json.load(json_file)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON: {error}") from error

    if not isinstance(data, list):
        raise ValueError("JSON must contain a list of records.")

    return data
