"""
CORTEX v1 - conservative incident candidate matching.

Entity-supported matches may form candidate incident groups.
Strong text-supported pairs are surfaced for human review only.

Scores are heuristics, not probabilities.
Outlet diversity does not prove independent reporting.
Publication times are not verified incident occurrence times.

Read-only: no database writes.
"""

import math
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

SRC_FOLDER = Path(__file__).resolve().parents[1]

if str(SRC_FOLDER) not in sys.path:
    sys.path.insert(0, str(SRC_FOLDER))

from database import get_database_connection

CORTEX_VERSION = "CORTEX_V1"

ENTITY_WEIGHT = 0.35
TEXT_WEIGHT = 0.50
TIME_WEIGHT = 0.15

MAX_HOURS_APART = 72
TIME_DECAY_HOURS = 24

MATCH_THRESHOLD = 0.45
CANDIDATE_THRESHOLD = 0.25

MIN_ENTITY_EVIDENCE = 0.15
MIN_TEXT_SIMILARITY = 0.10
MIN_TITLE_SIMILARITY = 0.12
MIN_SHARED_TITLE_TERMS = 2

COUNTRY_ONLY_MIN_TEXT = 0.20
COUNTRY_ONLY_MIN_TITLE = 0.20
COUNTRY_ONLY_MIN_TERMS = 3

SINGLE_ENTITY_MIN_TEXT = 0.15

TEXT_REVIEW_MIN_TITLE = 0.35
TEXT_REVIEW_MIN_TEXT = 0.15
TEXT_REVIEW_MIN_SHARED_TERMS = 3
TEXT_REVIEW_MAX_HOURS = 36

REPORT_PAIR_LIMIT = 25

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "from",
    "by",
    "with",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "has",
    "have",
    "had",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "after",
    "before",
    "over",
    "under",
    "into",
    "about",
    "amid",
    "says",
    "said",
    "say",
    "new",
    "least",
    "more",
    "than",
    "up",
    "out",
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "will",
    "would",
    "could",
    "can",
    "his",
    "her",
    "their",
    "they",
    "he",
    "she",
    "we",
    "you",
    "our",
    "us",
    "also",
    "during",
    "while",
    "s",
    "watch",
    "video",
    "report",
    "reports",
    "news",
    "latest",
}

WORD_FORMS = {
    "killed": "kill",
    "kills": "kill",
    "killing": "kill",
    "deaths": "death",
    "dead": "death",
    "crashes": "crash",
    "crashed": "crash",
    "attacks": "attack",
    "attacked": "attack",
    "attacking": "attack",
    "strikes": "strike",
    "struck": "strike",
    "drones": "drone",
    "trains": "train",
    "railway": "rail",
    "railroad": "rail",
    "elections": "election",
    "operators": "operator",
    "drivers": "driver",
    "stations": "station",
    "russian": "russia",
    "ukrainian": "ukraine",
    "spanish": "spain",
    "american": "america",
}

BROAD_TITLE_TERMS = {
    "country",
    "government",
    "official",
    "officials",
    "people",
    "person",
    "world",
    "international",
    "politics",
    "political",
    "president",
    "minister",
    "state",
    "states",
    "united",
    "america",
    "russia",
    "ukraine",
    "spain",
    "china",
    "israel",
    "brazil",
    "ethiopia",
    "japan",
    "britain",
    "election",
    "year",
    "day",
    "today",
}


def normalize_word(word):
    return WORD_FORMS.get(word, word)


def tokenize(text):
    if not isinstance(text, str) or not text.strip():
        return set()

    text = unicodedata.normalize("NFKC", text).casefold()
    words = re.findall(r"[^\W_]+", text, flags=re.UNICODE)

    return {
        normalize_word(word)
        for word in words
        if word not in STOPWORDS and len(word) > 1
    }


def normalize_time(value):
    if not isinstance(value, datetime):
        raise ValueError("Event has a missing or invalid event_time.")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Event event_time must include a timezone.")

    return value.astimezone(timezone.utc)


