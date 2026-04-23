import folium
import pandas as pd

from domain.data_structures import Plant
from domain.hub import Hub
from domain.project import Scenario
from domain.shipper import Shipper
from domain.trip import Trip

PLANT_COLOR = "#CE2900"
HUB_ORIGINAL_COLOR = "#A3990B"
HUB_NEW_COLOR = "#FFFB00"
HUB_SECOND_LEG_COLOR = "#E27115"
HUB_POINT_COLOR = "#E27115"
DIRECT_MAIN_STOP_ORIGINAL_COLOR = "#0033FF"
DIRECT_EXTRA_STOP_ORIGINAL_COLOR = "#00A2FF"
DIRECT_MAIN_STOP_NEW_COLOR = "#4B0090"
DIRECT_EXTRA_STOP_NEW_COLOR = "#FF31FF"

def _route_key(route):
    return (
        route.demand.flow_direction,
        tuple(shipper.cofor for shipper in route.demand.pattern.sequence),
    )

def _get_hub_route_keys(hubs: list[Hub], flow: str):
    linehaul_keys = set()
    first_leg_keys = set()

    for hub in hubs:
        if flow == "empties" and not hub.has_empties_flow:
            continue

        linehaul_route = hub.parts_linehaul_route if flow == "parts" else getattr(hub, "empties_linehaul_route", None)
        first_leg_routes = hub.parts_first_leg_routes if flow == "parts" else hub.empties_first_leg_routes

        if linehaul_route is not None:
            linehaul_keys.add((flow, hub.cofor))

        for route in first_leg_routes:
            first_leg_keys.add((flow, hub.cofor, route.shipper.cofor))

    return linehaul_keys, first_leg_keys


def create_map():
    return folium.Map(
        tiles="OpenStreetMap",
        control_scale=True
    )


def add_plant_marker(map_object, plant: Plant):
    tooltip = folium.Tooltip(
        f"""
            <b>Plant:</b> {plant.name}<br>
            <b>COFOR:</b> {plant.cofor}<br>
            {plant.formatted_coordinates}
        """,
        sticky=True
    )

    folium.CircleMarker(
        location=plant.coordinates,
        radius=8,
        color=PLANT_COLOR,
        fill=True,
        fill_color=PLANT_COLOR,
        fill_opacity=0.7,
        tooltip=tooltip
    ).add_to(map_object)


def _get_shipper_demand(shipper: Shipper, flow: str):
    return shipper.parts_demand if flow == "parts" else shipper.empties_demand


def _has_flow_demand(shipper: Shipper, flow: str) -> bool:
    demand = shipper.parts_demand if flow == "parts" else shipper.empties_demand
    return (
        demand is not None
        and (
            float(demand.weight or 0.0) > 0.0
            or float(demand.volume or 0.0) > 0.0
            or float(demand.loading_meters or 0.0) > 0.0
        )
    )

def _get_hub_shippers_from_hubs(hubs: list[Hub], flow: str) -> list[Shipper]:
    shippers_by_cofor: dict[str, Shipper] = {}

    for hub in hubs:
        if flow == "empties" and not hub.has_empties_flow:
            continue

        for shipper in hub.shippers:
            if not shipper.coordinates or not all(pd.notna(c) for c in shipper.coordinates):
                continue
            if not _has_flow_demand(shipper, flow):
                continue

            shippers_by_cofor[shipper.cofor] = shipper

    return list(shippers_by_cofor.values())


def _get_direct_shippers_from_routes(routes) -> list[Shipper]:
    shippers_by_cofor: dict[str, Shipper] = {}
    for route in routes:
        for shipper in route.demand.pattern.shippers:
            if not shipper.coordinates or not all(pd.notna(c) for c in shipper.coordinates):
                continue
            shippers_by_cofor[shipper.cofor] = shipper

    return list(shippers_by_cofor.values())


def plot_hub_points(shippers: list[Shipper], feature_group, flow: str):
    for shipper in shippers:
        demand = _get_shipper_demand(shipper, flow)
        if not demand:
            continue

        if (
            demand.weight == 0.0
            and demand.volume == 0.0
            and demand.loading_meters == 0.0
        ):
            continue

        tooltip = folium.Tooltip(
            f"""
                <b>Name:</b> {shipper.name}<br>
                <b>COFOR:</b> {shipper.cofor}<br>
                <b>Carrier:</b> {shipper.carrier.group}<br>
                <b>Flow:</b> {flow[0].upper()}<br>
                <b>Weight Demand:</b> {demand.weight:,.0f}kg<br>
                <b>Volume Demand:</b> {demand.volume:,.1f}m³<br>
                <b>Load Meter Demand:</b> {demand.loading_meters:,.2f}m<br>
                {shipper.formatted_coordinates}
            """,
            sticky=True
        )

        color = HUB_NEW_COLOR if shipper.original_network == "direct" else HUB_ORIGINAL_COLOR
        folium.CircleMarker(
            location=shipper.coordinates,
            radius=4,
            weight=0.5,
            color="black",
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            tooltip=tooltip
        ).add_to(feature_group)


