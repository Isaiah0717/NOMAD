import html
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import (
    get_cortex_incident_evidence,
    get_cortex_incidents,
    get_cortex_metrics,
    get_entity_events,
    get_entity_index,
    get_entity_neighborhood,
    get_event_types,
    get_recent_events,
    get_relationship_evidence,
    get_system_metrics,
    get_top_relationships,
    update_cortex_review_status,
)
from graph import build_network, compute_layout, render_graph

SRC_FOLDER = Path(__file__).resolve().parents[1]

if str(SRC_FOLDER) not in sys.path:
    sys.path.insert(0, str(SRC_FOLDER))

from database import get_database_connection

st.set_page_config(
    page_title="NOMAD",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="expanded",
)


AMBER = "#ff9d22"
MUTED = "#77818c"
DEFAULT_TAG_COLOR = "#77818c"
ALL_DOMAINS = "ALL"

PULSE_UP = "#5ce1a0"
PULSE_DOWN = "#ff453a"
PULSE_SPIKE = "#4cc9f0"

EVENT_TYPE_COLORS = {
    "AI_EVENT": "#b388ff",
    "EARTHQUAKE": "#ff453a",
    "EARTHQUAKE_EVENT": "#ff453a",
    "WEATHER": "#4cc9f0",
    "WORLD_EVENT": "#5ce1a0",
    "MARKET_EVENT": "#ffd166",
    "SPORTS_EVENT": "#ff6ec7",
}

REVIEW_COLORS = {
    "UNREVIEWED": "#ff9d22",
    "CONFIRMED": "#5ce1a0",
    "REJECTED": "#ff453a",
}

PULSE_SOURCE = "PULSE Market"
PULSE_DOMAINS = {ALL_DOMAINS, "MARKET_EVENT"}
PULSE_RING_SESSIONS = 5

PULSE_ID_PATTERN = re.compile(r"^pulse_(.+)_(\d{4}-\d{2}-\d{2})_1d$")
PULSE_RETURN_PATTERN = re.compile(r"close-to-close move ([+-]?[0-9]+(?:[.][0-9]+)?)%")
PULSE_VOLUME_PATTERN = re.compile(r"volume ([0-9]+(?:[.][0-9]+)?)x")

PULSE_COLUMNS = [
    "event_id",
    "symbol",
    "name",
    "session_date",
    "return_pct",
    "volume_ratio",
    "new_high",
    "new_low",
    "direction",
    "signals",
    "source_url",
]


CSS = """
<style>
html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"] {
    background: #000000;
}
[data-testid="stApp"]::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background: repeating-linear-gradient(
        0deg,
        rgba(255, 255, 255, 0.018) 0px,
        rgba(255, 255, 255, 0.018) 1px,
        transparent 1px,
        transparent 3px
    );
    z-index: 0;
}
[data-testid="stHeader"] {
    background: transparent;
}
#MainMenu, footer {
    visibility: hidden;
}
.block-container {
    padding-top: 1.4rem;
    padding-bottom: 2rem;
    max-width: 100%;
}
[data-testid="stSidebar"] {
    background: #05070a;
    border-right: 1px solid #1c2128;
}
.nomad-wordmark {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-weight: 800;
    font-size: 4.4rem;
    letter-spacing: -0.045em;
    color: #f0f3f6;
    line-height: 0.9;
    text-shadow: 0 0 28px rgba(255, 157, 34, 0.18);
}
.nomad-sub {
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.2em;
    color: #77818c;
    margin-top: 8px;
}
.nomad-status {
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.12em;
    color: #9aa4ae;
    text-align: right;
    line-height: 1.8;
}
.nomad-status .online {
    color: #5ce1a0;
    animation: nomad-breathe 2.4s ease-in-out infinite;
}
@keyframes nomad-breathe {
    0%, 100% { opacity: 1; text-shadow: 0 0 8px rgba(92, 225, 160, 0.7); }
    50% { opacity: 0.45; text-shadow: none; }
}
.nomad-rule {
    height: 2px;
    width: 220px;
    background: linear-gradient(90deg, #4cc9f0, #b388ff, #ff6ec7, #ff9d22);
    margin: 16px 0 18px 0;
}
.nomad-metrics {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    border: 1px solid #2a2f36;
    margin-bottom: 14px;
    background: linear-gradient(180deg, #05070a 0%, #000000 100%);
}
.nomad-metrics.six {
    grid-template-columns: repeat(6, 1fr);
}
.nomad-metric {
    padding: 10px 16px;
    border-right: 1px solid #2a2f36;
}
.nomad-metric:last-child {
    border-right: none;
}
.nomad-metric-label {
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.64rem;
    letter-spacing: 0.16em;
    color: #77818c;
}
.nomad-metric-value {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 2rem;
    font-weight: 700;
    color: #e6edf3;
    letter-spacing: -0.02em;
}
.nomad-metric-value.small {
    font-size: 1.35rem;
    padding-top: 6px;
}
.nomad-tape {
    overflow: hidden;
    white-space: nowrap;
    border-top: 1px solid #1c2128;
    border-bottom: 1px solid #1c2128;
    padding: 7px 0;
    margin-bottom: 14px;
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.74rem;
    letter-spacing: 0.08em;
    background: #030405;
}
.nomad-tape-inner {
    display: inline-block;
    padding-left: 100%;
    animation: nomad-tape 75s linear infinite;
}
.nomad-tape:hover .nomad-tape-inner {
    animation-play-state: paused;
}
.nomad-tape-item {
    margin-right: 34px;
    color: #9aa4ae;
}
.nomad-tape-item b {
    color: #f0f3f6;
    margin-right: 6px;
}
.nomad-tape-label {
    color: #ff9d22;
    margin-right: 30px;
}
@keyframes nomad-tape {
    from { transform: translateX(0); }
    to { transform: translateX(-100%); }
}
.nomad-panel {
    border: 1px solid #2a2f36;
    padding: 14px 16px;
    background: #000000;
    margin-bottom: 12px;
    box-shadow: inset 0 1px 0 rgba(255, 157, 34, 0.06);
}
.nomad-panel-title {
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.16em;
    color: #ff9d22;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
}
.nomad-panel-title .right {
    color: #77818c;
}
.nomad-entity-name {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 2.5rem;
    font-weight: 800;
    color: #f0f3f6;
    line-height: 1;
    letter-spacing: -0.03em;
    margin-bottom: 14px;
    word-break: break-word;
}
.nomad-kv {
    display: grid;
    grid-template-columns: 120px 1fr;
    gap: 5px 12px;
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.78rem;
    margin-bottom: 14px;
}
.nomad-k {
    color: #77818c;
    letter-spacing: 0.08em;
}
.nomad-v {
    color: #c9d1d9;
    overflow-wrap: anywhere;
}
.nomad-section {
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.66rem;
    letter-spacing: 0.16em;
    color: #77818c;
    margin: 12px 0 6px 0;
    border-top: 1px solid #1c2128;
    padding-top: 10px;
}
.nomad-bar-row {
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.76rem;
    color: #c9d1d9;
    margin: 6px 0;
}
.nomad-bar-row .count {
    float: right;
    color: #77818c;
}
.nomad-bar-track {
    height: 2px;
    background: #161b22;
    margin-top: 3px;
}
.nomad-bar-fill {
    height: 2px;
}
.nomad-row {
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.74rem;
    color: #c9d1d9;
    border-bottom: 1px solid #11161c;
    padding: 6px 0;
    line-height: 1.45;
    overflow-wrap: anywhere;
}
.nomad-row .time {
    color: #77818c;
    margin-right: 8px;
}
.nomad-row a {
    color: #c9d1d9;
    text-decoration: none;
}
.nomad-row a:hover {
    color: #ff9d22;
}
.nomad-tag {
    display: inline-block;
    padding: 0 6px;
    border: 1px solid;
    font-size: 0.6rem;
    letter-spacing: 0.1em;
    margin-right: 8px;
}
.nomad-pulse-symbol {
    display: inline-block;
    min-width: 58px;
    font-weight: 700;
    letter-spacing: 0.06em;
}
.nomad-pulse-return {
    display: inline-block;
    min-width: 72px;
    text-align: right;
    margin-right: 10px;
    font-weight: 700;
}
.nomad-pulse-name {
    color: #77818c;
    margin-left: 4px;
}
.nomad-log {
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.74rem;
    color: #9aa4ae;
    line-height: 1.75;
}
.nomad-log .time {
    color: #77818c;
    margin-right: 10px;
}
.nomad-log .key {
    color: #ff9d22;
    display: inline-block;
    width: 82px;
}
.nomad-hint {
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.75rem;
    color: #77818c;
    line-height: 1.6;
}
.nomad-incident-title {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 1.7rem;
    font-weight: 700;
    color: #f0f3f6;
    line-height: 1.2;
    margin: 12px 0;
    overflow-wrap: anywhere;
}
[data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 1px solid #2a2f36;
}
button[data-baseweb="tab"] {
    font-family: Consolas, 'Courier New', monospace;
    letter-spacing: 0.16em;
    font-size: 0.74rem;
    color: #77818c;
    background: transparent;
    padding: 8px 18px;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #ff9d22;
}
[data-baseweb="tab-highlight"] {
    background-color: #ff9d22;
}
@media (max-width: 900px) {
    .nomad-metrics, .nomad-metrics.six {
        grid-template-columns: repeat(3, 1fr);
    }
    .nomad-wordmark {
        font-size: 3.3rem;
    }
}
@media (max-width: 480px) {
    .nomad-metrics, .nomad-metrics.six {
        grid-template-columns: repeat(2, 1fr);
    }
    .nomad-kv {
        grid-template-columns: 95px 1fr;
    }
}
</style>
"""


