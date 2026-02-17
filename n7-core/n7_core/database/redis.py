from redis.asyncio import Redis, from_url

from ..config import settings

redis_client: Redis = from_url(str(settings.REDIS_URL), decode_responses=True)


async def get_redis() -> Redis:
    return redis_client
