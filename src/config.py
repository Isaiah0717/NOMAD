from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_FOLDER = PROJECT_ROOT / "data"
INCOMING_FOLDER = DATA_FOLDER / "incoming"
PROCESSED_FOLDER = DATA_FOLDER / "processed"
ARCHIVE_FOLDER = DATA_FOLDER / "archive"
FAILED_FOLDER = DATA_FOLDER / "failed"
LOG_FOLDER = PROJECT_ROOT / "logs"

REQUIRED_CUSTOMER_FIELDS = {
    "customer_id",
    "name",
    "city",
    "total_spent",
}
