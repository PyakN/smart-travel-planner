import pytest

from app.rate_limit import Limit, RateLimitedError, RateLimiter, describe_wait


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def limiter(*limits: Limit, **kwargs: int) -> tuple[RateLimiter, Clock]:
    clock = Clock()
    return RateLimiter(limits, clock=clock, **kwargs), clock


def test_allows_up_to_the_limit_then_refuses_until_the_window_slides() -> None:
    limits, clock = limiter(Limit(3, 60))
    for _ in range(3):
        limits.hit("a")
        clock.now += 10
    with pytest.raises(RateLimitedError) as refused:
        limits.hit("a")
    assert refused.value.retry_after_s == 30  # the first hit, at 0 s, leaves at 60 s
    clock.now += 30
    limits.hit("a")


def test_refused_requests_do_not_count() -> None:
    limits, clock = limiter(Limit(1, 60))
    limits.hit("a")
    for _ in range(5):
        with pytest.raises(RateLimitedError):
            limits.hit("a")
        clock.now += 10
    clock.now += 10  # 60 s after the only counted hit
    limits.hit("a")


def test_the_longest_wait_of_several_limits_counts() -> None:
    limits, clock = limiter(Limit(2, 60), Limit(3, 3600))
    limits.hit("a")
    limits.hit("a")
    with pytest.raises(RateLimitedError) as burst:
        limits.hit("a")
    assert burst.value.retry_after_s == 60
    clock.now += 60
    limits.hit("a")  # the third of the hour
    clock.now += 60
    with pytest.raises(RateLimitedError) as hourly:
        limits.hit("a")
    assert hourly.value.retry_after_s == 3600 - 120


def test_clients_have_limits_of_their_own() -> None:
    limits, _ = limiter(Limit(1, 60))
    limits.hit("a")
    limits.hit("b")
    with pytest.raises(RateLimitedError):
        limits.hit("a")


def test_forgets_the_clients_not_seen_for_longest() -> None:
    limits, _ = limiter(Limit(1, 60), max_keys=2)
    limits.hit("a")
    limits.hit("b")
    limits.hit("c")  # "a" is forgotten
    limits.hit("a")
    with pytest.raises(RateLimitedError):
        limits.hit("c")


def test_limits_of_zero_are_off() -> None:
    limits, _ = limiter(Limit(0, 60))
    for _ in range(100):
        limits.hit("a")


@pytest.mark.parametrize(
    ("seconds", "text"), [(1, "1 s"), (59, "59 s"), (60, "1 min"), (61, "2 min"), (7200, "2 h")]
)
def test_describe_wait(seconds: int, text: str) -> None:
    assert describe_wait(seconds) == text
