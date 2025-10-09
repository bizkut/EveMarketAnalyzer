import bz2
import io
import json
import os
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
from celery import group, chord

from app import crud, schemas
from app.tasks.data_fetching import (
    create_region,
    create_type,
    process_market_history,
    orchestrate_market_data_load,
    initial_data_load,
    daily_update_task,
    download_and_extract_ids,
    aggregate_and_dispatch_dependencies,
    dispatch_market_history_tasks,
    TEMP_DATA_DIR,
)

# Test data
DF_DATA = {"region_id": [10000002], "type_id": [34]}
DATE_STR = "2023-01-01"
FILE_PATH = os.path.join(TEMP_DATA_DIR, f"market-history-{DATE_STR}.csv.bz2")


@patch("app.tasks.data_fetching._fetch_esi_url")
def test_create_region(mock_fetch_esi, db_session):
    mock_fetch_esi.return_value = {"name": "The Forge", "description": "A region."}
    with patch("app.tasks.data_fetching.crud.get_or_create_region") as mock_get_or_create:
        create_region(10000002)
        mock_get_or_create.assert_called_once()


@patch("app.tasks.data_fetching._fetch_esi_url")
def test_create_type(mock_fetch_esi, db_session):
    mock_fetch_esi.return_value = {"name": "Tritanium", "description": "A mineral."}
    with patch("app.tasks.data_fetching.crud.get_or_create_type") as mock_get_or_create:
        create_type(34)
        mock_get_or_create.assert_called_once()


@patch("os.remove")
@patch("app.tasks.data_fetching.crud.create_bulk_market_history")
def test_process_market_history(mock_create_bulk, mock_os_remove, tmp_path):
    """
    Tests processing a local bz2 file, storing its data, and cleaning up.
    """
    # Create a dummy compressed file in a temporary directory
    temp_dir = tmp_path / "market_data"
    temp_dir.mkdir()
    dummy_file_path = temp_dir / f"market-history-{DATE_STR}.csv.bz2"

    df = pd.DataFrame({
        "date": [DATE_STR], "average": [100.0], "highest": [110.0],
        "lowest": [90.0], "order_count": [5_000_000_000], "volume": [10_000_000_000],
        "region_id": [10000002], "type_id": [34]
    })

    with bz2.open(dummy_file_path, "wt") as bz2f:
        df.to_csv(bz2f, index=False)

    process_market_history(str(dummy_file_path), DATE_STR)

    mock_create_bulk.assert_called_once()
    args, _ = mock_create_bulk.call_args
    assert len(args[1]) == 1
    assert args[1][0].volume == 10_000_000_000

    mock_os_remove.assert_called_once_with(str(dummy_file_path))


@patch("os.makedirs")
@patch("builtins.open")
@patch("httpx.stream")
def test_download_and_extract_ids(mock_stream, mock_open, mock_makedirs):
    """
    Tests downloading a file, saving it, and extracting IDs.
    """
    # Prepare mock data and responses
    df = pd.DataFrame(DF_DATA)
    csv_data = df.to_csv(index=False).encode("utf-8")
    compressed_data = bz2.compress(csv_data)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_bytes.return_value = [compressed_data]

    mock_stream_context = MagicMock()
    mock_stream_context.__enter__.return_value = mock_response
    mock_stream.return_value = mock_stream_context

    mock_file_context = MagicMock()
    mock_open.return_value = mock_file_context

    # We need to mock bz2.open to read our uncompressed data
    with patch("bz2.open", return_value=io.StringIO(df.to_csv(index=False))):
        result = download_and_extract_ids(DATE_STR)

    mock_makedirs.assert_called_once_with(TEMP_DATA_DIR, exist_ok=True)
    mock_stream.assert_called_once_with("GET", f"https://data.everef.net/market-history/{DATE_STR[:4]}/market-history-{DATE_STR}.csv.bz2", follow_redirects=True)
    mock_open.assert_called_once_with(FILE_PATH, "wb")

    assert result["file_path"] == FILE_PATH
    assert result["date"] == DATE_STR
    assert result["region_ids"] == [10000002]
    assert result["type_ids"] == [34]


@patch("app.tasks.data_fetching.chord")
@patch("app.tasks.data_fetching.group")
def test_dispatch_market_history_tasks(mock_group, mock_chord):
    """
    Tests that dispatch_market_history_tasks creates a chord with the correct
    header and callback, and that the workflow is delayed.
    """
    processing_info = [{"file_path": FILE_PATH, "date": DATE_STR}]

    # Mock the signature for the analysis task
    mock_analysis_sig = MagicMock()
    with patch(
        "app.tasks.data_fetching.perform_market_analysis.si",
        return_value=mock_analysis_sig,
    ):
        dispatch_market_history_tasks(processing_info)

    # Check that a group of tasks was created for the header
    mock_group.assert_called_once()
    tasks_list = list(mock_group.call_args.args[0])
    assert len(tasks_list) == 1
    task_sig = tasks_list[0]
    assert task_sig.immutable is True
    assert task_sig.args == (FILE_PATH, DATE_STR)

    # Check that the chord was created with the group and the analysis callback
    mock_chord.assert_called_once_with(mock_group.return_value, mock_analysis_sig)
    mock_chord.return_value.delay.assert_called_once()


@patch("app.tasks.data_fetching.chord")
@patch("app.tasks.data_fetching.dispatch_market_history_tasks.si")
@patch("app.tasks.data_fetching.crud.get_existing_type_ids", return_value=set())
@patch("app.tasks.data_fetching.crud.get_existing_region_ids", return_value=set())
def test_aggregate_and_dispatch_dependencies(mock_get_regions, mock_get_types, mock_dispatch_sig, mock_chord, db_session):
    """
    Tests that the aggregator correctly uses a chord with the correct file path info.
    """
    results = [
        {"region_ids": [1, 2], "type_ids": [10, 11], "file_path": "/path/1", "date": "2023-01-01"},
        {"region_ids": [], "type_ids": [], "file_path": None, "date": "2023-01-02"}, # Failed download
    ]

    aggregate_and_dispatch_dependencies(results)

    mock_chord.assert_called_once()
    kwargs = mock_chord.call_args.kwargs

    # Check the header of the chord (dependency creation tasks)
    header_group = kwargs['header']
    assert len(header_group.tasks) == 4 # 2 regions, 2 types

    # Check the body of the chord (dispatching history processing)
    mock_dispatch_sig.assert_called_once_with(
        processing_info=[{"file_path": "/path/1", "date": "2023-01-01"}]
    )
    assert kwargs['body'] == mock_dispatch_sig.return_value
    mock_chord.return_value.delay.assert_called_once()


@patch("app.tasks.data_fetching.chord")
@patch("app.tasks.data_fetching.group")
def test_orchestrate_market_data_load(mock_group, mock_chord):
    dates = ["2023-01-01", "2023-01-02"]

    # Mock the signature object that will be created
    mock_aggregator_sig = MagicMock()
    with patch("app.tasks.data_fetching.aggregate_and_dispatch_dependencies.s", return_value=mock_aggregator_sig):
        orchestrate_market_data_load(dates)

    # Assert that a group of download tasks was created
    mock_group.assert_called_once()
    download_call_args = mock_group.call_args_list[0].args[0]
    assert len(list(download_call_args)) == 2

    # Assert that the chord was created with the download group and the aggregator callback
    mock_chord.assert_called_once_with(header=mock_group.return_value, body=mock_aggregator_sig)
    mock_chord.return_value.delay.assert_called_once()