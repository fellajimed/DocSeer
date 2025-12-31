import asyncio
import httpx
from contextlib import asynccontextmanager
from typing import AsyncIterator, AsyncContextManager, Union


class AsyncRequester:
    RETRYABLE_EXCEPTIONS = (
        httpx.ConnectError,
        httpx.ReadTimeout,
        httpx.RequestError,
    )

    def __init__(
        self,
        *,
        timeout: float = 600.0,
        retry_timeout: float = 10.0,
        backoff: float = 0.2,
        max_backoff: float = 2.0,
    ):
        self.timeout = timeout
        self.retry_timeout = retry_timeout
        self.backoff = backoff
        self.max_backoff = max_backoff

    def _retry_state(self):
        loop = asyncio.get_running_loop()
        return {
            "backoff": self.backoff,
            "deadline": loop.time() + self.retry_timeout,
            "loop": loop,
        }

    async def _sleep(self, state):
        await asyncio.sleep(state["backoff"])
        state["backoff"] = min(state["backoff"] * 2, self.max_backoff)

    @asynccontextmanager
    async def _stream(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> AsyncIterator[httpx.Response]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout)
        ) as client:
            state = self._retry_state()
            while True:
                try:
                    async with client.stream(
                        method, url, **kwargs
                    ) as response:
                        response.raise_for_status()
                        yield response
                        return
                except self.RETRYABLE_EXCEPTIONS as exc:
                    if state["loop"].time() > state["deadline"]:
                        raise exc
                    await self._sleep(state)
                except httpx.HTTPStatusError as exc:
                    if 500 <= exc.response.status_code < 600:
                        if state["loop"].time() > state["deadline"]:
                            raise exc
                        await self._sleep(state)
                    else:
                        raise exc

    async def request(
        self,
        method: str,
        url: str,
        *,
        stream: bool = False,
        **kwargs,
    ) -> Union[httpx.Response, AsyncContextManager[httpx.Response]]:
        if stream:
            return self._stream(method, url, **kwargs)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout)
        ) as client:
            state = self._retry_state()
            while True:
                try:
                    response = await client.request(method, url, **kwargs)
                    response.raise_for_status()
                    return response
                except self.RETRYABLE_EXCEPTIONS as exc:
                    if state["loop"].time() > state["deadline"]:
                        raise exc
                    await self._sleep(state)
                except httpx.HTTPStatusError as exc:
                    if 500 <= exc.response.status_code < 600:
                        if state["loop"].time() > state["deadline"]:
                            raise exc
                        await self._sleep(state)
                    else:
                        raise exc
