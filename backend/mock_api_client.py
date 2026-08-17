import logging
from typing import Optional, Tuple, Dict, Any
import httpx
from backend.config import settings

logger = logging.getLogger("linkplease.mock_client")

class MockAPIResponse:
    def __init__(
        self, 
        status_code: int, 
        data: Optional[Dict[str, Any]] = None, 
        headers: Optional[Dict[str, str]] = None
    ):
        self.status_code = status_code
        self.data = data or {}
        self.headers = headers or {}

class MockAPIClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or settings.PSEUDOGRAM_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.PSEUDOGRAM_API_KEY
        self.custom_transport = None  # Mocking capability for unit testing

    async def send_dm(
        self, 
        recipient_user_id: str, 
        message: str, 
        comment_id: str, 
        idempotency_key: Optional[str] = None
    ) -> MockAPIResponse:
        url = f"{self.base_url}/v1/dm/send"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        payload = {
            "recipient_user_id": recipient_user_id,
            "message": message,
            "comment_id": comment_id,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0, transport=self.custom_transport) as client:
                res = await client.post(url, json=payload, headers=headers)
                data = res.json() if res.content else {}
                return MockAPIResponse(res.status_code, data, dict(res.headers))
        except Exception as e:
            logger.error(f"Error calling send_dm: {e}")
            return MockAPIResponse(500, {"error": "internal_error", "detail": str(e)})

    async def get_dm_status(self, dm_id: str) -> MockAPIResponse:
        url = f"{self.base_url}/v1/dm/{dm_id}"
        headers = {
            "X-API-Key": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0, transport=self.custom_transport) as client:
                res = await client.get(url, headers=headers)
                data = res.json() if res.content else {}
                return MockAPIResponse(res.status_code, data, dict(res.headers))
        except Exception as e:
            logger.error(f"Error calling get_dm_status: {e}")
            return MockAPIResponse(500, {"error": "internal_error", "detail": str(e)})

default_mock_client = MockAPIClient()
mock_client = default_mock_client
