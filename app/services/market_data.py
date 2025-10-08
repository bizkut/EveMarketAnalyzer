import asyncio
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from app.database import SessionLocal
from app.models.market_data import Region, ItemType, MarketHistory
from app.services.api_client import esi_client, everef_client
from datetime import datetime

async def update_regions():
    db: Session = next(SessionLocal())
    try:
        region_ids = await esi_client.get_regions()
        tasks = [esi_client.get_region_info(region_id) for region_id in region_ids]
        regions_info = await asyncio.gather(*tasks)

        for region_info in regions_info:
            stmt = insert(Region).values(
                region_id=region_info['region_id'],
                name=region_info['name']
            ).on_conflict_do_nothing()
            db.execute(stmt)
        db.commit()
    finally:
        db.close()

async def update_item_types_for_region(region_id: int):
    db: Session = next(SessionLocal())
    try:
        type_ids = await esi_client.get_type_ids_in_region(region_id)

        # Fetch existing type_ids to avoid re-fetching info
        existing_type_ids = {row[0] for row in db.query(ItemType.type_id).all()}
        new_type_ids = [tid for tid in type_ids if tid not in existing_type_ids]

        tasks = [esi_client.get_type_info(type_id) for type_id in new_type_ids]
        types_info = await asyncio.gather(*tasks)

        for type_info in types_info:
            stmt = insert(ItemType).values(
                type_id=type_info['type_id'],
                name=type_info['name']
            ).on_conflict_do_nothing()
            db.execute(stmt)
        db.commit()
    finally:
        db.close()

async def update_all_item_types():
    db: Session = next(SessionLocal())
    try:
        region_ids = [row[0] for row in db.query(Region.region_id).all()]
        await asyncio.gather(*(update_item_types_for_region(rid) for rid in region_ids))
    finally:
        db.close()


async def update_market_history():
    db: Session = next(SessionLocal())
    try:
        urls = await everef_client.get_market_history_urls()

        for url in urls:
            market_data_df = await everef_client.download_and_decompress_bz2(url)

            # Convert date column to datetime objects
            market_data_df['date'] = pd.to_datetime(market_data_df['date'])

            # Prepare data for bulk insert
            records = market_data_df.to_dict('records')

            if records:
                stmt = insert(MarketHistory).values(records)
                stmt = stmt.on_conflict_do_update(
                    constraint='_date_region_type_uc',
                    set_={
                        'average': stmt.excluded.average,
                        'highest': stmt.excluded.highest,
                        'lowest': stmt.excluded.lowest,
                        'order_count': stmt.excluded.order_count,
                        'volume': stmt.excluded.volume,
                    }
                )
                db.execute(stmt)
                db.commit()
    finally:
        db.close()