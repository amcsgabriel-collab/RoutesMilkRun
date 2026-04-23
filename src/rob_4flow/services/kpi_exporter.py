from ..domain.project import Scenario


class KpiExporter:
    def __init__(self, scenario: Scenario, baseline: Scenario):
        self.scenario = scenario
        self.baseline = baseline

    def kpi(self, group_attr: str, field: str, key: str, better_when: str):
        value = getattr(getattr(self.scenario, group_attr), field)
        base = getattr(getattr(self.baseline, group_attr), field)
        return {
            key: value,
            f"{key}_vs_as_is": base - value,
            f"{key}_better_when": better_when,
        }

    def kpi_block(self, group_attr: str):
        return {
            **self.kpi(group_attr, "total_cost", "total_cost", "lower"),
            **self.kpi(group_attr, "trucks", "total_trucks", "lower"),
            **self.kpi(group_attr, "utilization", "overall_utilization", "higher"),
            **self.kpi(group_attr, "euro_per_truck", "eur_per_truck", "lower"),
            **self.kpi(group_attr, "weight", "total_weight", "neutral"),
            **self.kpi(group_attr, "volume", "total_volume", "neutral"),
            **self.kpi(group_attr, "loading_meters", "total_loading_meters", "neutral"),
            **self.kpi(group_attr, "volume_per_truck", "volume_per_truck", "lower"),
        }

    def cost_only_kpi_block(self, group_attr: str):
        return {
            **self.kpi(group_attr, "total_cost", "total_cost", "lower"),
        }

    def get_kpis_template(self):
        return {
            "direct": {
                "ftl": {
                    "parts": self.kpi_block("ftl_parts_kpis"),
                    "empties": self.kpi_block("ftl_empties_kpis"),
                    "all": self.kpi_block("ftl_all_kpis"),
                },
                "mr": {
                    "parts": self.kpi_block("mr_parts_kpis"),
                    "empties": self.kpi_block("mr_empties_kpis"),
                    "all": self.kpi_block("mr_all_kpis"),
                },
                "total": {
                    "parts": self.kpi_block("direct_parts_kpis"),
                    "empties": self.kpi_block("direct_empties_kpis"),
                    "all": self.kpi_block("direct_all_kpis"),
                },
            },
            "grp": {
                "first_leg": {
                    "parts": self.cost_only_kpi_block("hub_parts_first_leg_kpis"),
                    "empties": self.cost_only_kpi_block("hub_empties_first_leg_kpis"),
                    "all": self.cost_only_kpi_block("hub_all_first_leg_kpis"),
                },
                "linehaul": {
                    "parts": self.kpi_block("hub_parts_linehaul_kpis"),
                    "empties": self.kpi_block("hub_empties_linehaul_kpis"),
                    "all": self.kpi_block("hub_all_linehaul_kpis"),
                },
                "total": {
                    "parts": self.kpi_block("hub_parts_kpis"),
                    "empties": self.kpi_block("hub_empties_kpis"),
                    "all": self.kpi_block("hub_all_kpis"),
                },
            },
            "totals": {
                "parts": self.kpi_block("global_parts_kpis"),
                "empties": self.kpi_block("global_empties_kpis"),
                "all": self.kpi_block("global_total_kpis"),
            },
        }

