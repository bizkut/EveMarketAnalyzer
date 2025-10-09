import pytest
from unittest.mock import patch
from app.main import lifespan


@pytest.mark.anyio
@patch("app.main.perform_market_analysis.delay")
@patch("app.main.initial_data_load.delay")
@patch("app.main.crud.is_analysis_table_empty")
@patch("app.main.crud.is_database_empty")
@patch("app.main.SessionLocal")
@patch("app.main.settings.TESTING", False)
async def test_startup_triggers_analysis_if_table_empty(
    mock_session_local,
    mock_is_db_empty,
    mock_is_analysis_empty,
    mock_initial_load,
    mock_perform_analysis,
    db_session,
):
    """
    Tests that the market analysis task is triggered on startup if the
    market_analysis table is empty, but the main DB is not.
    """
    mock_session_local.return_value = db_session
    mock_is_db_empty.return_value = False
    mock_is_analysis_empty.return_value = True

    async with lifespan(app=None):
        pass  # Startup logic runs on entering the context

    mock_perform_analysis.assert_called_once()
    mock_initial_load.assert_not_called()


@pytest.mark.anyio
@patch("app.main.perform_market_analysis.delay")
@patch("app.main.initial_data_load.delay")
@patch("app.main.crud.is_analysis_table_empty")
@patch("app.main.crud.is_database_empty")
@patch("app.main.SessionLocal")
@patch("app.main.settings.TESTING", False)
async def test_startup_does_not_trigger_analysis_if_table_not_empty(
    mock_session_local,
    mock_is_db_empty,
    mock_is_analysis_empty,
    mock_initial_load,
    mock_perform_analysis,
    db_session,
):
    """
    Tests that the market analysis task is NOT triggered on startup if the
    market_analysis table is not empty.
    """
    mock_session_local.return_value = db_session
    mock_is_db_empty.return_value = False
    mock_is_analysis_empty.return_value = False

    async with lifespan(app=None):
        pass

    mock_perform_analysis.assert_not_called()
    mock_initial_load.assert_not_called()


@pytest.mark.anyio
@patch("app.main.perform_market_analysis.delay")
@patch("app.main.initial_data_load.delay")
@patch("app.main.crud.is_analysis_table_empty")
@patch("app.main.crud.is_database_empty")
@patch("app.main.SessionLocal")
@patch("app.main.settings.TESTING", False)
async def test_startup_triggers_initial_load_and_analysis_if_both_empty(
    mock_session_local,
    mock_is_db_empty,
    mock_is_analysis_empty,
    mock_initial_load,
    mock_perform_analysis,
    db_session,
):
    """
    Tests that both the initial data load and market analysis tasks are
    triggered on startup if both the database and the analysis table are empty.
    """
    mock_session_local.return_value = db_session
    mock_is_db_empty.return_value = True
    mock_is_analysis_empty.return_value = True

    async with lifespan(app=None):
        pass

    mock_perform_analysis.assert_called_once()
    mock_initial_load.assert_called_once()