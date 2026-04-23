"""Base62 short ID encoder for workspace URLs (/w/{short_id}).

Encodes the lower 64 bits of a UUIDv7 as an 11-character base62 string.
Collision probability is negligible at v0 scale (~50–100 beta users).
"""

import time
import random
import uuid

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_BASE = 62
_PAD = 11  # ceil(log62(2^64)) = 11


def uuid7() -> uuid.UUID:
    """Generate a UUID version 7 (time-ordered, random tail)."""
    ts_ms = int(time.time() * 1000)
    rand_a = random.getrandbits(12)
    rand_b = random.getrandbits(62)
    value = (ts_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)


def _encode(num: int) -> str:
    if num == 0:
        return _ALPHABET[0] * _PAD
    chars: list[str] = []
    while num:
        chars.append(_ALPHABET[num % _BASE])
        num //= _BASE
    result = "".join(reversed(chars))
    return result.rjust(_PAD, _ALPHABET[0])


def short_id_from_uuid(uid: uuid.UUID) -> str:
    """Return the ~11-char base62 short ID for a UUID (lower 64 bits)."""
    return _encode(uid.int & 0xFFFF_FFFF_FFFF_FFFF)


def new_uuid_and_short_id() -> tuple[uuid.UUID, str]:
    """Generate a new UUIDv7 and its base62 short ID together."""
    uid = uuid7()
    return uid, short_id_from_uuid(uid)
