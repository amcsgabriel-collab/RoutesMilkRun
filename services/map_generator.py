import folium
import pandas as pd

from domain.data_structures import Plant
from domain.hub import Hub
from domain.operational_route import OperationalRoute
from domain.project import Scenario
from domain.shipper import Shipper
from paths import get_helper_path

# Variables & Constants
PLANT_COLOR = "#CE2900"
HUB_ORIGINAL_COLOR = "#A3990B"
HUB_NEW_COLOR = "#FFFB00"
HUB_SECOND_LEG_COLOR = "#E27115"
HUB_POINT_COLOR = "#E27115"
DIRECT_MR_ORIGINAL_COLOR = "#0033FF"
DIRECT_MR_NEW_COLOR = "#00A2FF"
DIRECT_FTL_ORIGINAL_COLOR = "#4B0090"
DIRECT_FTL_NEW_COLOR = "#FF31FF"


def create_map():
    return folium.Map(
        tiles="OpenStreetMap",
        control_scale=True
    )


def add_plant_marker(map_object, plant: Plant):
    # Plotting the Plant location
    tooltip = folium.Tooltip(
        f"""
            <b>Plant:</b> {plant.name}<br>
            <b>COFOR:</b> {plant.cofor}<br>
            {plant.formatted_coordinates}
            """, sticky=True
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


def plot_direct_points(shippers: list[Shipper], feature_group):
    for shipper in shippers:
        tooltip = folium.Tooltip(
            f"""
                <b>Shipper COFOR:</b> {shipper.cofor}<br>
                <b>Carrier:</b> {shipper.carrier.group}<br>
                <b>Weight Demand:</b> {shipper.weight:,.2f}<br>
                <b>Volume Demand:</b> {shipper.volume:,.2f}<br>
                <b>Load Meter Demand:</b> {shipper.loading_meters:,.2f}<br>
                {shipper.formatted_coordinates}
                """,
            sticky=True
        )

        color = DIRECT_MR_ORIGINAL_COLOR if shipper.original_network == 'direct' else DIRECT_MR_NEW_COLOR
        folium.CircleMarker(
            location=shipper.coordinates,
            radius=4,
            weight=0.5,
            color='black',
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            tooltip=tooltip
        ).add_to(feature_group)


def plot_hub_points(shippers: list[Shipper], feature_group):
    for shipper in shippers:
        tooltip = folium.Tooltip(
            f"""
                <b>Shipper COFOR:</b> {shipper.cofor}<br>
                <b>Carrier:</b> {shipper.carrier.group}<br>
                <b>Weight Demand:</b> {shipper.weight:,.2f}<br>
                <b>Volume Demand:</b> {shipper.volume:,.2f}<br>
                <b>Load Meter Demand:</b> {shipper.loading_meters:,.2f}<br>
                {shipper.formatted_coordinates}
                """,
            sticky=True
        )

        color = HUB_NEW_COLOR if shipper.original_network == 'direct' else HUB_ORIGINAL_COLOR
        folium.CircleMarker(
            location=shipper.coordinates,
            radius=4,
            weight=0.5,
            color='black',
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            tooltip=tooltip
        ).add_to(feature_group)


def plot_routes(routes: list[OperationalRoute], feature_group):
    for route in routes:
        coordinates = [
            shipper.coordinates
            for shipper in route.pattern.sequence
        ]

        if route.pattern.is_new_pattern:
            color = DIRECT_FTL_NEW_COLOR if route.pattern.transport_concept == "FTL" else DIRECT_MR_NEW_COLOR
        else:
            color = DIRECT_FTL_ORIGINAL_COLOR if route.pattern.transport_concept == "FTL" else DIRECT_MR_ORIGINAL_COLOR

        plant_coordinates = route.pattern.plant.coordinates
        coordinates.append(plant_coordinates)

        points = ", ".join(shipper.cofor for shipper in route.pattern.sequence)
        tooltip = folium.Tooltip(
            f"""
                <b>Route:</b> {route.pattern.route_name}<br>
                <b>Vehicle:</b> {route.vehicle.id}<br>
                <b>Frequency:</b> {route.frequency} T<br>
                <b>Utilization:</b> {route.max_utilization:.2%}<br>
                <b>Carrier:</b> {route.pattern.carrier}<br>
                <b>Points Attended:</b> {points}<br>
                """,
            sticky=True
        )

        folium.PolyLine(
            locations=coordinates,
            tooltip=tooltip,
            weight=1.5,
            opacity=0.5,
            color=color
        ).add_to(feature_group)


def plot_hubs(hubs: list[Hub], feature_group):
    for hub in hubs:
        # Adding HUB Second leg
        tooltip = folium.Tooltip(
            f"""
                <b>Linehaul Leg:</b><br>
                <b>Hub COFOR:</b> {hub.cofor}<br>
                <b>Hub Name:</b> {hub.name}<br>
                """,
            sticky=True
        )
        color = HUB_SECOND_LEG_COLOR
        folium.PolyLine(
            locations=[hub.coordinates, hub.plant.coordinates],
            tooltip=tooltip,
            weight=2,
            color=color
        ).add_to(feature_group)

        # Adding HUB First leg
        for shipper in hub.shippers:
            tooltip = folium.Tooltip(
                f"""
                    <b>First Leg:</b><br>
                    <b>Shipper COFOR:</b> {shipper.cofor}<br>
                    <b>Shipper Name:</b> {shipper.name}<br>
                    """,
                sticky=True
            )
            color = HUB_ORIGINAL_COLOR if shipper.original_network == 'hub' else HUB_NEW_COLOR
            folium.PolyLine(
                locations=[shipper.coordinates, hub.coordinates],
                tooltip=tooltip,
                weight=1.5,
                opacity=0.5,
                color=color
            ).add_to(feature_group)

        # Adding HUB Points
        tooltip = folium.Tooltip(
            f"""
                <b>Hub COFOR:</b> {hub.cofor}<br>
                <b>Hub Name:</b> {hub.name}<br>
                {hub.formatted_coordinates}
                """,
            sticky=True
        )

        color = HUB_POINT_COLOR
        folium.CircleMarker(
            location=hub.coordinates,
            radius=6,
            weight=2,
            color='black',
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            tooltip=tooltip
        ).add_to(feature_group)


def fit_map_to_routes(map_object, plant: Plant, routes: list[OperationalRoute], padding=(30, 30)):
    points = [plant.coordinates]

    for route in routes:
        for shipper in route.pattern.shippers:
            if shipper.coordinates:
                points.append(shipper.coordinates)

    if len(points) >= 2:
        map_object.fit_bounds(points, padding=padding)
    elif len(points) == 1:
        map_object.location = points[0]
        map_object.zoom_start = 10


def plot_route_map_embedded(scenario: Scenario) -> str:
    m = create_map()

    direct_fg = folium.FeatureGroup(name="Direct")
    hub_fg = folium.FeatureGroup(name="Hubs")
    direct_fg.add_to(m)
    hub_fg.add_to(m)

    direct_points = list(scenario.direct_shippers.values())
    direct_points = [p for p in direct_points if p.coordinates and all(pd.notna(c) for c in p.coordinates)]
    routes = list(scenario.get_in_use_routes())
    hub_points = list(scenario.hub_shippers.values())
    hub_points = [p for p in hub_points if p.coordinates and all(pd.notna(c) for c in p.coordinates)]
    hubs = list(scenario.get_in_use_hubs())
    plant = routes[0].pattern.plant

    plot_direct_points(direct_points, direct_fg)
    plot_routes(routes, direct_fg)
    plot_hub_points(hub_points, hub_fg)
    plot_hubs(hubs, hub_fg)
    add_plant_marker(m, plant)


    folium.LayerControl(collapsed=True).add_to(m)
    toggle_js = """
    <style>
    .leaflet-control-layers {
        display: none !important;
    }
    </style>

    <script>
    function toggleLayer(target, btn) {
        document.querySelectorAll(
            '.leaflet-control-layers-overlays input[type=checkbox]'
        ).forEach(cb => {
            const label = cb.nextSibling?.textContent?.trim();
            if (label === target) {
                cb.click();

                setTimeout(() => {
                    btn.classList.toggle('active', cb.checked);
                }, 0);
            }
        });
    }

    function syncButtons() {
    document.querySelectorAll('.map-btn').forEach(btn => {
        const target = btn.dataset.layer;

        document.querySelectorAll(
            '.leaflet-control-layers-overlays input[type=checkbox]'
        ).forEach(cb => {
            const label = cb.nextSibling?.textContent?.trim();
            if (label === target) {
                btn.classList.toggle('active', cb.checked);
            }
        });
    });
    }

    document.addEventListener("DOMContentLoaded", syncButtons);

    </script>

    <style>
    .map-btn {
        padding: 6px 10px;
        font-size: 13px;
        border-radius: 6px;
        border: 1px solid #d0d7de;
        background: #f6f8fa;
        cursor: pointer;
        }
    .map-btn.active {
        background: #b0cfff;
    }


    </style>

    <div style="
        position: fixed;
        top: 15px;
        right: 15px;
        z-index: 9999;
        background: white;
        padding: 6px;
        border-radius: 4px;
        box-shadow: 0 0 5px rgba(0,0,0,0.3);
    ">
        <button class="map-btn" data-layer="Direct" onclick="toggleLayer('Direct', this)">Direct</button>
        <button class="map-btn" data-layer="Hubs" onclick="toggleLayer('Hubs', this)">Hubs</button>
    </div>
    """
    m.get_root().html.add_child(folium.Element(toggle_js))
    fit_map_to_routes(m, plant, routes)
    return m.get_root().render()
