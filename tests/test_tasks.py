import bz2
import io
from datetime import date, datetime
from unittest.mock import patch, MagicMock, call

import pandas as pd
import pytest
from celery import group, chain

from app import crud, schemas
from app.tasks.data_fetching import (
    create_region,
    create_type,
    process_market_history,
    orchestrate_market_data_load,
    initial_data_load,
    daily_update_task,
    get_ids_from_date_file,
)


@patch("app.tasks.data_fetching._fetch_esi_url")
@patch("app.tasks.data_fetching.crud.get_or_create_region")
def test_create_region(mock_get_or_create_region, mock_fetch_esi, db_session):
    mock_fetch_esi.return_value = {"name": "The Forge", "description": "A region."}
    create_region(10000002)
    mock_fetch_esi.assert_called_once_with("https://esi.evetech.net/latest/universe/regions/10000002/")
    mock_get_or_create_region.assert_called_once()
    args, _ = mock_get_or_create_region.call_args
    assert isinstance(args[1], schemas.RegionCreate)
    assert args[1].region_id == 10000002
    assert args[1].name == "The Forge"


@patch("app.tasks.data_fetching._fetch_esi_url")
@patch("app.tasks.data_fetching.crud.get_or_create_type")
def test_create_type(mock_get_or_create_type, mock_fetch_esi, db_session):
    mock_fetch_esi.return_value = {
        "name": "Tritanium",
        "description": "A mineral.",
        "published": True,
        "dogma_attributes": [{"attribute_id": 1, "value": 1.0}],
    }
    create_type(34)
    mock_fetch_esi.assert_called_once_with("https://esi.evetech.net/latest/universe/types/34/")
    mock_get_or_create_type.assert_called_once()
    args, _ = mock_get_or_create_type.call_args
    assert isinstance(args[1], schemas.EveTypeCreate)
    assert args[1].type_id == 34
    assert args[1].name == "Tritanium"
    assert len(args[1].dogma_attributes) == 1


@patch("app.tasks.data_fetching.crud.create_bulk_market_history")
@patch("httpx.get")
def test_process_market_history(mock_http_get, mock_create_bulk, db_session):
    # Create a dummy CSV and compress it
    df = pd.DataFrame({
        "date": ["2023-01-01"], "average": [100.0], "highest": [110.0],
        "lowest": [90.0], "order_count": [10], "volume": [1000],
        "region_id": [10000002], "type_id": [34]
    })
    csv_data = df.to_csv(index=False).encode("utf-8")
    compressed_data = bz2.compress(csv_data)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = compressed_data
    mock_response.raise_for_status = MagicMock()
    mock_http_get.return_value = mock_response

    process_market_history("2023-01-01")

    mock_http_get.assert_called_once_with(
        "https://data.everef.net/market-history/2023/market-history-2023-01-01.csv.bz2",
        follow_redirects=True
    )
    mock_create_bulk.assert_called_once()
    args, _ = mock_create_bulk.call_args
    assert len(args[1]) == 1
    assert args[1][0].region_id == 10000002


@patch("httpx.get")
def test_get_ids_from_date_file(mock_http_get):
    # Mock market data fetching
    df = pd.DataFrame({
        "region_id": [10000002, 10000003, 10000002],
        "type_id": [34, 35, 34]
    })
    csv_data = df.to_csv(index=False).encode("utf-8")
    compressed_data = bz2.compress(csv_data)
    mock_response = MagicMock()
    mock_response.content = compressed_data
    mock_response.raise_for_status = MagicMock()
    mock_http_get.return_value = mock_response

    result = get_ids_from_date_file("2023-01-01")

    assert result["region_ids"] == {10000002, 10000003}
    assert result["type_ids"] == {34, 35}


@patch("app.tasks.data_fetching.chain")
@patch("app.tasks.data_fetching.group")
@patch("app.tasks.data_fetching.crud.get_existing_type_ids")
@patch("app.tasks.data_fetching.crud.get_existing_region_ids")
def test_orchestrate_market_data_load(
    mock_get_regions, mock_get_types, mock_group, mock_chain, db_session
):
    # Mock the result of the ID gathering tasks
    mock_id_results = [
        {"region_ids": {10000002, 10000003}, "type_ids": {34, 35}},
        {"region_ids": {10000002, 10000004}, "type_ids": {34, 36}},
    ]

    # Mock the group and chain machinery
    mock_async_result = MagicMock()
    mock_async_result.get.return_value = mock_id_results

    mock_id_gathering_group = MagicMock()
    mock_id_gathering_group.apply_async.return_value = mock_async_result

    # The group() call will be used for 3 things: id gathering, region creation, type creation, history processing
    # We want to intercept the first call and return our special mock.
    mock_group.side_effect = [
        mock_id_gathering_group, # First call is for ID gathering
        MagicMock(),             # Second is for region creation
        MagicMock(),             # Third is for type creation
        MagicMock()              # Fourth is for history processing
    ]

    # Mock DB lookups
    mock_get_regions.return_value = {10000002}  # 10000003 and 10000004 are missing
    mock_get_types.return_value = {34}          # 35 and 36 are missing

    # Call the orchestrator
    orchestrate_market_data_load(["2023-01-01", "2023-01-02"])

    # Assertions
    mock_get_regions.assert_called_once()
    mock_get_types.assert_called_once()

    # Check that the ID gathering group was called correctly
    id_gathering_call_args = mock_group.call_args_list[0].args[0]
    assert len(list(id_gathering_call_args)) == 2 # Called for 2 dates

    # Check that groups were created for the *missing* items
    # Region call is the second time mock_group is called
    region_creation_group_call_args = mock_group.call_args_list[1].args[0]
    assert len(list(region_creation_group_call_args)) == 2 # 2 missing regions

    # Type call is the third time
    type_creation_group_call_args = mock_group.call_args_list[2].args[0]
    assert len(list(type_creation_group_call_args)) == 2 # 2 missing types

    # History call is the fourth time
    history_processing_group_call_args = mock_group.call_args_list[3].args[0]
    assert len(list(history_processing_group_call_args)) == 2 # 2 dates

    mock_chain.assert_called_once()
    mock_chain.return_value.delay.assert_called_once()


@patch("app.tasks.data_fetching.orchestrate_market_data_load.delay")
def test_initial_data_load(mock_orchestrate):
    initial_data_load()
    mock_orchestrate.assert_called_once()
    args, kwargs = mock_orchestrate.call_args
    assert "dates" in kwargs
    assert len(kwargs["dates"]) == 365


@patch("app.tasks.data_fetching.orchestrate_market_data_load.delay")
def test_daily_update_task(mock_orchestrate):
    daily_update_task()
    mock_orchestrate.assert_called_once()
    args, kwargs = mock_orchestrate.call_args
    assert "dates" in kwargs
    assert len(kwargs["dates"]) == 1