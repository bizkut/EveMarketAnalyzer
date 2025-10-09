import redis
from .config import settings

# Initialize the Redis client from the URL in the settings
redis_client = redis.from_url(settings.REDIS_URL)