def plot_routes(routes, feature_group):
    for route in routes:
        sequence = [
            shipper for shipper in route.demand.pattern.sequence
            if shipper.coordinates and all(pd.notna(c) for c in shipper.coordinates)
        ]
        if not sequence:
            continue

        points = ", ".join(shipper.cofor for shipper in sequence)

        route_tooltip_html = f"""
            <b>Route:</b> {route.demand.pattern.route_name}<br>
            <b>Vehicle:</b> {route.vehicle.id}<br>
            <b>Frequency:</b> {route.frequency} T<br>
            <b>Utilization:</b> {route.max_utilization:.2f}%<br>
            <b>Flow:</b> {route.demand.flow_direction[0].upper()}<br>
            <b>Points Attended:</b> {points}<br>
            <b>Route Weight:</b> {route.weight:,.0f}kg<br>
            <b>Route Volume:</b> {route.volume:,.1f}m³<br>
            <b>Route Loading Meters:</b> {route.loading_meters:,.2f}m<br>
        """

        for idx, shipper in enumerate(sequence):
            is_first = idx == 0
            demand = shipper.parts_demand if route.demand.flow_direction == 'parts' else shipper.empties_demand
            tooltip_html = f"""
                <b>{'First Shipper' if is_first else 'Shipper'}:</b> {shipper.name}<br>
                <b>COFOR:</b> {shipper.cofor}<br>
                <b>Stop:</b> {idx + 1}/{len(sequence)}<br>
                <b>Carrier:</b> {shipper.carrier.group}<br>
                {shipper.formatted_coordinates}<br>
                <b>ZIP:</b> {shipper.zip_code}<br>
                <b>Weight:</b> {demand.weight:,.0f}kg<br>
                <b>Volume:</b> {demand.volume:,.1f}m³<br>
                <b>Loading Meters:</b> {demand.loading_meters:,.2f}m<br>
            """

            color = DIRECT_EXTRA_STOP_NEW_COLOR if route.demand.pattern.is_new_pattern or shipper.original_network == 'hub' else DIRECT_EXTRA_STOP_ORIGINAL_COLOR
            if is_first:
                tooltip_html += route_tooltip_html
                color =  DIRECT_MAIN_STOP_NEW_COLOR if route.demand.pattern.is_new_pattern or shipper.original_network == 'hub' else DIRECT_MAIN_STOP_ORIGINAL_COLOR

            folium.CircleMarker(
                location=shipper.coordinates,
                radius=5.5 if is_first else 4,
                weight=1 if is_first else 0.5,
                color="black",
                fill=True,
                fill_color=color,
                fill_opacity=0.85 if is_first else 0.7,
                tooltip=folium.Tooltip(tooltip_html, sticky=True),
            ).add_to(feature_group)

        if len(sequence) == 1:
            continue

        folium.PolyLine(
            locations=[shipper.coordinates for shipper in sequence],
            tooltip=folium.Tooltip(route_tooltip_html, sticky=True),
            weight=1.5,
            opacity=0.5,
            color=DIRECT_EXTRA_STOP_NEW_COLOR if route.demand.pattern.is_new_pattern else DIRECT_EXTRA_STOP_ORIGINAL_COLOR,
        ).add_to(feature_group)


