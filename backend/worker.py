import asyncio
import datetime
import random
import logging
from typing import Optional
from sqlalchemy import select, update
from backend.database import async_session_factory
from backend.models import DMTask, DeletedComment
from backend.rate_limiter import rate_limiter
from backend.mock_api_client import mock_client as default_client, MockAPIClient
from backend.config import settings

logger = logging.getLogger("linkplease.worker")

class BackgroundWorker:
    def __init__(self, mock_client: Optional[MockAPIClient] = None):
        self.mock_client = mock_client or default_client
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._reconcile_task: Optional[asyncio.Task] = None

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._process_queue_loop())
        self._reconcile_task = asyncio.create_task(self._reconcile_loop())
        logger.info("Background worker started")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
        if self._reconcile_task:
            self._reconcile_task.cancel()
        logger.info("Background worker stopped")

    async def _process_queue_loop(self):
        while self.is_running:
            try:
                processed_any = await self.process_pending_tasks()
                if not processed_any:
                    await asyncio.sleep(settings.WORKER_POLL_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in worker dispatch loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)

    async def process_pending_tasks(self) -> bool:
        """
        Fetches pending queued DM tasks and dispatches them adhering to rate limits.
        Returns True if a task was processed.
        """
        async with async_session_factory() as session:
            now = datetime.datetime.utcnow()
            stmt = (
                select(DMTask)
                .where(
                    DMTask.status == "queued",
                    DMTask.next_attempt_at <= now
                )
                .order_by(DMTask.id.asc())
                .limit(10)
            )
            res = await session.execute(stmt)
            tasks = res.scalars().all()

            if not tasks:
                return False

            for task in tasks:
                # Check for comment.deleted
                deleted_stmt = select(DeletedComment).where(DeletedComment.comment_id == task.comment_id)
                del_res = await session.execute(deleted_stmt)
                if del_res.scalar():
                    task.status = "cancelled"
                    task.last_error = "Comment was deleted before dispatch"
                    await session.commit()
                    continue

                # Acquire rate limit slot
                wait_seconds = await rate_limiter.acquire(session)
                if wait_seconds > 0:
                    # Defer this task slightly to respect rate limit
                    task.next_attempt_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=wait_seconds)
                    await session.commit()
                    # Sleep short to avoid busy spinning
                    await asyncio.sleep(min(wait_seconds, 1.0))
                    return True

                # Transition to 'sending'
                task.status = "sending"
                task.attempts += 1
                task.updated_at = datetime.datetime.utcnow()
                await session.commit()

                # Dispatch DM call
                resp = await self.mock_client.send_dm(
                    recipient_user_id=task.user_id,
                    message=task.dm_message,
                    comment_id=task.comment_id,
                    idempotency_key=task.idempotency_key
                )

                # Re-fetch task attached to current session
                task = await session.get(DMTask, task.id)
                if not task:
                    continue

                if resp.status_code == 202:
                    dm_id = resp.data.get("dm_id")
                    task.status = "sent_awaiting_reconciliation"
                    task.dm_id = dm_id
                    task.updated_at = datetime.datetime.utcnow()
                    await session.commit()
                elif resp.status_code == 429:
                    retry_after_str = resp.headers.get("Retry-After", "60")
                    try:
                        retry_after = float(retry_after_str)
                    except ValueError:
                        retry_after = 60.0
                    
                    task.status = "queued"
                    task.next_attempt_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=retry_after)
                    task.last_error = f"429 Rate limited (Retry-After: {retry_after}s)"
                    task.updated_at = datetime.datetime.utcnow()
                    await session.commit()
                elif resp.status_code == 400:
                    # Non-retryable
                    task.status = "failed"
                    task.last_error = f"400 Invalid Request: {resp.data.get('detail', 'Malformed payload')}"
                    task.updated_at = datetime.datetime.utcnow()
                    await session.commit()
                else:
                    # 500 or network failure -> exponential backoff retry
                    if task.attempts >= task.max_attempts:
                        task.status = "failed"
                        task.last_error = f"Max retries reached ({task.attempts}/{task.max_attempts}). Last status: {resp.status_code}"
                    else:
                        jitter = random.uniform(0.1, 0.5)
                        backoff = (2 ** task.attempts) + jitter
                        task.status = "queued"
                        task.next_attempt_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=backoff)
                        task.last_error = f"500 Internal error (Attempt {task.attempts}, retry in {backoff:.1f}s)"
                    task.updated_at = datetime.datetime.utcnow()
                    await session.commit()

            return True

    async def _reconcile_loop(self):
        while self.is_running:
            try:
                await self.reconcile_pending_dms()
                await asyncio.sleep(settings.RECONCILIATION_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in reconciliation loop: {e}", exc_info=True)
                await asyncio.sleep(2.0)

    async def reconcile_pending_dms(self):
        """
        Polls Mock API GET /v1/dm/{dm_id} for DMs in 'sent_awaiting_reconciliation'.
        """
        async with async_session_factory() as session:
            stmt = (
                select(DMTask)
                .where(DMTask.status == "sent_awaiting_reconciliation")
                .limit(20)
            )
            res = await session.execute(stmt)
            tasks = res.scalars().all()

            for task in tasks:
                if not task.dm_id:
                    continue

                # Check comment deletion
                del_stmt = select(DeletedComment).where(DeletedComment.comment_id == task.comment_id)
                if (await session.execute(del_stmt)).scalar():
                    task.status = "cancelled"
                    task.last_error = "Comment deleted while awaiting reconciliation"
                    await session.commit()
                    continue

                resp = await self.mock_client.get_dm_status(task.dm_id)
                if resp.status_code == 200:
                    status = resp.data.get("status")
                    if status == "delivered":
                        task.status = "delivered"
                        task.updated_at = datetime.datetime.utcnow()
                        await session.commit()
                    elif status == "failed":
                        # Mock API confirmed delivery failed!
                        if task.attempts < task.max_attempts:
                            # Re-queue for send attempt
                            task.status = "queued"
                            task.next_attempt_at = datetime.datetime.utcnow()
                            task.last_error = "Mock API delivery failed, re-queued for send"
                        else:
                            task.status = "failed"
                            task.last_error = "Mock API delivery permanently failed"
                        task.updated_at = datetime.datetime.utcnow()
                        await session.commit()
                    # If status == 'queued', remain in 'sent_awaiting_reconciliation'

worker_instance = BackgroundWorker()
