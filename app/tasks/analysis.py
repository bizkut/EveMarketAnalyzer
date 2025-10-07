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
        return prices[-1] if prices else 0

    X = pd.to_numeric(dates).values.reshape(-1, 1)
    y = prices.values

    model = LinearRegression()
    model.fit(X, y)

    next_date = (dates.max() + timedelta(days=1)).toordinal()
    return model.predict([[next_date]])[0]

@celery_app.task
def analyze_market_data():
    logger.info("Starting market data analysis...")
    db = get_db()
    try:
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        # Fetch all necessary data in one go
        all_history = db.query(MarketHistory).filter(MarketHistory.date >= thirty_days_ago).all()
        all_item_types = {item.id: item for item in db.query(ItemType).all()}
        all_regions = {region.id: region for region in db.query(Region).all()}

        if not all_history:
            logger.warning("No market history data found to analyze.")
            return

        df = pd.DataFrame([h.__dict__ for h in all_history])
        df['date'] = pd.to_datetime(df['date'])

        # Group by item and region for analysis
        grouped = df.groupby(['type_id', 'region_id'])

        analyzed_results = []
        for (type_id, region_id), group in grouped:
            if group.empty:
                continue

            # Sort by date to ensure correct calculations
            group = group.sort_values('date').reset_index()

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
        db.query(AnalyzedItem).delete() # Clear old analysis
        db.commit()

        # Convert to list of model objects and bulk insert
        analyzed_objects = [AnalyzedItem(**data) for data in analyzed_results]
        db.bulk_save_objects(analyzed_objects)
        db.commit()

        logger.info(f"Market data analysis completed. Saved {len(analyzed_results)} records.")

    except Exception as e:
        logger.error(f"An error occurred during market data analysis: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()