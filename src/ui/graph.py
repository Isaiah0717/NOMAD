import html
import math

import networkx as nx
import plotly.graph_objects as go

BACKGROUND = "#000000"
FRAME_COLOR = "#2a2f36"
TEXT_COLOR = "#c9d1d9"
MUTED_COLOR = "#77818c"
SMALL_CLUSTER_COLOR = "#4a525c"
AMBER = "#ff9d22"
RADAR_COLOR = "rgba(76,201,240,0.07)"
HUD_COLOR = "rgba(255,157,34,0.55)"
MONO_FONT = "Consolas, 'Courier New', monospace"

COMMUNITY_PALETTE = (
    "#4cc9f0",
    "#ff9d22",
    "#b388ff",
    "#5ce1a0",
    "#ff453a",
    "#f7d154",
    "#ff6ec7",
    "#2ec4b6",
    "#8fa8ff",
    "#c0ff6b",
)

SIGNAL_COLORS = {
    "UP": "#5ce1a0",
    "DOWN": "#ff453a",
    "VOLUME": "#4cc9f0",
}

SIGNAL_LABELS = {
    "UP": "PULSE · UPSIDE SIGNAL",
    "DOWN": "PULSE · DOWNSIDE SIGNAL",
    "VOLUME": "PULSE · VOLUME SPIKE",
}

MIN_COLORED_CLUSTER_SIZE = 3
CROSS_EDGE_COLOR = "rgba(119,129,140,0.16)"
DIM_EDGE_COLOR = "rgba(119,129,140,0.04)"

# Edge styling per strength level: weak, medium, strong.
EDGE_STYLE = {
    0: (0.5, 0.28),
    1: (0.9, 0.45),
    2: (1.6, 0.75),
}

GENERIC_ENTITIES = {
    "ai",
    "ai-powered",
    "ai-native",
    "artificial intelligence",
    "api",
    "llm",
    "llms",
}


# ------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------


def hex_to_rgba(hex_color, alpha):
    value = hex_color.lstrip("#")
    red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))

    return f"rgba({red},{green},{blue},{alpha})"


def is_generic(entity_name):
    return str(entity_name).strip().lower() in GENERIC_ENTITIES


