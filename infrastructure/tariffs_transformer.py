import pandas as pd

TARIFFS_COLUMNS_DIRECT = [
    {'raw': 'Unique_KEY', 'final': 'Tariff Key', 'dtype': 'string'},
    {'raw': 'iTMS_Mode', 'final': 'iTMS Mode', 'dtype': 'string'},
    {'raw': 'Singletrip', 'final': 'Base Cost', 'dtype': 'float32'},
    {'raw': 'Roundtrip', 'final': 'Roundtrip Base Cost', 'dtype': 'float32'},
    {'raw': 'Currency', 'final': 'Currency', 'dtype': 'category'},
    {'raw': 'Small (0-30km)', 'final': 'Small (0-30km)', 'dtype': 'float32'},
    {'raw': 'Low (30-50 km)', 'final': 'Low (30-50 km)', 'dtype': 'float32'},
    {'raw': 'Medium (50-100km)', 'final': 'Medium (50-100km)', 'dtype': 'float32'},
    {'raw': 'High (100-150km)', 'final': 'High (100-150km)', 'dtype': 'float32'},
    {'raw': '>150km', 'final': '>150km', 'dtype': 'float32'},
]

TARIFFS_COLUMNS_LTL = [
    {'raw': 'Unique_KEY', 'final': 'Tariff Key', 'dtype': 'string'},
    {'raw': 'iTMS_Mode', 'final': 'iTMS Mode', 'dtype': 'string'},
    {'raw': 'Currency', 'final': 'Currency', 'dtype': 'category'},
    {'raw': 'Price_min', 'final': 'Min Price', 'dtype': 'float32'},
    {'raw': 'Price_max', 'final': 'Max Price', 'dtype': 'float32'},
    {'raw': '<=200_LTL', 'final': '<=200_LTL', 'dtype': 'float32'},
    {'raw': '<=600_LTL', 'final': '<=600_LTL', 'dtype': 'float32'},
    {'raw': '<=1000_LTL', 'final': '<=1000_LTL', 'dtype': 'float32'},
    {'raw': '<=2000_LTL', 'final': '<=2000_LTL', 'dtype': 'float32'},
    {'raw': '<=4000_LTL', 'final': '<=4000_LTL', 'dtype': 'float32'},
    {'raw': '<=10000_LTL', 'final': '<=10000_LTL', 'dtype': 'float32'},
    {'raw': '<=15000_LTL', 'final': '<=15000_LTL', 'dtype': 'float32'},
    {'raw': '<=20000_LTL', 'final': '<=20000_LTL', 'dtype': 'float32'},
    {'raw': '<=25000_LTL', 'final': '<=25000_LTL', 'dtype': 'float32'},
    {'raw': '>25000_LTL', 'final': '>25000_LTL', 'dtype': 'float32'},
]

TARIFFS_COLUMNS_HUB = [
    {'raw': 'Unique_KEY', 'final': 'Tariff Key', 'dtype': 'string'},
    {'raw': 'iTMS_Mode', 'final': 'iTMS Mode', 'dtype': 'string'},
    {'raw': 'Currency', 'final': 'Currency', 'dtype': 'category'},
    {'raw': 'Price_min', 'final': 'Min Price', 'dtype': 'float32'},
    {'raw': 'Price_max', 'final': 'Max Price', 'dtype': 'float32'},
    {'raw': '<=3000_HUB', 'final': '<=3000_HUB', 'dtype': 'float32'},
    {'raw': '<=5000_HUB', 'final': '<=5000_HUB', 'dtype': 'float32'},
    {'raw': '<=7000_HUB', 'final': '<=7000_HUB', 'dtype': 'float32'},
    {'raw': '<=10000_HUB', 'final': '<=10000_HUB', 'dtype': 'float32'},
    {'raw': '<=15000_HUB', 'final': '<=15000_HUB', 'dtype': 'float32'},
    {'raw': '<=20000_HUB', 'final': '<=20000_HUB', 'dtype': 'float32'},
    {'raw': '>20000_HUB', 'final': '>20000_HUB', 'dtype': 'float32'},
]

HUB_WEIGHT_VARS = [
    '<=3000_HUB',
    '<=5000_HUB',
    '<=7000_HUB',
    '<=10000_HUB',
    '<=15000_HUB',
    '<=20000_HUB',
    '>20000_HUB'
]

LTL_WEIGHT_VARS = [
    '<=200_LTL',
    '<=600_LTL',
    '<=1000_LTL',
    '<=2000_LTL',
    '<=4000_LTL',
    '<=10000_LTL',
    '<=15000_LTL',
    '<=20000_LTL',
    '<=25000_LTL',
    '>25000_LTL'
]


