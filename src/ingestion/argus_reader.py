import feedparser
import requests

HEADERS = {"User-Agent": "NOMAD-ARGUS/1.0"}

DEFAULT_FEEDS = [
    {
        "source": "BBC",
        "source_name": "BBC News - World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
    },
    {
        "source": "ALJAZEERA",
        "source_name": "Al Jazeera English",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
    },
    {
        "source": "NPR",
        "source_name": "NPR World",
        "url": "https://feeds.npr.org/1004/rss.xml",
    },
]


def read_feed(feed):
    """
    Fetch and parse a single RSS feed.
    Returns a list of raw article dictionaries tagged with their source.
    """

    response = requests.get(
        feed["url"],
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    parsed = feedparser.parse(response.content)

    articles = []

    for entry in parsed.entries:
        articles.append(
            {
                "argus_source": feed["source"],
                "argus_source_name": feed["source_name"],
                "id": entry.get("id"),
                "guid": entry.get("guid"),
                "title": entry.get("title"),
                "summary": entry.get("summary"),
                "link": entry.get("link"),
                "published": entry.get("published"),
            }
        )

    return articles


def read_argus_news(feeds=None):
    """
    Fetch world-news articles from every ARGUS feed.

    One broken feed does not kill ARGUS.
    Failed feeds are reported, and the healthy feeds still return data.
    """

    feeds = feeds or DEFAULT_FEEDS

    all_articles = []
    failed_feeds = []

    for feed in feeds:
        try:
            articles = read_feed(feed)
            all_articles.extend(articles)

            print(f"[ARGUS] {feed['source_name']}: " f"{len(articles)} article(s)")

        except (requests.RequestException, ValueError) as error:
            failed_feeds.append(feed["source_name"])

            print(f"[ARGUS] FAILED {feed['source_name']}: {error}")

    if not all_articles and failed_feeds:
        raise RuntimeError("ARGUS could not read any feeds: " + ", ".join(failed_feeds))

    return all_articles


if __name__ == "__main__":
    articles = read_argus_news()

    print("\nARGUS WORLD NEWS FEED")
    print("=====================")
    print(f"Total articles received: {len(articles)}")

    for article in articles[:6]:
        print("\n---------------------")
        print(f"Source: {article.get('argus_source_name')}")
        print(f"Title: {article.get('title')}")
        print(f"Published: {article.get('published')}")
        print(f"URL: {article.get('link')}")
