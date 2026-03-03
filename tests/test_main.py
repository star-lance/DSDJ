"""Tests for src/main.py — LatestValueChannel, supervised_task."""

import asyncio
import pytest
from src.main import LatestValueChannel


# ---------------------------------------------------------------------------
# LatestValueChannel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_latest_value_channel_basic():
    ch = LatestValueChannel()
    ch.put({"a": 1})
    val = await asyncio.wait_for(ch.get(), timeout=1.0)
    assert val == {"a": 1}


@pytest.mark.asyncio
async def test_latest_value_channel_overwrites():
    ch = LatestValueChannel()
    ch.put({"a": 1})
    ch.put({"a": 2})   # overwrites before get
    val = await asyncio.wait_for(ch.get(), timeout=1.0)
    assert val["a"] == 2