def to_event_types(domain):
    return None if domain == ALL_DOMAINS else (domain,)


@st.cache_data(ttl=60)
def load_metrics():
    return get_system_metrics()


@st.cache_data(ttl=300)
def load_event_types():
    return get_event_types()


@st.cache_data(ttl=300)
def load_entities(event_types):
    return get_entity_index(limit=5000, event_types=event_types)


@st.cache_data(ttl=300)
def load_relationships(limit, min_co_occurrence, event_types):
    return get_top_relationships(
        limit=limit,
        min_co_occurrence=min_co_occurrence,
        event_types=event_types,
    )


@st.cache_resource(ttl=300)
def load_graph(limit, min_co_occurrence, exclude_generic, event_types):
    relationships = load_relationships(
        limit,
        min_co_occurrence,
        event_types,
    )
    entities = load_entities(event_types)

    if event_types is None:
        graph = build_network(
            relationships,
            entities,
            exclude_generic=exclude_generic,
        )
    else:
        graph = build_network(
            relationships,
            entities,
            exclude_generic=exclude_generic,
            min_degree=1,
            largest_component_only=False,
        )

    return graph, compute_layout(graph)


@st.cache_data(ttl=120)
def load_neighborhood(entity_id, limit, event_types):
    return get_entity_neighborhood(
        int(entity_id),
        limit=limit,
        event_types=event_types,
    )


@st.cache_data(ttl=120)
def load_entity_events(entity_id, limit, event_types):
    return get_entity_events(
        int(entity_id),
        limit=limit,
        event_types=event_types,
    )


@st.cache_data(ttl=120)
def load_evidence(entity_id_a, entity_id_b, limit, event_types):
    return get_relationship_evidence(
        int(entity_id_a),
        int(entity_id_b),
        limit=limit,
        event_types=event_types,
    )


@st.cache_data(ttl=60)
def load_recent_events(limit, event_types):
    return get_recent_events(limit=limit, event_types=event_types)


# ------------------------------------------------------------
# PULSE data access (read-only)
# ------------------------------------------------------------


def parse_pulse_row(row):
    event_id, source_event_id, title, source_url = row

    identity = PULSE_ID_PATTERN.fullmatch(str(source_event_id or ""))

    if identity is None:
        return None

    symbol, session_text = identity.groups()
    title = str(title or "")

    marker = f" ({symbol}): "

    if marker in title:
        name, rest = title.split(marker, 1)
        signal_text = rest.rsplit(" | ", 1)[0]
    else:
        name = symbol
        signal_text = title

    return_match = PULSE_RETURN_PATTERN.search(signal_text)
    volume_match = PULSE_VOLUME_PATTERN.search(signal_text)

    return_pct = float(return_match.group(1)) if return_match else None
    volume_ratio = float(volume_match.group(1)) if volume_match else None

    new_high = "closing high" in signal_text
    new_low = "closing low" in signal_text

    if (return_pct is not None and return_pct > 0) or new_high:
        direction = "UP"
    elif (return_pct is not None and return_pct < 0) or new_low:
        direction = "DOWN"
    else:
        direction = "VOLUME"

    return {
        "event_id": int(event_id),
        "symbol": symbol,
        "name": name,
        "session_date": pd.Timestamp(session_text),
        "return_pct": return_pct,
        "volume_ratio": volume_ratio,
        "new_high": new_high,
        "new_low": new_low,
        "direction": direction,
        "signals": [part.strip() for part in signal_text.split(";") if part.strip()],
        "source_url": source_url,
    }


