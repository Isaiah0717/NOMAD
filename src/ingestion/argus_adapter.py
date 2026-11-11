import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlsplit, urlunsplit

# Isaiah's call. Change this one line if you want a different label.
ARGUS_EVENT_TYPE = "WORLD_EVENT"


def clean_url(url):
    """
    Remove query strings and fragments so the same article
    always produces the same URL.
    """

    if not url:
        return None

    parts = urlsplit(url)

    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def is_article_url(url):
    """
    A usable ID must point at a specific article,
    not a bare homepage like https://www.aljazeera.com/
    """

    if not url:
        return False

    path = urlsplit(url).path

    return path not in ("", "/")


def build_source_event_id(article):
    """
    Pick a stable, article-specific ID.
    Priority: cleaned link -> raw guid -> raw id.
    Raw guid/id keep their query strings because some feeds
    put the unique part there.
    """

    link = clean_url(article.get("link"))

    if is_article_url(link):
        return link

    for key in ("guid", "id"):
        value = article.get(key)

        if value and value.strip() not in (
            "https://www.aljazeera.com/",
            "https://www.aljazeera.com",
        ):
            return value.strip()

    return None


def clean_text(text):
    """
    Strip HTML tags and extra whitespace from RSS summaries.
    """

    if not text:
        return None

    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

    return text or None


def parse_event_time(published):
    """
    Convert an RSS date into a timezone-aware datetime.
    Falls back to the current UTC time if missing or unreadable.
    """

    if not published:
        return datetime.now(timezone.utc)

    try:
        event_time = parsedate_to_datetime(published)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)

    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)

    return event_time


def adapt_argus_article(article):
    """
    Convert a raw ARGUS article into NOMAD's universal event structure.
    """

    source = article.get("argus_source")

    if not source:
        raise ValueError("ARGUS article is missing its source tag.")

    title = clean_text(article.get("title"))

    if not title:
        raise ValueError("ARGUS article does not contain a title.")

    source_event_id = build_source_event_id(article)

    if not source_event_id:
        raise ValueError(f"ARGUS article '{title}' has no article-specific id.")

    return {
        "source": source,
        "source_event_id": source_event_id,
        "event_type": ARGUS_EVENT_TYPE,
        "title": title,
        "description": clean_text(article.get("summary")),
        "event_time": parse_event_time(article.get("published")),
        "location_name": None,
        "latitude": None,
        "longitude": None,
        "severity": None,
        "source_url": clean_url(article.get("link")),
    }


if __name__ == "__main__":
    from src.ingestion.argus_reader import read_argus_news

    articles = read_argus_news()

    events = []
    rejected = 0

    for article in articles:
        try:
            events.append(adapt_argus_article(article))
        except ValueError as error:
            rejected += 1
            print(f"[ARGUS] Rejected: {error}")

    unique_ids = {(event["source"], event["source_event_id"]) for event in events}

    duplicates = len(events) - len(unique_ids)

    print("\nNOMAD UNIVERSAL WORLD EVENTS")
    print("============================")
    print(
        f"Adapted: {len(events)} | Rejected: {rejected} | "
        f"Unique IDs: {len(unique_ids)} | ID collisions: {duplicates}"
    )

    if duplicates:
        print("\n[ARGUS] WARNING: ID collisions detected. Do NOT load yet.")

    seen_sources = set()

    for event in events:
        if event["source"] in seen_sources:
            continue

        seen_sources.add(event["source"])

        print("\n---------------------")

        for key, value in event.items():
            print(f"{key}: {value}")