def compute_idf(item_sets):
    total = len(item_sets)

    if total == 0:
        return {}

    frequency = Counter(item for items in item_sets for item in set(items))

    return {
        item: math.log((total + 1) / (count + 0.5)) for item, count in frequency.items()
    }


def weighted_jaccard(items_a, items_b, weights):
    union = items_a | items_b

    if not union:
        return 0.0

    numerator = sum(weights.get(item, 1.0) for item in items_a & items_b)
    denominator = sum(weights.get(item, 1.0) for item in union)

    return numerator / denominator if denominator else 0.0


def prepare_events(events):
    prepared = []
    seen_ids = set()

    for original in events:
        event = dict(original)
        event_id = event["event_id"]

        if event_id in seen_ids:
            raise ValueError(f"Duplicate event_id: {event_id}")

        seen_ids.add(event_id)

        event["event_time"] = normalize_time(event["event_time"])
        event["entities"] = set(event.get("entities") or ())
        event["entity_types"] = dict(event.get("entity_types") or {})
        event["source"] = event.get("source") or "UNKNOWN"
        event["title"] = event.get("title") or ""
        event["description"] = event.get("description") or ""

        event["title_tokens"] = tokenize(event["title"])
        event["description_tokens"] = tokenize(event["description"])
        event["tokens"] = tokenize(f"{event['title']} {event['description']}")

        prepared.append(event)

    return prepared


def time_similarity(time_a, time_b):
    hours = abs((time_a - time_b).total_seconds()) / 3600

    if hours > MAX_HOURS_APART:
        return 0.0

    return math.exp(-hours / TIME_DECAY_HOURS)


def country_words_for_review(event_a, event_b):
    """
    Discount COUNTRY words only.

    Do not remove whole PRODUCT, ORGANIZATION, or other entity
    phrases: a noisy extraction such as "Russian fighter jets"
    must not erase "fighter" and "jets" from text evidence.
    """

    words = set()

    for event in (event_a, event_b):
        for name in event["entities"]:
            entity_type = str(event["entity_types"].get(name) or "").upper()

            if entity_type == "COUNTRY":
                words.update(tokenize(name))

    return words


