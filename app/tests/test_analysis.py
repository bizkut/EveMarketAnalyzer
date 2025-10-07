import pytest
from datetime import datetime, timedelta
import pandas as pd
from unittest.mock import patch, MagicMock

from app.tasks.analysis import analyze_market_data
from app.models import MarketHistory, AnalyzedItem, ItemType, Region

@pytest.fixture
def mock_db_session():
    """Pytest fixture for a mock SQLAlchemy session."""
    with patch('app.tasks.analysis.get_db') as mock_get_db:
        mock_session = MagicMock()
        mock_get_db.return_value = mock_session

        # Mock the query results for various models
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session.query.return_value.all.return_value = []
        mock_session.query.return_value.first.return_value = None

        yield mock_session

def test_analyze_market_data_no_history(mock_db_session):
    """Test that analysis task handles no market history."""
    with patch('pandas.read_sql') as mock_read_sql:
        mock_read_sql.return_value = pd.DataFrame()
        analyze_market_data()
        mock_db_session.query.assert_called_once_with(MarketHistory)
        mock_db_session.commit.assert_not_called()

def create_mock_market_history(days_ago, type_id, region_id, price, volume, orders):
    """Helper to create a single MarketHistory record."""
    return MarketHistory(
        type_id=type_id,
        region_id=region_id,
        date=datetime.utcnow() - timedelta(days=days_ago),
        average=price,
        highest=price + 5,
        lowest=price - 5,
        order_count=orders,
        volume=volume
    )

def test_analyze_market_data_full_run(mock_db_session):
    """Test a full run of the analysis task with mock data."""
    # Mock ItemType data
    mock_item_types = [ItemType(id=1, name='Item A'), ItemType(id=2, name='Item B')]

    # Mock MarketHistory data
    mock_history_data = [
        # Item 1, Region 1 - High Volume
        create_mock_market_history(1, 1, 1, 100, 10000, 50),
        create_mock_market_history(2, 1, 1, 98, 9500, 45),
        # Item 2, Region 1 - High Orders
        create_mock_market_history(1, 2, 1, 50, 200, 500),
        create_mock_market_history(2, 2, 1, 52, 210, 490),
        # Item 1, Region 2 - High Profit Margin
        create_mock_market_history(1, 1, 2, 200, 100, 10), # high price, low vol/orders
        create_mock_market_history(2, 1, 2, 205, 110, 12),
    ]

    # Setup mock returns
    with patch('pandas.read_sql') as mock_read_sql:
        mock_read_sql.return_value = pd.DataFrame([h.__dict__ for h in mock_history_data])

        # This is for the ItemType query
        mock_db_session.query.return_value.all.return_value = mock_item_types

        # Run the task
        analyze_market_data()

        # Verifications
        assert mock_db_session.query(AnalyzedItem).delete.call_count == 1
        assert mock_db_session.commit.call_count == 2 # Once for delete, once for save

        # Check what was saved
        saved_objects = mock_db_session.bulk_save_objects.call_args[0][0]
        assert len(saved_objects) > 0

        df = pd.DataFrame([o.__dict__ for o in saved_objects])

        # Check ranks for Item 1, Region 1 (High Volume)
        item1_region1 = df[(df['type_id'] == 1) & (df['region_id'] == 1)]
        assert not item1_region1.empty
        assert item1_region1.iloc[0]['volume_rank'] == 1.0

        # Check ranks for Item 2, Region 1 (High Orders)
        item2_region1 = df[(df['type_id'] == 2) & (df['region_id'] == 1)]
        assert not item2_region1.empty
        assert item2_region1.iloc[0]['order_count_rank'] == 1.0

        # Check ranks for Item 1, Region 2 (High Profit)
        item1_region2 = df[(df['type_id'] == 1) & (df['region_id'] == 2)]
        assert not item1_region2.empty
        assert item1_region2.iloc[0]['profit_margin_rank'] == 3.0

        # Check price stability (item1_region2 has lower relative price change, so higher stability)
        assert item1_region2.iloc[0]['price_stability'] > item2_region1.iloc[0]['price_stability']