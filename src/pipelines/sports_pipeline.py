"""
ESPN NFL scoreboard ingestion.

Fetches games, adapts them to SPORTS_EVENT records, and upserts
them through NOMAD's existing event repository.

Repeated scoreboard requests update existing game records.
sports_data is returned by the parser but is not persisted by
the current generic events repository.
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

SRC_FOLDER = Path(__file__).resolve().parents[1]

if str(SRC_FOLDER) not in sys.path:
    sys.path.insert(0, str(SRC_FOLDER))

from storage.event_repository import upsert_events
from storage.pipeline_run_repository import (
    start_pipeline_run,
    complete_pipeline_run,
    fail_pipeline_run,
)

ESPN_NFL_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/" "sports/football/nfl/scoreboard"
)

SOURCE_NAME = "ESPN NFL"
EVENT_TYPE = "SPORTS_EVENT"


def parse_datetime(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Game is missing a valid kickoff timestamp.")

    timestamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Kickoff timestamp must include a timezone.")

    return timestamp.astimezone(timezone.utc)


def get_competition(event):
    competitions = event.get("competitions")

    if not isinstance(competitions, list) or not competitions:
        raise ValueError("Game has no competitions list.")

    competition = competitions[0]

    if not isinstance(competition, dict):
        raise ValueError("Game competition must be an object.")

    return competition


def get_competitors(competition):
    competitors = competition.get("competitors")

    if not isinstance(competitors, list):
        raise ValueError("Game competitors must be a list.")

    home = None
    away = None

    for competitor in competitors:
        if not isinstance(competitor, dict):
            continue

        if competitor.get("homeAway") == "home":
            home = competitor
        elif competitor.get("homeAway") == "away":
            away = competitor

    if home is None or away is None:
        raise ValueError("Game is missing a home or away competitor.")

    return home, away


def get_team_name(competitor):
    team = competitor.get("team") or {}

    if not isinstance(team, dict):
        raise ValueError("Competitor team must be an object.")

    for field in ("displayName", "shortDisplayName", "name"):
        value = team.get(field)

        if isinstance(value, str) and value.strip():
            return value.strip()

    raise ValueError("Competitor is missing its team name.")


def get_score(competitor):
    score = competitor.get("score")

    if score is None:
        return None

    return str(score)


def get_status(competition, event):
    status = competition.get("status") or event.get("status") or {}

    if not isinstance(status, dict):
        raise ValueError("Game status must be an object.")

    status_type = status.get("type") or {}

    if not isinstance(status_type, dict):
        raise ValueError("Game status type must be an object.")

    return {
        "name": status_type.get("name"),
        "state": status_type.get("state"),
        "description": status_type.get("description"),
        "detail": status_type.get("detail"),
        "completed": status_type.get("completed") is True,
        "period": status.get("period"),
        "clock": status.get("displayClock"),
    }


def get_location(competition):
    venue = competition.get("venue") or {}

    if not isinstance(venue, dict):
        raise ValueError("Game venue must be an object.")

    address = venue.get("address") or {}

    if not isinstance(address, dict):
        address = {}

    location_parts = [
        value.strip()
        for value in (
            address.get("city"),
            address.get("state"),
            address.get("country"),
        )
        if isinstance(value, str) and value.strip()
    ]

    return (
        venue.get("fullName"),
        ", ".join(location_parts) or None,
    )


def get_broadcast(competition):
    broadcast = competition.get("broadcast")

    if isinstance(broadcast, str) and broadcast.strip():
        return broadcast.strip()

    broadcasts = competition.get("broadcasts") or []

    if not isinstance(broadcasts, list):
        return None

    names = []

    for group in broadcasts:
        if not isinstance(group, dict):
            continue

        for name in group.get("names") or []:
            if isinstance(name, str) and name not in names:
                names.append(name)

    return ", ".join(names) or None


def get_source_url(event):
    links = event.get("links") or []

    if not isinstance(links, list):
        return None

    fallback = None

    for link in links:
        if not isinstance(link, dict):
            continue

        href = link.get("href")

        if not isinstance(href, str):
            continue

        try:
            parsed = urlsplit(href)
        except ValueError:
            continue

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue

        if fallback is None:
            fallback = href

        relations = link.get("rel") or []

        if "summary" in relations or "event" in relations:
            return href

    return fallback


def build_description(
    home_team,
    away_team,
    home_score,
    away_score,
    status,
    venue_name,
    broadcast,
    season_year,
    week_number,
):
    parts = []

    if season_year is not None:
        season_text = f"NFL {season_year}"

        if week_number is not None:
            season_text += f" Week {week_number}"

        parts.append(season_text + ".")

    scores_available = home_score is not None and away_score is not None

    if status["completed"] and scores_available:
        parts.append(f"Final: {away_team} {away_score}, " f"{home_team} {home_score}.")
    elif status["state"] == "in" and scores_available:
        parts.append(
            f"In progress: {away_team} {away_score}, " f"{home_team} {home_score}."
        )
    else:
        parts.append(f"{away_team} at {home_team}.")

    detail = status["detail"] or status["description"]

    if detail:
        parts.append(f"Status: {detail}.")

    if venue_name:
        parts.append(f"Venue: {venue_name}.")

    if broadcast:
        parts.append(f"Broadcast: {broadcast}.")

    return " ".join(parts)


def parse_espn_event(event):
    if not isinstance(event, dict):
        raise ValueError("ESPN event must be an object.")

    raw_id = event.get("id")

    if raw_id is None or isinstance(raw_id, bool):
        raise ValueError("ESPN event is missing its game ID.")

    event_id = str(raw_id).strip()

    if not event_id:
        raise ValueError("ESPN event has an empty game ID.")

    competition = get_competition(event)
    home, away = get_competitors(competition)

    home_team = get_team_name(home)
    away_team = get_team_name(away)
    home_score = get_score(home)
    away_score = get_score(away)

    status = get_status(competition, event)
    venue_name, location_name = get_location(competition)
    broadcast = get_broadcast(competition)

    season = event.get("season") or {}
    week = event.get("week") or {}

    if not isinstance(season, dict):
        season = {}

    if not isinstance(week, dict):
        week = {}

    season_year = season.get("year")
    week_number = week.get("number")

    return {
        "source": SOURCE_NAME,
        "source_event_id": f"espn_nfl_{event_id}",
        "event_type": EVENT_TYPE,
        "title": f"{away_team} at {home_team}",
        "description": build_description(
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            status=status,
            venue_name=venue_name,
            broadcast=broadcast,
            season_year=season_year,
            week_number=week_number,
        ),
        "event_time": parse_datetime(competition.get("date") or event.get("date")),
        "location_name": location_name,
        "latitude": None,
        "longitude": None,
        "severity": None,
        "source_url": get_source_url(event),
        "sports_data": {
            "league": "NFL",
            "espn_event_id": event_id,
            "season_year": season_year,
            "season_type": season.get("slug"),
            "week": week_number,
            "status": status["description"],
            "status_state": status["state"],
            "completed": status["completed"],
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "venue": venue_name,
            "broadcast": broadcast,
        },
    }


def parse_espn_scoreboard(payload):
    if not isinstance(payload, dict):
        raise ValueError("ESPN payload must be a JSON object.")

    raw_events = payload.get("events")

    if not isinstance(raw_events, list):
        raise ValueError("ESPN payload is missing its events list.")

    valid_events = []
    rejected_events = []
    seen_ids = set()

    for raw_event in raw_events:
        try:
            event = parse_espn_event(raw_event)
            source_id = event["source_event_id"]

            if source_id in seen_ids:
                raise ValueError(f"Duplicate game ID in scoreboard: {source_id}")

            seen_ids.add(source_id)
            valid_events.append(event)

        except (TypeError, ValueError) as error:
            rejected_events.append(
                {
                    "source_event_id": (
                        raw_event.get("id") if isinstance(raw_event, dict) else None
                    ),
                    "error": str(error),
                }
            )

    return valid_events, rejected_events


def fetch_espn_scoreboard():
    logging.info("Fetching NFL scoreboard from ESPN.")

    response = requests.get(
        ESPN_NFL_SCOREBOARD_URL,
        timeout=30,
        headers={
            "User-Agent": "NOMAD/1.0",
            "Accept": "application/json",
        },
    )
    response.raise_for_status()

    payload = response.json()

    if not isinstance(payload, dict):
        raise ValueError("ESPN response must be a JSON object.")

    return payload


def process_sports_api(pipeline_definition):
    pipeline_name = pipeline_definition["name"]
    source_name = pipeline_definition.get("source_name", SOURCE_NAME)

    if pipeline_definition.get("destination") != "events":
        raise ValueError("Sports pipeline destination must be 'events'.")

    run_id = start_pipeline_run(
        "API",
        source_name,
        pipeline_name,
    )

    records_read = 0
    persistence_committed = False

    try:
        payload = fetch_espn_scoreboard()
        events, rejected = parse_espn_scoreboard(payload)

        records_read = len(events) + len(rejected)

        for rejection in rejected:
            logging.warning(
                "Rejected ESPN game %s | %s",
                rejection["source_event_id"],
                rejection["error"],
            )

        if records_read and not events:
            raise ValueError("Every ESPN game was rejected. No games were loaded.")

        records_loaded = upsert_events(events)
        persistence_committed = True

        quality_score = 100.0 * len(events) / records_read if records_read else 0.0

        complete_pipeline_run(
            run_id,
            records_read,
            records_loaded,
            records_valid=len(events),
            records_rejected=len(rejected),
            quality_score=quality_score,
        )

        logging.info(
            "Sports pipeline completed | read=%s | valid=%s | "
            "rejected=%s | upserted=%s | quality=%.2f%%",
            records_read,
            len(events),
            len(rejected),
            records_loaded,
            quality_score,
        )

        for event in events:
            logging.info(
                "SPORTS_EVENT | %s | %s",
                event["title"],
                event["sports_data"]["status"],
            )

        return {
            "records_read": records_read,
            "records_valid": len(events),
            "records_rejected": len(rejected),
            "records_loaded": records_loaded,
        }

    except Exception as error:
        logging.exception("Sports pipeline failed.")

        if persistence_committed:
            logging.warning(
                "Event upserts committed before the failure. "
                "Rerunning uses the same stable game identifiers."
            )

        try:
            fail_pipeline_run(run_id, records_read, error)
        except Exception:
            logging.exception("Could not record sports pipeline failure.")

        raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    result = process_sports_api(
        {
            "name": "sports",
            "source_name": SOURCE_NAME,
            "destination": "events",
        }
    )

    print("\nNOMAD SPORTS INGESTION")
    print("======================")

    for name, value in result.items():
        print(f"{name}: {value}")
