from __future__ import annotations

import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any


def _default_workers() -> int:
    try:
        return max(1, int(os.getenv("OPENAI_MAX_CONCURRENCY", "2")))
    except ValueError:
        return 2


def parallel_map(
    fn: Callable[[int, Any], Any],
    items: list[Any],
    *,
    max_workers: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[Any]:
    """items를 순서 보존하며 병렬 처리한다. fn(index, item) -> result.

    네트워크 지연이 지배적인 OpenAI 호출을 동시에 날려 대기 시간을 크게 줄인다.
    결과는 입력 순서대로 반환된다.
    """
    n = len(items)
    if n == 0:
        return []
    workers = max_workers or _default_workers()
    workers = min(workers, n)

    results: list[Any] = [None] * n
    done = 0
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fn, i, item): i for i, item in enumerate(items)}
        for fut in as_completed(futures):
            idx = futures[fut]
            results[idx] = fut.result()
            if on_progress:
                with lock:
                    done += 1
                    on_progress(done, n)
    return results
