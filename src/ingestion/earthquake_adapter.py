from datetime import datetime, timezone


def adapt_earthquake(feature):
    properties = feature["properties"]
    coordinates = feature["geometry"]["coordinates"]

    event_time = datetime.fromtimestamp(
        properties["time"] / 1000,
        tz=timezone.utc,
    )

    return {
        "source": "USGS",
        "source_event_id": feature["id"],
        "event_type": "EARTHQUAKE",
        "title": properties["title"],
        "description": (
            f"Magnitude {properties['mag']} earthquake " f"near {properties['place']}"
        ),
        "event_time": event_time,
        "location_name": properties["place"],
        "latitude": coordinates[1],
        "longitude": coordinates[0],
        "severity": properties["mag"],
        "source_url": properties["url"],
    }


if __name__ == "__main__":
    from src.ingestion.earthquake_api_reader import read_earthquake_api

    earthquake_data = read_earthquake_api()
    first_earthquake = earthquake_data["features"][0]

    event = adapt_earthquake(first_earthquake)

    print("\nUSGS RAW EARTHQUAKE")
    print("===================")
    print(first_earthquake)

    print("\nNOMAD UNIVERSAL EVENT")
    print("=====================")

    for key, value in event.items():
        print(f"{key}: {value}")
