class DomainError(Exception):
    """Base for domain errors."""


class RouteNotOrderedError(DomainError):
    def __init__(self):
        super().__init__(
            "Route not ordered.",
            "Please order the route pattern before proceeding."
        )


class DeviationNotCalculatedError(DomainError):
    def __init__(self):
        super().__init__(
            "Deviation not calculated.",
            "Please calculate the route pattern deviation before proceeding."
        )


class MissingVehiclesInHelperFileError(DomainError):
    def __init__(self, missing_vehicles: set[str]):
        super().__init__(
            "Missing vehicles in helper file.",
            f"{len(missing_vehicles)} vehicles not found in helper file (vehicles.csv): \n" +
            "\n".join(f"- Vehicle ID: {v}" for v in missing_vehicles)
        )


class CarriersNotInHelperError(DomainError):
    def __init__(self, missing_carriers: set[str]):
        super().__init__(
            "Missing carriers in helper data:",
            f"{len(missing_carriers)} carrier IDs are not mapped in the 'helper' sheet in the GRAF file: \n" +
            "\n".join(f"- Carrier ID: {c}" for c in missing_carriers)
        )


class MissingTariffsError(DomainError):
    def __init__(self, tariff_type, missing_tariffs: list[dict]):
        if tariff_type == 'ftl' or tariff_type == 'linehaul':
            tariffs_message = "\n".join(f" - Zip Key: {t['zip_key']} | COFOR: {t['cofor']} | Carrier: {t['carrier']} "
                      f"| Vehicle: {t['vehicle']} | MR Cluster: {t['deviation_bucket']}" for t in missing_tariffs)
        else:
            tariffs_message = "\n".join(f" - Zip Key: {t['zip_key']} | COFOR: {t['cofor']} | Carrier: {t['carrier']} "
                      f"| Weight Bracket: {t['weight_bracket']} | Destination HUB: {t['destination']}" for t in missing_tariffs)

        super().__init__(
            "Missing tariffs found.",
            f"{len(missing_tariffs)} {tariff_type.upper()} route(s) have no matching tariff: \n {tariffs_message}"
        )


class VehicleCapacityError(DomainError):
    pass


class MissingHelperDataError(DomainError):
    def __init__(self):
        super().__init__(
            "Helper data unavailable.",
            "Couldn't find helper data."
        )


class NonOptimalSolutionError(DomainError):
    def __init__(self):
        super().__init__(
            "Non-optimal solution",
            "Model couldn't solve to optimality. Verify settings and re-run."
        )


class CannotEditBaselineError(DomainError):
    def __init__(self):
        super().__init__(
            "Can't edit baseline.",
            "Create a new scenario before making changes."
        )


class UnsavedScenarioError(DomainError):
    def __init__(self):
        super().__init__(
            "Scenario not saved.",
            "Are you sure you want to continue? \nTo export current draft routes, save scenario first."
        )


class ExportingBaselineError(DomainError):
    def __init__(self):
        super().__init__(
            "Exporting Baseline.",
            "Trying to re-export the baseline transport plan. Select a different scenario"
        )


class NoProjectError(DomainError):
    def __init__(self):
        super().__init__(
            "No project available.",
            "No project is currently available. Failed to load."
        )


class InvalidFileTypeError(DomainError):
    def __init__(self, file_type, accepted_file_types):
        super().__init__(
            "Invalid Filetype.",
            f"Can't read file of type {file_type}. Must be one of {accepted_file_types}",
        )


class ShippersWithoutLocationsError(DomainError):
    def __init__(self, shippers_without_coordinates):
        super().__init__(
            "Couldn't find locations data for shippers:",
            f"{shippers_without_coordinates}"
        )
