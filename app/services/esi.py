import aiohttp
import asyncio
from tenacity import retry, stop_after_attempt, wait_fixed
from app.core.config import settings
import logging

# Configure logging
logging.basicConfig(level=settings.LOG_LEVEL.upper())
logger = logging.getLogger(__name__)

BASE_URL = "https://esi.evetech.net/latest"

class EsiService:
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def _request(self, session, url):
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Request to {url} failed: {e}")
            raise

    async def get_regions(self):
        url = f"{BASE_URL}/universe/regions/"
        async with aiohttp.ClientSession() as session:
            return await self._request(session, url)

    async def get_region_details(self, region_id: int):
        url = f"{BASE_URL}/universe/regions/{region_id}/"
        async with aiohttp.ClientSession() as session:
            return await self._request(session, url)

    async def get_type_ids_in_region(self, region_id: int):
        url = f"{BASE_URL}/markets/{region_id}/types/"
        async with aiohttp.ClientSession() as session:
            return await self._request(session, url)

    async def get_market_history(self, type_id: int, region_id: int):
        url = f"{BASE_URL}/markets/{region_id}/history/?type_id={type_id}"
        async with aiohttp.ClientSession() as session:
            return await self._request(session, url)

    async def get_type_details(self, type_id: int):
        url = f"{BASE_URL}/universe/types/{type_id}/"
        async with aiohttp.ClientSession() as session:
            data = await self._request(session, url)
            icon_url = f"https://images.evetech.net/types/{type_id}/icon"
            data['icon_url'] = icon_url
            return data

esi_service = EsiService()