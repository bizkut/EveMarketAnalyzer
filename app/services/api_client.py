import aiohttp
import asyncio
import bz2
import pandas as pd
from io import StringIO
from app.core.config import settings
from datetime import datetime, timedelta

class ESIClient:
    def __init__(self):
        self.base_url = settings.ESI_BASE_URL
        self.user_agent = settings.USER_AGENT
        self.headers = {"User-Agent": self.user_agent}

    async def get_regions(self) -> list[int]:
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(f"{self.base_url}/universe/regions/") as response:
                response.raise_for_status()
                return await response.json()

    async def get_region_info(self, region_id: int) -> dict:
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(f"{self.base_url}/universe/regions/{region_id}/") as response:
                response.raise_for_status()
                return await response.json()

    async def get_type_ids_in_region(self, region_id: int) -> list[int]:
        all_type_ids = []
        page = 1
        async with aiohttp.ClientSession(headers=self.headers) as session:
            while True:
                async with session.get(
                    f"{self.base_url}/markets/{region_id}/types/?page={page}"
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    if not data:
                        break
                    all_type_ids.extend(data)

                    pages = int(response.headers.get("X-Pages", 1))
                    if page >= pages:
                        break
                    page += 1
        return all_type_ids

    async def get_type_info(self, type_id: int) -> dict:
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(f"{self.base_url}/universe/types/{type_id}/") as response:
                response.raise_for_status()
                return await response.json()

class EverefClient:
    def __init__(self):
        self.base_url = "https://data.everef.net/market-history"

    async def get_market_history_urls(self) -> list[str]:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/totals.json") as response:
                response.raise_for_status()
                totals = await response.json()

                urls = []
                today = datetime.utcnow().date()
                for i in range(360):
                    day = today - timedelta(days=i)
                    if day.isoformat() in totals:
                        urls.append(f"{self.base_url}/{day.year}/market-history-{day.isoformat()}.csv.bz2")
                return urls

    async def download_and_decompress_bz2(self, url: str) -> pd.DataFrame:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                compressed_data = await response.read()
                decompressed_data = bz2.decompress(compressed_data)
                return pd.read_csv(StringIO(decompressed_data.decode("utf-8")))

esi_client = ESIClient()
everef_client = EverefClient()