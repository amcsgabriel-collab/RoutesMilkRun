from __future__ import annotations

import html
from collections.abc import Iterable, Sequence
from typing import Any

import pandas as pd

from ..domain.data_structures import Plant
from ..domain.hub import Hub
from ..domain.project import Scenario
from ..domain.shipper import Shipper
from ..domain.trip import Trip

VALID_NETWORKS = {"Direct", "Hubs"}
VALID_FLOWS = {"parts", "empties"}


def _h(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _num(value: Any, fmt: str = ",.2f") -> str:
    try:
        return format(float(value or 0.0), fmt)
    except (TypeError, ValueError):
        return ""


def _safe_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _valid_coordinates(coordinates: Any) -> bool:
    return (
        coordinates is not None
        and len(coordinates) == 2
        and all(pd.notna(c) for c in coordinates)
    )


def _coords(coordinates: Any) -> list[float] | None:
    if not _valid_coordinates(coordinates):
        return None
    return [float(coordinates[0]), float(coordinates[1])]


def _slug(value: Any) -> str:
    text = str(value)
    for ch in (":", "|", "/", "\\", " "):
        text = text.replace(ch, "_")
    return text


def _feature_id(*parts: Any) -> str:
    return ":".join(_slug(part) for part in parts if part is not None)


def _scope(baseline: bool) -> str:
    return "baseline" if baseline else "current"


def _flow_title(flow: str) -> str:
    return "Parts" if flow == "parts" else "Empties"


def _layer_name(network: str, flow: str, baseline: bool = False, last_leg: bool = False) -> str:
    prefix = "AS IS " if baseline else ""
    name = f"{prefix}{network[:-1] if network == 'Hubs' else network} {_flow_title(flow)}"
    if last_leg:
        name += " Last Leg"
    return name


def _normalise_ui_state(ui_state: dict | None = None) -> dict:
    ui_state = ui_state or {}
    flow = ui_state.get("flow", "parts")
    if flow not in VALID_FLOWS:
        flow = "parts"

    active_networks = set(ui_state.get("active_networks", ["Direct", "Hubs"]))
    active_networks = {network for network in active_networks if network in VALID_NETWORKS}
    if not active_networks:
        active_networks = {"Direct", "Hubs"}

    return {
        "flow": flow,
        "show_baseline": bool(ui_state.get("show_baseline", False)),
        "show_last_leg": bool(ui_state.get("show_last_leg", False)),
        "active_networks": sorted(active_networks),
    }


def _route_key(route: Any) -> tuple[str, tuple[str, ...]]:
    return (
        route.demand.flow_direction,
        tuple(shipper.cofor for shipper in route.demand.pattern.sequence),
    )


def _route_identity(route: Any) -> str:
    value = getattr(route, "id", None) or getattr(route, "route_id", None)
    if value is not None:
        return str(value)

    shipper = getattr(route, "shipper", None)
    if shipper is not None:
        return f"first_leg__{shipper.cofor}"

    pattern = getattr(getattr(route, "demand", None), "pattern", None)
    sequence = getattr(pattern, "sequence", [])

    sequence_key = "__".join(str(shipper.cofor) for shipper in sequence)
    flow = getattr(getattr(route, "demand", None), "flow_direction", "unknown")

    return f"{flow}__{sequence_key}"


def _route_cost(route: Any) -> float | None:
    for attr in ("cost", "total_cost"):
        value = getattr(route, attr, None)
        if value is not None:
            return _safe_float(value)

    costing = getattr(route, "costing", None)
    if costing is not None:
        for attr in ("cost", "total_cost"):
            value = getattr(costing, attr, None)
            if value is not None:
                return _safe_float(value)

    return None


def _get_shipper_demand(shipper: Shipper, flow: str):
    return shipper.parts_demand if flow == "parts" else shipper.empties_demand


def _has_flow_demand(shipper: Shipper, flow: str) -> bool:
    demand = _get_shipper_demand(shipper, flow)
    return (
        demand is not None
        and (
            float(getattr(demand, "weight", 0.0) or 0.0) > 0.0
            or float(getattr(demand, "volume", 0.0) or 0.0) > 0.0
            or float(getattr(demand, "loading_meters", 0.0) or 0.0) > 0.0
        )
    )


def _get_hub_shippers_from_hubs(hubs: list[Hub], flow: str) -> list[Shipper]:
    shippers_by_cofor: dict[str, Shipper] = {}

    for hub in hubs:
        if flow == "empties" and not getattr(hub, "has_empties_flow", False):
            continue

        for shipper in getattr(hub, "shippers", []):
            if not _valid_coordinates(getattr(shipper, "coordinates", None)):
                continue
            if not _has_flow_demand(shipper, flow):
                continue
            shippers_by_cofor[shipper.cofor] = shipper

    return list(shippers_by_cofor.values())


def _get_trip_routes_by_flow(trips: list[Trip], flow: str):
    if flow == "parts":
        return [
            trip.parts_route
            for trip in trips
            if trip.parts_route is not None and trip.parts_route.has_demand
        ]

    return [
        trip.empties_route
        for trip in trips
        if trip.empties_route is not None and trip.empties_route.has_demand
    ]


def _get_hub_route_keys(hubs: list[Hub], flow: str) -> tuple[set[tuple], set[tuple]]:
    linehaul_keys = set()
    first_leg_keys = set()

    for hub in hubs:
        if flow == "empties" and not getattr(hub, "has_empties_flow", False):
            continue

        linehaul_route = (
            hub.parts_linehaul_route
            if flow == "parts"
            else getattr(hub, "empties_linehaul_route", None)
        )
        first_leg_routes = (
            hub.parts_first_leg_routes
            if flow == "parts"
            else getattr(hub, "empties_first_leg_routes", [])
        )

        if linehaul_route is not None:
            linehaul_keys.add((flow, hub.cofor))

        for route in first_leg_routes:
            first_leg_keys.add((flow, hub.cofor, route.shipper.cofor))

    return linehaul_keys, first_leg_keys


def _get_plant(
    parts_routes: Sequence | None = None,
    empties_routes: Sequence | None = None,
    hubs: Sequence[Hub] | None = None,
) -> Plant:

    parts_routes = parts_routes or []
    empties_routes = empties_routes or []
    hubs = hubs or []

    if parts_routes:
        return parts_routes[0].demand.pattern.plant
    if empties_routes:
        return empties_routes[0].demand.pattern.plant
    if hubs:
        return hubs[0].plant

    raise ValueError("Could not infer plant for scenario map payload.")


def _bounds_for_routes(plant: Plant, routes: Sequence) -> list[list[float]]:
    points: list[list[float]] = []
    plant_coordinates = _coords(getattr(plant, "coordinates", None))
    if plant_coordinates is not None:
        points.append(plant_coordinates)

    for route in routes:
        for shipper in getattr(route.demand.pattern, "shippers", []):
            coordinates = _coords(getattr(shipper, "coordinates", None))
            if coordinates is not None:
                points.append(coordinates)

    return points


def _feature(
    *,
    feature_id: str,
    kind: str,
    subtype: str,
    geometry: dict,
    layer_name: str,
    network: str | None,
    flow: str | None,
    baseline: bool = False,
    last_leg: bool = False,
    tooltip_html: str | None = None,
    payload: dict | None = None,
    linked_feature_ids: list[str] | None = None,
    interactive: bool = True,
    sort_order: int = 100,
) -> dict:
    result = {
        "id": feature_id,
        "kind": kind,
        "subtype": subtype,
        "geometry": geometry,
        "layerName": layer_name,
        "network": network,
        "flow": flow,
        "baseline": baseline,
        "lastLeg": last_leg,
        "tooltipHtml": tooltip_html,
        "payload": payload or {},
        "linkedFeatureIds": linked_feature_ids or [],
        "interactive": interactive,
        "sortOrder": sort_order,
    }
    return {key: value for key, value in result.items() if value is not None}


def _route_payload(route: Any) -> dict:
    sequence = route.demand.pattern.sequence
    sequence_cofors = [shipper.cofor for shipper in sequence]

    vehicle = getattr(getattr(route, "vehicle", None), "id", None)

    return {
        "type": "route",
        "subtype": "direct",
        "name": route.demand.pattern.route_name,
        "key": "|".join(sequence_cofors),
        "route_key": sequence_cofors,
        "flow": route.demand.flow_direction,
        "flow_direction": route.demand.flow_direction,
        "is_locked": bool(getattr(route, "is_locked", False)),
        "is_blocked": bool(getattr(route, "is_blocked", False)),
        "is_new_pattern": bool(route.demand.pattern.is_new_pattern),
        "shippers": [{"cofor": shipper.cofor} for shipper in sequence],
        "vehicle": vehicle,
        "frequency": getattr(route, "frequency", None),
        "utilization": _safe_float(getattr(route, "max_utilization", None)),
        "cost": _route_cost(route),
        "actions": ["lock-route", "block-route", "edit-route"],
    }


def _hub_linehaul_payload(hub: Hub, route: Any, flow: str) -> dict:
    return {
        "type": "route",
        "subtype": "hub-linehaul",
        "name": f"{hub.cofor} Linehaul {flow}",
        "flow": flow,
        "hub": {"cofor": hub.cofor, "name": hub.name},
        "shippers": [],
        "vehicle": getattr(getattr(route, "vehicle", None), "id", None),
        "frequency": getattr(route, "frequency", None),
        "utilization": _safe_float(getattr(route, "max_utilization", None)),
        "cost": _route_cost(route),
        "actions": ["lock-route", "block-route", "edit-route"],
    }


def _hub_first_leg_payload(hub: Hub, route: Any, flow: str) -> dict:
    shipper = route.shipper
    return {
        "type": "route",
        "subtype": "hub-first-leg",
        "name": f"{shipper.cofor} -> {hub.cofor} {flow}",
        "flow": flow,
        "hub": {"cofor": hub.cofor, "name": hub.name},
        "shippers": [{"cofor": shipper.cofor, "name": shipper.name}],
        "is_new": shipper.original_network == "direct",
        "vehicle": getattr(getattr(route, "vehicle", None), "id", None),
        "frequency": getattr(route, "frequency", None),
        "utilization": _safe_float(getattr(route, "max_utilization", None)),
        "cost": _route_cost(route),
        "actions": ["lock-route", "block-route", "edit-route"],
    }


def _shipper_payload(
    shipper: Shipper,
    flow: str,
    current_route: str | None = None,
    is_new: bool = False,
    route_id: str | None = None,
    route_key: list[str] | None = None,
    route_name: str | None = None,
    route_subtype: str | None = None,
    hub_cofor: str | None = None,
    hub_name: str | None = None,
    baseline: bool = False,
) -> dict:
    carrier = getattr(getattr(shipper, "carrier", None), "group", None)

    payload = {
        "type": "shipper",
        "cofor": shipper.cofor,
        "name": shipper.name,
        "carrier": carrier,
        "flow": flow,
        "currentRoute": current_route,
        "actions": ["swap-network", "edit-shipper"],
        "is_new": bool(is_new),
        "baseline": bool(baseline),
    }

    if route_id or route_key or route_name or route_subtype:
        payload["route"] = {
            "id": route_id,
            "key": route_key,
            "name": route_name,
            "subtype": route_subtype,
        }

    if hub_cofor or hub_name:
        payload["hub"] = {
            "cofor": hub_cofor,
            "name": hub_name,
        }

    return payload

def _hub_payload(hub: Hub, flow: str) -> dict:
    return {
        "type": "hub",
        "cofor": hub.cofor,
        "name": hub.name,
        "flow": flow,
        "actions": ["edit-hub"],
    }


def _plant_payload(plant: Plant) -> dict:
    return {
        "type": "plant",
        "cofor": plant.cofor,
        "name": plant.name,
        "actions": [],
    }


def _plant_feature(plant: Plant) -> dict:
    coordinates = _coords(getattr(plant, "coordinates", None))
    if coordinates is None:
        raise ValueError(f"Plant {plant.cofor} has invalid coordinates.")

    tooltip = f"""
        <b>Plant:</b> {_h(plant.name)}<br>
        <b>COFOR:</b> {_h(plant.cofor)}<br>
        {_h(getattr(plant, 'formatted_coordinates', ''))}
    """
    return _feature(
        feature_id=_feature_id("plant", plant.cofor),
        kind="plant",
        subtype="plant",
        geometry={"type": "Point", "coordinates": coordinates},
        layer_name="Plant",
        network=None,
        flow=None,
        tooltip_html=tooltip,
        payload=_plant_payload(plant),
        interactive=True,
        sort_order=900,
    )


def _direct_route_base_id(route: Any, baseline: bool = False) -> str:
    return _feature_id(
        "direct-route",
        _scope(baseline),
        route.demand.flow_direction,
        _route_identity(route),
    )


def _direct_stop_id(route: Any, shipper: Shipper, index: int, baseline: bool = False) -> str:
    return _feature_id(_direct_route_base_id(route, baseline), "stop", index + 1, shipper.cofor)


def _direct_line_id(route: Any, baseline: bool = False) -> str:
    return _feature_id(_direct_route_base_id(route, baseline), "line")


def _direct_last_leg_id(route: Any, baseline: bool = False) -> str:
    return _feature_id(_direct_route_base_id(route, baseline), "last-leg")


def _direct_status_id(route: Any, baseline: bool = False) -> str:
    return _feature_id(_direct_route_base_id(route, baseline), "status")


def direct_route_feature_ids(route: Any, baseline: bool = False) -> list[str]:
    ids = [
        _direct_line_id(route, baseline),
        _direct_last_leg_id(route, baseline),
        _direct_status_id(route, baseline),
    ]
    sequence = getattr(route.demand.pattern, "sequence", [])
    ids.extend(_direct_stop_id(route, shipper, index, baseline) for index, shipper in enumerate(sequence))
    return ids


def _route_tooltip_html(route: Any, sequence: Sequence[Shipper]) -> str:
    points = ", ".join(shipper.cofor for shipper in sequence)
    return f"""
        <b>Route:</b> {_h(route.demand.pattern.route_name)}<br>
        <b>Vehicle:</b> {_h(getattr(getattr(route, 'vehicle', None), 'id', None))}<br>
        <b>Frequency:</b> {_h(getattr(route, 'frequency', None))} T<br>
        <b>Utilization:</b> {_num(getattr(route, 'max_utilization', None), '.2f')}%<br>
        <b>Flow:</b> {_h(route.demand.flow_direction[0].upper())}<br>
        <b>Points Attended:</b> {_h(points)}<br>
        <b>Route Weight:</b> {_num(getattr(route, 'weight', None), ',.0f')}kg<br>
        <b>Route Volume:</b> {_num(getattr(route, 'volume', None), ',.1f')}m&sup3;<br>
        <b>Route Loading Meters:</b> {_num(getattr(route, 'loading_meters', None), ',.2f')}m<br>
    """


def _direct_stop_tooltip_html(
    route: Any,
    shipper: Shipper,
    index: int,
    sequence_len: int,
    route_tooltip_html: str,
) -> str:
    is_first = index == 0
    demand = _get_shipper_demand(shipper, route.demand.flow_direction)
    tooltip = f"""
        <b>{'First Shipper' if is_first else 'Shipper'}:</b> {_h(shipper.name)}<br>
        <b>COFOR:</b> {_h(shipper.cofor)}<br>
        <b>Stop:</b> {index + 1}/{sequence_len}<br>
        <b>Carrier:</b> {_h(getattr(getattr(shipper, 'carrier', None), 'group', None))}<br>
        {_h(getattr(shipper, 'formatted_coordinates', ''))}<br>
        <b>ZIP:</b> {_h(getattr(shipper, 'zip_code', ''))}<br>
        <b>Weight:</b> {_num(getattr(demand, 'weight', None), ',.0f')}kg<br>
        <b>Volume:</b> {_num(getattr(demand, 'volume', None), ',.1f')}m&sup3;<br>
        <b>Loading Meters:</b> {_num(getattr(demand, 'loading_meters', None), ',.2f')}m<br>
    """
    if is_first:
        tooltip += route_tooltip_html
    return tooltip


def _direct_route_features(route: Any, baseline: bool = False, include_last_leg: bool = True) -> list[dict]:
    flow = route.demand.flow_direction
    layer_name = _layer_name("Direct", flow, baseline=baseline)
    last_leg_layer_name = _layer_name("Direct", flow, baseline=baseline, last_leg=True)

    sequence = [
        shipper
        for shipper in route.demand.pattern.sequence
        if _valid_coordinates(getattr(shipper, "coordinates", None))
    ]
    if not sequence:
        return []

    features: list[dict] = []
    route_tooltip = _route_tooltip_html(route, sequence)

    for index, shipper in enumerate(sequence):
        features.append(
            _feature(
                feature_id=_direct_stop_id(route, shipper, index, baseline),
                kind="shipper",
                subtype="direct-stop",
                geometry={"type": "Point", "coordinates": _coords(shipper.coordinates)},
                layer_name=layer_name,
                network="Direct",
                flow=flow,
                baseline=baseline,
                tooltip_html=_direct_stop_tooltip_html(route, shipper, index, len(sequence), route_tooltip),
                payload=_shipper_payload(
                    shipper,
                    flow,
                    current_route=route.demand.pattern.route_name,
                    is_new=(
                            bool(route.demand.pattern.is_new_pattern)
                            or getattr(shipper, "original_network", None) == "hub"
                    ),
                    route_id=_route_identity(route),
                    route_key=[s.cofor for s in route.demand.pattern.sequence],
                    route_name=route.demand.pattern.route_name,
                    route_subtype="direct",
                    baseline=baseline,
                ),
                sort_order=500,
            )
        )

    route_payload = _route_payload(route)

    plant = getattr(route.demand.pattern, "plant", None)
    plant_coordinates = _coords(getattr(plant, "coordinates", None)) if plant is not None else None
    last_leg_id = _direct_last_leg_id(route, baseline)
    line_id = _direct_line_id(route, baseline)
    has_last_leg = include_last_leg and plant_coordinates is not None
    has_line = len(sequence) > 1

    if has_last_leg:
        features.append(
            _feature(
                feature_id=last_leg_id,
                kind="route",
                subtype="direct-last-leg",
                geometry={
                    "type": "LineString",
                    "coordinates": [_coords(sequence[-1].coordinates), plant_coordinates],
                },
                layer_name=last_leg_layer_name,
                network="Direct",
                flow=flow,
                baseline=baseline,
                last_leg=True,
                tooltip_html=route_tooltip,
                payload=route_payload,
                linked_feature_ids=[line_id] if has_line else [],
                sort_order=100,
            )
        )

    if has_line:
        features.append(
            _feature(
                feature_id=line_id,
                kind="route",
                subtype="direct",
                geometry={"type": "LineString", "coordinates": [_coords(shipper.coordinates) for shipper in sequence]},
                layer_name=layer_name,
                network="Direct",
                flow=flow,
                baseline=baseline,
                tooltip_html=route_tooltip,
                payload=route_payload,
                linked_feature_ids=[last_leg_id] if has_last_leg else [],
                sort_order=100,
            )
        )

    status_feature = _direct_status_feature(route, sequence, baseline=baseline)
    if status_feature is not None:
        features.append(status_feature)


    return features


def _hub_shipper_feature(
    shipper: Shipper,
    flow: str,
    hub: Hub | None = None,
    route: Any | None = None,
    baseline: bool = False,
) -> dict | None:
    demand = _get_shipper_demand(shipper, flow)
    if demand is None or not _has_flow_demand(shipper, flow):
        return None

    coordinates = _coords(getattr(shipper, "coordinates", None))
    if coordinates is None:
        return None

    tooltip = f"""
        <b>Name:</b> {_h(shipper.name)}<br>
        <b>COFOR:</b> {_h(shipper.cofor)}<br>
        <b>Carrier:</b> {_h(getattr(getattr(shipper, 'carrier', None), 'group', None))}<br>
        <b>Flow:</b> {_h(flow[0].upper())}<br>
        <b>Hub:</b> {_h(getattr(hub, 'cofor', ''))}<br>
        <b>Weight Demand:</b> {_num(getattr(demand, 'weight', None), ',.0f')}kg<br>
        <b>Volume Demand:</b> {_num(getattr(demand, 'volume', None), ',.1f')}m&sup3;<br>
        <b>Load Meter Demand:</b> {_num(getattr(demand, 'loading_meters', None), ',.2f')}m<br>
        {_h(getattr(shipper, 'formatted_coordinates', ''))}
    """

    return _feature(
        feature_id=_feature_id("hub-shipper", _scope(baseline), flow, shipper.cofor),
        kind="shipper",
        subtype="hub-point",
        geometry={"type": "Point", "coordinates": coordinates},
        layer_name=_layer_name("Hubs", flow, baseline=baseline),
        network="Hubs",
        flow=flow,
        baseline=baseline,
        tooltip_html=tooltip,
        payload=_shipper_payload(
            shipper,
            flow,
            current_route="Hub network",
            is_new=(
                    not baseline
                    and (
                            getattr(shipper, "original_network", None) == "direct"
                            or bool(getattr(route, "is_new_pattern", False))
                    )
            ),
            route_id=_route_identity(route) if route is not None else None,
            route_key=[shipper.cofor],
            route_name=f"{shipper.cofor} -> {hub.cofor} {flow}" if hub is not None else "Hub network",
            route_subtype="hub-first-leg",
            hub_cofor=getattr(hub, "cofor", None),
            hub_name=getattr(hub, "name", None),
            baseline=baseline,
        ),
        sort_order=500,
    )

def _hub_shipper_features_from_hub(
    hub: Hub,
    flow: str,
    baseline: bool = False,
    skip_first_leg_keys: set | None = None,
) -> list[dict]:
    skip_first_leg_keys = skip_first_leg_keys or set()

    if flow == "empties" and not getattr(hub, "has_empties_flow", False):
        return []

    routes = (
        hub.parts_first_leg_routes
        if flow == "parts"
        else getattr(hub, "empties_first_leg_routes", [])
    )

    features: list[dict] = []

    for route in routes:
        first_leg_key = (flow, hub.cofor, route.shipper.cofor)

        if first_leg_key in skip_first_leg_keys:
            continue

        feature = _hub_shipper_feature(
            route.shipper,
            flow,
            hub=hub,
            route=route,
            baseline=baseline,
        )

        if feature is not None:
            features.append(feature)

    return features


def hub_shipper_feature_id(shipper: Shipper, flow: str) -> str:
    return _feature_id("hub-shipper", _scope(False), flow, shipper.cofor)


def _hub_linehaul_id(hub: Hub, flow: str, baseline: bool = False) -> str:
    return _feature_id("hub-linehaul", _scope(baseline), flow, hub.cofor)


def _hub_first_leg_id(hub: Hub, route: Any, flow: str, baseline: bool = False) -> str:
    return _feature_id("hub-first-leg", _scope(baseline), flow, hub.cofor, route.shipper.cofor)


def _hub_marker_id(hub: Hub, flow: str, baseline: bool = False) -> str:
    return _feature_id("hub-marker", _scope(baseline), flow, hub.cofor)


def hub_feature_ids(hub: Hub, flow: str, baseline: bool = False) -> list[str]:
    ids = [_hub_linehaul_id(hub, flow, baseline), _hub_marker_id(hub, flow, baseline)]
    first_leg_routes = hub.parts_first_leg_routes if flow == "parts" else getattr(hub, "empties_first_leg_routes", [])
    ids.extend(_hub_first_leg_id(hub, route, flow, baseline) for route in first_leg_routes)
    return ids


def _linehaul_tooltip_html(hub: Hub, linehaul_route: Any, flow: str) -> str:
    return f"""
        <b>Linehaul Leg:</b><br>
        <b>Hub COFOR:</b> {_h(hub.cofor)}<br>
        <b>Hub Name:</b> {_h(hub.name)}<br>
        <b>Flow:</b> {_h(flow)}<br>
        <b>Carrier:</b> {_h(getattr(getattr(linehaul_route, 'linehaul_carrier', None), 'group', None))}<br>
        <b>Frequency:</b> {_h(getattr(linehaul_route, 'frequency', None))} T<br>
        <b>Utilization:</b> {_num(getattr(linehaul_route, 'max_utilization', None), '.2f')}%<br>
        <b>Weight:</b> {_num(getattr(linehaul_route, 'weight', None), '.2f')}<br>
        <b>Volume:</b> {_num(getattr(linehaul_route, 'volume', None), '.2f')}<br>
        <b>Loading Meters:</b> {_num(getattr(linehaul_route, 'loading_meters', None), '.2f')}<br>
    """


def _chargeable_weight(route: Any) -> str:
    try:
        return _num(route.costing.chargeable_weight(route), ".2f")
    except Exception:
        return ""


def _first_leg_tooltip_html(route: Any, flow: str) -> str:
    return f"""
        <b>First Leg:</b><br>
        <b>Shipper COFOR:</b> {_h(route.shipper.cofor)}<br>
        <b>Shipper Name:</b> {_h(route.shipper.name)}<br>
        <b>Flow:</b> {_h(flow[0].upper())}<br>
        <b>Carrier:</b> {_h(getattr(getattr(route.demand, 'carrier', None), 'group', None))}<br>
        <b>Frequency:</b> {_h(getattr(route, 'frequency', None))} T<br>
        <b>Weight:</b> {_num(getattr(route, 'weight', None), '.2f')}<br>
        <b>Volume:</b> {_num(getattr(route, 'volume', None), '.2f')}<br>
        <b>Chargeable Weight:</b> {_chargeable_weight(route)}<br>
    """


def _hub_marker_tooltip_html(hub: Hub) -> str:
    return f"""
        <b>Hub COFOR:</b> {_h(hub.cofor)}<br>
        <b>Hub Name:</b> {_h(hub.name)}<br>
        {_h(getattr(hub, 'formatted_coordinates', ''))}
    """

def _unassigned_shipper_feature(
    shipper: Shipper,
    flow: str,
    baseline: bool = False,
) -> dict | None:
    coordinates = _coords(getattr(shipper, "coordinates", None))
    if coordinates is None:
        return None

    demand = _get_shipper_demand(shipper, flow)

    tooltip = f"""
        <b>Unassigned Shipper:</b> {_h(shipper.name)}<br>
        <b>COFOR:</b> {_h(shipper.cofor)}<br>
        <b>Carrier:</b> {_h(getattr(getattr(shipper, 'carrier', None), 'group', None))}<br>
        <b>Flow:</b> {_h(flow[0].upper())}<br>
        <b>Weight:</b> {_num(getattr(demand, 'weight', None), ',.0f')}kg<br>
        <b>Volume:</b> {_num(getattr(demand, 'volume', None), ',.1f')}m&sup3;<br>
        <b>Loading Meters:</b> {_num(getattr(demand, 'loading_meters', None), ',.2f')}m<br>
        {_h(getattr(shipper, 'formatted_coordinates', ''))}
    """

    return _feature(
        feature_id=_feature_id("unassigned-shipper", _scope(baseline), flow, shipper.cofor),
        kind="shipper",
        subtype="unassigned-shipper",
        geometry={"type": "Point", "coordinates": coordinates},
        layer_name=f"{'AS IS ' if baseline else ''}Unassigned {_flow_title(flow)}",
        network=None,
        flow=flow,
        baseline=baseline,
        tooltip_html=tooltip,
        payload=_shipper_payload(
            shipper,
            flow,
            current_route=None,
            is_new=False,
            route_subtype="unassigned",
            baseline=baseline,
        ),
        sort_order=700,
    )

def _assigned_shipper_cofors(features: list[dict], flow: str, baseline: bool = False) -> set[str]:
    return {
        feature.get("payload", {}).get("cofor")
        for feature in features
        if feature.get("kind") == "shipper"
        and feature.get("flow") == flow
        and feature.get("baseline") == baseline
        and feature.get("subtype") != "unassigned-shipper"
        and feature.get("payload", {}).get("cofor")
    }


def _hub_features(
    hub: Hub,
    flow: str,
    baseline: bool = False,
    skip_linehaul_keys: set | None = None,
    skip_first_leg_keys: set | None = None,
) -> list[dict]:
    skip_linehaul_keys = skip_linehaul_keys or set()
    skip_first_leg_keys = skip_first_leg_keys or set()

    if flow == "empties" and not getattr(hub, "has_empties_flow", False):
        return []

    linehaul_route = hub.parts_linehaul_route if flow == "parts" else getattr(hub, "empties_linehaul_route", None)
    first_leg_routes = hub.parts_first_leg_routes if flow == "parts" else getattr(hub, "empties_first_leg_routes", [])
    if linehaul_route is None:
        return []

    features: list[dict] = []
    layer_name = _layer_name("Hubs", flow, baseline=baseline)
    linehaul_key = (flow, hub.cofor)

    hub_coordinates = _coords(getattr(hub, "coordinates", None))
    plant_coordinates = _coords(getattr(getattr(hub, "plant", None), "coordinates", None))
    if hub_coordinates is None:
        return []

    if linehaul_key not in skip_linehaul_keys and plant_coordinates is not None:
        features.append(
            _feature(
                feature_id=_hub_linehaul_id(hub, flow, baseline),
                kind="route",
                subtype="hub-linehaul",
                geometry={"type": "LineString", "coordinates": [hub_coordinates, plant_coordinates]},
                layer_name=layer_name,
                network="Hubs",
                flow=flow,
                baseline=baseline,
                tooltip_html=_linehaul_tooltip_html(hub, linehaul_route, flow),
                payload=_hub_linehaul_payload(hub, linehaul_route, flow),
                sort_order=100,
            )
        )

    plotted_first_leg = False
    for route in first_leg_routes:
        first_leg_key = (flow, hub.cofor, route.shipper.cofor)
        if first_leg_key in skip_first_leg_keys:
            continue

        shipper_coordinates = _coords(getattr(route.shipper, "coordinates", None))
        if shipper_coordinates is None:
            continue

        features.append(
            _feature(
                feature_id=_hub_first_leg_id(hub, route, flow, baseline),
                kind="route",
                subtype="hub-first-leg",
                geometry={"type": "LineString", "coordinates": [shipper_coordinates, hub_coordinates]},
                layer_name=layer_name,
                network="Hubs",
                flow=flow,
                baseline=baseline,
                tooltip_html=_first_leg_tooltip_html(route, flow),
                payload=_hub_first_leg_payload(
                    hub, route, flow),
                sort_order=100,
            )
        )
        plotted_first_leg = True

    if linehaul_key in skip_linehaul_keys and not plotted_first_leg:
        return features

    features.append(
        _feature(
            feature_id=_hub_marker_id(hub, flow, baseline),
            kind="hub",
            subtype="hub",
            geometry={"type": "Point", "coordinates": hub_coordinates},
            layer_name=layer_name,
            network="Hubs",
            flow=flow,
            baseline=baseline,
            tooltip_html=_hub_marker_tooltip_html(hub),
            payload=_hub_payload(hub, flow),
            sort_order=500,
        )
    )

    return features

def _direct_status_feature(route: Any, sequence: Sequence[Shipper], baseline: bool = False) -> dict | None:
    is_locked = bool(getattr(route, "is_locked", False))
    is_blocked = bool(getattr(route, "is_blocked", False))

    if not is_locked and not is_blocked:
        return None

    first_shipper = sequence[0]
    coordinates = _coords(getattr(first_shipper, "coordinates", None))
    if coordinates is None:
        return None

    flow = route.demand.flow_direction
    status = "blocked" if is_blocked else "locked"

    feature = _feature(
        feature_id=_direct_status_id(route, baseline),
        kind="route-status",
        subtype="route-status",
        geometry={"type": "Point", "coordinates": coordinates},
        layer_name=_layer_name("Direct", flow, baseline=baseline),
        network="Direct",
        flow=flow,
        baseline=baseline,
        tooltip_html=f"""
            <b>Route:</b> {_h(route.demand.pattern.route_name)}<br>
            <b>Status:</b> {_h(status.title())}
        """,
        payload={
            **_route_payload(route),
            "status": status,
        },
        interactive=True,
        sort_order=80,
    )

    feature.update({
        "markerType": "divIcon",
        "iconHtml": _route_status_svg(status),
        "iconClassName": "scenario-map-div-icon scenario-map-route-status",
        "iconSize": [24, 24],
        "iconAnchor": [12, -6],
    })

    return feature

def _route_status_svg(status: str) -> str:
    color = "#334155"

    if status == "blocked":
        return f"""
        <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
          <circle
            cx="12"
            cy="12"
            r="7.5"
            fill="rgba(255,255,255,0.92)"
            stroke="{color}"
            stroke-width="2"
          />
          <line
            x1="7.8"
            y1="16.2"
            x2="16.2"
            y2="7.8"
            stroke="{color}"
            stroke-width="2"
            stroke-linecap="round"
          />
        </svg>
        """

    return f"""
    <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
      <rect
        x="7"
        y="11"
        width="10"
        height="8"
        rx="1.8"
        fill="rgba(255,255,255,0.92)"
        stroke="{color}"
        stroke-width="2"
      />
      <path
        d="M9 11V8.5a3 3 0 0 1 6 0V11"
        fill="none"
        stroke="{color}"
        stroke-width="2"
        stroke-linecap="round"
      />
    </svg>
    """


def _base_payload_from_plant(plant: Plant, ui_state: dict | None = None) -> dict:
    ui_state = _normalise_ui_state(ui_state)
    plant_feature = _plant_feature(plant)
    coordinates = plant_feature["geometry"]["coordinates"]
    return {
        "version": 1,
        "type": "scenario-map-base",
        "uiState": ui_state,
        "map": {
            "tiles": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            "tileOptions": {
                "maxZoom": 19,
                "attribution": "&copy; OpenStreetMap contributors",
            },
            "zoomControl": False,
            "controlScale": True,
        },
        "plant": plant_feature,
        "bounds": [coordinates],
    }


def build_scenario_map_base_payload(scenario: Scenario, ui_state: dict | None = None) -> dict:
    trips = list(scenario.get_in_use_trips())
    parts_routes = _get_trip_routes_by_flow(trips, "parts")
    empties_routes = _get_trip_routes_by_flow(trips, "empties")
    hubs = list(scenario.get_in_use_hubs())
    plant = _get_plant(parts_routes, empties_routes, hubs)
    return _base_payload_from_plant(plant, ui_state)


def build_scenario_map_full_payload(
    scenario: Scenario,
    baseline_scenario: Scenario | None = None,
    ui_state: dict | None = None,
) -> dict:
    ui_state = _normalise_ui_state(ui_state)

    trips = list(scenario.get_in_use_trips())
    parts_routes = _get_trip_routes_by_flow(trips, "parts")
    empties_routes = _get_trip_routes_by_flow(trips, "empties")
    hubs = list(scenario.get_in_use_hubs())
    plant = _get_plant(parts_routes, empties_routes, hubs)

    features: list[dict] = []

    for route in parts_routes:
        features.extend(_direct_route_features(route, baseline=False))
    for route in empties_routes:
        features.extend(_direct_route_features(route, baseline=False))

    for hub in hubs:
        features.extend(_hub_shipper_features_from_hub(hub, "parts", baseline=False))
    for hub in hubs:
        features.extend(_hub_features(hub, "parts", baseline=False))

    for hub in hubs:
        features.extend(_hub_shipper_features_from_hub(hub, "empties", baseline=False))
    for hub in hubs:
        features.extend(_hub_features(hub, "empties", baseline=False))

    current_shippers = {s for s in scenario.shippers.values()}

    for flow in ("parts", "empties"):
        assigned = _assigned_shipper_cofors(features, flow, baseline=False)

        for shipper in current_shippers:
            if shipper.cofor in assigned:
                continue

            feature = _unassigned_shipper_feature(shipper, flow, baseline=False)
            if feature is not None:
                features.append(feature)


    if baseline_scenario is not None:
        baseline_trips = list(baseline_scenario.get_in_use_trips())
        baseline_parts_routes = _get_trip_routes_by_flow(baseline_trips, "parts")
        baseline_empties_routes = _get_trip_routes_by_flow(baseline_trips, "empties")

        current_route_keys = {_route_key(route) for route in parts_routes + empties_routes}
        baseline_parts_routes = [route for route in baseline_parts_routes if _route_key(route) not in current_route_keys]
        baseline_empties_routes = [route for route in baseline_empties_routes if _route_key(route) not in current_route_keys]

        for route in baseline_parts_routes:
            features.extend(_direct_route_features(route, baseline=True))
        for route in baseline_empties_routes:
            features.extend(_direct_route_features(route, baseline=True))


        baseline_hubs = list(baseline_scenario.get_in_use_hubs())
        current_parts_linehaul_keys, current_parts_first_leg_keys = _get_hub_route_keys(hubs, "parts")
        current_empties_linehaul_keys, current_empties_first_leg_keys = _get_hub_route_keys(hubs, "empties")

        for hub in baseline_hubs:
            features.extend(_hub_shipper_features_from_hub(hub, "parts", baseline=True))
        for hub in baseline_hubs:
            features.extend(
                _hub_shipper_features_from_hub(
                    hub,
                    "parts",
                    baseline=True,
                    skip_first_leg_keys=current_parts_first_leg_keys,
                )
            )

        for hub in baseline_hubs:
            features.extend(_hub_shipper_features_from_hub(hub, "empties", baseline=True))
        for hub in baseline_hubs:
            features.extend(
                _hub_shipper_features_from_hub(
                    hub,
                    "empties",
                    baseline=True,
                    skip_first_leg_keys=current_empties_first_leg_keys,
                )
            )

        baseline_shippers = {s for s in baseline_scenario.shippers.values()}

        for flow in ("parts", "empties"):
            assigned = _assigned_shipper_cofors(features, flow, baseline=True)

            for shipper in baseline_shippers:
                if shipper.cofor in assigned:
                    continue

                feature = _unassigned_shipper_feature(shipper, flow, baseline=True)
                if feature is not None:
                    features.append(feature)

    bounds = _bounds_for_routes(plant, parts_routes or empties_routes)
    return {
        "version": 1,
        "type": "scenario-map-full",
        "uiState": ui_state,
        "base": _base_payload_from_plant(plant, ui_state),
        "features": features,
        "bounds": bounds,
    }


def make_patch(*ops: dict) -> dict:
    return {"version": 1, "ops": [op for op in ops if op]}

def build_scenario_map_patch_from_changes(project, map_changes: dict) -> dict:
    scenario = project.current_scenario
    baseline_scenario = project.current_region.scenarios['AS-IS']

    builder = ScenarioMapPatchBuilder(scenario, baseline_scenario)

    return combine_patches(
        *[
            builder.remove_direct_route(route)
            for route in map_changes.get("removed_direct_routes", [])
        ],
        *[
            builder.upsert_direct_route(route)
            for route in map_changes.get("upserted_direct_routes", [])
        ],
        *[
            builder.upsert_hub(hub, "parts")
            for hub in map_changes.get("upserted_hubs", [])
        ],
        *[
            builder.upsert_hub(hub, "empties")
            for hub in map_changes.get("upserted_hubs", [])
        ],
        *[
            builder.upsert_hub_shipper(shipper, "parts")
            for shipper in map_changes.get("upserted_hub_shippers", [])
        ],
        *[
            builder.upsert_hub_shipper(shipper, "empties")
            for shipper in map_changes.get("upserted_hub_shippers", [])
        ],
        *[
            builder.remove_hub_shipper(shipper, "parts")
            for shipper in map_changes.get("removed_hub_shippers", [])
        ],
        *[
            builder.remove_hub_shipper(shipper, "empties")
            for shipper in map_changes.get("removed_hub_shippers", [])
        ],
    )


def combine_patches(*patches: dict | None) -> dict:
    ops: list[dict] = []
    for patch in patches:
        if not patch:
            continue
        ops.extend(patch.get("ops", []))
    return {"version": 1, "ops": ops}


def render_base_patch(base_payload: dict) -> dict:
    return make_patch({"op": "renderBase", "payload": base_payload})


def render_full_patch(full_payload: dict) -> dict:
    return make_patch({"op": "renderFull", "payload": full_payload})


def upsert_features_patch(features: Iterable[dict], bounds: list[list[float]] | None = None) -> dict:
    patch = make_patch({"op": "upsertFeatures", "features": list(features)})
    if bounds is not None:
        patch["bounds"] = bounds
    return patch


def remove_features_patch(feature_ids: Iterable[str]) -> dict:
    return make_patch({"op": "removeFeatures", "ids": list(feature_ids)})


def patch_feature_patch(feature_id: str, changes: dict) -> dict:
    return make_patch({"op": "patchFeature", "id": feature_id, "changes": changes})


def set_ui_state_patch(ui_state: dict) -> dict:
    return make_patch({"op": "setUiState", "uiState": _normalise_ui_state(ui_state)})


class ScenarioMapPatchBuilder:
    """Build payloads and incremental patches for the Leaflet map.

    This class does not mutate your domain model. Call your existing route/hub/shipper
    services first, then call these methods with the affected objects and send the
    returned patch to the browser.
    """

    def __init__(self, scenario: Scenario, baseline_scenario: Scenario | None = None):
        self.scenario = scenario
        self.baseline_scenario = baseline_scenario

    def base_payload(self, ui_state: dict | None = None) -> dict:
        return build_scenario_map_base_payload(self.scenario, ui_state)

    def full_payload(self, ui_state: dict | None = None) -> dict:
        return build_scenario_map_full_payload(self.scenario, self.baseline_scenario, ui_state)

    def render_base(self, ui_state: dict | None = None) -> dict:
        return render_base_patch(self.base_payload(ui_state))

    def render_full(self, ui_state: dict | None = None) -> dict:
        return render_full_patch(self.full_payload(ui_state))

    def set_ui_state(self, ui_state: dict) -> dict:
        return set_ui_state_patch(ui_state)

    def patch_feature(self, feature_id: str, changes: dict) -> dict:
        return patch_feature_patch(feature_id, changes)

    def upsert_features(self, features: Iterable[dict], bounds: list[list[float]] | None = None) -> dict:
        return upsert_features_patch(features, bounds=bounds)

    def remove_features(self, feature_ids: Iterable[str]) -> dict:
        return remove_features_patch(feature_ids)

    def upsert_direct_route(self, route: Any, baseline: bool = False, include_last_leg: bool = True) -> dict:
        return combine_patches(
            self.remove_features([_direct_status_id(route, baseline=baseline)]),
            self.upsert_features(
                _direct_route_features(
                    route,
                    baseline=baseline,
                    include_last_leg=include_last_leg,
                )
            ),
        )

    def remove_direct_route(self, route: Any, baseline: bool = False) -> dict:
        return self.remove_features(direct_route_feature_ids(route, baseline=baseline))

    def replace_direct_route(self, old_route: Any, new_route: Any, baseline: bool = False) -> dict:
        return combine_patches(
            self.remove_direct_route(old_route, baseline=baseline),
            self.upsert_direct_route(new_route, baseline=baseline),
        )

    def upsert_hub(self, hub: Hub, flow: str, baseline: bool = False) -> dict:
        return self.upsert_features(_hub_features(hub, flow, baseline=baseline))

    def remove_hub(self, hub: Hub, flow: str, baseline: bool = False) -> dict:
        return self.remove_features(hub_feature_ids(hub, flow, baseline=baseline))

    def upsert_hub_shipper(self, shipper: Shipper, flow: str) -> dict:
        feature = _hub_shipper_feature(shipper, flow)
        return self.upsert_features([] if feature is None else [feature])

    def remove_hub_shipper(self, shipper: Shipper, flow: str) -> dict:
        return self.remove_features([hub_shipper_feature_id(shipper, flow)])

    def upsert_hub_network_for_flow(self, hubs: Sequence[Hub], flow: str) -> dict:
        features: list[dict] = []
        for shipper in _get_hub_shippers_from_hubs(list(hubs), flow):
            feature = _hub_shipper_feature(shipper, flow)
            if feature is not None:
                features.append(feature)
        for hub in hubs:
            features.extend(_hub_features(hub, flow, baseline=False))
        return self.upsert_features(features)