from .solver_input_parsing import SolverInputs
from .solver_state import MilkRunSolverState


class ShipperClassifier:
    def __init__(
        self,
        inputs: SolverInputs,
        state: MilkRunSolverState,
        tracker=None,
    ):
        self.inputs = inputs
        self.state = state
        self.tracker = tracker or (lambda _: None)

    def prepare(self) -> None:
        self._add_locked_routes()
        self._classify_parts_shippers()
        self._classify_empties_shippers()
        self._collect_existing_patterns()

        self.tracker(
            f"Shippers prepared: {len(self.inputs.parts_shippers)} parts "
            f"({len(self.state.non_exclusive_parts_shippers)} Non FTL exclusive, "
            f"{len(self.state.ftl_exclusive_parts_shippers)} FTL exclusive) "
            f"{len(self.inputs.empties_shippers)} empties: "
            f"({len(self.state.non_exclusive_empties_shippers)} Non FTL exclusive, "
            f"{len(self.state.ftl_exclusive_empties_shippers)} FTL exclusive)"
        )

        self.tracker(
            f"Existing network verified: {len(self.inputs.existing_trips)} existing trips, "
            f"{len(self.inputs.locked_parts_routes)} locked parts routes, "
            f"{len(self.inputs.locked_empties_routes)} locked empties routes"
        )

    def _add_locked_routes(self):
        self.state.locked_parts_routes = set(self.inputs.locked_parts_routes)
        self.state.locked_empties_routes = set(self.inputs.locked_empties_routes)

    def _classify_parts_shippers(self) -> None:
        self.state.ftl_exclusive_parts_shippers = {
            shipper
            for shipper in self.inputs.parts_shippers
            if shipper.is_ftl_exclusive_parts
        }

        self.state.non_exclusive_parts_shippers = {
            shipper
            for shipper in self.inputs.parts_shippers
            if not shipper.is_ftl_exclusive_parts
        }

    def _classify_empties_shippers(self) -> None:
        self.state.ftl_exclusive_empties_shippers = {
            shipper
            for shipper in self.inputs.empties_shippers
            if shipper.is_ftl_exclusive_empties
        }

        self.state.non_exclusive_empties_shippers = {
            shipper
            for shipper in self.inputs.empties_shippers
            if not shipper.is_ftl_exclusive_empties
        }

    def _collect_existing_patterns(self) -> None:
        self.state.existing_parts_patterns = {
            trip.parts_route.demand.pattern
            for trip in self.inputs.existing_trips
            if trip.parts_route is not None
        }

        self.state.existing_empties_patterns = {
            trip.empties_route.demand.pattern
            for trip in self.inputs.existing_trips
            if trip.empties_route is not None
        }