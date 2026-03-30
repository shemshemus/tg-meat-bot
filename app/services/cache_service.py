import json
import logging

import redis

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def init_redis(url: str) -> None:
    """Connect to Redis. Call once at startup."""
    global _client
    try:
        _client = redis.from_url(url, decode_responses=True)
        _client.ping()
        logger.info("Redis connected: %s", url)
    except Exception:
        logger.warning("Redis unavailable — caching disabled")
        _client = None


def get_client() -> redis.Redis | None:
    return _client


# ──────────────────────────────────────────────
# Generic JSON cache helpers
# ──────────────────────────────────────────────

def cache_get(key: str):
    """Get a JSON-decoded value from Redis, or None on miss/error."""
    try:
        if not _client:
            return None
        raw = _client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.debug("cache_get(%s) failed", key)
        return None


def cache_set(key: str, value, ttl: int) -> None:
    """Store a JSON-encoded value in Redis with TTL in seconds."""
    try:
        if not _client:
            return
        _client.setex(key, ttl, json.dumps(value))
    except Exception:
        logger.debug("cache_set(%s) failed", key)


def cache_delete(*keys: str) -> None:
    """Delete one or more keys from Redis."""
    try:
        if not _client or not keys:
            return
        _client.delete(*keys)
    except Exception:
        logger.debug("cache_delete(%s) failed", keys)


# ──────────────────────────────────────────────
# User language (Redis hash: user:languages)
# ──────────────────────────────────────────────

def set_user_language(user_id: int, lang: str) -> None:
    try:
        if not _client:
            return
        _client.hset("user:languages", str(user_id), lang)
    except Exception:
        logger.debug("set_user_language failed for %s", user_id)


def get_user_language(user_id: int) -> str | None:
    try:
        if not _client:
            return None
        return _client.hget("user:languages", str(user_id))
    except Exception:
        logger.debug("get_user_language failed for %s", user_id)
        return None


def get_all_user_languages() -> dict[int, str]:
    try:
        if not _client:
            return {}
        raw = _client.hgetall("user:languages")
        return {int(uid): lang for uid, lang in raw.items()}
    except Exception:
        logger.debug("get_all_user_languages failed")
        return {}


# ──────────────────────────────────────────────
# Known users (Redis set: promo:users)
# ──────────────────────────────────────────────

def add_known_user(user_id: int) -> None:
    try:
        if not _client:
            return
        _client.sadd("promo:users", str(user_id))
    except Exception:
        logger.debug("add_known_user failed for %s", user_id)


def get_known_users() -> set[int]:
    try:
        if not _client:
            return set()
        members = _client.smembers("promo:users")
        return {int(uid) for uid in members}
    except Exception:
        logger.debug("get_known_users failed")
        return set()


# ──────────────────────────────────────────────
# Last promo product ID
# ──────────────────────────────────────────────

def set_last_promo_product(product_id: int) -> None:
    try:
        if not _client:
            return
        _client.set("promo:last_product_id", str(product_id))
    except Exception:
        logger.debug("set_last_promo_product failed")


def get_last_promo_product() -> int | None:
    try:
        if not _client:
            return None
        val = _client.get("promo:last_product_id")
        return int(val) if val is not None else None
    except Exception:
        logger.debug("get_last_promo_product failed")
        return None


# ──────────────────────────────────────────────
# User contact info (Redis hash: user:phones, user:addresses)
# ──────────────────────────────────────────────

def set_user_phone(user_id: int, phone: str) -> None:
    try:
        if not _client:
            return
        _client.hset("user:phones", str(user_id), phone)
    except Exception:
        logger.debug("set_user_phone failed for %s", user_id)


def get_user_phone(user_id: int) -> str | None:
    try:
        if not _client:
            return None
        return _client.hget("user:phones", str(user_id))
    except Exception:
        logger.debug("get_user_phone failed for %s", user_id)
        return None


def set_user_address(user_id: int, address: str) -> None:
    try:
        if not _client:
            return
        _client.hset("user:addresses", str(user_id), address)
    except Exception:
        logger.debug("set_user_address failed for %s", user_id)


def get_user_address(user_id: int) -> str | None:
    try:
        if not _client:
            return None
        return _client.hget("user:addresses", str(user_id))
    except Exception:
        logger.debug("get_user_address failed for %s", user_id)
        return None
