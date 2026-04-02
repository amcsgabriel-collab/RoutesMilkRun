import pandas as pd

from domain.hub import Hub
from domain.routes.direct_route import DirectRoute
from domain.scenario import Scenario
from domain.trip import Trip


class GrafExporter:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario

    def prepare_trip_dataframe(self, trip: Trip) -> pd.DataFrame:
        parts_route_df = self.prepare_route_dataframe(trip.parts_route, trip.generate_tour_name("parts"), trip.roundtrip_id)



    @staticmethod
    def prepare_route_dataframe(route, tour_name: str, roundtrip_id: str) -> pd.DataFrame:
        rows = []
        shippers = sorted(
            route.demand.pattern.shippers,
            key=lambda s: ((s.name or "").lower(), (s.cofor or "").lower())
        )

        first_route_row = True
        for shipper in shippers:
            sellers = sorted(
                shipper.sellers,
                key=lambda s: ((s.name or "").lower(), (s.cofor or "").lower())
            )

            first_shipper_row = True
            for seller in sellers:
                route_row = {
                    'Tour name': tour_name,
                    'Route name': route.route_name,
                    'Shipper COFOR': shipper.cofor,
                    'Seller COFOR': seller.cofor,
                    'Hybrid COFOR': seller.cofor,
                    'Plant COFOR': route.demand.plant.cofor,
                    'Parts or Empties': route.demand.flow_type.str[0].upper(),
                    'Index of MR': route.demand.pattern.sequence.index(shipper) + 1,
                    'Roundtrip Identifier': roundtrip_id,
                    'Docks (,)': shipper.docks,
                    'First pickup': '',
                    'Total transit time (days)': '',
                    'First delivery': '',
                    'Carrier COFOR': shipper.carrier.cofor,
                    'Carrier ID': shipper.carrier.id,
                    'Carrier name': shipper.carrier.name,
                    'Means of Transport': route.vehicle.id,
                    'Transport Concept': route.demand.pattern.transport_concept,
                    'MR Cluster\n(S, L, M, H)': route.demand.pattern.mr_cluster if route.demand.pattern.transport_concept == "MR" else "",
                    'SELLER NAME': seller.name,
                    'SELLER ZIP CODE': seller.zip,
                    'SELLER CITY': seller.city,
                    'SELLER COUNTRY': seller.country,
                    'SHIPPER NAME': shipper.name,
                    'SHIPPER  ZIP CODE': shipper.zip_code,
                    'SHIPPER CITY': shipper.city,
                    'SHIPPER STREET': shipper.street,
                    'SHIPPER COUNTRY': shipper.country,
                    'SHIPPER SOURCING REGION': shipper.sourcing_region,
                    'HEV: empties truck loading begins at Stellantis Plant': '',
                    'HEE: empties truck leaving plant site at Stellantis Plant': '',
                    'HMD: parts truck arrival at shipper location': '',
                    'HEF: parts truck leaving shipper location': '',
                    'Pick Mon': '',
                    'Pick Tue': '',
                    'Pick Wed': '',
                    'Pick Thu': '',
                    'Pick Fri': '',
                    'Pick Sat': '',
                    'Pick Sun': '',
                    'Frequency / week': route.frequency,
                    'DEL Mon': '',
                    'DEL Tue': '',
                    'DEL Wed': '',
                    'DEL Thu': '',
                    'DEL Fri': '',
                    'DEL Sat': '',
                    'DEL Sun': '',
                    'HAS: parts truck arrival at Stellantis plant': '',
                    'Parts truck unloading starts in last dock at Stellantis Plant': '',
                    'HDE: Empties truck arrival at supplier': '',
                    'Empties truck unloading complete at supplier location': '',
                    'PLE: HAS': '',
                    'PLE: HRQ/HEE Dock 1': '',
                    'PLE: HRQ/HEE Dock 2': '',
                    'PLE: HRQ/HEE Dock 3': '',
                    'PLE: HRQ/HEE Dock 4': '',
                    'PLE: HRQ/HEE Dock 5': '',
                    'PLE: HRQ/HEE Dock 6': '',
                    'PLE: HRQ/HEE Dock 7': '',
                    'PLE: HRQ/HEE Dock 8': '',
                    'Avg. Loading Meters / week': shipper.loading_meters if first_shipper_row else '',
                    'Avg. Weight / week': shipper.weight if first_shipper_row else '',
                    'Avg. Volume / week': shipper.volume if first_shipper_row else '',
                    'Avg. Loading Meters / week on route': route.demand.pattern.loading_meters if first_route_row else '',
                    'Avg. Loading Meters / transport': route.demand.pattern.loading_meters / route.frequency if (
                            first_route_row and route.frequency) else (0 if first_route_row else ''),
                    'Avg. Weight / week on route': route.demand.pattern.weight if first_route_row else '',
                    'Avg. Weight / transport': route.demand.pattern.weight / route.frequency if (
                            first_route_row and route.frequency) else (0 if first_route_row else ''),
                    'Avg. Volume / week on route': route.demand.pattern.volume if first_route_row else '',
                    'Avg. Volume / transport': route.demand.pattern.volume / route.frequency if (
                            first_route_row and route.frequency) else (0 if first_route_row else ''),
                    'Avg. Loading meter utilization in %': route.loading_meters_utilization if first_route_row else '',
                    'Avg. Weight utilization in %': route.weight_utilization if first_route_row else '',
                    'Avg. Volume utilization in %': route.volume_utilization if first_route_row else '',
                    'Max. Utilization in %': route.max_utilization if first_route_row else '',
                    'Base cost': route.tariff.base_cost if first_route_row else '',
                    'Stop cost': route.tariff.stop_cost if first_route_row else '',
                    'Total costs per load': route.route_cost if first_route_row else '',
                    'Total costs per week': route.total_cost if first_route_row else '',
                    '[PERS. COLUMN] Original Network': shipper.original_network
                }
                rows.append(route_row)

                first_shipper_row = False
                first_route_row = False

        return pd.DataFrame(rows)


def export_graf(
        path: str,
        scenario_routes: set[DirectRoute],
        scenario_hubs: set[Hub]
) -> None:
    direct_dataframe = pd.concat(
        [route.to_dataframe() for route in scenario_routes],
        ignore_index=True
    )

    hubs_dataframe = pd.concat(
        [hub.to_dataframe() for hub in scenario_hubs],
        ignore_index=True
    )

    with pd.ExcelWriter(path, engine='xlsxwriter') as writer:
        sheet1 = 'Direct GRAF Template'
        direct_dataframe.to_excel(
            writer,
            sheet_name=sheet1,
            startrow=1,
            header=False,
            index=False
        )
        ws1 = writer.sheets[sheet1]
        ws1.add_table(0, 0, len(direct_dataframe), len(direct_dataframe.columns) - 1, {
            'columns': [{'header': col} for col in direct_dataframe.columns],
            'style': 'Table Style Medium 2',
        })

        sheet2 = 'GRP GRAF Template'
        hubs_dataframe.to_excel(writer, sheet_name=sheet2, index=False)
        ws2 = writer.sheets[sheet2]
        ws2.add_table(0, 0, len(hubs_dataframe), len(hubs_dataframe.columns) - 1, {
            'columns': [{'header': col} for col in hubs_dataframe.columns],
            'style': 'Table Style Medium 2',
        })
