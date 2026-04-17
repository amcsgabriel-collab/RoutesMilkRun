import pandas as pd

from domain.hub import Hub
from domain.trip import Trip


def export_graf(
        path: str,
        scenario_trips: set[Trip],
        scenario_hubs: set[Hub]
) -> None:
    trip_frames = []
    for trip in scenario_trips:
        df = trip.export_dataframe()
        if not df.empty:
            trip_frames.append(df)

    trips_dataframe = pd.concat(trip_frames, ignore_index=True) if trip_frames else pd.DataFrame()

    hub_frames = []
    for hub in scenario_hubs:
        df = hub.to_dataframe()
        if not df.empty:
            hub_frames.append(df)

    hubs_dataframe = pd.concat(hub_frames, ignore_index=True) if hub_frames else pd.DataFrame()

    with pd.ExcelWriter(path, engine='xlsxwriter') as writer:
        sheet1 = 'Direct GRAF Template'
        if not trips_dataframe.empty:
            trips_dataframe.to_excel(
                writer,
                sheet_name=sheet1,
                startrow=1,
                header=False,
                index=False
            )
            ws1 = writer.sheets[sheet1]
            ws1.add_table(0, 0, len(trips_dataframe), len(trips_dataframe.columns) - 1, {
                'columns': [{'header': col} for col in trips_dataframe.columns],
                'style': 'Table Style Medium 2',
            })
        else:
            pd.DataFrame().to_excel(writer, sheet_name=sheet1, index=False)

        sheet2 = 'GRP GRAF Template'
        if not hubs_dataframe.empty:
            hubs_dataframe.to_excel(
                writer,
                sheet_name=sheet2,
                startrow=1,
                header=False,
                index=False
            )
            ws2 = writer.sheets[sheet2]
            ws2.add_table(0, 0, len(hubs_dataframe), len(hubs_dataframe.columns) - 1, {
                'columns': [{'header': col} for col in hubs_dataframe.columns],
                'style': 'Table Style Medium 2',
            })
        else:
            pd.DataFrame().to_excel(writer, sheet_name=sheet2, index=False)