def score_pair(event_a, event_b, entity_idf, token_idf):
    hours_apart = (
        abs((event_a["event_time"] - event_b["event_time"]).total_seconds()) / 3600
    )

    if hours_apart > MAX_HOURS_APART:
        return None

    time_score = time_similarity(
        event_a["event_time"],
        event_b["event_time"],
    )

    shared_entities = event_a["entities"] & event_b["entities"]

    entity_score = weighted_jaccard(
        event_a["entities"],
        event_b["entities"],
        entity_idf,
    )
    text_score = weighted_jaccard(
        event_a["tokens"],
        event_b["tokens"],
        token_idf,
    )
    title_score = weighted_jaccard(
        event_a["title_tokens"],
        event_b["title_tokens"],
        token_idf,
    )
    description_score = weighted_jaccard(
        event_a["description_tokens"],
        event_b["description_tokens"],
        token_idf,
    )

    shared_title_words = event_a["title_tokens"] & event_b["title_tokens"]

    shared_entity_words = set()

    for entity_name in shared_entities:
        shared_entity_words.update(tokenize(entity_name))

    shared_title_terms = shared_title_words - shared_entity_words

    specific_entities = set()

    for entity_name in shared_entities:
        type_a = str(event_a["entity_types"].get(entity_name) or "").upper()
        type_b = str(event_b["entity_types"].get(entity_name) or "").upper()

        if (
            type_a
            and type_a == type_b
            and type_a not in {"COUNTRY", "UNKNOWN", "AMBIGUOUS"}
        ):
            specific_entities.add(entity_name)

    country_only = bool(shared_entities) and not specific_entities

    reasons = []

    if not shared_entities:
        reasons.append("no shared canonical entities")

    if entity_score < MIN_ENTITY_EVIDENCE:
        reasons.append("weak entity overlap")

    if text_score < MIN_TEXT_SIMILARITY:
        reasons.append("weak overall text overlap")

    if title_score < MIN_TITLE_SIMILARITY:
        reasons.append("weak title overlap")

    if len(shared_title_terms) < MIN_SHARED_TITLE_TERMS:
        reasons.append("too few shared non-entity title terms")

    if country_only:
        if (
            text_score < COUNTRY_ONLY_MIN_TEXT
            or title_score < COUNTRY_ONLY_MIN_TITLE
            or len(shared_title_terms) < COUNTRY_ONLY_MIN_TERMS
        ):
            reasons.append(
                "country-only or uncertain-type overlap " "lacks specific text evidence"
            )
    elif len(shared_entities) == 1:
        if text_score < SINGLE_ENTITY_MIN_TEXT:
            reasons.append("single shared entity needs stronger text evidence")

    text_evidence = 0.60 * title_score + 0.40 * text_score

    score = (
        ENTITY_WEIGHT * entity_score
        + TEXT_WEIGHT * text_evidence
        + TIME_WEIGHT * time_score
    )

    eligible = not reasons
    is_match = eligible and score >= MATCH_THRESHOLD

    country_words = country_words_for_review(event_a, event_b)

    # These are review clues, not verified actions or targets.
    distinctive_title_terms = {
        word
        for word in shared_title_words - country_words
        if word not in BROAD_TITLE_TERMS and not word.isdigit()
    }

    shared_numbers = {word for word in shared_title_words if word.isdigit()}

    text_review = (
        not is_match
        and hours_apart <= TEXT_REVIEW_MAX_HOURS
        and title_score >= TEXT_REVIEW_MIN_TITLE
        and text_score >= TEXT_REVIEW_MIN_TEXT
        and len(distinctive_title_terms) >= TEXT_REVIEW_MIN_SHARED_TERMS
    )

    if is_match:
        verdict = "MATCH"
    elif text_review:
        verdict = "TEXT_REVIEW"
    elif eligible:
        verdict = "REVIEW"
    else:
        verdict = "BLOCKED"

    return {
        "event_a": event_a,
        "event_b": event_b,
        "entity_score": entity_score,
        "text_score": text_score,
        "title_score": title_score,
        "description_score": description_score,
        "time_score": time_score,
        "hours_apart": hours_apart,
        "same_source": event_a["source"] == event_b["source"],
        "shared_entities": shared_entities,
        "shared_title_terms": shared_title_terms,
        "distinctive_title_terms": distinctive_title_terms,
        "shared_numbers": shared_numbers,
        "country_only": country_only,
        "eligible": eligible,
        "is_match": is_match,
        "text_review": text_review,
        "verdict": verdict,
        "reasons": reasons,
        "score": score,
    }


def find_matches(events):
    prepared = prepare_events(events)

    entity_idf = compute_idf([event["entities"] for event in prepared])
    token_idf = compute_idf([event["tokens"] for event in prepared])

    ordered = sorted(
        prepared,
        key=lambda event: (
            event["event_time"],
            str(event["event_id"]),
        ),
    )

    pairs = []

    for index, event_a in enumerate(ordered):
        for event_b in ordered[index + 1 :]:
            hours_apart = (
                event_b["event_time"] - event_a["event_time"]
            ).total_seconds() / 3600

            if hours_apart > MAX_HOURS_APART:
                break

            result = score_pair(
                event_a,
                event_b,
                entity_idf,
                token_idf,
            )

            if result is not None and (
                result["score"] >= CANDIDATE_THRESHOLD or result["text_review"]
            ):
                pairs.append(result)

    pairs.sort(
        key=lambda pair: (
            -pair["score"],
            str(pair["event_a"]["event_id"]),
            str(pair["event_b"]["event_id"]),
        )
    )

    return pairs


def pair_key(id_a, id_b):
    return frozenset((id_a, id_b))


