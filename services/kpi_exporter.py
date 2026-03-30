from domain.project import Scenario


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

    def get_kpis_template(self):
        return {
            "direct": {
                "ftl": {
                    **self.kpi("ftl_kpis", "total_cost", "total_cost", "lower"),
                    **self.kpi("ftl_kpis", "trucks", "total_trucks", "lower"),
                    **self.kpi("ftl_kpis", "utilization", "overall_utilization", "higher"),
                    **self.kpi("ftl_kpis", "euro_per_truck", "eur_per_truck", "lower"),
                    **self.kpi("ftl_kpis", "weight", "total_weight", "neutral"),
                    **self.kpi("ftl_kpis", "volume", "total_volume", "neutral"),
                    **self.kpi("ftl_kpis", "loading_meters", "total_loading_meters", "neutral"),
                    **self.kpi("ftl_kpis", "volume_per_truck", "volume_per_truck", "lower"),
                },
                "mr": {
                    **self.kpi("mr_kpis", "total_cost", "total_cost", "lower"),
                    **self.kpi("mr_kpis", "trucks", "total_trucks", "lower"),
                    **self.kpi("mr_kpis", "utilization", "overall_utilization", "higher"),
                    **self.kpi("mr_kpis", "euro_per_truck", "eur_per_truck", "lower"),
                    **self.kpi("mr_kpis", "weight", "total_weight", "neutral"),
                    **self.kpi("mr_kpis", "volume", "total_volume", "neutral"),
                    **self.kpi("mr_kpis", "loading_meters", "total_loading_meters", "neutral"),
                    **self.kpi("mr_kpis", "volume_per_truck", "volume_per_truck", "lower"),
                },
                "total": {
                    **self.kpi("direct_kpis", "total_cost", "total_cost", "lower"),
                    **self.kpi("direct_kpis", "trucks", "total_trucks", "lower"),
                    **self.kpi("direct_kpis", "utilization", "overall_utilization", "higher"),
                    **self.kpi("direct_kpis", "euro_per_truck", "eur_per_truck", "lower"),
                    **self.kpi("direct_kpis", "weight", "total_weight", "neutral"),
                    **self.kpi("direct_kpis", "volume", "total_volume", "neutral"),
                    **self.kpi("direct_kpis", "loading_meters", "total_loading_meters", "neutral"),
                    **self.kpi("direct_kpis", "volume_per_truck", "volume_per_truck", "lower"),
                },
            },
            "grp": {
                "first_leg": {
                    **self.kpi("hub_first_leg_kpis", "total_cost", "total_cost", "lower"),
                },
                "linehaul": {
                    **self.kpi("hub_linehaul_kpis", "total_cost", "total_cost", "lower"),
                    **self.kpi("hub_linehaul_kpis", "trucks", "total_trucks", "lower"),
                    **self.kpi("hub_linehaul_kpis", "utilization", "overall_utilization", "higher"),
                    **self.kpi("hub_linehaul_kpis", "euro_per_truck", "eur_per_truck", "lower"),
                    **self.kpi("hub_linehaul_kpis", "weight", "total_weight", "neutral"),
                    **self.kpi("hub_linehaul_kpis", "volume", "total_volume", "neutral"),
                    **self.kpi("hub_linehaul_kpis", "loading_meters", "total_loading_meters", "neutral"),
                    **self.kpi("hub_linehaul_kpis", "volume_per_truck", "volume_per_truck", "lower"),
                },
                "total": {
                    **self.kpi("hub_kpis", "total_cost", "total_cost", "lower"),
                    **self.kpi("hub_kpis", "trucks", "total_trucks", "lower"),
                    **self.kpi("hub_kpis", "utilization", "overall_utilization", "higher"),
                    **self.kpi("hub_kpis", "euro_per_truck", "eur_per_truck", "lower"),
                    **self.kpi("hub_kpis", "weight", "total_weight", "neutral"),
                    **self.kpi("hub_kpis", "volume", "total_volume", "neutral"),
                    **self.kpi("hub_kpis", "loading_meters", "total_loading_meters", "neutral"),
                    **self.kpi("hub_kpis", "volume_per_truck", "volume_per_truck", "lower"),
                },
            },
            "totals": {
                **self.kpi("global_total_kpis", "total_cost", "total_cost", "lower"),
                **self.kpi("global_total_kpis", "trucks", "total_trucks", "lower"),
                **self.kpi("global_total_kpis", "utilization", "overall_utilization", "higher"),
                **self.kpi("global_total_kpis", "euro_per_truck", "eur_per_truck", "lower"),
                **self.kpi("global_total_kpis", "weight", "total_weight", "neutral"),
                **self.kpi("global_total_kpis", "volume", "total_volume", "neutral"),
                **self.kpi("global_total_kpis", "loading_meters", "total_loading_meters", "neutral"),
                **self.kpi("global_total_kpis", "volume_per_truck", "volume_per_truck", "lower"),
            },
        }