def plot_hubs(
    hubs: list[Hub],
    feature_group,
    flow: str,
    baseline: bool = False,
    skip_linehaul_keys=None,
    skip_first_leg_keys=None,
):
    skip_linehaul_keys = skip_linehaul_keys or set()
    skip_first_leg_keys = skip_first_leg_keys or set()

    for hub in hubs:
        if flow == "empties" and not hub.has_empties_flow:
            continue

        linehaul_route = hub.parts_linehaul_route if flow == "parts" else getattr(hub, "empties_linehaul_route", None)
        first_leg_routes = hub.parts_first_leg_routes if flow == "parts" else hub.empties_first_leg_routes

        if linehaul_route is None:
            continue

        linehaul_key = (flow, hub.cofor)
        if linehaul_key not in skip_linehaul_keys:
            tooltip = folium.Tooltip(
                f"""
                    <b>Linehaul Leg:</b><br>
                    <b>Hub COFOR:</b> {hub.cofor}<br>
                    <b>Hub Name:</b> {hub.name}<br>
                    <b>Flow:</b> {flow}<br>
                    <b>Carrier:</b> {linehaul_route.linehaul_carrier.group}<br>
                    <b>Frequency:</b> {linehaul_route.frequency} T<br>
                    <b>Utilization:</b> {linehaul_route.max_utilization:.2f}%<br>
                    <b>Weight:</b> {linehaul_route.weight:.2f}<br>
                    <b>Volume:</b> {linehaul_route.volume:.2f}<br>
                    <b>Loading Meters:</b> {linehaul_route.loading_meters:.2f}<br>
                """,
                sticky=True
            )
            folium.PolyLine(
                locations=[hub.coordinates, hub.plant.coordinates],
                tooltip=tooltip,
                weight=2,
                color=HUB_SECOND_LEG_COLOR if not baseline else HUB_ORIGINAL_COLOR
            ).add_to(feature_group)

        plotted_first_leg = False
        for route in first_leg_routes:
            first_leg_key = (flow, hub.cofor, route.shipper.cofor)
            if first_leg_key in skip_first_leg_keys:
                continue

            tooltip = folium.Tooltip(
                f"""
                    <b>First Leg:</b><br>
                    <b>Shipper COFOR:</b> {route.shipper.cofor}<br>
                    <b>Shipper Name:</b> {route.shipper.name}<br>
                    <b>Flow:</b> {flow[0].upper()}<br>
                    <b>Carrier:</b> {route.demand.carrier.group}<br>
                    <b>Frequency:</b> {route.frequency} T<br>
                    <b>Weight:</b> {route.weight:.2f}<br>
                    <b>Volume:</b> {route.volume:.2f}<br>
                    <b>Chargeable Weight:</b> {route.costing.chargeable_weight(route):.2f}<br>
                """,
                sticky=True
            )
            color = (
                HUB_ORIGINAL_COLOR
                if baseline
                else (HUB_ORIGINAL_COLOR if route.shipper.original_network == "hub" else HUB_NEW_COLOR)
            )
            folium.PolyLine(
                locations=[route.shipper.coordinates, hub.coordinates],
                tooltip=tooltip,
                weight=1.5,
                opacity=0.5,
                color=color
            ).add_to(feature_group)
            plotted_first_leg = True

        if linehaul_key in skip_linehaul_keys and not plotted_first_leg:
            continue

        tooltip = folium.Tooltip(
            f"""
                <b>Hub COFOR:</b> {hub.cofor}<br>
                <b>Hub Name:</b> {hub.name}<br>
                {hub.formatted_coordinates}
            """,
            sticky=True
        )

        folium.CircleMarker(
            location=hub.coordinates,
            radius=6,
            weight=2,
            color="black",
            fill=True,
            fill_color=HUB_POINT_COLOR,
            fill_opacity=0.7,
            tooltip=tooltip
        ).add_to(feature_group)


def fit_map_to_routes(map_object, plant: Plant, routes, padding=(30, 30)):
    points = [plant.coordinates]

    for route in routes:
        for shipper in route.demand.pattern.shippers:
            if shipper.coordinates:
                points.append(shipper.coordinates)

    if len(points) >= 2:
        map_object.fit_bounds(points, padding=padding)
    elif len(points) == 1:
        map_object.location = points[0]
        map_object.zoom_start = 10


def _get_trip_routes_by_flow(trips: list[Trip], flow: str):
    if flow == "parts":
        return [trip.parts_route for trip in trips if trip.parts_route is not None and trip.parts_route.has_demand]
    return [trip.empties_route for trip in trips if trip.empties_route is not None and trip.empties_route.has_demand]


