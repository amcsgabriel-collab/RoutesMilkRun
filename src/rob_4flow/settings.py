GRAF_TEMPLATE_HEADER_ROW = 4
VOLUME_CHARGEABLE_WEIGHT_CONVERSION_RATE = 250
DEFAULT_VEHICLE_ID = "SR30"

def get_column_sequence_graf_format(
        direct_or_hub: str,

) -> list[str]:
    """
    Add columns to the direct treated database to match the format of the hub table.

    :param direct_or_hub: 'hub' for GRP template format, 'direct' for Direct template format.
    :return: list of columns in correct sequence to export to GRAF, either in Hub or Direct format.
    """

    start = {
        'hub': ['Route name', 'HUB name', 'HUB COFOR'],
        'direct': ['Tour name', 'Route name']
    }

    cofor_columns = ['Shipper COFOR', 'Seller COFOR', 'Hybrid COFOR', 'Plant COFOR']

    extra_route_details = {
        'hub': ['Parts or Empties', 'Docks (,)', 'First pickup', 'Total transit time (days)', 'First delivery'],
        'direct': ['Parts or Empties', 'Index on MR', 'Roundtrip identifier', 'Docks (,)', 'First pickup',
                   'Transit time', 'First delivery']
    }

    carrier_columns = ['Carrier COFOR', 'Carrier ID'] + (
        ['Carrier Name'] if direct_or_hub == 'hub' else ['Carrier name']
    )

    transport_concept_details = {
        'hub': ['Means of Transport', 'Transport concept'],
        'direct': ['Means of Transport', 'Transport concept', "MR Cluster\n(S, L, M, H)"]
    }
    seller_shipper_columns = [
        'SELLER NAME', 'SELLER ZIP CODE', 'SELLER CITY', 'SELLER COUNTRY', 'SHIPPER NAME', 'SHIPPER  ZIP CODE',
        'SHIPPER CITY', 'SHIPPER STREET', 'SHIPPER COUNTRY', 'SHIPPER SOURCING REGION'
    ]

    empty_group_1 = [
        'HEV: empties truck loading begins at Stellantis Plant',
        'HEE: empties truck leaving plant site at Stellantis Plant',
        'HMD: parts truck arrival at shipper location',
        'HEF: parts truck leaving shipper location',
        'Pick Mon', 'Pick Tue', 'Pick Wed', 'Pick Thu', 'Pick Fri',
        'Pick Sat', 'Pick Sun', 'Frequency / week'
    ]
    empty_hub = [
        'Frist leg transit time (days)',
        'Arrival at HUB',
        'Waiting time in HUB\n(>= 24 h spent in HUB)',
        'HXC: Departure from HUB',
        'Second leg transit time (days)'
    ]
    empty_group_2 = [
        'DEL Mon', 'DEL Tue', 'DEL Wed', 'DEL Thu', 'DEL Fri', 'DEL Sat', 'DEL Sun',
        'HAS: parts truck arrival at Stellantis plant',
        'Parts truck unloading starts in last dock at Stellantis Plant',
        'HDE: Empties truck arrival at supplier',
        'Empties truck unloading complete at supplier location',
        'PLE: HAS', 'PLE: HRQ/HEE Dock 1', 'PLE: HRQ/HEE Dock 2', 'PLE: HRQ/HEE Dock 3', 'PLE: HRQ/HEE Dock 4',
        'PLE: HRQ/HEE Dock 5', 'PLE: HRQ/HEE Dock 6', 'PLE: HRQ/HEE Dock 7', 'PLE: HRQ/HEE Dock 8'
    ]

    empties = {
        'hub': empty_group_1 + empty_hub + empty_group_2,
        'direct': empty_group_1 + empty_group_2,
    }

    demand_columns_shipper = ['Avg. Loading Meters / week', 'Avg. Weight / week', 'Avg. Volume / week']

    demand_columns_direct = [
        'Avg. Loading Meters / week on route', 'Avg. Loading Meters / Transport',
        'Avg. Weight / week on route', 'Avg. Weight / Transport',
        'Avg. Volume / week on route', 'Avg. Volume / Transport'
    ]
    demand_columns_hub = [
        'Avg. Loading Meters / week (Linehaul)', 'Avg. Loading Meters / Transport',
        'Avg. Weight / week (Linehaul)', 'Avg. Weight / Transport',
        'Avg. Volume / Transport (Linehaul)', 'Avg. Volume / Transport'
    ]

    demand_columns = {
        'hub': demand_columns_shipper + demand_columns_hub,
        'direct': demand_columns_shipper + demand_columns_direct
    }

    utilization_columns = [
        'Avg. Loading meter utilization in %', 'Avg. Weight utilization in %', 'Avg. Volume utilization in %',
        'Max. Utilization in %'
    ]

    cost_columns = {
        'hub': ['Pre/on carriage total costs', 'Pre/on carriage costs per week',
                'Linehaul total costs', 'Linehaul costs per week'],
        'direct': ['Base cost', 'Stop cost', 'Total costs per load', 'Total costs per week']
    }

    full_sequence = (
            start[direct_or_hub] + cofor_columns + extra_route_details[direct_or_hub] + carrier_columns +
            transport_concept_details[direct_or_hub] + seller_shipper_columns + empties[direct_or_hub] +
            demand_columns[direct_or_hub] + utilization_columns + cost_columns[direct_or_hub]
    )

    return full_sequence