class TariffsTransformer:
    def __init__(
            self,
            tariffs_dataframe: pd.DataFrame,
            plant_cofor: str,
            hub_cofors: list[str]
    ):
        self.tariffs_dataframe = tariffs_dataframe
        self.plant = plant_cofor
        self.hubs = hub_cofors

    def get_transformed_tariffs(self, tariffs_type: str) -> pd.DataFrame:
        tariffs = self.tariffs_dataframe.copy()
        tariffs = self._filter_itms_mode(tariffs, tariffs_type)
        tariffs = self._filter_relevant_columns(tariffs, tariffs_type)
        tariffs = self._rename_tariffs_columns(tariffs, tariffs_type)
        tariffs = self._split_tariffs_key(tariffs)
        if tariffs_type == 'ftl':
            return self._melt_tariffs_deviation_bucket(tariffs)
        tariffs = self._melt_tariffs_chargeable_weight(tariffs, tariffs_type)
        return self._filter_empty_cost_rows(tariffs)

    @staticmethod
    def _filter_itms_mode(tariffs: pd.DataFrame, tariffs_type: str) -> pd.DataFrame:
        itms_mode = "FTL / MR" if tariffs_type == 'ftl' else "LTL / GRP / HUB"
        return tariffs[tariffs['iTMS_Mode'] == itms_mode]

    @staticmethod
    def _get_tariff_columns_config(tariffs_type: str) -> list[dict[str, str]]:
        if tariffs_type == "ftl":
            return TARIFFS_COLUMNS_DIRECT
        if tariffs_type == "ltl":
            return TARIFFS_COLUMNS_LTL
        if tariffs_type == "hub":
            return TARIFFS_COLUMNS_HUB
        raise ValueError(f"Unexpected Tariff Type: {tariffs_type}.")

    def _filter_relevant_columns(self, tariffs: pd.DataFrame, tariffs_type: str) -> pd.DataFrame:
        source = self._get_tariff_columns_config(tariffs_type)
        columns = [c['raw'] for c in source]
        return tariffs[columns]

    def _rename_tariffs_columns(self, tariffs: pd.DataFrame, tariffs_type: str) -> pd.DataFrame:
        source = self._get_tariff_columns_config(tariffs_type)
        return tariffs.rename(
            columns={c['raw']: c['final'] for c in source}
        )

    @staticmethod
    def _split_tariffs_key(tariffs: pd.DataFrame) -> pd.DataFrame:
        tariffs = tariffs.copy()
        parts = tariffs["Tariff Key"].str.split("---")
        parts = parts.apply(lambda x: [p.strip() for p in x] if isinstance(x, list) else x)
        part_count = parts.str.len()

        tariffs["Carrier Short Name"] = parts.str[0]
        tariffs["Destination Code"] = parts.str[-1]
        tariffs["Origin Code"] = parts.str[-2]
        tariffs["Means of Transport"] = None

        mask_4 = part_count == 4
        mask_5 = part_count == 5

        tariffs.loc[mask_4, "Means of Transport"] = parts[mask_4].str[1]
        tariffs.loc[mask_5, "Means of Transport"] = parts[mask_5].str[2]
        invalid = ~part_count.isin([3, 4, 5])
        if invalid.any():
            bad_counts = sorted(part_count[invalid].unique().tolist())
            raise ValueError(f"Unexpected Tariff Key format with parts counts: {bad_counts}")
        return tariffs.drop(columns=["Tariff Key"])


    @staticmethod
    def _melt_tariffs_deviation_bucket(tariffs: pd.DataFrame) -> pd.DataFrame:
        return tariffs.melt(
            id_vars=[
                'Carrier Short Name',
                'Means of Transport',
                'Origin Code',
                'Destination Code',
                'iTMS Mode',
                'Base Cost',
                'Roundtrip Base Cost',
                'Currency'
            ],
            value_vars=[
                'Small (0-30km)',
                'Low (30-50 km)',
                'Medium (50-100km)',
                'High (100-150km)',
                '>150km'
            ],
            var_name='Deviation Bucket',
            value_name='Stop Cost'
        )

    @staticmethod
    def _melt_tariffs_chargeable_weight(tariffs: pd.DataFrame, tariffs_type: str) -> pd.DataFrame:
        if tariffs_type == 'ltl':
            value_vars = LTL_WEIGHT_VARS
        elif tariffs_type == 'hub':
            value_vars = HUB_WEIGHT_VARS
        else:
            raise ValueError(f"Unexpected Tariffs type: {tariffs_type.upper()}.")
        return tariffs.melt(
            id_vars=[
                'Carrier Short Name',
                'Means of Transport',
                'Origin Code',
                'Destination Code',
                'iTMS Mode',
                'Currency',
                'Min Price',
                'Max Price',
            ],
            value_vars=value_vars,
            var_name='Chargeable Weight Bracket',
            value_name='Cost per 100kg'
        )

    @staticmethod
    def _filter_empty_cost_rows(tariffs: pd.DataFrame) -> pd.DataFrame:
        return tariffs[tariffs['Cost per 100kg'] > 0]
