"""One polite, sequential HTTP client shared by both sites."""

import json
import time
import urllib.request
from dataclasses import dataclass

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) itau-volar-cli/0.1"
TIMEOUT_SECONDS = 90
DEFAULT_DELAY_SECONDS = 1.0


@dataclass(slots=True)
class Client:
    """Fetches pages, keeping consecutive requests `delay` seconds apart."""

    delay: float = DEFAULT_DELAY_SECONDS
    _last_request_at: float = 0.0

    def get(self, url: str) -> str:
        return self._send(urllib.request.Request(url, headers=self._headers()))

    def post_json(self, url: str, body: dict[str, object]) -> str:
        headers = self._headers() | {"Content-Type": "application/json"}
        return self._send(
            urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        )

    @staticmethod
    def _headers() -> dict[str, str]:
        return {"User-Agent": USER_AGENT, "Accept": "application/json, text/html"}

    def _send(self, request: urllib.request.Request) -> str:
        wait = self.delay - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")
        finally:
            self._last_request_at = time.monotonic()
