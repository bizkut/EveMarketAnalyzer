import logging
import pandas as pd
from sklearn.linear_model import LinearRegression
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import MarketHistory, AnalyzedItem, ItemType, Region
from app.tasks.worker import celery_app
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def get_db() -> Session:
    return SessionLocal()

def predict_price(dates, prices):
    """Predicts the next price point using linear regression."""
    if len(dates) < 2:
        return prices.iloc[-1] if not prices.empty else 0

    X = pd.to_numeric(dates).values.reshape(-1, 1)
    y = prices.values

    model = LinearRegression()
    model.fit(X, y)

    next_date = (dates.max() + timedelta(days=1)).toordinal()
    return model.predict([[next_date]])[0]

@celery_app.task
def analyze_market_data(previous_result=None):
    logger.info("Starting market data analysis...")
    db = get_db()
    try:
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        # Get unique combinations of (type_id, region_id) from recent history
        # This is much more memory-efficient than loading all history at once.
        item_region_pairs = db.query(
            MarketHistory.type_id,
            MarketHistory.region_id
        ).filter(
            MarketHistory.date >= thirty_days_ago
        ).distinct().all()

        if not item_region_pairs:
            logger.warning("No recent market history found to analyze.")
            return

        logger.info(f"Found {len(item_region_pairs)} item-region pairs to analyze.")

        # Fetch all item types into a map for quick lookups
        all_item_types = {item.id: item for item in db.query(ItemType).all()}

        analyzed_results = []
        for i, (type_id, region_id) in enumerate(item_region_pairs):
            if (i + 1) % 100 == 0:
                logger.info(f"Analyzing pair {i + 1}/{len(item_region_pairs)}...")

            # Fetch history for this specific pair
            history_records = db.query(MarketHistory).filter(
                MarketHistory.type_id == type_id,
                MarketHistory.region_id == region_id,
                MarketHistory.date >= thirty_days_ago
            ).order_by(MarketHistory.date).all()

            if not history_records:
                continue

            group = pd.DataFrame([h.__dict__ for h in history_records])
            group['date'] = pd.to_datetime(group['date'])

            # Basic stats from the most recent day
            latest_record = group.iloc[-1]
            avg_buy_price = latest_record['lowest']
            avg_sell_price = latest_record['highest']

            # Profitability
            profit_per_unit = avg_sell_price - avg_buy_price
            roi_percent = (profit_per_unit / avg_buy_price) * 100 if avg_buy_price > 0 else 0

            # Volume and Volatility
            avg_daily_volume = group['volume'].mean()
            volatility_30d = group['average'].std() / group['average'].mean() if group['average'].mean() > 0 else 0

            # Trend Direction
            if len(group) > 1:
                X = group['date'].apply(lambda d: d.toordinal()).values.reshape(-1, 1)
                y = group['average'].values
                model = LinearRegression().fit(X, y)
                trend_direction = 1 if model.coef_[0] > 0 else -1
            else:
                trend_direction = 0

            # Price Prediction
            predicted_buy_price = predict_price(group['date'], group['lowest'])
            predicted_sell_price = predict_price(group['date'], group['highest'])

            item_info = all_item_types.get(type_id)
            if not item_info:
                logger.warning(f"No item type found for type_id: {type_id}")
                continue

            analyzed_results.append({
                'type_id': type_id,
                'region_id': region_id,
                'item_name': item_info.name,
                'avg_buy_price': avg_buy_price,
                'avg_sell_price': avg_sell_price,
                'predicted_buy_price': predicted_buy_price,
                'predicted_sell_price': predicted_sell_price,
                'profit_per_unit': profit_per_unit,
                'roi_percent': roi_percent,
                'avg_daily_volume': avg_daily_volume,
                'volatility_30d': volatility_30d,
                'trend_direction': trend_direction,
                'last_updated': datetime.utcnow()
            })

        if not analyzed_results:
            logger.info("No data to save after analysis.")
            return

        # Bulk insert/update
        logger.info("Clearing old analyzed data...")
        db.query(AnalyzedItem).delete()
        db.commit()

        logger.info(f"Saving {len(analyzed_results)} new analysis records...")
        analyzed_objects = [AnalyzedItem(**data) for data in analyzed_results]
        db.bulk_save_objects(analyzed_objects)
        db.commit()

        logger.info("Market data analysis completed successfully.")

    except Exception as e:
        logger.error(f"An error occurred during market data analysis: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()