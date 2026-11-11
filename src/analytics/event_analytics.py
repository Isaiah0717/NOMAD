import pandas as pd

from src.database import get_database_connection


def load_events():
    query = """
        SELECT
            event_id,
            source,
            source_event_id,
            event_type,
            title,
            description,
            event_time,
            location_name,
            latitude,
            longitude,
            severity,
            source_url,
            ingested_at
        FROM events
        ORDER BY event_time DESC;
    """

    with get_database_connection() as connection:
        events = pd.read_sql(query, connection)

    return events


def build_world_events_report(events):
    print("\nNOMAD WORLD EVENTS REPORT")
    print("=========================")

    print(f"\nTotal observed events: {len(events)}")

    print("\nEVENT TYPES")
    print("-----------")
    print(events["event_type"].value_counts())

    print("\nSOURCES")
    print("-------")
    print(events["source"].value_counts())

    print("\nSEVERITY")
    print("--------")
    print(f"Average severity: {events['severity'].mean():.2f}")
    print(f"Maximum severity: {events['severity'].max():.2f}")

    significant_events = events[events["severity"] >= 5.0].copy()

    print(f"Events severity >= 5.0: " f"{len(significant_events)}")

    print("\nTOP 10 EVENTS BY SEVERITY")
    print("-------------------------")

    strongest_events = events.sort_values("severity", ascending=False).head(10)

    for _, event in strongest_events.iterrows():
        print(
            f"{event['severity']:.1f} | "
            f"{event['event_time']} | "
            f"{event['location_name']}"
        )

    print("\nEVENTS BY HOUR")
    print("--------------")

    events["event_hour"] = events["event_time"].dt.floor("h")

    hourly_events = events.groupby("event_hour").size().sort_index()

    print(hourly_events)


if __name__ == "__main__":
    events = load_events()

    build_world_events_report(events)
