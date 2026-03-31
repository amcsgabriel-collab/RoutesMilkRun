from domain.exceptions import CannotEditBaselineError


class ScenarioService:
    def _create_scenario(self, project, template: str = 'AS-IS'):
        scenarios = project.current_region.scenarios
        if template not in scenarios:
            raise KeyError(f"Scenario '{template}' does not exist.")
        new_scenario = scenarios[template].copy()
        existing_names = set(scenarios.keys())
        base_name = "new_scenario" if template == "AS-IS" else f"{template}_copy"
        new_name = self._next_name(existing_names, base_name)
        new_scenario.name = new_name
        new_scenario.is_baseline = False
        scenarios[new_name] = new_scenario
        project.set_current_scenario(new_name)

    def add_scenario(self, project):
        self._create_scenario(project, 'AS-IS')

    def duplicate_scenario(self, project, template_scenario_name):
        if not template_scenario_name:
            raise ValueError("Scenario name is required.")
        self._create_scenario(project, template_scenario_name)

    @staticmethod
    def delete_scenario(project, scenario_name: str):
        scenarios = project.scenarios_list
        if scenario_name not in scenarios:
            raise KeyError(f"Scenario '{scenario_name}' does not exist.")
        if scenarios[scenario_name].is_baseline:
            raise CannotEditBaselineError()
        scenarios.pop(scenario_name)

    @staticmethod
    def _next_name(existing: set[str], base: str) -> str:
        """Return base, base1, base2, ... not present in existing."""
        if base not in existing:
            return base
        i = 1
        while f"{base}{i}" in existing:
            i += 1
        return f"{base}{i}"