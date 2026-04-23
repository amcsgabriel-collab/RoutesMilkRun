import pandas as pd

from ..domain.tariff import FtlTariff, LtlTariff, HubTariff


def ftl_tariffs_from_dataframe(tariffs_dataframe: pd.DataFrame) -> dict[tuple[str, str, str, str], FtlTariff]:
    return {
        (
            row['Carrier Short Name'],
            row['Means of Transport'],
            row['Deviation Bucket'],
            row['Origin Code'],
            row['Destination Code'],
        ): FtlTariff(
            base_cost=row['Base Cost'],
            roundtrip_base_cost=row['Roundtrip Base Cost'],
            stop_cost=row['Stop Cost'],
        )
        for _, row in tariffs_dataframe.iterrows()
    }


def ltl_tariffs_from_dataframe(tariffs_dataframe: pd.DataFrame) -> dict[tuple[str, str, str, str], LtlTariff]:
    return {
        (
            row['Carrier Short Name'],
            row['Chargeable Weight Bracket'],
            row['Origin Code'],
            row['Destination Code'],
        ): LtlTariff(
            cost_per_100kg=row['Cost per 100kg'],
            min_price=row['Min Price'],
            max_price=row['Max Price']
        )
        for _, row in tariffs_dataframe.iterrows()
    }

def hub_tariffs_from_dataframe(tariffs_dataframe: pd.DataFrame) -> dict[tuple[str, str, str, str], HubTariff]:
    return {
        (
            row['Carrier Short Name'],
            row['Chargeable Weight Bracket'],
            row['Origin Code'],
            row['Destination Code'],
        ): HubTariff(
            cost_per_100kg=row['Cost per 100kg'],
            min_price=row['Min Price'],
            max_price=row['Max Price']
        )
        for _, row in tariffs_dataframe.iterrows()
    }
