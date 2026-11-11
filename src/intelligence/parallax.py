import re

PARALLAX_VERSION = "PARALLAX_V1"


def _entity(canonical_name, entity_type):
    return {
        "canonical_name": canonical_name,
        "entity_type": entity_type,
    }


TRUSTED_CANONICAL_ENTITIES = {
    "openai": _entity("OpenAI", "ORGANIZATION"),
    "microsoft": _entity("Microsoft", "ORGANIZATION"),
    "nvidia": _entity("NVIDIA", "ORGANIZATION"),
    "google": _entity("Google", "ORGANIZATION"),
    "anthropic": _entity("Anthropic", "ORGANIZATION"),
    "servicenow": _entity("ServiceNow", "ORGANIZATION"),
    "amazon": _entity("Amazon", "ORGANIZATION"),
    "meta": _entity("Meta", "ORGANIZATION"),
    "apple": _entity("Apple", "ORGANIZATION"),
    "chatgpt": _entity("ChatGPT", "PRODUCT"),
    "chatgpt enterprise": _entity("ChatGPT Enterprise", "PRODUCT"),
    "codex": _entity("Codex", "PRODUCT"),
    "sora": _entity("Sora", "PRODUCT"),
    "azure": _entity("Azure", "PRODUCT"),
}


ENTITY_ALIASES = {
    "us": _entity("United States", "COUNTRY"),
    "u.s.": _entity("United States", "COUNTRY"),
    "u.s": _entity("United States", "COUNTRY"),
    "u.s.a.": _entity("United States", "COUNTRY"),
    "usa": _entity("United States", "COUNTRY"),
    "united states": _entity("United States", "COUNTRY"),
    "united states of america": _entity("United States", "COUNTRY"),
    "america": _entity("United States", "COUNTRY"),
    "uk": _entity("United Kingdom", "COUNTRY"),
    "u.k.": _entity("United Kingdom", "COUNTRY"),
    "united kingdom": _entity("United Kingdom", "COUNTRY"),
    "britain": _entity("United Kingdom", "COUNTRY"),
    "great britain": _entity("United Kingdom", "COUNTRY"),
    "russian federation": _entity("Russia", "COUNTRY"),
    "people's republic of china": _entity("China", "COUNTRY"),
    "prc": _entity("China", "COUNTRY"),
    "uae": _entity("United Arab Emirates", "COUNTRY"),
    "dprk": _entity("North Korea", "COUNTRY"),
    "south korea": _entity("South Korea", "COUNTRY"),
    "republic of korea": _entity("South Korea", "COUNTRY"),
    "eu": _entity("European Union", "ORGANIZATION"),
    "european union": _entity("European Union", "ORGANIZATION"),
    "un": _entity("United Nations", "ORGANIZATION"),
    "u.n.": _entity("United Nations", "ORGANIZATION"),
    "united nations": _entity("United Nations", "ORGANIZATION"),
    "nato": _entity("NATO", "ORGANIZATION"),
    "man utd": _entity("Manchester United", "ORGANIZATION"),
    "man united": _entity("Manchester United", "ORGANIZATION"),
    "manchester united": _entity("Manchester United", "ORGANIZATION"),
    "man city": _entity("Manchester City", "ORGANIZATION"),
    "manchester city": _entity("Manchester City", "ORGANIZATION"),
}


# Exact whole-name matches only, and only for COUNTRY detections.
COUNTRY_DEMONYMS = {
    "russian": "Russia",
    "ukrainian": "Ukraine",
}


FORCED_PRODUCT_PATTERNS = (
    r"^gpt-\d",
    r"^gpt \d",
)


FORCED_TECHNOLOGY_NAMES = {
    "ai",
    "artificial intelligence",
    "machine learning",
    "reinforcement learning",
    "agi",
    "language models",
}


REJECTED_ENTITY_NAMES = {
    "",
    "world",
    "businesses",
}


KEEP_LEADING_THE = {
    "the hague",
    "the gambia",
    "the bahamas",
}


def normalize_name(name):
    if not name:
        return ""

    return re.sub(r"\s+", " ", name.strip().lower())


def clean_display_name(name):
    if not name:
        return ""

    cleaned = re.sub(r"\s+", " ", name).strip()
    cleaned = cleaned.strip(" \"'“”‘’.,;:!?()[]")
    cleaned = re.sub(r"['’]s$", "", cleaned)
    cleaned = re.sub(r"['’]$", "", cleaned)

    if cleaned.lower().startswith("the ") and cleaned.lower() not in KEEP_LEADING_THE:
        cleaned = cleaned[4:]

    return cleaned.strip()


def is_lowercase_noise(cleaned_name, normalized_name):
    """
    Existing heuristic, not a universal rule about proper names.
    Some legitimate lowercase names can still be missed.
    """

    if normalized_name in FORCED_TECHNOLOGY_NAMES:
        return False

    if normalized_name in TRUSTED_CANONICAL_ENTITIES:
        return False

    return cleaned_name == cleaned_name.lower()


def determine_canonical_type(normalized_name, detected_type):
    if normalized_name in FORCED_TECHNOLOGY_NAMES:
        return "TECHNOLOGY"

    for pattern in FORCED_PRODUCT_PATTERNS:
        if re.search(pattern, normalized_name):
            return "PRODUCT"

    return detected_type


