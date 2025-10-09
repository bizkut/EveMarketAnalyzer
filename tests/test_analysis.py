import pytest
from datetime import date
from sqlalchemy.orm import Session
from unittest.mock import patch

from app import crud, models, schemas
from app.tasks.analysis import perform_market_analysis


def test_perform_market_analysis(db_session: Session):
    """
    Tests that the market analysis task correctly calculates and stores analysis data.
    """
    # 1. Setup: Create prerequisite data
    region = crud.get_or_create_region(
        db_session, schemas.RegionCreate(region_id=1, name="The Forge")
    )
    type_ = crud.get_or_create_type(
        db_session, schemas.EveTypeCreate(type_id=1, name="Tritanium")
    )

    # Add market history to be analyzed
    history_data = [
        schemas.MarketHistoryCreate(
            date=date(2023, 1, 1), average=10, highest=20, lowest=10,
            order_count=10, volume=100, region_id=region.region_id, type_id=type_.type_id
        ),
        schemas.MarketHistoryCreate(
            date=date(2023, 1, 2), average=12, highest=22, lowest=12,
            order_count=12, volume=120, region_id=region.region_id, type_id=type_.type_id
        ),
    ]
    crud.create_bulk_market_history(db_session, history_data)

    # 2. Execution: Run the analysis task, patching SessionLocal to use the test DB
    with patch("app.tasks.analysis.SessionLocal", return_value=db_session):
        perform_market_analysis()

    # 3. Assertion: Verify the results in the database
    analysis_results = db_session.query(models.MarketAnalysis).all()
    assert len(analysis_results) == 1

    result = analysis_results[0]
    assert result.type_id == 1
    assert result.region_id == 1
    assert result.demand == pytest.approx(110)
    assert result.profit_margin == pytest.approx(90.9090909090909)


def test_create_or_update_market_analysis(db_session: Session):
    """
    Tests the 'upsert' functionality of the market analysis CRUD function.
    """
    # 1. Setup
    region = crud.get_or_create_region(
        db_session, schemas.RegionCreate(region_id=1, name="The Forge")
    )
    type_ = crud.get_or_create_type(
        db_session, schemas.EveTypeCreate(type_id=1, name="Tritanium")
    )

    # 2. Initial Creation
    initial_analysis = [
        schemas.MarketAnalysisCreate(
            type_id=type_.type_id,
            region_id=region.region_id,
            demand=100,
            profit_margin=50.0,
        )
    ]
    crud.create_or_update_market_analysis(db_session, initial_analysis)

    # 3. Assertion after creation
    created_record = db_session.query(models.MarketAnalysis).one()
    assert created_record.demand == 100
    assert created_record.profit_margin == 50.0

    # 4. Update with new data
    updated_analysis = [
        schemas.MarketAnalysisCreate(
            type_id=type_.type_id,
            region_id=region.region_id,
            demand=150,
            profit_margin=75.0,
        )
    ]
    crud.create_or_update_market_analysis(db_session, updated_analysis)

    # 5. Assertion after update
    db_session.expire_all()  # Ensure we get fresh data from the DB
    updated_record = db_session.query(models.MarketAnalysis).one()
    assert updated_record.demand == 150
    assert updated_record.profit_margin == 75.0

    # Ensure no new record was created
    assert db_session.query(models.MarketAnalysis).count() == 1