import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from app.models.market_data import MarketHistory, AnalyzedItem, ItemType
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime, timedelta
from app.services.prediction import train_and_predict

def calculate_metrics(df: pd.DataFrame, region_id: int, type_id: int, item_name: str):
    """
    Calculates various financial metrics for a given item's market history.
    """
    if df.empty:
        return None

    df = df.sort_values('date').reset_index(drop=True)

    last_30_days = df[df['date'] >= (df['date'].max() - pd.Timedelta(days=30))]

    if last_30_days.empty:
        return None

    avg_daily_volume = last_30_days['volume'].mean()
    avg_buy_price = last_30_days['lowest'].mean()
    avg_sell_price = last_30_days['highest'].mean()
    volatility_30d = last_30_days['average'].std()

    tax_and_broker_fee = avg_sell_price * 0.05
    profit_per_unit = avg_sell_price - avg_buy_price - tax_and_broker_fee
    roi_percent = (profit_per_unit / avg_buy_price) * 100 if avg_buy_price > 0 else 0

    if len(last_30_days) > 1:
        price_slope = np.polyfit(range(len(last_30_days)), last_30_days['average'], 1)[0]
        trend_direction = 1 if price_slope > 0.05 else -1 if price_slope < -0.05 else 0
    else:
        trend_direction = 0

    return {
        "type_id": type_id,
        "region_id": region_id,
        "item_name": item_name,
        "avg_buy_price": avg_buy_price,
        "avg_sell_price": avg_sell_price,
        "profit_per_unit": profit_per_unit,
        "roi_percent": roi_percent,
        "avg_daily_volume": avg_daily_volume,
        "volatility_30d": volatility_30d,
        "trend_direction": trend_direction,
    }

def analyze_and_store_market_data(db: Session):
    """
    Fetches market history, analyzes it, runs predictions, and stores the results.
    """
    today = datetime.utcnow().date()
    start_date = today - timedelta(days=360)

    item_types = {it.type_id: it.name for it in db.query(ItemType).all()}
    pairs = db.query(MarketHistory.region_id, MarketHistory.type_id).distinct().all()

    for region_id, type_id in pairs:
        history_records = db.query(MarketHistory).filter(
            MarketHistory.region_id == region_id,
            MarketHistory.type_id == type_id,
            MarketHistory.date >= start_date
        ).order_by(MarketHistory.date).all()

        if not history_records:
            continue

        history_df = pd.DataFrame([h.__dict__ for h in history_records])
        history_df['date'] = pd.to_datetime(history_df['date'])

        item_name = item_types.get(type_id, "Unknown Item")
        metrics = calculate_metrics(history_df, region_id, type_id, item_name)

        if metrics:
            predictions = train_and_predict(history_df)
            metrics['predicted_buy_price'] = predictions.get('predicted_buy_price')
            metrics['predicted_sell_price'] = predictions.get('predicted_sell_price')
            metrics['last_updated'] = datetime.utcnow()

            stmt = insert(AnalyzedItem).values(metrics)
            stmt = stmt.on_conflict_do_update(
                constraint='_type_region_uc',
                set_={
                    'item_name': stmt.excluded.item_name,
                    'avg_buy_price': stmt.excluded.avg_buy_price,
                    'avg_sell_price': stmt.excluded.avg_sell_price,
                    'profit_per_unit': stmt.excluded.profit_per_unit,
                    'roi_percent': stmt.excluded.roi_percent,
                    'avg_daily_volume': stmt.excluded.avg_daily_volume,
                    'volatility_30d': stmt.excluded.volatility_30d,
                    'trend_direction': stmt.excluded.trend_direction,
                    'predicted_buy_price': stmt.excluded.predicted_buy_price,
                    'predicted_sell_price': stmt.excluded.predicted_sell_price,
                    'last_updated': stmt.excluded.last_updated,
                }
            )
            db.execute(stmt)

    db.commit()