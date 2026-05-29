"""
WebSocket client for Stake.com real-time betting.
Taraje-compatible: uses graphql-ws protocol over aiohttp WS.
"""
import asyncio
import json
import uuid
import time
from typing import Optional, Callable, Awaitable

import aiohttp


class StakeWebSocket:
    """
    Stake.com WebSocket client for GraphQL subscriptions.
    Protocol: graphql-ws (subscriptions-transport-ws).
    - connection_init → connection_ack
    - subscribe (mutation) → bet result via subscription
    """

    def __init__(self, access_token: str, base_url: str = "https://stake.com"):
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected = False
        self._bet_results: asyncio.Queue = asyncio.Queue()
        self._subscription_id: Optional[str] = None

        # Headers matching Taraje style
        self._headers = {
            "x-access-token": access_token,
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Mobile Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    @property
    def ws_url(self) -> str:
        """WS URL: wss://stake.com/_api/websockets"""
        return self.base_url.replace("https://", "wss://") + "/_api/websockets"

    async def connect(self) -> bool:
        """Connect to WS and initialize (connection_init)."""
        if self._connected:
            return True

        self._session = aiohttp.ClientSession(headers=self._headers)
        try:
            self._ws = await self._session.ws_connect(
                self.ws_url,
                heartbeat=30.0,  # 30s ping/pong like Taraje
                compress=15,     # enable compression
                max_msg_size=0,  # no limit
            )
            # Send connection_init
            await self._ws.send_json({
                "type": "connection_init",
                "payload": {"accessToken": self.access_token},
            })
            # Wait for connection_ack
            msg = await self._ws.receive(timeout=10)
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("type") == "connection_ack":
                    self._connected = True
                    return True
                elif data.get("type") == "error":
                    raise Exception(f"WS auth error: {data}")
            raise Exception(f"Unexpected WS msg: {msg}")
        except Exception as e:
            await self.disconnect()
            raise e

    async def subscribe(self, query: str, variables: dict = None) -> str:
        """Subscribe to a GraphQL subscription. Returns subscription ID."""
        sub_id = str(uuid.uuid4())
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        await self._ws.send_json({
            "type": "subscribe",
            "id": sub_id,
            "payload": payload,
        })
        self._subscription_id = sub_id
        return sub_id

    async def send_mutation(self, query: str, variables: dict = None) -> dict:
        """
        Send a bet mutation via WebSocket.
        Returns the bet result from the subscription response.
        """
        # Subscribe to houseBets first (to receive result)
        sub_query = """
        subscription HouseBets {
            houseBets {
                id iid type scope
                game { name }
                bet {
                    id active amount amountMultiplier payout payoutMultiplier
                    createdAt updatedAt currency game nonce
                    user { name }
                    state {
                        ... on CasinoGameDice { result target condition }
                        ... on CasinoGameLimbo { result multiplierTarget }
                    }
                }
            }
        }
        """
        sub_id = await self.subscribe(sub_query)
        sub_id_str = str(sub_id)

        # Send the mutation
        await self._ws.send_json({
            "type": "subscribe",
            "id": sub_id_str,
            "payload": {
                "query": query,
                "variables": variables or {},
            },
        })

        # Wait for result (mutation complete + subscription data)
        timeout = 15.0
        start = time.time()
        while time.time() - start < timeout:
            msg = await self._ws.receive(timeout=timeout)
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                msg_type = data.get("type", "")

                if msg_type == "data":
                    payload = data.get("payload", {})
                    # Check for subscription data (houseBets update)
                    sub_data = payload.get("data", {}).get("houseBets")
                    if sub_data:
                        bet_info = sub_data.get("bet", {})
                        state = bet_info.get("state", {})
                        return {
                            "id": bet_info.get("id", ""),
                            "amount": float(bet_info.get("amount", 0)),
                            "payout": float(bet_info.get("payout", 0)),
                            "payout_multiplier": float(bet_info.get("payoutMultiplier", 0)),
                            "active": bet_info.get("active", False),
                            "currency": bet_info.get("currency", "").lower(),
                            "game": bet_info.get("game", ""),
                            "nonce": bet_info.get("nonce", 0),
                            "result": state.get("result", 0),
                            "condition": state.get("condition", ""),
                            "target": state.get("target", 0),
                            "multiplier_target": state.get("multiplierTarget", 0),
                            "won": bet_info.get("payout", 0) > bet_info.get("amount", 0),
                        }
                elif msg_type == "error":
                    payload = data.get("payload", {})
                    raise Exception(f"WS error: {payload.get('message', msg)}")
                elif msg_type == "complete":
                    # Subscription complete (not an error)
                    pass
            elif msg.type == aiohttp.WSMsgType.ERROR:
                raise Exception(f"WS error: {self._ws.exception()}")
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                raise Exception("WS closed")

        raise Exception("WS timeout waiting for bet result")

    async def disconnect(self):
        """Close WS connection."""
        self._connected = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
            self._ws = None
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()