def build_incidents(pairs):
    """
    Every cross-group pair must pass the match rules.
    TEXT_REVIEW pairs never authorize a merge.

    Greedy, conservative grouping, not optimal clustering.
    """

    matches = sorted(
        (pair for pair in pairs if pair["is_match"]),
        key=lambda pair: (
            -pair["score"],
            str(pair["event_a"]["event_id"]),
            str(pair["event_b"]["event_id"]),
        ),
    )

    events_by_id = {}
    pair_lookup = {}

    for pair in matches:
        event_a = pair["event_a"]
        event_b = pair["event_b"]

        events_by_id[event_a["event_id"]] = event_a
        events_by_id[event_b["event_id"]] = event_b

        pair_lookup[pair_key(event_a["event_id"], event_b["event_id"])] = pair

    groups = {event_id: {event_id} for event_id in events_by_id}
    owner = {event_id: event_id for event_id in events_by_id}

    for pair in matches:
        id_a = pair["event_a"]["event_id"]
        id_b = pair["event_b"]["event_id"]

        root_a = owner[id_a]
        root_b = owner[id_b]

        if root_a == root_b:
            continue

        group_a = groups[root_a]
        group_b = groups[root_b]

        if not all(
            pair_key(member_a, member_b) in pair_lookup
            for member_a in group_a
            for member_b in group_b
        ):
            continue

        merged = group_a | group_b
        groups[root_a] = merged
        del groups[root_b]

        for event_id in merged:
            owner[event_id] = root_a

    incidents = []

    for member_ids in groups.values():
        if len(member_ids) < 2:
            continue

        members = sorted(
            (events_by_id[event_id] for event_id in member_ids),
            key=lambda event: (
                event["event_time"],
                str(event["event_id"]),
            ),
        )

        internal_scores = [
            pair_lookup[pair_key(id_a, id_b)]["score"]
            for id_a, id_b in combinations(member_ids, 2)
        ]

        entity_counts = Counter(
            entity for member in members for entity in member["entities"]
        )

        core_entities = sorted(
            (entity for entity, count in entity_counts.items() if count >= 2),
            key=lambda entity: (-entity_counts[entity], entity),
        )

        incidents.append(
            {
                "members": members,
                "sources": sorted({member["source"] for member in members}),
                "core_entities": core_entities,
                "first_seen": members[0]["event_time"],
                "last_seen": members[-1]["event_time"],
                "match_score": min(internal_scores),
                "mean_pair_score": (sum(internal_scores) / len(internal_scores)),
            }
        )

    incidents.sort(
        key=lambda incident: (
            -len(incident["sources"]),
            -incident["match_score"],
            str(incident["members"][0]["event_id"]),
        )
    )

    return incidents


