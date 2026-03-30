"""
Project object: Current "Solver", should contain all the context data, the specified GRAF file, all the domain objects
created, should manage all the scenarios and regions, and should enable continuing with an optimization after closing
(saved states).

should have a "meta" object to enable quick reading/saving without having to read all data at once.
"""

from dataclasses import dataclass, field
from domain.data_structures import Plant, Vehicle
from domain.general_algorithms import utc_now_iso
from domain.routes.direct_route import DirectRoute
from domain.routes.route_pattern import RoutePattern
from domain.scenario import Scenario
from domain.tariff import FtlTariff, LtlTariff
from services.tariff_service import TariffService


# --------------------------------------------------------------
# Sourcing Region
@dataclass
class SourcingRegion:
    name: str
    scenarios: dict[str, Scenario]
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


# --------------------------------------------------------------
# Project
@dataclass()
class ProjectContext:
    plant: Plant
    vehicles: list[Vehicle]
    ftl_tariffs: dict[str, FtlTariff]
    ltl_tariffs: dict[str, LtlTariff]
    regions: dict[str, SourcingRegion]

    def __post_init__(self) -> None:
        self.tariffs_service = TariffService(
            ftl_mr_tariffs=self.ftl_tariffs,
            ltl_tariffs=self.ltl_tariffs,
            hub_tariffs=None
        )


@dataclass
class ProjectMeta:
    graf_file_path: str
    name: str = 'new project'
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    last_saved_at: bool | None = None
    current_region: str = None
    current_scenario: str = None
    context_file_path: str | None = None
    rob_file_path: str | None = None
    schema_version: int = 1


@dataclass
class Project:
    meta: ProjectMeta
    context: ProjectContext

    @property
    def name(self):
        return self.meta.name

    @property
    def regions_list(self):
        return [region for region in self.context.regions.keys()]

    @property
    def current_region(self):
        return self.context.regions[self.meta.current_region]

    @property
    def scenarios_list(self):
        return [scenario for scenario in self.current_region.scenarios.keys()]

    @property
    def current_scenario(self):
        return self.current_region.scenarios[self.meta.current_scenario]

    @property
    def plant(self):
        return self.context.plant

    @property
    def summary(self):
        return {
            "meta": {
                "name": self.name,
                "current_region": self.current_region.name,
                "current_scenario": self.current_scenario.name,
            },
            "context": {
                "plant_name": self.plant.name
            }
        }

    def set_current_scenario(self, scenario):
        self.meta.current_scenario = scenario

    def set_current_region(self, region):
        self.meta.current_region = region
        self.set_current_scenario("AS-IS")

    def create_ftl_route(self, shipper, vehicle_id="SR30"):
        new_pattern = RoutePattern({shipper}, self.plant)
        new_route = DirectRoute(new_pattern, self.context.vehicles[vehicle_id])
        self.context.tariffs_service.assign_ftl_mr_route(new_route)
        return new_route

    def create_pattern(self, shippers_key):
        return RoutePattern(self.current_scenario.get_shippers_from_key(shippers_key), self.plant)

    def create_route(self, shippers_key, vehicle_id):
        return DirectRoute(self.create_pattern(shippers_key), self.context.vehicles[vehicle_id])

    def refresh_tariffs_scenario_hubs(self):
        for hub in self.current_scenario.get_in_use_hubs():
            self.context.tariffs_service.assign_ltl_routes(hub.first_leg_routes)