def positive_count(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 1

    if not math.isfinite(number) or number < 1:
        return 1

    return int(number)


def split_xy(points):
    """Turn [(x, y), (x, y)] into ([x, x], [y, y])."""

    points = list(points)

    if not points:
        return [], []

    xs, ys = zip(*points)
    return list(xs), list(ys)


# ------------------------------------------------------------
# Graph construction
# ------------------------------------------------------------


def build_network(
    relationships,
    entities,
    exclude_generic=True,
    min_degree=2,
    largest_component_only=True,
    min_component_size=2,
):
    """Entity co-occurrence graph used by app.py."""

    graph = nx.Graph()
    entity_lookup = entities.set_index("entity_id").to_dict("index")

    for row in relationships.itertuples(index=False):
        if exclude_generic and (is_generic(row.entity_a) or is_generic(row.entity_b)):
            continue

        endpoints = (
            (row.entity_id_a, row.entity_a, row.type_a),
            (row.entity_id_b, row.entity_b, row.type_b),
        )

        for entity_id, entity_name, entity_type in endpoints:
            if entity_id not in graph:
                info = entity_lookup.get(entity_id, {})

                graph.add_node(
                    entity_id,
                    name=entity_name,
                    entity_type=str(entity_type).upper(),
                    node_kind="ENTITY",
                    event_count=positive_count(info.get("event_count", 1)),
                )

        count = positive_count(row.co_occurrence_count)
        events_a = graph.nodes[row.entity_id_a]["event_count"]
        events_b = graph.nodes[row.entity_id_b]["event_count"]

        graph.add_edge(
            row.entity_id_a,
            row.entity_id_b,
            count=count,
            association=count / math.sqrt(events_a * events_b),
            relationship="CO_OCCURS",
        )

    if min_degree > 1 and graph.number_of_nodes():
        graph = nx.k_core(graph, min_degree).copy()

    if graph.number_of_nodes():
        if largest_component_only:
            largest = max(nx.connected_components(graph), key=len)
            graph = graph.subgraph(largest).copy()
        else:
            keep = set()

            for component in nx.connected_components(graph):
                if len(component) >= min_component_size:
                    keep.update(component)

            graph = graph.subgraph(keep).copy()

    assign_communities(graph)
    return graph


def assign_communities(graph):
    if not graph.number_of_nodes():
        return

    if not graph.number_of_edges():
        communities = [{node} for node in graph.nodes]
    else:
        communities = nx.community.louvain_communities(
            graph,
            weight="association",
            seed=42,
        )

    communities = sorted(communities, key=len, reverse=True)
    color_index = 0

    for index, members in enumerate(communities):
        major = len(members) >= MIN_COLORED_CLUSTER_SIZE

        if major:
            color = COMMUNITY_PALETTE[color_index % len(COMMUNITY_PALETTE)]
            color_index += 1
        else:
            color = SMALL_CLUSTER_COLOR

        for node in members:
            attributes = graph.nodes[node]
            attributes["community"] = index
            attributes["major_cluster"] = major
            attributes["color"] = (
                AMBER if attributes.get("node_kind") == "INCIDENT" else color
            )


# ------------------------------------------------------------
# Layout
# ------------------------------------------------------------


def normalize_positions(positions, percentile=0.9, soft_limit=1.0):
    if not positions:
        return {}

    all_x, all_y = split_xy(positions.values())
    center_x = sum(all_x) / len(all_x)
    center_y = sum(all_y) / len(all_y)

    distances = sorted(
        math.hypot(x - center_x, y - center_y) for x, y in positions.values()
    )

    reference = distances[int((len(distances) - 1) * percentile)] or 1.0
    normalized = {}

    for node, (x, y) in positions.items():
        dx = (x - center_x) / reference
        dy = (y - center_y) / reference
        distance = math.hypot(dx, dy)

        if distance > soft_limit:
            compressed = soft_limit + 0.15 * math.tanh((distance - soft_limit) / 0.5)
            scale = compressed / distance
            dx *= scale
            dy *= scale

        normalized[node] = (dx, dy)

    return normalized


def compute_layout(graph, seed=42):
    if not graph.number_of_nodes():
        return {}

    positions = nx.spring_layout(
        graph,
        k=2.2 / math.sqrt(graph.number_of_nodes()),
        iterations=500,
        weight="association",
        seed=seed,
    )

    return normalize_positions(positions)


# ------------------------------------------------------------
# Edge strength
# ------------------------------------------------------------


def strength_cuts(graph):
    """Return (medium_cut, strong_cut) association thresholds."""

    values = sorted(
        data.get("association", 0.0) for _, _, data in graph.edges(data=True)
    )

    if not values:
        return 0.0, 0.0

    medium_cut = values[int((len(values) - 1) * 0.50)]
    strong_cut = values[int((len(values) - 1) * 0.85)]

    return medium_cut, strong_cut


def edge_strength(data, cuts):
    """0 = weak, 1 = medium, 2 = strong."""

    association = data.get("association", 0.0)
    medium_cut, strong_cut = cuts

    if association >= strong_cut:
        return 2

    if association >= medium_cut:
        return 1

    return 0


# ------------------------------------------------------------
# Labels
# ------------------------------------------------------------


def label_collides(position, chosen_positions, min_distance):
    x, y = position

    for other_x, other_y in chosen_positions:
        if math.hypot(x - other_x, (y - other_y) * 1.6) < min_distance:
            return True

    return False


def choose_labels(
    graph,
    positions,
    focus,
    selected_entity_id,
    label_limit,
    min_distance=0.11,
    priority=None,
):
    candidates = []

    if selected_entity_id in graph:
        candidates.append(selected_entity_id)
        candidates.extend(
            sorted(
                focus - {selected_entity_id},
                key=lambda node: graph.nodes[node]["event_count"],
                reverse=True,
            )
        )
    else:
        # Incidents first, then PULSE-signal nodes, then cluster leaders.
        candidates.extend(
            node
            for node in graph.nodes
            if graph.nodes[node].get("node_kind") == "INCIDENT"
        )

        if priority:
            candidates.extend(
                sorted(
                    priority,
                    key=lambda node: graph.nodes[node]["event_count"],
                    reverse=True,
                )
            )

        communities = {}

        for node in graph.nodes:
            if graph.nodes[node]["major_cluster"]:
                communities.setdefault(graph.nodes[node]["community"], []).append(node)

        for members in communities.values():
            candidates.append(max(members, key=graph.degree))

        candidates.extend(sorted(graph.nodes, key=graph.degree, reverse=True))

    chosen = []
    chosen_positions = []

    for node in candidates:
        if node in chosen:
            continue

        if len(chosen) >= label_limit:
            break

        position = positions[node]

        if node != selected_entity_id and label_collides(
            position, chosen_positions, min_distance
        ):
            continue

        chosen.append(node)
        chosen_positions.append(position)

    return set(chosen)


# ------------------------------------------------------------
# Rendering
# ------------------------------------------------------------


def edge_key(graph, node_a, node_b, data, selected_entity_id, cuts):
    strength = edge_strength(data, cuts)
    attributes_a = graph.nodes[node_a]
    attributes_b = graph.nodes[node_b]

    if selected_entity_id is not None:
        if selected_entity_id in (node_a, node_b):
            return "focus", None, strength
        return "dim", None, 0

    if data.get("relationship") == "MENTIONED_IN_EVIDENCE":
        return "incident", None, strength

    if (
        attributes_a["community"] == attributes_b["community"]
        and attributes_a["major_cluster"]
    ):
        return "community", attributes_a["color"], strength

    return "cross", None, 0


def edge_line_style(kind, color, strength):
    width, alpha = EDGE_STYLE[strength]

    if kind == "community":
        return width, hex_to_rgba(color, alpha)

    if kind == "incident":
        return width + 0.3, hex_to_rgba(AMBER, alpha + 0.1)

    if kind == "focus":
        return width + 0.5, hex_to_rgba(AMBER, min(alpha + 0.25, 0.95))

    if kind == "cross":
        return 0.5, CROSS_EDGE_COLOR

    return 0.4, DIM_EDGE_COLOR


def add_edges(figure, graph, positions, selected_entity_id):
    cuts = strength_cuts(graph)
    edge_groups = {}

    for node_a, node_b, data in graph.edges(data=True):
        key = edge_key(graph, node_a, node_b, data, selected_entity_id, cuts)

        x0, y0 = positions[node_a]
        x1, y1 = positions[node_b]

        xs, ys = edge_groups.setdefault(key, ([], []))
        xs.extend([x0, x1, None])
        ys.extend([y0, y1, None])

    # Weak edges first, focus edges last, so strong lines sit on top.
    ordered = sorted(
        edge_groups.items(),
        key=lambda item: (item[0][0] == "focus", item[0][2]),
    )

    for (kind, color, strength), (xs, ys) in ordered:
        width, line_color = edge_line_style(kind, color, strength)

        figure.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line=dict(width=width, color=line_color),
                hoverinfo="skip",
                showlegend=False,
            )
        )


