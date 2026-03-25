import pandas as pd

from domain.hub import Hub
from domain.operational_route import OperationalRoute


def export_graf(
        path: str,
        scenario_routes: set[OperationalRoute],
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