def build_known_entity(
    known,
    original_name,
    detected_type,
    extraction_method,
    extraction_confidence,
    resolution_method,
):
    return {
        "original_name": original_name,
        "canonical_name": known["canonical_name"],
        "normalized_name": normalize_name(known["canonical_name"]),
        "entity_type": known["entity_type"],
        "original_type": detected_type,
        "extraction_method": extraction_method,
        "extraction_confidence": extraction_confidence,
        "resolution_method": resolution_method,
        "resolution_confidence": 1.0,
        "parallax_version": PARALLAX_VERSION,
    }


def resolve_entity(entity):
    original_name = entity.get("entity_name", "")
    detected_type = entity.get("entity_type")
    extraction_method = entity.get("extraction_method", "UNKNOWN")
    extraction_confidence = float(entity.get("confidence", 0.0))

    cleaned_name = clean_display_name(original_name)
    normalized_name = normalize_name(cleaned_name)

    if normalized_name in REJECTED_ENTITY_NAMES:
        return None

    if len(normalized_name) < 2:
        return None

    # Check this before the lowercase heuristic so a COUNTRY
    # detection of "ukrainian" can still resolve correctly.
    if (
        str(detected_type or "").strip().upper() == "COUNTRY"
        and normalized_name in COUNTRY_DEMONYMS
    ):
        return build_known_entity(
            _entity(COUNTRY_DEMONYMS[normalized_name], "COUNTRY"),
            original_name,
            detected_type,
            extraction_method,
            extraction_confidence,
            "KNOWN_ALIAS",
        )

    if is_lowercase_noise(cleaned_name, normalized_name):
        return None

    if normalized_name in ENTITY_ALIASES:
        return build_known_entity(
            ENTITY_ALIASES[normalized_name],
            original_name,
            detected_type,
            extraction_method,
            extraction_confidence,
            "KNOWN_ALIAS",
        )

    if normalized_name in TRUSTED_CANONICAL_ENTITIES:
        return build_known_entity(
            TRUSTED_CANONICAL_ENTITIES[normalized_name],
            original_name,
            detected_type,
            extraction_method,
            extraction_confidence,
            "TRUSTED_CANONICAL",
        )

    canonical_type = determine_canonical_type(
        normalized_name,
        detected_type,
    )

    if canonical_type != detected_type:
        resolution_method = "TYPE_OVERRIDE"
        resolution_confidence = 0.95
    else:
        resolution_method = "NORMALIZED"
        resolution_confidence = extraction_confidence

    return {
        "original_name": original_name,
        "canonical_name": cleaned_name,
        "normalized_name": normalized_name,
        "entity_type": canonical_type,
        "original_type": detected_type,
        "extraction_method": extraction_method,
        "extraction_confidence": extraction_confidence,
        "resolution_method": resolution_method,
        "resolution_confidence": resolution_confidence,
        "parallax_version": PARALLAX_VERSION,
    }


def resolve_entities(entities):
    resolved_entities = {}

    for entity in entities:
        resolved = resolve_entity(entity)

        if resolved is None:
            continue

        # Keep identity consistent with the database uniqueness key.
        key = (
            resolved["normalized_name"],
            resolved["entity_type"],
        )
        existing = resolved_entities.get(key)

        if (
            existing is None
            or resolved["resolution_confidence"] > existing["resolution_confidence"]
        ):
            resolved_entities[key] = resolved

    return list(resolved_entities.values())


if __name__ == "__main__":
    # Explicit regression cases, not live observations.
    test_cases = [
        ("U.S.", "COUNTRY", "United States"),
        ("us", "COUNTRY", None),
        ("GPT-5", "TECHNOLOGY", "GPT-5"),
        ("OpenAI", "PERSON", "OpenAI"),
        ("artificial intelligence", "TECHNOLOGY", "artificial intelligence"),
        ("world", "LOCATION", None),
        ("Man Utd", "ORGANIZATION", "Manchester United"),
        ("Manchester United", "ORGANIZATION", "Manchester United"),
        ("Russia's", "COUNTRY", "Russia"),
        ("the EU", "ORGANIZATION", "European Union"),
        ("The Hague", "LOCATION", "The Hague"),
        ("drone", "TECHNOLOGY", None),
        ("military-backed authorities", "ORGANIZATION", None),
        ("Imaan Mazari", "PERSON", "Imaan Mazari"),
        ("Britain", "COUNTRY", "United Kingdom"),
        ("Russian", "COUNTRY", "Russia"),
        ("Ukrainian", "COUNTRY", "Ukraine"),
        ("ukrainian", "COUNTRY", "Ukraine"),
        ("Russian", "LANGUAGE", "Russian"),
        ("Russian fighter jets", "PRODUCT", "Russian fighter jets"),
    ]

    print("\nPARALLAX TEST")
    print("=============")

    for name, entity_type, expected in test_cases:
        result = resolve_entity(
            {
                "entity_name": name,
                "entity_type": entity_type,
                "extraction_method": "GLINER",
                "confidence": 0.9,
            }
        )

        actual = result["canonical_name"] if result else None

        assert actual == expected, f"{name!r}: expected {expected!r}, got {actual!r}"

        if result is None:
            print(f"PASS | {name:<30} -> REJECTED")
        else:
            print(
                f"PASS | {name:<30} -> {actual}"
                f" | {result['entity_type']}"
                f" | {result['resolution_method']}"
            )

    print(f"\nAll {len(test_cases)} checks passed.")
