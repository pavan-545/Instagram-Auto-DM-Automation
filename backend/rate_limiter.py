import time
import asyncio
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import RateLimitTick
from backend.config import settings

class DatabaseRateLimiter:
    """
    Persistent, process-safe sliding-window rate limiter.
    Strictly enforces maximum N requests per rolling window seconds.
    """

    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def acquire(self, session: AsyncSession) -> float:
        """
        Attempts to acquire a slot for sending a DM request.
        Returns:
            0.0 if slot acquired immediately.
            > 0.0 (seconds to wait) if rate limit would be exceeded.
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Clean up expired ticks
        await session.execute(
            delete(RateLimitTick).where(RateLimitTick.timestamp < window_start)
        )

        # Count active ticks in rolling window
        count_stmt = select(func.count(RateLimitTick.id)).where(RateLimitTick.timestamp >= window_start)
        res = await session.execute(count_stmt)
        count = res.scalar() or 0

        if count < self.max_requests:
            # Slot available -> record tick
            tick = RateLimitTick(timestamp=now)
            session.add(tick)
            await session.commit()
            return 0.0

        # Limit reached -> find oldest tick in window
        oldest_stmt = (
            select(RateLimitTick.timestamp)
            .where(RateLimitTick.timestamp >= window_start)
            .order_by(RateLimitTick.timestamp.asc())
            .limit(1)
        )
        res = await session.execute(oldest_stmt)
        oldest_ts = res.scalar()

        if oldest_ts:
            wait_seconds = max(0.1, (oldest_ts + self.window_seconds) - now + 0.1)
        else:
            wait_seconds = 1.0

        return wait_seconds

rate_limiter = DatabaseRateLimiter(
    max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS
)
