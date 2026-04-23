"""Unit tests for short_id.py — no DB required."""

import re
import uuid

import pytest

from contexthub_backend.db.short_id import (
    _encode,
    _ALPHABET,
    _PAD,
    short_id_from_uuid,
    new_uuid_and_short_id,
    uuid7,
)


class TestUuid7:
    def test_version_field(self):
        uid = uuid7()
        assert uid.version == 7

    def test_time_ordered_across_ms(self):
        import time
        # Generate pairs separated by at least 1ms; leading 48 bits must be ≤
        uid_early = uuid7()
        time.sleep(0.002)  # 2ms gap
        uid_late = uuid7()
        ts_early = uid_early.int >> 80
        ts_late = uid_late.int >> 80
        assert ts_early <= ts_late, "UUIDv7 timestamp component must be non-decreasing"

    def test_unique(self):
        ids = {uuid7() for _ in range(1000)}
        assert len(ids) == 1000


class TestEncode:
    def test_zero(self):
        result = _encode(0)
        assert result == _ALPHABET[0] * _PAD

    def test_length(self):
        # 2^64 - 1 should fit in _PAD chars
        max_64 = (1 << 64) - 1
        assert len(_encode(max_64)) == _PAD

    def test_charset(self):
        for _ in range(200):
            uid = uuid7()
            sid = short_id_from_uuid(uid)
            assert re.fullmatch(r"[0-9A-Za-z]+", sid), f"Bad chars in {sid}"

    def test_pad_to_eleven(self):
        # small values should be left-padded
        result = _encode(1)
        assert len(result) == _PAD
        assert result.startswith(_ALPHABET[0] * (_PAD - 1))


class TestShortIdFromUuid:
    def test_deterministic(self):
        uid = uuid.UUID("01960000-0000-7000-8000-000000000001")
        s1 = short_id_from_uuid(uid)
        s2 = short_id_from_uuid(uid)
        assert s1 == s2

    def test_length(self):
        for _ in range(50):
            uid = uuid7()
            assert len(short_id_from_uuid(uid)) == _PAD

    def test_different_uuids_different_ids(self):
        ids = {short_id_from_uuid(uuid7()) for _ in range(200)}
        assert len(ids) == 200


class TestNewUuidAndShortId:
    def test_returns_tuple(self):
        uid, sid = new_uuid_and_short_id()
        assert isinstance(uid, uuid.UUID)
        assert isinstance(sid, str)
        assert len(sid) == _PAD

    def test_short_id_derives_from_uuid(self):
        uid, sid = new_uuid_and_short_id()
        assert sid == short_id_from_uuid(uid)
