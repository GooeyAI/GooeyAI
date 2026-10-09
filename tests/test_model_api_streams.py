import asyncio

import pytest

from model_api.streams import MeteredStream


def test_completed_stream_is_left_to_the_success_callback():
    async def scenario():
        upstream = FakeUpstream(["a", "b", "c"])
        incomplete = []
        stream = MeteredStream(upstream, on_incomplete=collect_into(incomplete))
        relayed = [chunk async for chunk in stream.relay()]
        await upstream.aclose()  # the Proxy closes the stream when it ends
        return relayed, incomplete, upstream

    relayed, incomplete, upstream = asyncio.run(scenario())
    assert relayed == ["a", "b", "c"]
    assert incomplete == []
    assert upstream.closed


def test_closing_mid_stream_stops_the_read_and_settles_what_was_read():
    async def scenario():
        upstream = FakeUpstream(["a", "b", "c", "d"], delay=0.05, block_after=2)
        incomplete = []
        stream = MeteredStream(upstream, on_incomplete=collect_into(incomplete))
        relay = stream.relay()
        first = await relay.__anext__()
        await asyncio.sleep(0.2)  # the client stops reading here
        await upstream.aclose()  # ...and the Proxy closes the stream
        return first, incomplete, upstream, stream

    first, incomplete, upstream, stream = asyncio.run(scenario())
    assert first == "a"
    assert incomplete == [["a", "b"]]
    assert upstream.read_cancelled
    assert upstream.closed
    assert stream.reader.done()


def test_upstream_error_is_relayed_and_settles_what_was_read():
    async def scenario():
        upstream = FakeUpstream(["a", "b"], fail_after=2)
        incomplete = []
        stream = MeteredStream(upstream, on_incomplete=collect_into(incomplete))
        relayed = []
        with pytest.raises(ConnectionError):
            async for chunk in stream.relay():
                relayed.append(chunk)
        await upstream.aclose()
        return relayed, incomplete

    relayed, incomplete = asyncio.run(scenario())
    assert relayed == ["a", "b"]
    assert incomplete == [["a", "b"]]


def test_closing_twice_settles_once():
    async def scenario():
        upstream = FakeUpstream(["a"], delay=1)
        incomplete = []
        MeteredStream(upstream, on_incomplete=collect_into(incomplete))
        await upstream.aclose()
        await upstream.aclose()
        return incomplete

    assert asyncio.run(scenario()) == [[]]


def test_a_stream_without_aclose_gets_one():
    async def scenario():
        upstream = FakeUpstreamWithoutAclose(["a", "b", "c"], delay=0.05, block_after=1)
        incomplete = []
        stream = MeteredStream(upstream, on_incomplete=collect_into(incomplete))
        assert stream.upstream_aclose is None
        await asyncio.sleep(0.2)
        await upstream.aclose()  # what the Proxy now finds and calls
        return incomplete, upstream

    incomplete, upstream = asyncio.run(scenario())
    assert incomplete == [["a"]]
    assert upstream.read_cancelled


class FakeUpstream:
    """An async-iterable upstream with `aclose`, like LiteLLM's CustomStreamWrapper."""

    def __init__(self, chunks, delay=0.0, block_after=None, fail_after=None):
        self.chunks = chunks
        self.delay = delay
        self.block_after = block_after
        self.fail_after = fail_after
        self.closed = False
        self.read_cancelled = False

    def __aiter__(self):
        return self.read()

    async def read(self):
        try:
            for i, chunk in enumerate(self.chunks):
                if i == self.block_after:
                    await asyncio.Event().wait()  # a provider that's still generating
                await asyncio.sleep(self.delay)
                yield chunk
            if self.fail_after is not None:
                raise ConnectionError("upstream dropped")
        except asyncio.CancelledError:
            self.read_cancelled = True
            raise

    async def aclose(self):
        self.closed = True


class FakeUpstreamWithoutAclose(FakeUpstream):
    """Like the Gemini route's stream iterator, which has no aclose."""

    aclose = None


def collect_into(calls: list):
    async def on_incomplete(chunks):
        calls.append(list(chunks))

    return on_incomplete
