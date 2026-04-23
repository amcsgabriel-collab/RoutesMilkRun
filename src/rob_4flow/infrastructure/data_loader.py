import pandas as pd


class DataLoader:
    def __init__(self, path):
        self.path = path

    def load_csv(self, filename: str) -> pd.DataFrame:
        filepath = self.path / f"{filename}.csv"
        try:
            return pd.read_csv(filepath, sep=';', decimal=',')
        except FileNotFoundError:
            raise FileNotFoundError(f'Could not find "{filename}.csv" in the specified path.')

    def load_excel(self, filename: str, sheet, columns = None) -> pd.DataFrame:
        filepath = self.path / f"{filename}.xlsx"
        try:
            return pd.read_excel(io=filepath, sheet_name=sheet, usecols=columns)
        except FileNotFoundError:
            raise FileNotFoundError(f'Could not find "{filename}.csv" in the specified path.')
