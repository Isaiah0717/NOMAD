import logging


def configure_logging(log_folder):
    log_folder.mkdir(parents=True, exist_ok=True)
    log_file = log_folder / "nomad.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
