import pandas as pd
from pyxlsb import open_workbook

from ..settings import GRAF_TEMPLATE_HEADER_ROW, get_column_sequence_graf_format, get_graf_dtype_map

TARIFFS_RELEVANT_COLUMNS = [
    'Unique_KEY', 'iTMS_Mode', 'Singletrip', 'non-Singletrip',
    'Roundtrip', 'Currency', 'Small (0-30km)', 'Low (30-50 km)',
    'Medium (50-100km)', 'High (100-150km)', '>150km', 'Price_min',
    'Price_max', '<=200_LTL', '<=600_LTL', '<=1000_LTL', '<=2000_LTL',
    '<=4000_LTL', '<=10000_LTL', '<=15000_LTL', '<=20000_LTL', '<=25000_LTL',
    '>25000_LTL', '<=3000_HUB', '<=5000_HUB', '<=7000_HUB', '<=10000_HUB', '<=15000_HUB',
    '<=20000_HUB', '>20000_HUB'
]

class GrafLoader:
    def __init__(self, graf_path):
        self.graf_path = graf_path

    def load_demand_database(
            self,
            direct_or_hub: str,
    ) -> pd.DataFrame:
        """
        Reads GRAF file to retrieve Direct or Hub suppliers data, tariffs and other helper tables.
        :param direct_or_hub: What raw database is being read. Either "Hub" or "Direct".
        :return: Loaded suppliers dataframe with standardized column names.
        """

        sheet_name = "Direct RAF Template" if direct_or_hub == "Direct" else "GRP RAF Template"
        columns = get_column_sequence_graf_format(str.lower(direct_or_hub))
        dtypes = get_graf_dtype_map(str.lower(direct_or_hub))
        header_row = GRAF_TEMPLATE_HEADER_ROW
        return self.read_graf_file(sheet_name, header_row, columns, dtypes)

    def load_tariffs_database(self):
        sheet_name = "PriceSheet"
        columns = TARIFFS_RELEVANT_COLUMNS
        header_row = 0
        return self.read_graf_file(sheet_name, header_row, columns)

    def load_carrier_helper(self):
        sheet_name = 'helper'
        header_row = 0
        columns = ['Carrier Key', 'Pricesheet name']
        carrier_helper = self.read_graf_file(sheet_name, header_row, columns)
        carrier_helper.columns = ['Carrier ID Helper', 'Carrier Short Name']
        carrier_helper = carrier_helper.drop_duplicates()
        return carrier_helper

    def load_plant_name_helper(self):
        sheet_name = 'helper'
        header_row = 0
        columns = ['Plant name', 'COFOR']
        plant_name_helper = self.read_graf_file(sheet_name, header_row, columns)
        plant_name_helper = plant_name_helper.drop_duplicates()
        plant_name_helper['Plant name'] = plant_name_helper['Plant name'].str.upper()
        plant_name_helper.columns = ['Plant Name', 'Plant COFOR']
        return plant_name_helper

    def load_vehicles(self):
        sheet_name = 'Equipments'
        header_row = 1
        columns = ['Name', 'Max Ldm', 'Max weight', 'Max volume']
        vehicles = self.read_graf_file(sheet_name, header_row, columns)
        vehicles = vehicles.drop_duplicates()
        return vehicles

    def load_kpi_vehicles_count(self):
        sheet_name = "Summary"
        target_row = 10  # C10
        target_col = 3  # column C

        print(f'Reading cell C10 from file: {self.graf_path} on sheet {sheet_name}.')

        try:
            with open_workbook(self.graf_path) as wb:
                with wb.get_sheet(sheet_name) as sheet:
                    for i, row in enumerate(sheet.rows(), start=1):
                        if i == target_row:
                            return row[target_col - 1].v  # zero-based index

        except FileNotFoundError:
            raise FileNotFoundError(
                f'Could not find the GRAF file in the specified path.'
            )

    def read_graf_file(
            self,
            sheet_name: str,
            header_row: int,
            columns: list[str],
            dtype: dict | None = None
    ) -> pd.DataFrame:

        print(f'Reading file: {self.graf_path} on sheet {sheet_name}.')
        try:
            database = pd.read_excel(
                io=self.graf_path,
                sheet_name=sheet_name,
                header=header_row,
                usecols=columns,
                dtype=dtype
            )
            return database
        except FileNotFoundError:
            raise FileNotFoundError(f'Could not find the GRAF file in the specified path.')
