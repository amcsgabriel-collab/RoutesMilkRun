import pytest

from infrastructure.data_loader import DataLoader
from paths import get_test_path


class TestDataLoader:

    def test_properly_reads_csv(self):
        test_data_loader = DataLoader(get_test_path('infrastructure'))
        vehicles_df = test_data_loader.load('vehicles')
        assert len(vehicles_df) == 4
        assert vehicles_df['id'].iloc[0] == 'SR30'

    def test_raises_file_not_found_error(self):
        with pytest.raises(FileNotFoundError, match='Could not find "vehicles.csv" in the specified path.'):
            DataLoader(get_test_path()).load('vehicles')

