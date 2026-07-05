"""Тесты sliding-window RateLimiter с инъекцией времени."""
from chatcore.ratelimit import RateLimiter


def _make(max_calls: int = 3, period: float = 60.0):
    fake_now = [0.0]
    limiter = RateLimiter(max_calls, period, clock=lambda: fake_now[0])
    return limiter, fake_now


def test_allows_under_limit():
    rl, _ = _make(max_calls=3)
    assert rl.is_allowed(1) is True
    assert rl.is_allowed(1) is True
    assert rl.is_allowed(1) is True


def test_blocks_at_limit():
    rl, _ = _make(max_calls=3)
    for _ in range(3):
        rl.is_allowed(1)
    assert rl.is_allowed(1) is False


def test_window_slides():
    rl, t = _make(max_calls=3, period=60.0)
    for _ in range(3):
        rl.is_allowed(1)
    t[0] = 60.1  # все вызовы вышли из окна
    assert rl.is_allowed(1) is True


def test_partial_window_slide():
    rl, t = _make(max_calls=3, period=60.0)
    t[0] = 0.0
    rl.is_allowed(1)  # @ t=0
    t[0] = 10.0
    rl.is_allowed(1)  # @ t=10
    t[0] = 20.0
    rl.is_allowed(1)  # @ t=20
    # сдвигаем так, чтобы вызов @0 выпал (t-60 = -31, cutoff=31 → 0 <= cutoff? нет при t=61)
    t[0] = 61.0  # cutoff=1.0 → выпал только @0, остаётся 2 → разрешён 1 новый
    assert rl.is_allowed(1) is True   # 3-й занял место 1-го
    assert rl.is_allowed(1) is False  # окно снова полное


def test_warn_once_per_window():
    rl, _ = _make(max_calls=2)
    rl.is_allowed(1)
    rl.is_allowed(1)
    # лимит исчерпан
    assert rl.is_allowed(1) is False
    assert rl.should_warn(1) is True   # первый раз — предупреждаем
    assert rl.should_warn(1) is False  # повторно — молчим
    assert rl.should_warn(1) is False


def test_warn_resets_after_window():
    rl, t = _make(max_calls=2, period=60.0)
    rl.is_allowed(1)
    rl.is_allowed(1)
    rl.is_allowed(1)       # False — лимит
    rl.should_warn(1)      # True → флаг выставлен
    t[0] = 61.0            # окно сдвинулось
    assert rl.is_allowed(1) is True   # разрешён → флаг сброшен
    # снова достигаем лимита
    rl.is_allowed(1)
    assert rl.is_allowed(1) is False
    assert rl.should_warn(1) is True  # флаг снова работает


def test_zero_limit_disables():
    rl, _ = _make(max_calls=0)
    for _ in range(100):
        assert rl.is_allowed(1) is True


def test_users_independent():
    rl, _ = _make(max_calls=2)
    rl.is_allowed(1)
    rl.is_allowed(1)
    assert rl.is_allowed(1) is False  # user 1 исчерпан
    assert rl.is_allowed(2) is True   # user 2 не затронут
