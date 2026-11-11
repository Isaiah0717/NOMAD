import time
from datetime import datetime

from config import LOG_FOLDER
from logging_setup import configure_logging
from main import (
    process_incoming_files,
    process_weather_api,
)

FILE_INTERVAL_SECONDS = 30
WEATHER_INTERVAL_SECONDS = 900


def run_automation_loop():
    configure_logging(LOG_FOLDER)

    print("NOMAD automation is online.")
    print("File intake: every 30 seconds.")
    print("Weather ingestion: every 15 minutes.")
    print("Press Ctrl+C to stop NOMAD safely.")

    last_file_run = 0
    last_weather_run = 0

    try:
        while True:
            now = time.time()

            if now - last_file_run >= FILE_INTERVAL_SECONDS:
                print()
                print(
                    f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                    "Checking incoming files..."
                )

                process_incoming_files()
                last_file_run = now

            if now - last_weather_run >= WEATHER_INTERVAL_SECONDS:
                print()
                print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] " "Collecting weather...")

                process_weather_api()
                last_weather_run = now

            time.sleep(1)

    except KeyboardInterrupt:
        print()
        print("Shutdown requested.")
        print("NOMAD automation stopped safely.")


if __name__ == "__main__":
    run_automation_loop()
