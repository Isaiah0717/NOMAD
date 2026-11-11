import feedparser

OPENAI_NEWS_URL = "https://openai.com/news/rss.xml"


def read_ai_news():
    feed = feedparser.parse(OPENAI_NEWS_URL)

    if feed.bozo:
        raise ValueError(f"Could not parse OpenAI RSS feed: {feed.bozo_exception}")

    return feed.entries


if __name__ == "__main__":
    articles = read_ai_news()

    print(f"NOMAD received {len(articles)} AI news entries.")

    if articles:
        first_article = articles[0]

        print("\nFirst AI news entry:")
        print(first_article)
