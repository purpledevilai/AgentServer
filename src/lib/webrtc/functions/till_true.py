import asyncio
from typing import Callable, Optional

async def till_true(condition: Callable[[], bool], timeout: Optional[float] = None, interval: float = 0.1) -> bool:
    elapsed_time = 0.0
    while not condition():
        if timeout is not None and elapsed_time >= timeout:
            return False
        await asyncio.sleep(interval)
        elapsed_time += interval
    return True