def node_hover(graph, node, signals):
    attributes = graph.nodes[node]
    name = html.escape(str(attributes["name"]))

    if attributes.get("node_kind") == "INCIDENT":
        return (
            f"<b>{name}</b><br>"
            "Human-confirmed article grouping<br>"
            f"supporting articles: {attributes['event_count']}<br>"
            f"minimum pair score: {attributes['match_score']:.3f}<br>"
            "Links mean mentioned in supporting evidence."
        )

    signal_line = ""

    if node in signals:
        direction = signals[node]
        signal_line = (
            f'<br><span style="color:{SIGNAL_COLORS[direction]}">'
            f"{SIGNAL_LABELS[direction]}</span>"
        )

    return (
        f"<b>{name}</b><br>"
        f"{html.escape(str(attributes['entity_type']))}<br>"
        f"observed events: {attributes['event_count']}<br>"
        f"connections: {graph.degree(node)}<br>"
        f"cluster: {attributes['community']:02d}"
        f"{signal_line}"
    )


def render_graph(
    graph,
    positions,
    selected_entity_id=None,
    label_limit=18,
    height=760,
    signal_entities=None,
    title="nomad // relationship field",
):
    """
    signal_entities: optional {node_id: "UP" | "DOWN" | "VOLUME"}.
    Nodes listed here receive a PULSE signal ring.
    """

    figure = go.Figure()

    if not graph.number_of_nodes():
        apply_layout(figure, height, title=title)
        figure.add_annotation(
            text="NO RELATIONSHIPS OBSERVED",
            showarrow=False,
            font=dict(family=MONO_FONT, color=MUTED_COLOR),
        )
        return figure

    if selected_entity_id not in graph:
        selected_entity_id = None

    signals = {
        node: direction
        for node, direction in (signal_entities or {}).items()
        if node in graph and direction in SIGNAL_COLORS
    }

    focus = set()

    if selected_entity_id is not None:
        focus = {selected_entity_id} | set(graph.neighbors(selected_entity_id))

    add_edges(figure, graph, positions, selected_entity_id)

    nodes = list(graph.nodes)
    max_events = max(graph.nodes[node]["event_count"] for node in nodes)

    labeled_nodes = choose_labels(
        graph,
        positions,
        focus,
        selected_entity_id,
        label_limit,
        priority=set(signals),
    )

    size_of = {}
    opacity_of = {}

    for node in nodes:
        attributes = graph.nodes[node]

        if attributes.get("node_kind") == "INCIDENT":
            size_of[node] = 24
        else:
            size_of[node] = 3 + 14 * math.sqrt(attributes["event_count"] / max_events)

        opacity_of[node] = 1.0 if not focus or node in focus else 0.1

    xs, ys = split_xy(positions[node] for node in nodes)
    sizes = [size_of[node] for node in nodes]
    colors = [graph.nodes[node]["color"] for node in nodes]
    opacities = [opacity_of[node] for node in nodes]
    symbols = [
        "diamond" if graph.nodes[node].get("node_kind") == "INCIDENT" else "circle"
        for node in nodes
    ]
    labels = [
        graph.nodes[node]["name"] if node in labeled_nodes else "" for node in nodes
    ]
    hovers = [node_hover(graph, node, signals) for node in nodes]

    # Glow: wide haze + mid halo under each node.
    for scale, alpha in ((3.6, 0.05), (2.2, 0.14)):
        figure.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers",
                marker=dict(
                    size=[size * scale for size in sizes],
                    color=[hex_to_rgba(color, alpha) for color in colors],
                    opacity=opacities,
                    symbol=symbols,
                    line=dict(width=0),
                ),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # PULSE rings sit beneath the core so the core stays clickable.
    if signals:
        signal_nodes = list(signals)
        ring_x, ring_y = split_xy(positions[node] for node in signal_nodes)

        for ring_extra, ring_alpha, ring_width in ((18, 0.35, 1.0), (9, 0.95, 1.8)):
            figure.add_trace(
                go.Scatter(
                    x=ring_x,
                    y=ring_y,
                    mode="markers",
                    marker=dict(
                        size=[size_of[node] + ring_extra for node in signal_nodes],
                        color="rgba(0,0,0,0)",
                        opacity=[opacity_of[node] for node in signal_nodes],
                        line=dict(
                            width=ring_width,
                            color=[
                                hex_to_rgba(SIGNAL_COLORS[signals[node]], ring_alpha)
                                for node in signal_nodes
                            ],
                        ),
                    ),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

    # Solid core: the only trace with customdata, so clicks resolve here.
    figure.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            text=labels,
            textposition="top center",
            textfont=dict(family=MONO_FONT, size=10, color=TEXT_COLOR),
            marker=dict(
                size=sizes,
                color=colors,
                opacity=opacities,
                symbol=symbols,
                line=dict(width=0),
            ),
            hovertext=hovers,
            hoverinfo="text",
            customdata=nodes,
            showlegend=False,
        )
    )

    # Hub rings around the six most-observed entities.
    hub_nodes = sorted(
        (node for node in nodes if graph.nodes[node].get("node_kind") != "INCIDENT"),
        key=lambda node: graph.nodes[node]["event_count"],
        reverse=True,
    )[:6]

    if hub_nodes:
        hub_x, hub_y = split_xy(positions[node] for node in hub_nodes)

        figure.add_trace(
            go.Scatter(
                x=hub_x,
                y=hub_y,
                mode="markers",
                marker=dict(
                    size=[size_of[node] + 9 for node in hub_nodes],
                    color="rgba(0,0,0,0)",
                    line=dict(width=0.8, color="rgba(230,237,243,0.55)"),
                ),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # Target lock on the focused node.
    if selected_entity_id is not None:
        focus_x, focus_y = positions[selected_entity_id]

        for ring_size, ring_alpha, ring_width in ((40, 0.9, 1.4), (62, 0.35, 0.8)):
            figure.add_trace(
                go.Scatter(
                    x=[focus_x],
                    y=[focus_y],
                    mode="markers",
                    marker=dict(
                        size=ring_size,
                        color="rgba(0,0,0,0)",
                        line=dict(
                            width=ring_width, color=hex_to_rgba(AMBER, ring_alpha)
                        ),
                    ),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

    apply_layout(figure, height, title=title, signal_count=len(signals))
    return figure


def radar_shapes():
    """Faint concentric rings and crosshair behind the field."""

    shapes = []

    for radius in (0.35, 0.7, 1.05):
        shapes.append(
            dict(
                type="circle",
                xref="x",
                yref="y",
                x0=-radius,
                y0=-radius,
                x1=radius,
                y1=radius,
                line=dict(color=RADAR_COLOR, width=1),
                layer="below",
            )
        )

    for x0, y0, x1, y1 in ((-1.2, 0, 1.2, 0), (0, -1.15, 0, 1.15)):
        shapes.append(
            dict(
                type="line",
                xref="x",
                yref="y",
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                line=dict(color=RADAR_COLOR, width=1, dash="dot"),
                layer="below",
            )
        )

    return shapes


def hud_corners(length=0.035):
    """Corner brackets framing the field, in paper coordinates."""

    shapes = []

    for corner_x, corner_y in ((0, 0), (0, 1), (1, 0), (1, 1)):
        step_x = length if corner_x == 0 else -length
        step_y = length * 1.6 if corner_y == 0 else -length * 1.6

        for end_x, end_y in (
            (corner_x + step_x, corner_y),
            (corner_x, corner_y + step_y),
        ):
            shapes.append(
                dict(
                    type="line",
                    xref="paper",
                    yref="paper",
                    x0=corner_x,
                    y0=corner_y,
                    x1=end_x,
                    y1=end_y,
                    line=dict(color=HUD_COLOR, width=1.5),
                )
            )

    return shapes


def apply_layout(figure, height, title="nomad // relationship field", signal_count=0):
    legend = (
        "color = cluster · size = observations · "
        "ring = PULSE signal (green up · red down · blue volume) · "
        "diamond = confirmed grouping"
    )

    if signal_count:
        status = f"PULSE LINKED · {signal_count} SIGNAL ENTITIES"
        status_color = AMBER
    else:
        status = "PULSE · NO LINKED SIGNALS"
        status_color = MUTED_COLOR

    figure.update_layout(
        height=height,
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        margin=dict(l=20, r=20, t=40, b=40),
        showlegend=False,
        xaxis=dict(visible=False, range=(-1.25, 1.25), fixedrange=False),
        yaxis=dict(visible=False, range=(-1.2, 1.2), fixedrange=False),
        dragmode="pan",
        hoverlabel=dict(
            bgcolor="#05070a",
            bordercolor=AMBER,
            font=dict(family=MONO_FONT, color=TEXT_COLOR, size=11),
        ),
        shapes=radar_shapes() + hud_corners(),
        annotations=(
            dict(
                text=title,
                xref="paper",
                yref="paper",
                x=0.01,
                y=1.0,
                yanchor="bottom",
                showarrow=False,
                font=dict(family=MONO_FONT, size=11, color=MUTED_COLOR),
            ),
            dict(
                text=status,
                xref="paper",
                yref="paper",
                x=0.99,
                y=1.0,
                xanchor="right",
                yanchor="bottom",
                showarrow=False,
                font=dict(family=MONO_FONT, size=10, color=status_color),
            ),
            dict(
                text=legend,
                xref="paper",
                yref="paper",
                x=0.01,
                y=0.0,
                yanchor="top",
                showarrow=False,
                font=dict(family=MONO_FONT, size=10, color=MUTED_COLOR),
            ),
        ),
    )


# ------------------------------------------------------------
# Confirmed incident explorer
# ------------------------------------------------------------


INCIDENT_CSS = """
<style>
html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"] {
    background: #000000;
    color: #c9d1d9;
}
[data-testid="stHeader"] {
    background: transparent;
}
#MainMenu, footer {
    visibility: hidden;
}
[data-testid="stSidebar"] {
    background: #05070a;
    border-right: 1px solid #1c2128;
}
.cortex-wordmark {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-weight: 800;
    font-size: 3.2rem;
    letter-spacing: -0.04em;
    color: #f0f3f6;
    line-height: 0.95;
}
.cortex-wordmark span {
    color: #ff9d22;
}
.cortex-sub {
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.2em;
    color: #77818c;
    margin: 8px 0 14px 0;
}
.cortex-rule {
    height: 2px;
    width: 220px;
    background: linear-gradient(90deg, #ff9d22, #ff6ec7, #b388ff);
    margin-bottom: 16px;
}
.cortex-title {
    font-family: Consolas, 'Courier New', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.16em;
    color: #ff9d22;
    margin: 6px 0 10px 0;
}
.cortex-headline {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 1.5rem;
    font-weight: 700;
    color: #f0f3f6;
    line-height: 1.2;
    margin-bottom: 8px;
    overflow-wrap: anywhere;
}
[data-testid="stMetricValue"] {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    color: #e6edf3;
}
[data-testid="stMetricLabel"] {
    font-family: Consolas, 'Courier New', monospace;
    letter-spacing: 0.12em;
    color: #77818c;
}
</style>
"""


def load_confirmed_incident_graph(exclude_generic=True):
    """
    Read existing tables only.

    Incident/entity edges mean an entity was extracted from at
    least one supporting article. No actor roles are inferred.
    """

    from data import run_query

    incidents = run_query("""
        SELECT
            ci.incident_id,
            ci.title,
            ci.match_score,
            ci.sources,
            COUNT(cie.event_id) AS evidence_count
        FROM cortex_incidents ci
        LEFT JOIN cortex_incident_events cie
            ON cie.incident_id = ci.incident_id
        WHERE ci.review_status = 'CONFIRMED'
        GROUP BY ci.incident_id
        ORDER BY ci.incident_id;
    """)

    mentions = run_query("""
        SELECT
            ci.incident_id,
            en.entity_id,
            en.entity_name,
            en.entity_type,
            COUNT(DISTINCT cie.event_id) AS supporting_mentions
        FROM cortex_incidents ci
        JOIN cortex_incident_events cie
            ON cie.incident_id = ci.incident_id
        JOIN event_entities ee
            ON ee.event_id = cie.event_id
        JOIN entities en
            ON en.entity_id = ee.entity_id
        WHERE ci.review_status = 'CONFIRMED'
        GROUP BY
            ci.incident_id,
            en.entity_id,
            en.entity_name,
            en.entity_type
        ORDER BY ci.incident_id, en.entity_id;
    """)

    graph = nx.Graph()

    # Namespaced keys prevent incident #2 colliding with entity #2.
    for row in incidents.itertuples(index=False):
        graph.add_node(
            f"incident:{int(row.incident_id)}",
            name=f"INCIDENT #{int(row.incident_id)}",
            node_kind="INCIDENT",
            entity_type="INCIDENT",
            incident_id=int(row.incident_id),
            title=row.title,
            match_score=float(row.match_score),
            event_count=positive_count(row.evidence_count),
        )

    for row in mentions.itertuples(index=False):
        if exclude_generic and is_generic(row.entity_name):
            continue

        incident_key = f"incident:{int(row.incident_id)}"
        entity_key = f"entity:{int(row.entity_id)}"

        # A concurrent review change can make the two reads differ.
        if incident_key not in graph:
            continue

        if entity_key not in graph:
            graph.add_node(
                entity_key,
                name=row.entity_name,
                node_kind="ENTITY",
                entity_type=str(row.entity_type).upper(),
                entity_id=int(row.entity_id),
                event_count=1,
            )

        graph.add_edge(
            incident_key,
            entity_key,
            count=positive_count(row.supporting_mentions),
            association=1.0,
            relationship="MENTIONED_IN_EVIDENCE",
        )

    # Distinct supporting articles across confirmed groups.
    entity_counts = run_query("""
        SELECT
            ee.entity_id,
            COUNT(DISTINCT ee.event_id) AS event_count
        FROM event_entities ee
        WHERE EXISTS (
            SELECT 1
            FROM cortex_incident_events cie
            JOIN cortex_incidents ci
                ON ci.incident_id = cie.incident_id
            WHERE cie.event_id = ee.event_id
              AND ci.review_status = 'CONFIRMED'
        )
        GROUP BY ee.entity_id;
    """)

    for row in entity_counts.itertuples(index=False):
        key = f"entity:{int(row.entity_id)}"

        if key in graph:
            graph.nodes[key]["event_count"] = positive_count(row.event_count)

    assign_communities(graph)
    return graph


def is_safe_url(url):
    from urllib.parse import urlsplit

    if not isinstance(url, str):
        return False

    try:
        parsed = urlsplit(url)
    except ValueError:
        return False

    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def run_incident_explorer():
    import streamlit as st

    from data import get_cortex_incident_evidence

    st.set_page_config(
        page_title="NOMAD | CORTEX",
        page_icon="◈",
        layout="wide",
    )

    st.markdown(INCIDENT_CSS, unsafe_allow_html=True)

    st.markdown(
        '<div class="cortex-wordmark">NOMAD <span>// CORTEX</span></div>'
        '<div class="cortex-sub">CONFIRMED INCIDENT FIELD · EVIDENCE · ENTITIES</div>'
        '<div class="cortex-rule"></div>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown(
            '<div class="cortex-title">INCIDENT FIELD</div>', unsafe_allow_html=True
        )
        exclude_generic = st.toggle("Hide generic entities", value=True)
        st.button("Refresh incident field")

    # Uncached so review changes appear on the next rerun.
    graph = load_confirmed_incident_graph(exclude_generic)

    if not graph.number_of_nodes():
        st.info(
            "No confirmed candidates yet. In the main NOMAD app, "
            "inspect a candidate and confirm its grouping if appropriate. "
            "Then refresh this page."
        )
        return

    incident_nodes = [n for n in graph if graph.nodes[n]["node_kind"] == "INCIDENT"]
    entity_nodes = [n for n in graph if graph.nodes[n]["node_kind"] == "ENTITY"]

    groups_column, entities_column, edges_column = st.columns(3)
    groups_column.metric("CONFIRMED GROUPINGS", len(incident_nodes))
    entities_column.metric("MENTIONED ENTITIES", len(entity_nodes))
    edges_column.metric("EVIDENCE CONNECTIONS", graph.number_of_edges())

    st.caption(
        "Diamond = confirmed grouping. Circle = extracted entity. "
        "An edge does not establish responsibility, participation, "
        "or the truth of a source claim."
    )

    pending = st.session_state.pop("incident_graph_pending", None)

    if pending in graph:
        st.session_state["incident_graph_focus"] = pending

    options = [None] + sorted(
        graph.nodes,
        key=lambda node: (
            graph.nodes[node]["node_kind"] != "INCIDENT",
            str(graph.nodes[node]["name"]),
        ),
    )

    if st.session_state.get("incident_graph_focus") not in options:
        st.session_state["incident_graph_focus"] = None

    selected = st.selectbox(
        "Focus node",
        options,
        key="incident_graph_focus",
        format_func=lambda node: (
            "Full incident field"
            if node is None
            else f"{graph.nodes[node]['name']} [{graph.nodes[node]['entity_type']}]"
        ),
    )

    graph_column, dossier_column = st.columns((2.2, 1))

    with graph_column:
        figure = render_graph(
            graph,
            compute_layout(graph),
            selected_entity_id=selected,
            label_limit=30,
            height=700,
            title="nomad // cortex incident field",
        )

        event = st.plotly_chart(
            figure,
            key=f"incident_field_{selected}",
            on_select="rerun",
            selection_mode="points",
            config={"scrollZoom": True, "displayModeBar": False},
            width="stretch",
        )

        points = (event.get("selection", {}) or {}).get("points", []) or []

        for point in points:
            clicked = point.get("customdata")

            if isinstance(clicked, (list, tuple)):
                clicked = next(iter(clicked), None)

            if isinstance(clicked, str) and clicked in graph:
                if clicked != selected:
                    st.session_state["incident_graph_pending"] = clicked
                    st.rerun()
                break

    with dossier_column:
        if selected is None:
            st.markdown(
                '<div class="cortex-title">INCIDENT DOSSIER</div>'
                '<div class="cortex-headline">Choose a diamond</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Click an incident diamond or select a node above to inspect its evidence."
            )
            return

        attributes = graph.nodes[selected]

        if attributes["node_kind"] == "INCIDENT":
            incident_key = selected
        else:
            st.markdown(
                '<div class="cortex-title">ENTITY</div>'
                f'<div class="cortex-headline">{html.escape(str(attributes["name"]))}</div>',
                unsafe_allow_html=True,
            )
            st.caption(attributes["entity_type"])

            connected = [
                node
                for node in graph.neighbors(selected)
                if graph.nodes[node]["node_kind"] == "INCIDENT"
            ]

            if not connected:
                st.info("No confirmed grouping is linked to this entity.")
                return

            incident_key = st.selectbox(
                "Related confirmed grouping",
                connected,
                format_func=lambda node: graph.nodes[node]["name"],
                key=f"incident_for_{selected}",
            )

        incident = graph.nodes[incident_key]

        st.markdown(
            f'<div class="cortex-title">{html.escape(incident["name"])} · CONFIRMED</div>'
            f'<div class="cortex-headline">{html.escape(str(incident["title"]))}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Minimum pair score {incident['match_score']:.3f}")

        evidence = get_cortex_incident_evidence(incident["incident_id"])

        st.markdown(
            f'<div class="cortex-title">SUPPORTING ARTICLES · {len(evidence)}</div>',
            unsafe_allow_html=True,
        )

        for row in evidence.itertuples(index=False):
            with st.expander(f"{row.source} | event {row.event_id}", expanded=True):
                st.write(row.title)
                st.caption(str(row.event_time))

                if row.description:
                    st.text(str(row.description))

                if is_safe_url(row.source_url):
                    st.link_button("Open source article", row.source_url)

                names = list(row.entities) if row.entities is not None else []
                st.text(
                    "Extracted entities: " + ("; ".join(names) if names else "None")
                )

        st.caption(
            "This view reads current stored articles and entities. "
            "It does not infer actor roles or verify article claims. "
            "Change review decisions in the main NOMAD dashboard."
        )


if __name__ == "__main__":
    run_incident_explorer()
