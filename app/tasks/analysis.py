import logging

from celery import shared_task
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import crud, models, schemas
from ..database import SessionLocal

logger = logging.getLogger(__name__)


@shared_task
def perform_market_analysis():
    """
    Performs market analysis and stores the results in the database.
    """
    db: Session = SessionLocal()
    try:
        logger.info("Starting market analysis...")

        # Calculate average volume (demand) and average high/low prices
        analysis_query = (
            db.query(
                models.MarketHistory.type_id,
                models.MarketHistory.region_id,
                func.avg(models.MarketHistory.volume).label("demand"),
                func.avg(models.MarketHistory.highest).label("avg_highest"),
                func.avg(models.MarketHistory.lowest).label("avg_lowest"),
            )
            .group_by(
                models.MarketHistory.type_id,
                models.MarketHistory.region_id,
            )
            .all()
        )

        analysis_records = []
        for row in analysis_query:
            profit_margin = 0
            if row.avg_lowest and row.avg_lowest > 0:
                profit_margin = (
                    (row.avg_highest - row.avg_lowest) / row.avg_lowest
                ) * 100

            analysis_records.append(
                schemas.MarketAnalysisCreate(
                    type_id=row.type_id,
                    region_id=row.region_id,
                    demand=row.demand,
                    profit_margin=profit_margin,
                )
            )

        # Bulk create or update the analysis records
        crud.create_or_update_market_analysis(db, analysis_records)

        logger.info(f"Market analysis complete. Updated {len(analysis_records)} records.")
    except Exception as e:
        logger.error(f"An error occurred during market analysis: {e}")
    finally:
        db.close()