@st.cache_data(ttl=60)
def load_pulse(limit=5000):
    query = """
        SELECT
            event_id,
            source_event_id,
            title,
            source_url
        FROM events
        WHERE event_type = 'MARKET_EVENT'
          AND source = %(source)s
        ORDER BY event_time DESC, event_id DESC
        LIMIT %(limit)s;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"source": PULSE_SOURCE, "limit": int(limit)},
            )
            rows = cursor.fetchall()

    parsed = [item for item in (parse_pulse_row(row) for row in rows) if item]

    return pd.DataFrame(parsed, columns=PULSE_COLUMNS)


@st.cache_data(ttl=60)
def load_pulse_total():
    query = """
        SELECT COUNT(*)
        FROM events
        WHERE event_type = 'MARKET_EVENT'
          AND source = %(source)s;
    """

    with get_database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, {"source": PULSE_SOURCE})
            return int(cursor.fetchone()[0])


def build_signal_entities(pulse_frame, entity_lookup, sessions=PULSE_RING_SESSIONS):
    """Map graph nodes to their latest PULSE direction in recent sessions."""

    if pulse_frame is None or pulse_frame.empty or not entity_lookup:
        return {}

    recent_dates = sorted(pulse_frame["session_date"].unique(), reverse=True)[:sessions]
    recent = pulse_frame[pulse_frame["session_date"].isin(recent_dates)]

    signals = {}

    # pulse_frame is newest-first, so the first hit per node is the latest.
    for row in recent.itertuples(index=False):
        for key in (str(row.symbol).casefold(), str(row.name).casefold()):
            node = entity_lookup.get(key)

            if node is not None and node not in signals:
                signals[node] = row.direction

    return signals


# ------------------------------------------------------------
# Formatting helpers
# ------------------------------------------------------------


def esc(value):
    return html.escape(str(value))


def fmt_time(value, pattern="%Y-%m-%d %H:%M"):
    if value is None or pd.isna(value):
        return "—"

    return pd.Timestamp(value).strftime(pattern)


def fmt_utc(value):
    if value is None or pd.isna(value):
        return "—"

    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        return timestamp.strftime("%Y-%m-%d %H:%M") + " (timezone unknown)"

    return timestamp.tz_convert("UTC").strftime("%Y-%m-%d %H:%M UTC")


def fmt_int(value):
    if value is None or pd.isna(value):
        return "0"

    return f"{int(value):,}"


def fmt_pct(value):
    if value is None or pd.isna(value):
        return "—"

    return f"{value:+.2f}%"


def direction_color(direction):
    return {
        "UP": PULSE_UP,
        "DOWN": PULSE_DOWN,
    }.get(direction, PULSE_SPIKE)


def direction_glyph(direction):
    return {
        "UP": "▲",
        "DOWN": "▼",
    }.get(direction, "◆")


def safe_url(value):
    if not isinstance(value, str):
        return None

    value = value.strip()

    try:
        parsed = urlsplit(value)
    except ValueError:
        return None

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None

    return value


def linked_title(title, source_url):
    title = esc(title)
    url = safe_url(source_url)

    if url:
        return (
            f'<a href="{esc(url)}" target="_blank" '
            f'rel="noopener noreferrer">{title}</a>'
        )

    return title


def clear_focus():
    st.session_state["entity_picker"] = None


def focus_entity(entity_id):
    st.session_state["pending_select"] = int(entity_id)


def refresh_memory():
    st.cache_data.clear()
    st.cache_resource.clear()


# ------------------------------------------------------------
# Header + ticker tape
# ------------------------------------------------------------


def render_header(metrics, domain, pulse_total):
    now = datetime.now().strftime("%H:%M:%S")
    last_ingest = fmt_utc(metrics.get("last_ingested_at"))

    left, right = st.columns([3, 1.4])

    with left:
        st.markdown(
            '<div class="nomad-wordmark">NOMAD</div>'
            '<div class="nomad-sub">'
            "WORLD INTELLIGENCE SYSTEM // OBSERVATION · MEMORY · RELATIONSHIP · CHANGE"
            "</div>",
            unsafe_allow_html=True,
        )

    with right:
        st.markdown(
            '<div class="nomad-status">'
            '<span class="online">● SYSTEM ONLINE</span><br>'
            f"DOMAIN&nbsp;&nbsp;{esc(domain)}<br>"
            f"LAST INGEST&nbsp;&nbsp;{esc(last_ingest)}<br>"
            f"RENDERED&nbsp;&nbsp;{now}"
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="nomad-rule"></div>',
        unsafe_allow_html=True,
    )

    cells = [
        ("OBSERVED EVENTS", metrics.get("observed_events")),
        ("AI EVENTS", metrics.get("ai_events")),
        ("WORLD EVENTS", metrics.get("world_events")),
        ("PULSE SIGNALS", pulse_total),
        ("CANONICAL ENTITIES", metrics.get("canonical_entities")),
        ("ENTITY MENTIONS", metrics.get("entity_mentions")),
        ("RELATIONSHIPS", metrics.get("relationships")),
    ]

    html_cells = "".join(
        '<div class="nomad-metric">'
        f'<div class="nomad-metric-label">{label}</div>'
        f'<div class="nomad-metric-value">{fmt_int(value)}</div>'
        "</div>"
        for label, value in cells
    )

    st.markdown(
        f'<div class="nomad-metrics">{html_cells}</div>',
        unsafe_allow_html=True,
    )


def render_tape(pulse_frame):
    if pulse_frame is None or pulse_frame.empty:
        return

    latest = pulse_frame.head(40)
    items = []

    for row in latest.itertuples(index=False):
        color = direction_color(row.direction)
        detail = []

        if row.return_pct is not None and not pd.isna(row.return_pct):
            detail.append(fmt_pct(row.return_pct))

        if row.volume_ratio is not None and not pd.isna(row.volume_ratio):
            detail.append(f"VOL {row.volume_ratio:.1f}x")

        if row.new_high:
            detail.append("20S HIGH")

        if row.new_low:
            detail.append("20S LOW")

        items.append(
            '<span class="nomad-tape-item">'
            f'<span style="color:{color};">{direction_glyph(row.direction)}</span> '
            f"<b>{esc(row.symbol)}</b>"
            f'<span style="color:{color};">{esc(" · ".join(detail))}</span>'
            f' <span style="color:#4a525c;">{fmt_time(row.session_date, "%m-%d")}</span>'
            "</span>"
        )

    st.markdown(
        '<div class="nomad-tape"><div class="nomad-tape-inner">'
        '<span class="nomad-tape-label">PULSE //</span>'
        f'{"".join(items)}'
        "</div></div>",
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------
# Relationship field panels
# ------------------------------------------------------------


def render_bar_list(rows, max_value):
    parts = []

    for name, count, color in rows:
        width = 100 * count / max_value if max_value else 0

        parts.append(
            '<div class="nomad-bar-row">'
            f'{esc(name)}<span class="count">{fmt_int(count)}</span>'
            '<div class="nomad-bar-track">'
            f'<div class="nomad-bar-fill" '
            f'style="width:{width:.1f}%;background:{color};"></div>'
            "</div></div>"
        )

    return "".join(parts)


def render_field_overview(graph):
    ranked = sorted(
        graph.nodes,
        key=lambda node: graph.nodes[node]["event_count"],
        reverse=True,
    )[:10]

    rows = [
        (
            graph.nodes[node]["name"],
            graph.nodes[node]["event_count"],
            graph.nodes[node]["color"],
        )
        for node in ranked
    ]

    max_value = rows[0][1] if rows else 0

    st.markdown(
        '<div class="nomad-panel">'
        '<div class="nomad-panel-title">'
        "<span>ENTITY DOSSIER</span>"
        '<span class="right">NO FOCUS</span></div>'
        '<div class="nomad-entity-name">Full field</div>'
        '<div class="nomad-hint">'
        "Click any node in the relationship field, or pick an entity "
        "in the sidebar, to open its dossier.</div>"
        '<div class="nomad-section">MOST OBSERVED IN FIELD</div>'
        f"{render_bar_list(rows, max_value)}"
        "</div>",
        unsafe_allow_html=True,
    )


def render_dossier(graph, entities, selected, event_types):
    attributes = graph.nodes[selected]
    entity_rows = entities[entities["entity_id"] == selected]

    if entity_rows.empty:
        first_observed = "—"
        last_observed = "—"
    else:
        entity_row = entity_rows.iloc[0]
        first_observed = fmt_time(entity_row["first_observed_at"])
        last_observed = fmt_time(entity_row["last_observed_at"])

    neighbors = load_neighborhood(selected, 12, event_types)
    events = load_entity_events(selected, 8, event_types)

    bar_rows = []

    for row in neighbors.itertuples(index=False):
        neighbor_id = int(row.neighbor_id)
        color = graph.nodes[neighbor_id]["color"] if neighbor_id in graph else MUTED

        bar_rows.append((row.neighbor_name, int(row.co_occurrence_count), color))

    max_value = bar_rows[0][1] if bar_rows else 0

    event_parts = []

    for row in events.itertuples(index=False):
        title = linked_title(row.title, row.source_url)

        event_parts.append(
            '<div class="nomad-row">'
            f'<span class="time">'
            f'{fmt_time(row.event_time, "%Y-%m-%d")}'
            f"</span>{title}</div>"
        )

    event_html = "".join(event_parts) or (
        '<div class="nomad-hint">No events found.</div>'
    )

    st.markdown(
        '<div class="nomad-panel">'
        '<div class="nomad-panel-title">'
        f"<span>ENTITY DOSSIER</span>"
        f'<span class="right">ID {selected}</span></div>'
        f'<div class="nomad-entity-name">{esc(attributes["name"])}</div>'
        '<div class="nomad-kv">'
        '<div class="nomad-k">TYPE</div>'
        f'<div class="nomad-v">{esc(attributes["entity_type"])}</div>'
        '<div class="nomad-k">OBSERVED IN</div>'
        f'<div class="nomad-v">'
        f'{fmt_int(attributes["event_count"])} events</div>'
        '<div class="nomad-k">CONNECTIONS</div>'
        f'<div class="nomad-v">{graph.degree(selected)} in field</div>'
        '<div class="nomad-k">CLUSTER</div>'
        f'<div class="nomad-v" style="color:{attributes["color"]};">'
        f'■ {attributes["community"]:02d}</div>'
        '<div class="nomad-k">FIRST SEEN</div>'
        f'<div class="nomad-v">{first_observed}</div>'
        '<div class="nomad-k">LAST SEEN</div>'
        f'<div class="nomad-v">{last_observed}</div>'
        "</div>"
        '<div class="nomad-section">'
        "STRONGEST CONNECTIONS · SHARED EVENTS</div>"
        f"{render_bar_list(bar_rows, max_value)}"
        '<div class="nomad-section">RECENT OBSERVATIONS</div>'
        f"{event_html}</div>",
        unsafe_allow_html=True,
    )


def render_evidence(graph, selected, event_types, domain):
    if selected is None:
        st.markdown(
            '<div class="nomad-panel">'
            '<div class="nomad-panel-title">'
            "<span>RELATIONSHIP EVIDENCE</span></div>"
            '<div class="nomad-hint">'
            "Focus an entity to see the events behind its connections."
            "</div></div>",
            unsafe_allow_html=True,
        )
        return

    neighbors = load_neighborhood(selected, 25, event_types)

    if neighbors.empty:
        st.info("No relationships recorded.")
        return

    neighbor_lookup = {
        int(row.neighbor_id): (
            row.neighbor_name,
            int(row.co_occurrence_count),
        )
        for row in neighbors.itertuples(index=False)
    }

    st.markdown(
        '<div class="nomad-panel-title">' "<span>RELATIONSHIP EVIDENCE</span></div>",
        unsafe_allow_html=True,
    )

    neighbor_id = st.selectbox(
        "Connection",
        list(neighbor_lookup),
        format_func=lambda node: (
            f"{graph.nodes[selected]['name']} ↔ "
            f"{neighbor_lookup[node][0]} · "
            f"{neighbor_lookup[node][1]} shared"
        ),
        key=f"evidence_{domain}_{selected}",
        label_visibility="collapsed",
    )

    evidence = load_evidence(
        selected,
        neighbor_id,
        12,
        event_types,
    )

    parts = []

    for row in evidence.itertuples(index=False):
        title = linked_title(row.title, row.source_url)

        parts.append(
            '<div class="nomad-row">'
            f'<span class="time">'
            f'{fmt_time(row.event_time, "%Y-%m-%d")}'
            f"</span>{title}</div>"
        )

    st.markdown("".join(parts), unsafe_allow_html=True)


def render_observation_stream(event_types):
    events = load_recent_events(14, event_types)
    parts = []

    for row in events.itertuples(index=False):
        event_type = str(row.event_type)
        color = EVENT_TYPE_COLORS.get(
            event_type.upper(),
            DEFAULT_TAG_COLOR,
        )

        parts.append(
            '<div class="nomad-row">'
            f'<span class="time">'
            f'{fmt_time(row.event_time, "%m-%d %H:%M")}</span>'
            f'<span class="nomad-tag" '
            f'style="color:{color};border-color:{color};">'
            f"{esc(event_type)}</span>"
            f"{esc(row.title)}</div>"
        )

    body = "".join(parts) or ('<div class="nomad-hint">No events in this domain.</div>')

    st.markdown(
        '<div class="nomad-panel">'
        '<div class="nomad-panel-title">'
        "<span>OBSERVATION STREAM</span>"
        f'<span class="right">SHOWING {len(events)}</span></div>'
        f"{body}</div>",
        unsafe_allow_html=True,
    )


def render_system_log(metrics, graph, selected, domain, pulse_total):
    now = datetime.now().strftime("%H:%M:%S")

    clusters = len({graph.nodes[node]["community"] for node in graph.nodes})

    lines = [
        ("DOMAIN", f"{domain} field active"),
        (
            "MEMORY",
            f"{fmt_int(metrics.get('observed_events'))} " "events held in PostgreSQL",
        ),
        (
            "PARALLAX",
            f"{fmt_int(metrics.get('canonical_entities'))} " "canonical entity records",
        ),
        (
            "PULSE",
            f"{fmt_int(pulse_total)} market-change signals stored",
        ),
        (
            "LINKS",
            f"{fmt_int(metrics.get('entity_mentions'))} " "event-entity mentions",
        ),
        (
            "RELATIONS",
            f"{fmt_int(metrics.get('relationships'))} " "relationships stored",
        ),
        (
            "FIELD",
            f"{graph.number_of_nodes()} nodes · "
            f"{graph.number_of_edges()} edges · "
            f"{clusters} clusters rendered",
        ),
    ]

    if selected is not None:
        lines.append(
            (
                "FOCUS",
                f"{graph.nodes[selected]['name']} · "
                f"{graph.degree(selected)} links isolated",
            )
        )

    body = "".join(
        f'<div><span class="time">{now}</span>'
        f'<span class="key">{key}</span>{esc(text)}</div>'
        for key, text in lines
    )

    st.markdown(
        '<div class="nomad-panel">'
        '<div class="nomad-panel-title">'
        "<span>SYSTEM LOG</span></div>"
        f'<div class="nomad-log">{body}</div></div>',
        unsafe_allow_html=True,
    )


def render_empty_domain(domain, min_co_occurrence):
    st.markdown(
        '<div class="nomad-panel">'
        '<div class="nomad-panel-title">'
        "<span>RELATIONSHIP FIELD</span>"
        f'<span class="right">{esc(domain)}</span></div>'
        '<div class="nomad-entity-name">No field</div>'
        '<div class="nomad-hint">'
        f"No visible relationships for {esc(domain)} with at least "
        f"{min_co_occurrence} shared event(s).<br>"
        "Lower the threshold or check graph filters and extraction coverage."
        "</div></div>",
        unsafe_allow_html=True,
    )


def extract_clicked_entity(event):
    if not event:
        return None

    selection = event.get("selection", {}) or {}
    points = selection.get("points", []) or []

    for point in points:
        customdata = point.get("customdata")

        if customdata is None:
            continue

        if isinstance(customdata, (list, tuple)):
            if not customdata:
                continue
            customdata = customdata[0]

        try:
            return int(customdata)
        except (TypeError, ValueError):
            continue

    return None


def render_field(
    graph,
    positions,
    event_types,
    domain,
    metrics,
    min_co_occurrence,
    pulse_total,
    signal_entities=None,
):
    if graph is None or graph.number_of_nodes() == 0:
        render_empty_domain(domain, min_co_occurrence)
        render_observation_stream(event_types)
        return

    entities = load_entities(event_types)

    ranked_nodes = sorted(
        graph.nodes,
        key=lambda node: graph.nodes[node]["event_count"],
        reverse=True,
    )

    options = [None] + ranked_nodes

    if st.session_state.get("entity_picker") not in options:
        st.session_state["entity_picker"] = None

    with st.sidebar:
        st.selectbox(
            "Focus entity",
            options,
            key="entity_picker",
            format_func=lambda node: (
                "— full field —"
                if node is None
                else (
                    f"{graph.nodes[node]['name']} · "
                    f"{graph.nodes[node]['event_count']}"
                )
            ),
        )

        st.button("Clear focus", on_click=clear_focus)

    selected = st.session_state.get("entity_picker")

    graph_column, dossier_column = st.columns(
        [2.6, 1.15],
        gap="small",
    )

    with graph_column:
        figure = render_graph(
            graph,
            positions,
            selected_entity_id=selected,
            label_limit=18,
            height=720,
            signal_entities=signal_entities,
        )

        event = st.plotly_chart(
            figure,
            key=f"field_{domain}_{selected}",
            on_select="rerun",
            selection_mode="points",
            config={
                "displayModeBar": False,
                "scrollZoom": True,
            },
            width="stretch",
        )

        clicked = extract_clicked_entity(event)

        if clicked is not None and clicked != selected and clicked in graph:
            st.session_state["pending_select"] = clicked
            st.rerun()

    with dossier_column:
        if selected is None:
            render_field_overview(graph)
        else:
            render_dossier(
                graph,
                entities,
                selected,
                event_types,
            )

    evidence_column, stream_column, log_column = st.columns(
        [1.3, 1.3, 1],
        gap="small",
    )

    with evidence_column:
        render_evidence(graph, selected, event_types, domain)

    with stream_column:
        render_observation_stream(event_types)

    with log_column:
        render_system_log(metrics, graph, selected, domain, pulse_total)


# ------------------------------------------------------------
# PULSE interface
# ------------------------------------------------------------


def pulse_chips(row):
    chips = []

    if row.return_pct is not None and not pd.isna(row.return_pct):
        chips.append(("MOVE", direction_color(row.direction)))

    if row.volume_ratio is not None and not pd.isna(row.volume_ratio):
        chips.append((f"VOL {row.volume_ratio:.1f}x", PULSE_SPIKE))

    if row.new_high:
        chips.append(("20S HIGH", PULSE_UP))

    if row.new_low:
        chips.append(("20S LOW", PULSE_DOWN))

    return "".join(
        f'<span class="nomad-tag" style="color:{color};border-color:{color};">'
        f"{esc(label)}</span>"
        for label, color in chips
    )


def build_pulse_field(view):
    figure = go.Figure()

    groups = (
        ("UP", "Upside", "circle"),
        ("DOWN", "Downside", "circle"),
        ("VOLUME", "Volume only", "diamond-open"),
    )

    for direction, label, shape in groups:
        part = view[view["direction"] == direction]

        if part.empty:
            continue

        y_values = part["return_pct"].fillna(0.0)
        sizes = part["volume_ratio"].fillna(1.0).clip(1.0, 8.0) * 4 + 7

        hover = [
            f"<b>{esc(row.symbol)}</b> · {esc(row.name)}<br>"
            f"{fmt_time(row.session_date, '%Y-%m-%d')}<br>"
            + "<br>".join(esc(signal) for signal in row.signals)
            for row in part.itertuples(index=False)
        ]

        figure.add_trace(
            go.Scatter(
                x=part["session_date"],
                y=y_values,
                mode="markers",
                name=label,
                text=hover,
                hovertemplate="%{text}<extra></extra>",
                marker=dict(
                    size=sizes,
                    color=direction_color(direction),
                    symbol=shape,
                    opacity=0.82,
                    line=dict(width=1, color="#000000"),
                ),
            )
        )

    labeled = (
        view.dropna(subset=["return_pct"])
        .assign(magnitude=lambda frame: frame["return_pct"].abs())
        .sort_values("magnitude", ascending=False)
        .head(8)
    )

    if not labeled.empty:
        figure.add_trace(
            go.Scatter(
                x=labeled["session_date"],
                y=labeled["return_pct"],
                mode="text",
                text=labeled["symbol"],
                textposition="top center",
                textfont=dict(
                    family="Consolas, Courier New, monospace",
                    size=10,
                    color="#c9d1d9",
                ),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    for level, color in ((4.0, PULSE_UP), (-4.0, PULSE_DOWN)):
        figure.add_hline(
            y=level,
            line=dict(color=color, width=1, dash="dot"),
            opacity=0.35,
        )

    figure.add_hline(y=0, line=dict(color="#2a2f36", width=1))

    figure.update_layout(
        height=430,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="#000000",
        plot_bgcolor="#000000",
        font=dict(family="Consolas, Courier New, monospace", color="#9aa4ae", size=11),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(gridcolor="#11161c", zeroline=False, showline=False),
        yaxis=dict(
            gridcolor="#11161c",
            zeroline=False,
            ticksuffix="%",
            title=dict(text="close-to-close return", font=dict(size=10)),
        ),
        hoverlabel=dict(
            bgcolor="#05070a",
            bordercolor="#ff9d22",
            font=dict(family="Consolas, Courier New, monospace", color="#e6edf3"),
        ),
    )

    return figure


def build_instrument_history(history):
    colors = [direction_color(direction) for direction in history["direction"]]
    values = history["return_pct"].fillna(0.0)

    hover = [
        f"<b>{fmt_time(row.session_date, '%Y-%m-%d')}</b><br>"
        + "<br>".join(esc(signal) for signal in row.signals)
        for row in history.itertuples(index=False)
    ]

    figure = go.Figure(
        go.Bar(
            x=history["session_date"],
            y=values,
            marker=dict(color=colors, line=dict(width=0)),
            text=hover,
            hovertemplate="%{text}<extra></extra>",
        )
    )

    figure.update_layout(
        height=240,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="#000000",
        plot_bgcolor="#000000",
        font=dict(family="Consolas, Courier New, monospace", color="#9aa4ae", size=10),
        xaxis=dict(gridcolor="#11161c"),
        yaxis=dict(
            gridcolor="#11161c", ticksuffix="%", zeroline=True, zerolinecolor="#2a2f36"
        ),
        showlegend=False,
        bargap=0.35,
        hoverlabel=dict(
            bgcolor="#05070a",
            bordercolor="#ff9d22",
            font=dict(family="Consolas, Courier New, monospace", color="#e6edf3"),
        ),
    )

    return figure


def render_pulse(pulse_frame, pulse_total, pulse_error, domain, entity_lookup):
    st.markdown(
        '<div class="nomad-panel-title">'
        "<span>PULSE // MARKET CHANGE DETECTION</span>"
        f'<span class="right">{fmt_int(pulse_total)} SIGNALS STORED</span></div>',
        unsafe_allow_html=True,
    )

    if domain not in PULSE_DOMAINS:
        st.markdown(
            '<div class="nomad-panel"><div class="nomad-hint">'
            f"PULSE watches MARKET_EVENT observations. The {esc(domain)} domain "
            "is active. Switch to ALL or MARKET_EVENT to open the market field."
            "</div></div>",
            unsafe_allow_html=True,
        )
        return

    if pulse_error:
        st.error(
            "Could not load PULSE signals. Check the database connection "
            "and confirm the pulse pipeline has run with save_events enabled."
        )
        return

    if pulse_frame is None or pulse_frame.empty:
        st.markdown(
            '<div class="nomad-panel"><div class="nomad-hint">'
            "No PULSE signals stored yet. Run NOMAD with the pulse pipeline enabled."
            "</div></div>",
            unsafe_allow_html=True,
        )
        return

    sessions = sorted(
        pulse_frame["session_date"].drop_duplicates().tolist(),
        reverse=True,
    )

    control_column, caption_column = st.columns([1, 3])

    with control_column:
        window = st.selectbox(
            "Window",
            [5, 20, 60, 250],
            index=1,
            format_func=lambda size: f"Last {size} stored sessions",
            key="pulse_window",
        )

    with caption_column:
        st.caption(
            "PULSE triggers describe market movement, not cause. Prices are "
            "unadjusted, so splits can create artifacts. Dates are session "
            "dates, not exact trade times. Not trading advice."
        )

    window_dates = sessions[:window]
    view = pulse_frame[pulse_frame["session_date"].isin(window_dates)]

    latest_session = sessions[0]
    latest_count = int((pulse_frame["session_date"] == latest_session).sum())

    upside = int((view["return_pct"].notna() & (view["return_pct"] > 0)).sum())
    downside = int((view["return_pct"].notna() & (view["return_pct"] < 0)).sum())
    spikes = int(view["volume_ratio"].notna().sum())
    breakouts = int((view["new_high"] | view["new_low"]).sum())

    cells = [
        ("SIGNALS IN WINDOW", fmt_int(len(view)), "#e6edf3", ""),
        (
            f"LATEST · {fmt_time(latest_session, '%m-%d')}",
            fmt_int(latest_count),
            AMBER,
            "",
        ),
        ("UPSIDE MOVES ≥4%", fmt_int(upside), PULSE_UP, ""),
        ("DOWNSIDE MOVES ≥4%", fmt_int(downside), PULSE_DOWN, ""),
        ("VOLUME SPIKES ≥2.5x", fmt_int(spikes), PULSE_SPIKE, ""),
        ("20-SESSION BREAKOUTS", fmt_int(breakouts), "#b388ff", ""),
    ]

    html_cells = "".join(
        '<div class="nomad-metric">'
        f'<div class="nomad-metric-label">{esc(label)}</div>'
        f'<div class="nomad-metric-value {extra}" style="color:{color};">'
        f"{value}</div></div>"
        for label, value, color, extra in cells
    )

    st.markdown(
        f'<div class="nomad-metrics six">{html_cells}</div>',
        unsafe_allow_html=True,
    )

    field_column, feed_column = st.columns([2.2, 1.2], gap="small")

    with field_column:
        st.markdown(
            '<div class="nomad-panel-title">'
            "<span>SIGNAL FIELD</span>"
            '<span class="right">SIZE = VOLUME RATIO</span></div>',
            unsafe_allow_html=True,
        )

        st.plotly_chart(
            build_pulse_field(view),
            key=f"pulse_field_{window}",
            config={"displayModeBar": False},
            width="stretch",
        )

    with feed_column:
        latest_rows = (
            view.assign(magnitude=view["return_pct"].abs().fillna(0.0))
            .sort_values(["session_date", "magnitude"], ascending=[False, False])
            .head(16)
        )

        parts = []

        for row in latest_rows.itertuples(index=False):
            color = direction_color(row.direction)
            symbol_html = linked_title(row.symbol, row.source_url)

            parts.append(
                '<div class="nomad-row">'
                f'<span class="time">{fmt_time(row.session_date, "%m-%d")}</span>'
                f'<span class="nomad-pulse-symbol" style="color:{color};">'
                f"{direction_glyph(row.direction)} {symbol_html}</span>"
                f'<span class="nomad-pulse-return" style="color:{color};">'
                f"{fmt_pct(row.return_pct)}</span>"
                f"{pulse_chips(row)}"
                f'<span class="nomad-pulse-name">{esc(row.name)}</span>'
                "</div>"
            )

        st.markdown(
            '<div class="nomad-panel">'
            '<div class="nomad-panel-title">'
            "<span>LATEST TRIGGERS</span>"
            f'<span class="right">TOP {len(latest_rows)}</span></div>'
            f'{"".join(parts)}</div>',
            unsafe_allow_html=True,
        )

    activity_column, instrument_column = st.columns([1, 1.6], gap="small")

    activity = (
        view.groupby("symbol")
        .agg(
            signals=("event_id", "count"),
            up=("direction", lambda values: int((values == "UP").sum())),
            down=("direction", lambda values: int((values == "DOWN").sum())),
        )
        .sort_values("signals", ascending=False)
    )

    with activity_column:
        bar_rows = []

        for symbol, row in activity.head(12).iterrows():
            if row["up"] > row["down"]:
                color = PULSE_UP
            elif row["down"] > row["up"]:
                color = PULSE_DOWN
            else:
                color = PULSE_SPIKE

            bar_rows.append((symbol, int(row["signals"]), color))

        max_value = bar_rows[0][1] if bar_rows else 0

        st.markdown(
            '<div class="nomad-panel">'
            '<div class="nomad-panel-title">'
            "<span>MOST ACTIVE INSTRUMENTS</span>"
            '<span class="right">SIGNALS IN WINDOW</span></div>'
            f"{render_bar_list(bar_rows, max_value)}"
            '<div class="nomad-hint" style="margin-top:10px;">'
            "Green = mostly upside triggers · Red = mostly downside · "
            "Blue = mixed or volume-led</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    with instrument_column:
        st.markdown(
            '<div class="nomad-panel-title">'
            "<span>INSTRUMENT HISTORY</span>"
            '<span class="right">ALL LOADED SIGNALS</span></div>',
            unsafe_allow_html=True,
        )

        symbols = list(activity.index) or sorted(pulse_frame["symbol"].unique())

        symbol = st.selectbox(
            "Instrument",
            symbols,
            key="pulse_instrument",
            label_visibility="collapsed",
        )

        history = pulse_frame[pulse_frame["symbol"] == symbol].sort_values(
            "session_date"
        )

        st.plotly_chart(
            build_instrument_history(history),
            key=f"pulse_history_{symbol}",
            config={"displayModeBar": False},
            width="stretch",
        )

        name = history["name"].iloc[-1] if not history.empty else symbol

        entity_id = entity_lookup.get(str(symbol).casefold()) or entity_lookup.get(
            str(name).casefold()
        )

        if entity_id is not None:
            st.button(
                f"Focus {symbol} in relationship field",
                key=f"pulse_focus_{symbol}",
                on_click=focus_entity,
                args=(entity_id,),
            )
            st.caption("Opens the entity dossier in the ◉ RELATIONSHIP FIELD tab.")
        else:
            st.caption(
                f"{symbol} is not visible in the current relationship field. "
                "Lower the minimum shared events or disable generic-hub hiding."
            )


# ------------------------------------------------------------
# CORTEX review interface
# ------------------------------------------------------------


def submit_cortex_review(incident_id, new_status, expected_status):
    """
    Button callback.

    expected_status is bound when the button is rendered, rather
    than read again after the click. This preserves the repository's
    stale-status protection.

    Never cache this function.
    """

    try:
        result = update_cortex_review_status(
            incident_id=int(incident_id),
            new_status=new_status,
            expected_status=expected_status,
        )
    except ValueError as error:
        st.session_state["cortex_notice"] = (
            "warning",
            str(error),
        )
    except Exception:
        st.session_state["cortex_notice"] = (
            "error",
            "Could not confirm the review update. Refresh the queue "
            "to check the current status before retrying.",
        )
    else:
        st.session_state["cortex_notice"] = (
            "success",
            f"Candidate #{result['incident_id']} saved as "
            f"{result['review_status']}.",
        )

        # Review queries below are uncached. Clear cached data as
        # well so future cached summaries cannot retain old status.
        st.cache_data.clear()


def render_cortex_notice():
    notice = st.session_state.pop("cortex_notice", None)

    if notice is None:
        return

    level, message = notice

    if level == "success":
        st.success(message)
    elif level == "warning":
        st.warning(message)
    else:
        st.error(message)


def render_cortex_evidence(evidence):
    st.markdown(
        '<div class="nomad-panel-title">' "<span>SUPPORTING OBSERVATIONS</span></div>",
        unsafe_allow_html=True,
    )

    st.caption(
        "Descriptions and entities below are the current stored article "
        "data, not immutable snapshots of the original CORTEX run."
    )

    for row in evidence.itertuples(index=False):
        label = f"{row.source} · event {row.event_id} · " f"{fmt_utc(row.event_time)}"

        with st.expander(label, expanded=True):
            st.markdown(
                '<div class="nomad-row">'
                f"{linked_title(row.title, row.source_url)}"
                "</div>",
                unsafe_allow_html=True,
            )

            st.caption(
                f"Event type: {row.event_type} | "
                f"Extraction: {row.entity_extraction_version or 'Unknown'}"
            )

            if row.description:
                # Render source descriptions as text, not executable HTML.
                st.text(str(row.description))
            else:
                st.caption("No description stored.")

            if row.location_name:
                st.text(f"Stored location: {row.location_name}")

            entity_names = list(row.entities) if row.entities is not None else []

            st.text(
                "Entities: "
                + ("; ".join(entity_names) if entity_names else "None extracted")
            )


def render_cortex(event_types, domain):
    st.markdown(
        '<div class="nomad-panel-title">'
        "<span>CORTEX // INCIDENT REVIEW</span>"
        f'<span class="right">{esc(domain)}</span></div>',
        unsafe_allow_html=True,
    )

    render_cortex_notice()

    st.caption(
        "Review candidate article groupings. CONFIRMED means you accept "
        "the grouping, not that every claim in the articles is verified. "
        "Scores are heuristic similarities, not probabilities."
    )

    # Deliberately uncached: fetch current review state each rerun.
    try:
        metrics = get_cortex_metrics(event_types=event_types)
    except Exception:
        st.error(
            "Could not load CORTEX. Check the database connection "
            "and confirm the CORTEX tables exist."
        )
        return

    columns = st.columns(4)

    for column, label, field in zip(
        columns,
        ("SAVED CANDIDATES", "UNREVIEWED", "CONFIRMED", "REJECTED"),
        (
            "candidate_incidents",
            "unreviewed_incidents",
            "confirmed_incidents",
            "rejected_incidents",
        ),
    ):
        column.metric(label, fmt_int(metrics.get(field)))

    st.caption(
        "Counts describe saved candidate snapshots. Different memberships "
        "can produce overlapping snapshots of the same real-world incident."
    )

    filter_column, limit_column = st.columns([2, 1])

    with filter_column:
        status_filter = st.selectbox(
            "Review status",
            ["UNREVIEWED", "CONFIRMED", "REJECTED", "ALL"],
            key=f"cortex_status_{domain}",
        )

    with limit_column:
        queue_limit = st.selectbox(
            "Queue size",
            [25, 50, 100, 250, 1000],
            index=2,
            key=f"cortex_limit_{domain}",
        )

    requested_status = None if status_filter == "ALL" else status_filter

    try:
        queue = get_cortex_incidents(
            limit=queue_limit,
            review_status=requested_status,
            event_types=event_types,
        )
    except Exception:
        st.error("Could not load the candidate queue.")
        return

    if requested_status is None:
        total = int(metrics.get("candidate_incidents", 0))
    else:
        count_field = {
            "UNREVIEWED": "unreviewed_incidents",
            "CONFIRMED": "confirmed_incidents",
            "REJECTED": "rejected_incidents",
        }[requested_status]
        total = int(metrics.get(count_field, 0))

    st.caption(f"Showing {len(queue):,} of {total:,} matching saved candidates.")

    if queue.empty:
        st.info(
            "No candidates in this view. Choose another review status "
            "or domain. CORTEX currently analyzes WORLD_EVENT."
        )
        return

    lookup = {int(row.incident_id): row for row in queue.itertuples(index=False)}
    incident_ids = list(lookup)
    picker_key = f"cortex_picker_{domain}_{status_filter}"

    if st.session_state.get(picker_key) not in incident_ids:
        st.session_state[picker_key] = incident_ids[0]

    incident_id = st.selectbox(
        "Candidate incident",
        incident_ids,
        format_func=lambda candidate_id: (
            f"#{candidate_id} · {lookup[candidate_id].review_status} · "
            f"{lookup[candidate_id].title}"
        ),
        key=picker_key,
    )

    incident = lookup[incident_id]
    status = str(incident.review_status)
    color = REVIEW_COLORS.get(status, MUTED)

    sources = list(incident.sources) if incident.sources is not None else []
    entities = (
        list(incident.core_entities) if incident.core_entities is not None else []
    )

    st.markdown(
        '<div class="nomad-panel">'
        '<div class="nomad-panel-title">'
        f"<span>CANDIDATE #{incident_id}</span>"
        f'<span style="color:{color};">{esc(status)}</span></div>'
        f'<div class="nomad-incident-title">{esc(incident.title)}</div>'
        '<div class="nomad-kv">'
        '<div class="nomad-k">MIN PAIR</div>'
        f'<div class="nomad-v">{float(incident.match_score):.3f}</div>'
        '<div class="nomad-k">MEAN PAIR</div>'
        f'<div class="nomad-v">{float(incident.mean_pair_score):.3f}</div>'
        '<div class="nomad-k">OUTLETS</div>'
        f'<div class="nomad-v">{esc(", ".join(sources) or "—")}</div>'
        '<div class="nomad-k">CORE ENTITIES</div>'
        f'<div class="nomad-v">{esc(", ".join(entities) or "—")}</div>'
        '<div class="nomad-k">EVIDENCE</div>'
        f'<div class="nomad-v">{fmt_int(incident.evidence_count)} articles</div>'
        '<div class="nomad-k">FIRST PUBLISHED</div>'
        f'<div class="nomad-v">{esc(fmt_utc(incident.first_published_at))}</div>'
        '<div class="nomad-k">LAST PUBLISHED</div>'
        f'<div class="nomad-v">{esc(fmt_utc(incident.last_published_at))}</div>'
        '<div class="nomad-k">VERSION</div>'
        f'<div class="nomad-v">{esc(incident.cortex_version)}</div>'
        '<div class="nomad-k">UPDATED</div>'
        f'<div class="nomad-v">{esc(fmt_utc(incident.updated_at))}</div>'
        "</div></div>",
        unsafe_allow_html=True,
    )

    st.caption(
        "The title is copied from a representative article, not generated "
        "as a verified incident summary. Outlet diversity does not establish "
        "independent reporting."
    )

    try:
        evidence = get_cortex_incident_evidence(int(incident_id))
    except Exception:
        st.error(
            "Could not load the supporting observations. "
            "Review controls are unavailable until evidence loads."
        )
        return

    evidence_complete = (
        len(evidence) == int(incident.evidence_count) and len(evidence) >= 2
    )

    if not evidence_complete:
        st.warning(
            "The evidence count changed or is incomplete. "
            "Refresh before making a review decision."
        )

    render_cortex_evidence(evidence)

    st.markdown(
        '<div class="nomad-section">REVIEW DECISION</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "Confirm accepts this grouping. Reject marks it as unsuitable. "
        "Reopen returns it to UNREVIEWED. Source articles are never changed."
    )

    confirm_column, reject_column, reopen_column = st.columns(3)

    with confirm_column:
        st.button(
            "Confirm grouping",
            key=f"cortex_confirm_{incident_id}",
            disabled=not evidence_complete or status == "CONFIRMED",
            on_click=submit_cortex_review,
            args=(int(incident_id), "CONFIRMED", status),
        )

    with reject_column:
        st.button(
            "Reject grouping",
            key=f"cortex_reject_{incident_id}",
            disabled=not evidence_complete or status == "REJECTED",
            on_click=submit_cortex_review,
            args=(int(incident_id), "REJECTED", status),
        )

    with reopen_column:
        st.button(
            "Reopen review",
            key=f"cortex_reopen_{incident_id}",
            disabled=not evidence_complete or status == "UNREVIEWED",
            on_click=submit_cortex_review,
            args=(int(incident_id), "UNREVIEWED", status),
        )

    st.caption(
        "This local prototype stores current status only. It does not yet "
        "record reviewer identity, review notes, or decision history."
    )


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------


def main():
    st.markdown(CSS, unsafe_allow_html=True)

    if "pending_select" in st.session_state:
        st.session_state["entity_picker"] = st.session_state.pop("pending_select")

    event_type_counts = load_event_types()

    domain_counts = {ALL_DOMAINS: int(event_type_counts["event_count"].sum())}

    for row in event_type_counts.itertuples(index=False):
        domain_counts[str(row.event_type)] = int(row.event_count)

    if st.session_state.get("domain") not in domain_counts:
        st.session_state["domain"] = ALL_DOMAINS

    with st.sidebar:
        st.markdown(
            '<div class="nomad-panel-title"><span>DOMAIN</span></div>',
            unsafe_allow_html=True,
        )

        domain = st.radio(
            "Domain",
            list(domain_counts),
            format_func=lambda value: (f"{value} · {domain_counts.get(value, 0):,}"),
            key="domain",
            label_visibility="collapsed",
        )

        st.markdown(
            '<div class="nomad-panel-title">' "<span>FIELD CONTROLS</span></div>",
            unsafe_allow_html=True,
        )

        relationship_limit = st.slider(
            "Relationships loaded",
            100,
            1500,
            600,
            50,
        )
        min_co_occurrence = st.slider(
            "Minimum shared events",
            1,
            10,
            2,
        )
        exclude_generic = st.toggle(
            "Hide generic hubs (AI, API…)",
            value=True,
        )

        st.button("Refresh memory", on_click=refresh_memory)

    event_types = to_event_types(domain)
    metrics = load_metrics()

    pulse_frame = None
    pulse_total = 0
    pulse_error = False

    try:
        pulse_frame = load_pulse()
        pulse_total = load_pulse_total()
    except Exception:
        pulse_error = True

    render_header(metrics, domain, pulse_total)
    render_tape(pulse_frame)

    relationships = load_relationships(
        relationship_limit,
        min_co_occurrence,
        event_types,
    )

    graph = None
    positions = None

    if not relationships.empty:
        graph, positions = load_graph(
            relationship_limit,
            min_co_occurrence,
            exclude_generic,
            event_types,
        )

    entity_lookup = {}

    if graph is not None:
        for node in graph.nodes:
            entity_lookup.setdefault(
                str(graph.nodes[node]["name"]).casefold(),
                node,
            )

    signal_entities = build_signal_entities(pulse_frame, entity_lookup)

    field_tab, pulse_tab, cortex_tab = st.tabs(
        [
            "◉ RELATIONSHIP FIELD",
            "▲ PULSE",
            "◆ CORTEX",
        ]
    )

    with field_tab:
        render_field(
            graph,
            positions,
            event_types,
            domain,
            metrics,
            min_co_occurrence,
            pulse_total,
            signal_entities,
        )

    with pulse_tab:
        render_pulse(
            pulse_frame,
            pulse_total,
            pulse_error,
            domain,
            entity_lookup,
        )

    with cortex_tab:
        render_cortex(event_types, domain)


if __name__ == "__main__":
    main()
