"""
Threat Intelligence Router.
Exposes IOC cache statistics from Redis.
Ref: TDD Section 4.X TI Fetcher, SRS FR-C011
"""
from fastapi import APIRouter

from ...database.redis import redis_client

router = APIRouter(tags=["Threat Intelligence"])


@router.get("/stats")
async def get_ti_stats():
    """
    Return counts of IOCs currently in the Redis cache, broken down by type.
    Scans Redis for n7:ioc:* keys and counts by type prefix.
    """
    counts = {"ip": 0, "domain": 0, "url": 0, "hash": 0, "other": 0, "total": 0}

    try:
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match="n7:ioc:*", count=1000)
            for key in keys:
                # Key format: n7:ioc:{type}:{value}
                parts = key.split(":", 3)
                if len(parts) >= 3:
                    ioc_type = parts[2]
                    if ioc_type in counts:
                        counts[ioc_type] += 1
                    else:
                        counts["other"] += 1
                counts["total"] += 1
            if cursor == 0:
                break
    except Exception as e:
        return {"status": "error", "error": str(e), "ioc_counts": counts}

    return {"status": "active", "ioc_counts": counts}


@router.get("/lookup")
async def lookup_ioc(ioc_type: str, ioc_value: str):
    """
    Look up a specific IOC in the cache.
    Query params: ioc_type (ip|domain|url|hash), ioc_value
    """
    import json
    key = f"n7:ioc:{ioc_type}:{ioc_value}"
    cached = await redis_client.get(key)
    if cached:
        return {"found": True, "ioc": json.loads(cached)}
    return {"found": False, "ioc_type": ioc_type, "ioc_value": ioc_value}
