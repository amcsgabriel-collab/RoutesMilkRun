from domain.routes.route import Route


class Trip:
    def __init__(
            self,
            name,
            parts_route: Route,
            empties_route: Route
    ):
        self.name = name
        self.parts_route = parts_route
        self.empties_route = empties_route
        self.tariff = None

    @property
    def classification(self):
        if self.parts_route is not None and self.empties_route is not None:
            return "RT"
        elif self.parts_route is not None:
            return "PS"
        elif self.empties_route is not None:
            return "ES"
        else:
            return "N/D"

    def generate_tour_name(self, flow_direction: str) -> str:
        pass

    @property
    def roundtrip_id(self):
        return self.roundtrip_id if (self.empties_route and self.parts_route) else ""


