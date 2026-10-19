import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
# Verified against when the account does not exist, so timing doesn't reveal valid emails.
_DUMMY_HASH = _hasher.hash("zerobase-dummy-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


class LoginThrottle:
    """Tiny in-memory limiter: too many failures for a key locks it out for a while."""

    def __init__(self, max_failures: int = 8, window_seconds: int = 900) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        failures = self._failures[key]
        cutoff = time.monotonic() - self.window
        while failures and failures[0] < cutoff:
            failures.popleft()
        if not failures:
            self._failures.pop(key, None)
        return failures

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.max_failures

    def record_failure(self, key: str) -> None:
        if len(self._failures) > 10_000:  # bound memory under a spray attack
            self._failures.clear()
        self._failures[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
