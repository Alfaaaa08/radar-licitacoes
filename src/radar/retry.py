import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from radar.pncp import RateLimitedError, ServerError

RETRYABLE_ERRORS = (RateLimitedError, ServerError, httpx.TransportError)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay: float = 2.0
    max_delay: float = 60.0

    def delay(self, attempt: int) -> float:
        return min(self.max_delay, self.base_delay * 2**attempt)


DEFAULT_RETRY = RetryPolicy()


def retry_call[T](
    func: Callable[[], T],
    policy: RetryPolicy = DEFAULT_RETRY,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    attempt = 0
    while True:
        try:
            return func()
        except RETRYABLE_ERRORS:
            attempt += 1
            if attempt >= policy.max_attempts:
                raise
            sleep(policy.delay(attempt - 1))