def generate_scenario_map_html(
    scenario: Scenario,
    baseline_scenario: Scenario | None = None,
    ui_state: dict | None = None,
) -> str:
    ui_state = ui_state or {}

    active_flow = ui_state.get("flow", "parts")
    show_baseline = bool(ui_state.get("show_baseline", False))

    active_networks = set(ui_state.get("active_networks", ["Direct", "Hubs"]))
    active_networks = {n for n in active_networks if n in {"Direct", "Hubs"}}
    if not active_networks:
        active_networks = {"Direct", "Hubs"}

    def _show_layer(network: str, flow: str, baseline: bool = False) -> bool:
        return (
            flow == active_flow
            and network in active_networks
            and (show_baseline or not baseline)
        )

    m = create_map()

    direct_parts_fg = folium.FeatureGroup(name="Direct Parts", show=_show_layer("Direct", "parts"))
    direct_empties_fg = folium.FeatureGroup(name="Direct Empties", show=_show_layer("Direct", "empties"))
    hub_parts_fg = folium.FeatureGroup(name="Hub Parts", show=_show_layer("Hubs", "parts"))
    hub_empties_fg = folium.FeatureGroup(name="Hub Empties", show=_show_layer("Hubs", "empties"))

    asis_direct_parts_fg = folium.FeatureGroup(name="AS IS Direct Parts",
                                               show=_show_layer("Direct", "parts", baseline=True))
    asis_direct_empties_fg = folium.FeatureGroup(name="AS IS Direct Empties",
                                                 show=_show_layer("Direct", "empties", baseline=True))
    asis_hub_parts_fg = folium.FeatureGroup(name="AS IS Hub Parts", show=_show_layer("Hubs", "parts", baseline=True))
    asis_hub_empties_fg = folium.FeatureGroup(name="AS IS Hub Empties",
                                              show=_show_layer("Hubs", "empties", baseline=True))

    direct_parts_fg.add_to(m)
    direct_empties_fg.add_to(m)
    hub_parts_fg.add_to(m)
    hub_empties_fg.add_to(m)
    asis_direct_parts_fg.add_to(m)
    asis_direct_empties_fg.add_to(m)
    asis_hub_parts_fg.add_to(m)
    asis_hub_empties_fg.add_to(m)

    trips = list(scenario.get_in_use_trips())

    parts_routes = _get_trip_routes_by_flow(trips, "parts")
    empties_routes = _get_trip_routes_by_flow(trips, "empties")

    plot_routes(parts_routes, direct_parts_fg)
    plot_routes(empties_routes, direct_empties_fg)

    hubs = list(scenario.get_in_use_hubs())
    hub_parts_points = _get_hub_shippers_from_hubs(hubs, "parts")
    hub_empties_points = _get_hub_shippers_from_hubs(hubs, "empties")

    plot_hub_points(hub_parts_points, hub_parts_fg, "parts")
    plot_hubs(hubs, hub_parts_fg, "parts")

    plot_hub_points(hub_empties_points, hub_empties_fg, "empties")
    plot_hubs(hubs, hub_empties_fg, "empties")

    if baseline_scenario is not None:
        baseline_trips = list(baseline_scenario.get_in_use_trips())
        baseline_parts_routes = _get_trip_routes_by_flow(baseline_trips, "parts")
        baseline_empties_routes = _get_trip_routes_by_flow(baseline_trips, "empties")

        current_route_keys = {_route_key(route) for route in parts_routes + empties_routes}

        baseline_parts_routes = [
            route for route in baseline_parts_routes
            if _route_key(route) not in current_route_keys
        ]
        baseline_empties_routes = [
            route for route in baseline_empties_routes
            if _route_key(route) not in current_route_keys
        ]

        plot_routes(baseline_parts_routes, asis_direct_parts_fg)
        plot_routes(baseline_empties_routes, asis_direct_empties_fg)

        baseline_hubs = list(baseline_scenario.get_in_use_hubs())

        current_parts_linehaul_keys, current_parts_first_leg_keys = _get_hub_route_keys(hubs, "parts")
        current_empties_linehaul_keys, current_empties_first_leg_keys = _get_hub_route_keys(hubs, "empties")

        plot_hubs(
            baseline_hubs,
            asis_hub_parts_fg,
            "parts",
            baseline=True,
            skip_linehaul_keys=current_parts_linehaul_keys,
            skip_first_leg_keys=current_parts_first_leg_keys,
        )
        plot_hubs(
            baseline_hubs,
            asis_hub_empties_fg,
            "empties",
            baseline=True,
            skip_linehaul_keys=current_empties_linehaul_keys,
            skip_first_leg_keys=current_empties_first_leg_keys,
        )

    plant = scenario.plant if hasattr(scenario, "plant") else (
        parts_routes[0].demand.pattern.plant if parts_routes else(
            empties_routes[0].demand.pattern.plant if empties_routes else hubs[0].plant)
    )
    add_plant_marker(m, plant)

    folium.LayerControl(collapsed=True).add_to(m)

    toggle_js = f"""
        <style>
        .leaflet-control-layers {{
            display: none !important;
        }}
        .map-btn {{
            padding: 6px 10px;
            font-size: 13px;
            border-radius: 6px;
            border: 1px solid #d0d7de;
            background: #f6f8fa;
            cursor: pointer;
        }}
        .map-btn.active {{
            background: #b0cfff;
        }}
        .map-btn.radio-active {{
            background: #7fb3ff;
            font-weight: 600;
        }}
        </style>

        <script>
        function getCurrentMapState() {{
            return {{
                flow: activeFlow,
                show_baseline: showBaseline,
                active_networks: Array.from(activeNetworks),
            }};
        }}

        function publishMapState() {{
            const state = getCurrentMapState();

            window.scenarioMapState = state;

            window.parent.postMessage({{
                type: "scenario-map-state-changed",
                payload: state
            }}, "*");
        }}

        let activeNetworks = new Set({list(active_networks)!r});
        let activeFlow = {active_flow!r};
        let showBaseline = {str(show_baseline).lower()};

        function getOverlayCheckbox(labelText) {{
            const checkboxes = document.querySelectorAll('.leaflet-control-layers-overlays input[type=checkbox]');
            for (const cb of checkboxes) {{
                const label = cb.nextSibling?.textContent?.trim();
                if (label === labelText) return cb;
            }}
            return null;
        }}

        function setLayerVisible(labelText, visible) {{
            const cb = getOverlayCheckbox(labelText);
            if (!cb) return;
            if (cb.checked !== visible) cb.click();
        }}

        function syncVisibleLayers() {{
            const allLayers = [
                "Direct Parts", "Direct Empties", "Hub Parts", "Hub Empties",
                "AS IS Direct Parts", "AS IS Direct Empties", "AS IS Hub Parts", "AS IS Hub Empties"
            ];

            allLayers.forEach(layer => {{
                const isBaseline = layer.startsWith("AS IS");
                const isDirect = layer.includes("Direct");
                const networkEnabled = isDirect ? activeNetworks.has("Direct") : activeNetworks.has("Hubs");
                const isParts = layer.endsWith("Parts");
                const flowEnabled = activeFlow === (isParts ? "parts" : "empties");
                const baselineEnabled = !isBaseline || showBaseline;

                setLayerVisible(layer, networkEnabled && flowEnabled && baselineEnabled);
            }});

            document.querySelectorAll('.network-btn').forEach(btn => {{
                btn.classList.toggle('active', activeNetworks.has(btn.dataset.network));
            }});

            document.querySelectorAll('.flow-btn').forEach(btn => {{
                btn.classList.toggle('radio-active', btn.dataset.flow === activeFlow);
            }});

            const baselineBtn = document.querySelector('.baseline-btn');
            if (baselineBtn) {{
                baselineBtn.classList.toggle('active', showBaseline);
            }}

            publishMapState();
        }}

        function toggleNetwork(network) {{
            if (activeNetworks.has(network)) {{
                activeNetworks.delete(network);
            }} else {{
                activeNetworks.add(network);
            }}
            syncVisibleLayers();
        }}

        function selectFlow(flow) {{
            activeFlow = flow;
            syncVisibleLayers();
        }}

        function toggleBaseline() {{
            showBaseline = !showBaseline;
            syncVisibleLayers();
        }}

        document.addEventListener("DOMContentLoaded", function() {{
            syncVisibleLayers();
        }});
        </script>

        <div style="
            position: fixed;
            top: 15px;
            left: 15px;
            z-index: 9999;
            background: white;
            padding: 8px;
            border-radius: 4px;
            box-shadow: 0 0 5px rgba(0,0,0,0.3);
        ">
            <button class="map-btn baseline-btn" onclick="toggleBaseline()">Compare to AS IS</button>
        </div>

        <div style="
            position: fixed;
            top: 15px;
            right: 15px;
            z-index: 9999;
            background: white;
            padding: 8px;
            border-radius: 4px;
            box-shadow: 0 0 5px rgba(0,0,0,0.3);
            display: flex;
            flex-direction: column;
            gap: 8px;
        ">
            <div style="display:flex; gap:6px;">
                <button class="map-btn network-btn active" data-network="Direct" onclick="toggleNetwork('Direct')">Direct</button>
                <button class="map-btn network-btn active" data-network="Hubs" onclick="toggleNetwork('Hubs')">Hubs</button>
            </div>
            <div style="display:flex; gap:6px;">
                <button class="map-btn flow-btn radio-active" data-flow="parts" onclick="selectFlow('parts')">Parts</button>
                <button class="map-btn flow-btn" data-flow="empties" onclick="selectFlow('empties')">Empties</button>
            </div>
        </div>
        """
    m.get_root().html.add_child(folium.Element(toggle_js))

    fit_map_to_routes(m, plant, parts_routes or empties_routes)
    return m.get_root().render()