def load_events(event_types=("WORLD_EVENT",)):
    if isinstance(event_types, str):
        event_types = [event_types]
    else:
        event_types = list(event_types)

    if not event_types:
        return []

    query = """
        SELECT
            ev.event_id,
            ev.source,
            ev.title,
            ev.description,
            ev.event_time,
            en.entity_name,
            en.entity_type
        FROM events ev
        LEFT JOIN event_entities ee
            ON ee.event_id = ev.event_id
        LEFT JOIN entities en
            ON en.entity_id = ee.entity_id
        WHERE ev.event_type = ANY(%(event_types)s)
          AND ev.entities_extracted_at IS NOT NULL
          AND ev.event_time IS NOT NULL
        ORDER BY ev.event_time, ev.event_id;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, {"event_types": event_types})
            rows = cursor.fetchall()

    events = {}
    observed_types = {}

    for row in rows:
        (
            event_id,
            source,
            title,
            description,
            event_time,
            entity_name,
            entity_type,
        ) = row

        event = events.setdefault(
            event_id,
            {
                "event_id": event_id,
                "source": source or "UNKNOWN",
                "title": title or "",
                "description": description or "",
                "event_time": event_time,
                "entities": set(),
                "entity_types": {},
            },
        )

        if entity_name:
            event["entities"].add(entity_name)

            observed_types.setdefault((event_id, entity_name), set()).add(
                str(entity_type or "").upper()
            )

    for (event_id, entity_name), types in observed_types.items():
        events[event_id]["entity_types"][entity_name] = (
            next(iter(types)) if len(types) == 1 else ""
        )

    return list(events.values())


def format_entities(event):
    return (
        "; ".join(
            f"{name} [{event['entity_types'].get(name) or 'UNKNOWN'}]"
            for name in sorted(event["entities"])
        )
        or "(none extracted)"
    )


def print_pair(pair):
    print(
        f"\n{pair['score']:.2f} {pair['verdict']}"
        f" | ent={pair['entity_score']:.2f}"
        f" text={pair['text_score']:.2f}"
        f" title={pair['title_score']:.2f}"
        f" description={pair['description_score']:.2f}"
        f" hours={pair['hours_apart']:.1f}"
    )

    for label, key in (("A", "event_a"), ("B", "event_b")):
        event = pair[key]
        print(
            f"  {label} [{event['source']}] "
            f"ID {event['event_id']} | {event['title']}"
        )
        print(f"    Entities: {format_entities(event)}")

    for label, key in (
        ("Shared entities", "shared_entities"),
        ("Shared non-entity title terms", "shared_title_terms"),
        ("Distinctive shared title terms", "distinctive_title_terms"),
        ("Shared title numbers", "shared_numbers"),
    ):
        print(f"  {label}: " + (", ".join(sorted(pair[key])) or "-"))

    if pair["reasons"]:
        print("  Automatic grouping blocked: " + "; ".join(pair["reasons"]))

    if pair["text_review"]:
        print(
            "  Review reason: strong wording overlap within " "the review time window."
        )
        print(
            "  Not grouped automatically. Check locations, "
            "incident dates, actions, and descriptions."
        )


def print_report(events, pairs, incidents):
    text_reviews = [pair for pair in pairs if pair["text_review"]]

    print("\nCORTEX V1 - INCIDENT CANDIDATE ANALYSIS")
    print("======================================")
    print(f"Observations analyzed:       {len(events)}")
    print(f"Pairs retained for review:   {len(pairs)}")
    print("Entity-supported matches:    " f"{sum(pair['is_match'] for pair in pairs)}")
    print(f"Text-supported review pairs: {len(text_reviews)}")
    print(
        "Blocked diagnostic pairs:    "
        f"{sum(pair['verdict'] == 'BLOCKED' for pair in pairs)}"
    )
    print(f"Candidate incident groups:   {len(incidents)}")
    print(
        "Multi-outlet groups:         "
        f"{sum(len(i['sources']) > 1 for i in incidents)}"
    )

    print("\nScores are heuristic similarities, not probabilities.")
    print("Multi-outlet coverage does not prove independence.")
    print("Times are publication times, not verified incident times.")
    print("TEXT_REVIEW pairs never authorize incident grouping.")

    for number, incident in enumerate(incidents, start=1):
        print(
            f"\nCANDIDATE INCIDENT {number:02d}"
            f" | minimum pair score {incident['match_score']:.2f}"
            f" | outlets: {', '.join(incident['sources'])}"
        )
        print("  Core entities: " + (", ".join(incident["core_entities"]) or "-"))

        for member in incident["members"]:
            print(
                f"  [{member['source']:<9}] "
                f"{member['event_time']:%m-%d %H:%M} "
                f"{member['title']}"
            )

    print("\nTEXT-SUPPORTED REVIEW QUEUE")
    print("---------------------------")

    if not text_reviews:
        print("No pairs passed the text-review rules.")

    for pair in text_reviews[:REPORT_PAIR_LIMIT]:
        print_pair(pair)

    if len(text_reviews) > REPORT_PAIR_LIMIT:
        print(
            f"\nShowing {REPORT_PAIR_LIMIT} of "
            f"{len(text_reviews)} text-review pairs."
        )

    print("\nTOP PAIR SCORES - DIAGNOSTICS")
    print("----------------------------")

    for pair in pairs[:REPORT_PAIR_LIMIT]:
        print_pair(pair)

    if len(pairs) > REPORT_PAIR_LIMIT:
        print(f"\nShowing {REPORT_PAIR_LIMIT} of " f"{len(pairs)} retained pairs.")


if __name__ == "__main__":
    events = load_events()
    pairs = find_matches(events)
    incidents = build_incidents(pairs)
    print_report(events, pairs, incidents)
