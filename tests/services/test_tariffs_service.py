import pytest

from domain.domain_algorithms import get_deviation_bin
from domain.exceptions import MissingTariffKeyError
from tests.factories import make_tariffs_service, make_route_tariff_key


class TestTariffsService:
    def test_raises_missing_tariff_key_for_route(self):
        tariff_key = ('DHL', 'srxx', get_deviation_bin(0)[0], 'FR45', 's1')
        route = make_route_tariff_key(tariff_key=tariff_key)
        tariffs_service = make_tariffs_service()
        with pytest.raises(
                MissingTariffKeyError,
                match=f"Tariff key not found in tariffs database:"
        ):
            tariffs_service.assign({route})


    def test_correctly_retrieving_tariffs_by_zip_key(self):

        route = make_route_tariff_key(destination_key="ZIP")
        tariffs_service = make_tariffs_service()
        tariffs_service.assign({route})
        assert route.base_cost == 100
        assert route.stop_cost == 10
        assert route.tariff_source == "Zip Key"


    def test_correctly_retrieving_tariffs_by_cofor(self):

        route = make_route_tariff_key(destination_key="COFOR")
        tariffs_service = make_tariffs_service()
        tariffs_service.assign({route})
        assert route.base_cost == 120
        assert route.stop_cost == 10
        assert route.tariff_source == "COFOR"

