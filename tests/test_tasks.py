import bz2
import io
import json
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
    aggregate_and_dispatch_dependencies,
    chord,
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

    assert isinstance(result["region_ids"], list)
    assert isinstance(result["type_ids"], list)
    assert set(result["region_ids"]) == {10000002, 10000003}
    assert set(result["type_ids"]) == {34, 35}

def test_get_ids_from_date_file_is_json_serializable():
    # This test ensures that the output of the task can be serialized to JSON,
    # preventing regressions of the int64 issue.
    # We create a dataframe with numpy's default int64 type.
    df = pd.DataFrame({
        "region_id": [10000002, 10000003],
        "type_id": [34, 35]
    })

    # Create a mock that returns this dataframe
    with patch('pandas.read_csv', return_value=df):
        with patch('httpx.get'): # We still need to patch the network call
            result = get_ids_from_date_file("2023-01-01")

    # Attempt to serialize the result to JSON
    try:
        json.dumps(result)
    except TypeError:
        pytest.fail("The result of get_ids_from_date_file is not JSON serializable")


@patch("app.tasks.data_fetching.chain")
@patch("app.tasks.data_fetching.crud.get_existing_type_ids")
@patch("app.tasks.data_fetching.crud.get_existing_region_ids")
def test_aggregate_and_dispatch_dependencies(
    mock_get_regions, mock_get_types, mock_chain, db_session
):
    """
    Tests that the aggregator task correctly identifies missing dependencies
    and constructs a chain of groups with immutable signatures.
    """
    # Input to the aggregator task
    mock_id_results = [
        {"region_ids": [10000002, 10000003], "type_ids": [34, 35]},
        {"region_ids": [10000002, 10000004], "type_ids": [34, 36]},
    ]
    dates = ["2023-01-01", "2023-01-02"]

    # Mock DB lookups
    mock_get_regions.return_value = {10000002}  # 10000003 and 10000004 are missing
    mock_get_types.return_value = {34}          # 35 and 36 are missing

    # Call the aggregator
    aggregate_and_dispatch_dependencies(mock_id_results, dates)

    # Assertions
    mock_get_regions.assert_called_once()
    mock_get_types.assert_called_once()

    # Check that chain was called and inspect its arguments
    mock_chain.assert_called_once()
    args, _ = mock_chain.call_args

    # The chain should contain 3 groups of tasks
    assert len(args) == 3
    region_group, type_group, history_group = args

    # Verify the contents and immutability of each group
    assert len(region_group.tasks) == 2
    for task_sig in region_group.tasks:
        assert task_sig.immutable is True
    assert {s.args[0] for s in region_group.tasks} == {10000003, 10000004}

    assert len(type_group.tasks) == 2
    for task_sig in type_group.tasks:
        assert task_sig.immutable is True
    assert {s.args[0] for s in type_group.tasks} == {35, 36}

    assert len(history_group.tasks) == 2
    for task_sig in history_group.tasks:
        assert task_sig.immutable is True
    assert {s.args[0] for s in history_group.tasks} == set(dates)

    # Check that delay was called on the chain
    mock_chain.return_value.delay.assert_called_once()


@patch("app.tasks.data_fetching.chord")
@patch("app.tasks.data_fetching.group")
@patch("app.tasks.data_fetching.aggregate_and_dispatch_dependencies")
def test_orchestrate_market_data_load(mock_aggregator, mock_group, mock_chord):
    dates = ["2023-01-01", "2023-01-02"]

    # Call the orchestrator
    orchestrate_market_data_load(dates)

    # Assert that a group of ID gathering tasks was created
    mock_group.assert_called_once()
    id_gathering_call_args = mock_group.call_args_list[0].args[0]
    assert len(list(id_gathering_call_args)) == 2

    # Assert that the aggregator (callback) was prepared correctly
    mock_aggregator.s.assert_called_once_with(dates=dates)

    # Assert that the chord was created and delayed
    mock_chord.assert_called_once()
    mock_chord.return_value.delay.assert_called_once()


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