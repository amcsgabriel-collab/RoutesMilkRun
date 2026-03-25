from domain.project import Scenario


class KpiExporter:
    def __init__(self, scenario: Scenario, baseline: Scenario):
        self.scenario = scenario
        self.baseline = baseline

    def kpi(self, attr, key, better_when):
        value = getattr(self.scenario, attr)
        base = getattr(self.baseline, attr)
        return {
            key: value,
            f"{key}_vs_as_is": base - value,
            f"{key}_better_when": better_when,
        }
    
    def get_kpis_template(self):
        return {
            "direct": {
                "ftl": {
                    **self.kpi("ftl_total_cost", "total_cost", "lower"),
                    **self.kpi("ftl_trucks", "total_trucks", "lower"),
                    **self.kpi("ftl_utilization", "overall_utilization", "higher"),
                    **self.kpi("ftl_euro_per_truck", "eur_per_truck", "lower"),
                    **self.kpi("ftl_weight", "total_weight", "neutral"),
                    **self.kpi("ftl_volume", "total_volume", "neutral"),
                    **self.kpi("ftl_loading_meters", "total_loading_meters", "neutral"),
                    **self.kpi("ftl_volume_per_truck", "volume_per_truck", "lower")
                },
                "mr": {
                    **self.kpi("mr_total_cost", "total_cost", "lower"),
                    **self.kpi("mr_trucks", "total_trucks", "lower"),
                    **self.kpi("mr_utilization", "overall_utilization", "higher"),
                    **self.kpi("mr_euro_per_truck", "eur_per_truck", "lower"),
                    **self.kpi("mr_weight", "total_weight", "neutral"),
                    **self.kpi("mr_volume", "total_volume", "neutral"),
                    **self.kpi("mr_loading_meters", "total_loading_meters", "neutral"),
                    **self.kpi("mr_volume_per_truck", "volume_per_truck", "lower")
                },
                "total": {
                    **self.kpi("direct_total_cost", "total_cost", "lower"),
                    **self.kpi("direct_trucks", "total_trucks", "lower"),
                    **self.kpi("direct_utilization", "overall_utilization", "higher"),
                    **self.kpi("direct_euro_per_truck", "eur_per_truck", "lower"),
                    **self.kpi("direct_weight", "total_weight", "neutral"),
                    **self.kpi("direct_volume", "total_volume", "neutral"),
                    **self.kpi("direct_loading_meters", "total_loading_meters", "neutral"),
                    **self.kpi("direct_volume_per_truck", "volume_per_truck", "lower")
                },
            },
            "grp": {
                "first_leg": {
                    **self.kpi("first_leg_total_cost", 'total_cost', "lower"),
                    **self.kpi("first_leg_weight", "total_weight", "neutral"),
                    **self.kpi("first_leg_volume", "total_volume", "neutral"),
                    **self.kpi("first_leg_loading_meters", "total_loading_meters", "neutral"),
                },
                "linehaul": {
                    **self.kpi("linehaul_total_cost", 'total_cost', "lower"),
                    **self.kpi("linehaul_trucks", "total_trucks", "lower"),
                    **self.kpi("linehaul_utilization", "overall_utilization", "higher"),
                    **self.kpi("linehaul_euro_per_truck", "eur_per_truck", "lower"),
                    **self.kpi("linehaul_weight", "total_weight", "neutral"),
                    **self.kpi("linehaul_volume", "total_volume", "neutral"),
                    **self.kpi("linehaul_loading_meters", "total_loading_meters", "neutral"),
                    **self.kpi("linehaul_volume_per_truck", "volume_per_truck", "lower")
                },
                "total": {
                    **self.kpi("hub_total_cost", "total_cost", "lower"),
                    **self.kpi("hub_trucks", "total_trucks", "lower"),
                    **self.kpi("hub_utilization", "overall_utilization", "higher"),
                    **self.kpi("hub_euro_per_truck", "eur_per_truck", "lower"),
                    **self.kpi("hub_weight", "total_weight", "neutral"),
                    **self.kpi("hub_volume", "total_volume", "neutral"),
                    **self.kpi("hub_loading_meters", "total_loading_meters", "neutral"),
                    **self.kpi("hub_volume_per_truck", "volume_per_truck", "lower")
                },
            },
            "totals": {
                    **self.kpi("total_cost", "total_cost", "lower"),
                    **self.kpi("total_trucks", "total_trucks", "lower"),
                    **self.kpi("overall_utilization", "overall_utilization", "higher"),
                    **self.kpi("average_euro_per_truck", "eur_per_truck", "lower"),
                    **self.kpi("total_weight", "total_weight", "neutral"),
                    **self.kpi("total_volume", "total_volume", "neutral"),
                    **self.kpi("total_loading_meters", "total_loading_meters", "neutral"),
                    **self.kpi("average_volume_per_truck", "volume_per_truck", "lower")
                },
        }

