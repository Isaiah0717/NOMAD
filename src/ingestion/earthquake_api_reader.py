import requests

USGS_EARTHQUAKE_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
)


def read_earthquake_api():
    response = requests.get(
        USGS_EARTHQUAKE_URL,
        timeout=30,
    )

    response.raise_for_status()

    earthquake_data = response.json()

    return earthquake_data


if __name__ == "__main__":
    data = read_earthquake_api()

    earthquakes = data["features"]

    print(f"NOMAD received {len(earthquakes)} earthquakes.")

    if earthquakes:
        first_earthquake = earthquakes[0]

        print("\nFirst earthquake:")
        print(first_earthquake)
