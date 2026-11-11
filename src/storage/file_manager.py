import json
import logging
import shutil
from datetime import datetime

from config import PROCESSED_FOLDER


def save_processed_data(records, original_file):
    PROCESSED_FOLDER.mkdir(parents=True, exist_ok=True)

    output_file = PROCESSED_FOLDER / f"{original_file.stem}_processed.json"

    with output_file.open("w", encoding="utf-8") as json_file:
        json.dump(records, json_file, indent=4)

    logging.info("Saved processed data to: %s", output_file.name)


def move_file(file_path, destination_folder):
    destination_folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
    destination = destination_folder / new_name

    shutil.move(str(file_path), str(destination))

    logging.info(
        "Moved %s to %s/%s",
        file_path.name,
        destination_folder.name,
        new_name,
    )
