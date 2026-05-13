from dataclasses import dataclass
from typing import Callable

from .direct_routes.vehicle_permutation_service import VehiclePermutationService
from ..hub_assignment import HubAssignmentService
from ..tariff_service import TariffService


@dataclass(frozen=True)
class SolverServices:
    tariff_service: TariffService
    vehicle_permutation_service: VehiclePermutationService
    tracker: Callable
    hub_assignment_service: HubAssignmentService


