import re

from gliner import GLiNER

MODEL_NAME = "gliner-community/gliner_small-v2.5"
MODEL = GLiNER.from_pretrained(MODEL_NAME)

GLINER_THRESHOLD = 0.55


KNOWN_ENTITIES = {
    "OpenAI": "ORGANIZATION",
    "Microsoft": "ORGANIZATION",
    "ServiceNow": "ORGANIZATION",
    "NVIDIA": "ORGANIZATION",
    "Google": "ORGANIZATION",
    "Anthropic": "ORGANIZATION",
    "Meta": "ORGANIZATION",
    "Amazon": "ORGANIZATION",
    "Apple": "ORGANIZATION",
    "Azure": "PRODUCT",
    "ChatGPT": "PRODUCT",
    "Codex": "PRODUCT",
    "GPT": "TECHNOLOGY",
}


GLINER_LABELS = [
    "person",
    "organization",
    "product",
    "technology",
    "country",
    "location",
    "sports team",
    "sports league",
]


NOMAD_ENTITY_TYPES = {
    "person": "PERSON",
    "organization": "ORGANIZATION",
    "product": "PRODUCT",
    "technology": "TECHNOLOGY",
    "country": "COUNTRY",
    "location": "LOCATION",
    "sports team": "TEAM",
    "sports league": "LEAGUE",
}


def normalize_entity_name(entity_name):
    return " ".join(entity_name.strip().lower().split())


def dictionary_match(text, entity_name):
    pattern = rf"(?<!\w){re.escape(entity_name)}(?!\w)"

    return (
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        is not None
    )


def add_entity(
    entities,
    entity_name,
    entity_type,
    extraction_method,
    confidence,
):
    entity_name = entity_name.strip()
    normalized_name = normalize_entity_name(entity_name)

    if not normalized_name:
        return

    existing_keys = [key for key in entities if key[0] == normalized_name]

    for existing_key in existing_keys:
        existing_entity = entities[existing_key]

        if existing_entity["confidence"] >= confidence:
            return

        del entities[existing_key]

    key = (
        normalized_name,
        entity_type,
    )

    entities[key] = {
        "entity_name": entity_name,
        "normalized_name": normalized_name,
        "entity_type": entity_type,
        "extraction_method": extraction_method,
        "confidence": confidence,
    }


def extract_entities(text):
    if not text:
        return []

    entities = {}

    # NOMAD's trusted domain knowledge wins conflicts.
    for entity_name, entity_type in KNOWN_ENTITIES.items():
        if dictionary_match(text, entity_name):
            add_entity(
                entities=entities,
                entity_name=entity_name,
                entity_type=entity_type,
                extraction_method="DICTIONARY",
                confidence=1.0,
            )

    # GLiNER dynamically discovers entities using NOMAD's requested labels.
    predictions = MODEL.predict_entities(
        text,
        GLINER_LABELS,
        threshold=GLINER_THRESHOLD,
    )

    for prediction in predictions:
        gliner_label = prediction["label"].lower()

        nomad_type = NOMAD_ENTITY_TYPES.get(gliner_label)

        if nomad_type is None:
            continue

        add_entity(
            entities=entities,
            entity_name=prediction["text"],
            entity_type=nomad_type,
            extraction_method="GLINER",
            confidence=float(prediction["score"]),
        )

    return list(entities.values())


if __name__ == "__main__":
    test_text = (
        "NVIDIA announced a partnership with Microsoft "
        "in Japan. OpenAI expanded ChatGPT and Codex. "
        "Sam Altman discussed a new artificial intelligence "
        "product in Tokyo."
    )

    extracted_entities = extract_entities(test_text)

    print("\nNOMAD DYNAMIC ENTITY EXTRACTION")
    print("===============================")

    for entity in extracted_entities:
        print(
            f"{entity['entity_name']} | "
            f"{entity['entity_type']} | "
            f"{entity['extraction_method']} | "
            f"{entity['confidence']:.3f}"
        )
