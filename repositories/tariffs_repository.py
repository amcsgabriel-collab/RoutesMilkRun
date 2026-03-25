import pandas as pd


def ftl_tariffs_from_dataframe(tariffs_dataframe: pd.DataFrame) -> dict[tuple[str, str, str, str], tuple[float, float]]:
    return {
        (
            row['Carrier Short Name'],
            row['Means of Transport'],
            row['Deviation Bucket'],
            row['Origin Code']
        ): (
            row['Base Cost'],
            row['Stop Cost']
        )
        for _, row in tariffs_dataframe.iterrows()
    }

def hub_tariffs_from_dataframe(tariffs_dataframe: pd.DataFrame) -> dict[tuple[str, str, str, str], tuple[float, float, float]]:
    return {
        (
            row['Carrier Short Name'],
            row['Chargeable Weight Bracket'],
            row['Destination COFOR'],
            row['Origin Code'],
        ): (
            row['Cost per 100kg'],
            row['Min Price'],
            row['Max Price']
        )
        for _, row in tariffs_dataframe.iterrows()
    }
