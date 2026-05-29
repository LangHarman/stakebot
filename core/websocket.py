"""
WebSocket client for Stake.com — Optional module for real-time bet results.

Protocol: graphql-ws over wss://<mirror>/_api/websockets
Subscribe to: HouseBets (all bets on the platform)
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional, Callable

import aiohttp

from .client import StakeConfig, GQL_HOUSE_BETS, MIRRORS


class StakeWebSocket:
    """graphql-ws client for Stake.com real-time data.

    Usage:
        ws = StakeWebSocket(config)
        await ws.connect()
        sub_id = await ws.subscribe_house_bets(on_bet)
        # ... streaming ...
        await ws.close()
    """

    def __init__(self, config: StakeConfig):
        self.cfg = config
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._subs: dict[str, Callable] = {}
        self._counter = 0
        self._running = False

    async def connect(self):
        """Connect to the first available mirror."""
        self._session = aiohttp.ClientSession()
        headers = {"x-access-token": self.cfg.access_token}
        if self.cfg.session_cookie:
            headers["Cookie"] = self.cfg.session_cookie

        mirrors = [self.cfg.base_url] + [m for m in MIRRORS if m != self.cfg.base_url]
        for base in mirrors:
            ws_url = base.replace("https://", "wss://").rstrip("/") + "/_api/websockets"
            try:
                self._ws = await self._session.ws_connect(
                    ws_url, headers=headers,
                    protocols=["graphql-ws"],
                    timeout=aiohttp.ClientTimeout(total=10),
                )
                # Send connection_init
                await self._ws.send_json({"type": "connection_init"})
                msg = await self._ws.receive(timeout=5)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("type") == "connection_ack":
                        self._running = True
                        return True
            except Exception:
                continue
            finally:
                if not self._running and self._ws:
                    await self._ws.close()
        return False

    async def subscribe_house_bets(self, callback: Callable[[dict], None]) -> str:
        """Subscribe to HouseBets stream. Returns subscription ID."""
        if not self._ws or not self._running:
            raise RuntimeError("Not connected. Call connect() first.")

        self._counter += 1
        sub_id = str(self._counter)
        self._subs[sub_id] = callback

        payload = {
            "id": sub_id,
            "type": "subscribe",
            "payload": {
                "query": GQL_HOUSE_BETS,
                "operationName": "HouseBets",
            },
        }
        await self._ws.send_json(payload)

        # Start reader task
        asyncio.create_task(self._reader())
        return sub_id

    async def _reader(self):
        """Read messages from WebSocket and dispatch to callbacks."""
        while self._running and self._ws and not self._ws.closed:
            try:
                msg = await self._ws.receive(timeout=30)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    sid = data.get("id", "")
                    if sid in self._subs:
                        self._subs[sid](data.get("payload", {}).get("data", {}))
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    async def close(self):
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
