import asyncio
import typing
from contextlib import suppress

_END = object()


class MeteredStream:
    """
    Relays an upstream stream while a separate task reads it, so the call can
    still be settled when the client goes away mid-stream.

    The Proxy fires neither its success nor its failure callback on a client
    disconnect, and it only closes a nested iterator hook's generator when that
    generator is garbage collected. It does call `aclose()` on the upstream
    response when the stream ends for any reason, so that's the signal used
    here: `aclose()` cancels the read (which closes the upstream socket) and, if
    the stream didn't complete, hands the chunks read so far to `on_incomplete`.
    A completed stream is left to the success callback.
    """

    def __init__(
        self,
        response,
        *,
        on_incomplete: typing.Callable[[list], typing.Awaitable[None]],
    ):
        self.response = response
        self.on_incomplete = on_incomplete
        self.chunks: list = []
        self.completed = False
        self.closed = False
        self.queue: asyncio.Queue = asyncio.Queue()
        # streams without an aclose (e.g. the Gemini route's) get one, since the
        # Proxy closes a stream only if it has one
        self.upstream_aclose = getattr(response, "aclose", None)
        response.aclose = self.aclose
        self.reader = asyncio.ensure_future(self.read())

    async def relay(self) -> typing.AsyncIterator:
        while True:
            item = await self.queue.get()
            if item is _END:
                return
            if isinstance(item, Exception):
                raise item
            yield item

    async def read(self):
        try:
            async for chunk in self.response:
                self.chunks.append(chunk)
                self.queue.put_nowait(chunk)
        except Exception as e:
            self.queue.put_nowait(e)
            return
        self.completed = True
        self.queue.put_nowait(_END)

    async def aclose(self):
        if self.closed:
            return
        self.closed = True
        if not self.reader.done():
            self.reader.cancel()
            with suppress(asyncio.CancelledError):
                await self.reader
        try:
            if self.upstream_aclose:
                await self.upstream_aclose()
        finally:
            if not self.completed:
                await self.on_incomplete(self.chunks)
