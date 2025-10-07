import logging
import pandas as pd
from sklearn.linear_model import LinearRegression
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import MarketHistory, AnalyzedItem, ItemType
from app.tasks.worker import celery_app
from datetime import datetime, timedelta
from ast import literal_eval

logger = logging.getLogger(__name__)

def get_db() -> Session:
    return SessionLocal()

def predict_price(dates, prices):
    if len(dates) < 2:
        return prices.iloc[-1] if not prices.empty else 0
    X = pd.to_numeric(dates).values.reshape(-1, 1)
    y = prices.values
    model = LinearRegression().fit(X, y)
    next_date = (dates.max() + timedelta(days=1)).toordinal()
    return model.predict([[next_date]])[0]

@celery_app.task
def analyze_market_data(previous_result=None):
    logger.info("Starting market data analysis...")
    db = get_db()
    try:
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        history_query = db.query(MarketHistory).filter(MarketHistory.date >= thirty_days_ago)
        all_history_df = pd.read_sql(history_query.statement, db.bind)

        if all_history_df.empty:
            logger.warning("No recent market history found to analyze.")
            return

        all_item_types = {item.id: item for item in db.query(ItemType).all()}

        # Group by item and region to perform calculations
        grouped = all_history_df.groupby(['type_id', 'region_id'])

        analyzed_results = []
        for (type_id, region_id), group in grouped:
            group = group.copy()
            group['date'] = pd.to_datetime(group['date'])
            group = group.sort_values('date')

            latest = group.iloc[-1]

            # Calculations
            avg_daily_volume = group['volume'].mean()
            volatility_30d = group['average'].std() / group['average'].mean() if group['average'].mean() > 0 else 0
            price_stability = 1 - volatility_30d if volatility_30d < 1 else 0.0

            profit_per_unit = latest['highest'] - latest['lowest']

            # Enhanced profit margin score
            profit_margin_score = profit_per_unit * latest['volume'] * latest['order_count']

            item_info = all_item_types.get(type_id)
            if not item_info:
                continue

            analyzed_results.append({
                'type_id': type_id,
                'region_id': region_id,
                'item_name': item_info.name,
                'avg_buy_price': latest['lowest'],
                'avg_sell_price': latest['highest'],
                'predicted_buy_price': predict_price(group['date'], group['lowest']),
                'predicted_sell_price': predict_price(group['date'], group['highest']),
                'profit_per_unit': profit_per_unit,
                'roi_percent': (profit_per_unit / latest['lowest']) * 100 if latest['lowest'] > 0 else 0,
                'avg_daily_volume': avg_daily_volume,
                'volatility_30d': volatility_30d,
                'price_stability': price_stability,
                'trend_direction': 0, # Placeholder, can be enhanced
                'last_updated': datetime.utcnow(),
                'order_count': latest['order_count'],
                'volume': latest['volume'],
                'profit_margin_score': profit_margin_score
            })

        if not analyzed_results:
            logger.info("No data to save after analysis.")
            return

        # Create a DataFrame for ranking
        analysis_df = pd.DataFrame(analyzed_results)

        # Rank items
        analysis_df['order_count_rank'] = analysis_df['order_count'].rank(method='first', ascending=False)
        analysis_df['volume_rank'] = analysis_df['volume'].rank(method='first', ascending=False)
        analysis_df['profit_margin_rank'] = analysis_df['profit_margin_score'].rank(method='first', ascending=False)

        # Filter for top 100 in each category to keep DB clean
        top_orders = analysis_df.nsmallest(100, 'order_count_rank')
        top_volume = analysis_df.nsmallest(100, 'volume_rank')
        top_profit = analysis_df.nsmallest(100, 'profit_margin_rank')

        # Combine and remove duplicates
        final_df = pd.concat([top_orders, top_volume, top_profit]).drop_duplicates(subset=['type_id', 'region_id'])

        # Drop temporary columns
        final_df = final_df.drop(columns=['order_count', 'volume', 'profit_margin_score'])

        # Bulk insert/update
        logger.info("Clearing old analyzed data...")
        db.query(AnalyzedItem).delete()
        db.commit()

        logger.info(f"Saving {len(final_df)} new analysis records...")
        analyzed_objects = [AnalyzedItem(**row) for row in final_df.to_dict('records')]
        db.bulk_save_objects(analyzed_objects)
        db.commit()

        logger.info("Market data analysis completed successfully.")

    except Exception as e:
        logger.error(f"An error occurred during market data analysis: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()