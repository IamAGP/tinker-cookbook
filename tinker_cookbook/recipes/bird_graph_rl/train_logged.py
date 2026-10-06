"""``train.py`` with the training call's own metrics written to disk.

The upstream RL loop logs the optimiser step's metrics but not the output of
``forward_backward`` (which carries the loss). This wrapper records that output, one JSON line
per call, to ``$BIRD_FWD_BWD_LOG``. It changes nothing about training: the result object is
passed through untouched, and a failure to log is swallowed.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

import chz
import tinker

from tinker_cookbook.recipes.bird_graph_rl import train


class _LoggedFuture:
    def __init__(self, inner: Any, n_datums: int, path: str) -> None:
        self._inner, self._n, self._path = inner, n_datums, path

    async def result_async(self, *args: Any, **kwargs: Any) -> Any:
        result = await self._inner.result_async(*args, **kwargs)
        try:
            with open(self._path, "a") as f:
                f.write(json.dumps({"t": time.time(), "n_datums": self._n, "metrics": dict(result.metrics or {})}) + "\n")
        except Exception as exc:  # noqa: BLE001 - logging must never break a billed training step
            print(f"forward_backward log failed: {exc!r}", flush=True)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _log_forward_backward(path: str) -> None:
    original = tinker.TrainingClient.forward_backward_async

    async def logged(self: tinker.TrainingClient, data: Any, *args: Any, **kwargs: Any) -> Any:
        return _LoggedFuture(await original(self, data, *args, **kwargs), len(data), path)

    tinker.TrainingClient.forward_backward_async = logged  # type: ignore[method-assign]


if __name__ == "__main__":
    _log_forward_backward(os.environ["BIRD_FWD_BWD_LOG"])
    asyncio.run(train.cli_main(chz.entrypoint(train.CLIConfig)))
