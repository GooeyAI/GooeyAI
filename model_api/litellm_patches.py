"""
Backports for LiteLLM Proxy bugs the Model API runs into on its pinned version
(1.93.0). Each patch checks for the upstream fix first and does nothing once
it's there, so an upgrade can't double-apply it.
"""

import functools
import inspect


def apply():
    accept_request_in_data_generators()


def accept_request_in_data_generators():
    """
    /cursor/chat/completions streams fail in 1.93.0 with
    "cursor_data_generator() got an unexpected keyword argument 'request'":
    the shared request processing started passing `request=` to every data
    generator, and the Cursor endpoint's own generator (a closure inside the
    endpoint, so it can't be patched directly) wasn't updated. Fixed upstream
    in 1.97.0 by adding `request=None` to it.

    Wraps the caller instead: a generator that doesn't take `request` gets an
    adapter that drops it. Upstream forwards it for disconnect handling; the
    Model API's MeteredStream settles disconnects without it.
    """
    # imported here: it needs the Proxy's own dependencies, which the main
    # app's environment (and CI) doesn't install
    from litellm.proxy.common_request_processing import ProxyBaseLLMRequestProcessing

    original = ProxyBaseLLMRequestProcessing.base_process_llm_request
    if getattr(original, "_gooey_patched", False):
        return

    @functools.wraps(original)
    async def base_process_llm_request(self, *args, **kwargs):
        generator = kwargs.get("select_data_generator")
        if generator and "request" not in inspect.signature(generator).parameters:
            kwargs["select_data_generator"] = drop_request_kwarg(generator)
        return await original(self, *args, **kwargs)

    base_process_llm_request._gooey_patched = True
    ProxyBaseLLMRequestProcessing.base_process_llm_request = base_process_llm_request


def drop_request_kwarg(generator):
    @functools.wraps(generator)
    def adapter(*args, request=None, **kwargs):
        return generator(*args, **kwargs)

    return adapter
