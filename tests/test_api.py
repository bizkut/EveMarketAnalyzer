import pytest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import crud, schemas


def test_get_market_history(client: TestClient, db_session: Session):
    # First, create some test data
    region = crud.get_or_create_region(db_session, schemas.RegionCreate(region_id=1, name="Test Region"))
    eve_type = crud.get_or_create_type(db_session, schemas.EveTypeCreate(type_id=1, name="Test Type"))

    history_data = schemas.MarketHistoryCreate(
        date=date(2023, 1, 1),
        average=100.0,
        highest=110.0,
        lowest=90.0,
        order_count=10,
        volume=1000,
        region_id=region.region_id,
        type_id=eve_type.type_id,
    )
    crud.create_bulk_market_history(db_session, [history_data])

    # Make the API request
    response = client.get(f"/markets/{region.region_id}/history?type_id={eve_type.type_id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["average"] == 100.0
    assert data[0]["date"] == "2023-01-01"


def test_get_market_history_not_found(client: TestClient, db_session: Session):
    response = client.get("/markets/999/history?type_id=999")
    assert response.status_code == 404
    assert response.json() == {"detail": "No market history found for the specified region and type."}


@patch("app.api.endpoints.initial_data_load")
def test_refresh_endpoint_success(mock_initial_data_load, client: TestClient):
    response = client.post("/refresh", headers={"X-API-KEY": "test_api_key"})
    assert response.status_code == 202
    assert response.json() == {"message": "Market data refresh initiated."}
    mock_initial_data_load.delay.assert_called_once()


def test_refresh_endpoint_no_key(client: TestClient):
    response = client.post("/refresh")
    assert response.status_code == 403
    assert response.json() == {"detail": "Could not validate credentials"}


def test_refresh_endpoint_wrong_key(client: TestClient):
    response = client.post("/refresh", headers={"X-API-KEY": "wrong_key"})
    assert response.status_code == 403
    assert response.json() == {"detail": "Could not validate credentials"}


def test_get_market_analysis(client: TestClient, db_session: Session):
    # Create test data
    region1 = crud.get_or_create_region(db_session, schemas.RegionCreate(region_id=1, name="The Forge"))
    region2 = crud.get_or_create_region(db_session, schemas.RegionCreate(region_id=2, name="Domain"))
    type1 = crud.get_or_create_type(db_session, schemas.EveTypeCreate(type_id=1, name="Tritanium"))
    type2 = crud.get_or_create_type(db_session, schemas.EveTypeCreate(type_id=2, name="Pyerite"))

    # History for Tritanium in The Forge (High profit, low demand)
    crud.create_bulk_market_history(db_session, [
        schemas.MarketHistoryCreate(date=date(2023, 1, 1), average=10, highest=20, lowest=10, order_count=10, volume=100, region_id=region1.region_id, type_id=type1.type_id),
        schemas.MarketHistoryCreate(date=date(2023, 1, 2), average=12, highest=22, lowest=12, order_count=12, volume=120, region_id=region1.region_id, type_id=type1.type_id),
    ])

    # History for Pyerite in The Forge (Low profit, high demand)
    crud.create_bulk_market_history(db_session, [
        schemas.MarketHistoryCreate(date=date(2023, 1, 1), average=50, highest=55, lowest=50, order_count=100, volume=1000, region_id=region1.region_id, type_id=type2.type_id),
        schemas.MarketHistoryCreate(date=date(2023, 1, 2), average=52, highest=57, lowest=52, order_count=120, volume=1200, region_id=region1.region_id, type_id=type2.type_id),
    ])

    # History for Tritanium in Domain (Medium profit, medium demand)
    crud.create_bulk_market_history(db_session, [
        schemas.MarketHistoryCreate(date=date(2023, 1, 1), average=15, highest=25, lowest=15, order_count=50, volume=500, region_id=region2.region_id, type_id=type1.type_id),
    ])

    # Test sorting by profit_margin
    response = client.get("/analysis?sort_by=profit_margin")
    assert response.status_code == 200
    data = response.json()["results"]
    assert len(data) == 3
    assert data[0]["type_name"] == "Tritanium"
    assert data[0]["region_name"] == "The Forge"
    assert data[0]["profit_margin"] == pytest.approx(90.9090909090909)
    assert data[1]["type_name"] == "Tritanium"
    assert data[1]["region_name"] == "Domain"
    assert data[2]["type_name"] == "Pyerite"

    # Test sorting by demand
    response = client.get("/analysis?sort_by=demand")
    assert response.status_code == 200
    data = response.json()["results"]
    assert len(data) == 3
    assert data[0]["type_name"] == "Pyerite"
    assert data[0]["region_name"] == "The Forge"
    assert data[0]["demand"] == 1100.0
    assert data[1]["type_name"] == "Tritanium"
    assert data[1]["region_name"] == "Domain"
    assert data[2]["type_name"] == "Tritanium"


def test_get_market_analysis_no_data(client: TestClient, db_session: Session):
    response = client.get("/analysis")
    assert response.status_code == 200
    data = response.json()["results"]
    assert len(data) == 0