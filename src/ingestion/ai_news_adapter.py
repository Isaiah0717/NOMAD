from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def adapt_ai_news(article):
    published = article.get("published")

    if published:
        event_time = parsedate_to_datetime(published)

        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
    else:
        event_time = datetime.now(timezone.utc)

    source_event_id = article.get("id") or article.get("guid") or article.get("link")

    if not source_event_id:
        raise ValueError("AI news entry does not contain an id, guid, or link.")

    title = article.get("title")

    if not title:
        raise ValueError("AI news entry does not contain a title.")

    return {
        "source": "OPENAI",
        "source_event_id": source_event_id,
        "event_type": "AI_EVENT",
        "title": title,
        "description": article.get("summary"),
        "event_time": event_time,
        "location_name": None,
        "latitude": None,
        "longitude": None,
        "severity": None,
        "source_url": article.get("link"),
    }


if __name__ == "__main__":
    from src.ingestion.ai_news_reader import read_ai_news

    articles = read_ai_news()

    if not articles:
        print("No AI news entries received.")
    else:
        first_article = articles[0]

        event = adapt_ai_news(first_article)

        print("\nNOMAD UNIVERSAL AI EVENT")
        print("========================")

        for key, value in event.items():
            print(f"{key}: {value}")
