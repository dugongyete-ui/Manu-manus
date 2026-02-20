import json
import logging
from typing import Optional, List
from datetime import datetime, UTC

from app.domain.models.session import Session, SessionStatus
from app.domain.models.file import FileInfo
from app.domain.models.event import BaseEvent
from app.domain.repositories.session_repository import SessionRepository
from app.infrastructure.storage.postgresql import get_postgresql

logger = logging.getLogger(__name__)


class PgSessionRepository(SessionRepository):

    def __init__(self):
        self.pg = get_postgresql()

    def _row_to_session(self, row) -> Session:
        events_data = json.loads(row['events']) if isinstance(row['events'], str) else (row['events'] or [])
        files_data = json.loads(row['files']) if isinstance(row['files'], str) else (row['files'] or [])
        return Session(
            id=row['session_id'],
            user_id=row['user_id'],
            sandbox_id=row['sandbox_id'],
            agent_id=row['agent_id'],
            task_id=row['task_id'],
            title=row['title'],
            unread_message_count=row['unread_message_count'],
            latest_message=row['latest_message'],
            latest_message_at=row['latest_message_at'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            events=events_data,
            status=SessionStatus(row['status']),
            files=[FileInfo.model_validate(f) for f in files_data],
            is_shared=row['is_shared'] or False,
        )

    async def save(self, session: Session) -> None:
        logger.info(f"Saving session: {session.id}")
        events_json = json.dumps(
            [e.model_dump() if hasattr(e, 'model_dump') else e for e in session.events],
            default=str,
        )
        files_json = json.dumps(
            [f.model_dump() if hasattr(f, 'model_dump') else f for f in session.files],
            default=str,
        )
        async with self.pg.pool.acquire() as conn:
            await conn.execute(
                '''INSERT INTO sessions (session_id, user_id, sandbox_id, agent_id, task_id, title,
                       unread_message_count, latest_message, latest_message_at, created_at, updated_at,
                       events, status, files, is_shared)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13, $14::jsonb, $15)
                   ON CONFLICT (session_id) DO UPDATE SET
                       user_id = $2, sandbox_id = $3, agent_id = $4, task_id = $5, title = $6,
                       unread_message_count = $7, latest_message = $8, latest_message_at = $9,
                       updated_at = $11, events = $12::jsonb, status = $13, files = $14::jsonb, is_shared = $15''',
                session.id, session.user_id, session.sandbox_id, session.agent_id,
                session.task_id, session.title, session.unread_message_count,
                session.latest_message, session.latest_message_at,
                session.created_at, datetime.now(UTC),
                events_json, session.status.value, files_json, session.is_shared,
            )

    async def find_by_id(self, session_id: str) -> Optional[Session]:
        logger.debug(f"Finding session by ID: {session_id}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM sessions WHERE session_id = $1', session_id)
        if not row:
            return None
        return self._row_to_session(row)

    async def find_by_user_id(self, user_id: str) -> List[Session]:
        logger.debug(f"Finding sessions for user: {user_id}")
        async with self.pg.pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT * FROM sessions WHERE user_id = $1 ORDER BY latest_message_at DESC',
                user_id,
            )
        return [self._row_to_session(row) for row in rows]

    async def find_by_id_and_user_id(self, session_id: str, user_id: str) -> Optional[Session]:
        logger.debug(f"Finding session {session_id} for user {user_id}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM sessions WHERE session_id = $1 AND user_id = $2',
                session_id, user_id,
            )
        if not row:
            return None
        return self._row_to_session(row)

    async def update_title(self, session_id: str, title: str) -> None:
        logger.debug(f"Updating title for session: {session_id}")
        async with self.pg.pool.acquire() as conn:
            result = await conn.execute(
                'UPDATE sessions SET title = $1, updated_at = $2 WHERE session_id = $3',
                title, datetime.now(UTC), session_id,
            )
        if result == 'UPDATE 0':
            raise ValueError(f"Session {session_id} not found")

    async def update_latest_message(self, session_id: str, message: str, timestamp: datetime) -> None:
        logger.debug(f"Updating latest message for session: {session_id}")
        async with self.pg.pool.acquire() as conn:
            result = await conn.execute(
                'UPDATE sessions SET latest_message = $1, latest_message_at = $2, updated_at = $3 WHERE session_id = $4',
                message, timestamp, datetime.now(UTC), session_id,
            )
        if result == 'UPDATE 0':
            raise ValueError(f"Session {session_id} not found")

    async def add_event(self, session_id: str, event: BaseEvent) -> None:
        logger.debug(f"Adding event to session: {session_id}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT events FROM sessions WHERE session_id = $1', session_id)
            if not row:
                raise ValueError(f"Session {session_id} not found")
            events = json.loads(row['events']) if isinstance(row['events'], str) else (row['events'] or [])
            events.append(event.model_dump())
            events_json = json.dumps(events, default=str)
            await conn.execute(
                'UPDATE sessions SET events = $1::jsonb, updated_at = $2 WHERE session_id = $3',
                events_json, datetime.now(UTC), session_id,
            )

    async def add_file(self, session_id: str, file_info: FileInfo) -> None:
        logger.debug(f"Adding file to session: {session_id}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT files FROM sessions WHERE session_id = $1', session_id)
            if not row:
                raise ValueError(f"Session {session_id} not found")
            files = json.loads(row['files']) if isinstance(row['files'], str) else (row['files'] or [])
            files.append(file_info.model_dump())
            files_json = json.dumps(files, default=str)
            await conn.execute(
                'UPDATE sessions SET files = $1::jsonb, updated_at = $2 WHERE session_id = $3',
                files_json, datetime.now(UTC), session_id,
            )

    async def remove_file(self, session_id: str, file_id: str) -> None:
        logger.debug(f"Removing file {file_id} from session: {session_id}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT files FROM sessions WHERE session_id = $1', session_id)
            if not row:
                raise ValueError(f"Session {session_id} not found")
            files = json.loads(row['files']) if isinstance(row['files'], str) else (row['files'] or [])
            files = [f for f in files if f.get('file_id') != file_id]
            files_json = json.dumps(files, default=str)
            await conn.execute(
                'UPDATE sessions SET files = $1::jsonb, updated_at = $2 WHERE session_id = $3',
                files_json, datetime.now(UTC), session_id,
            )

    async def get_file_by_path(self, session_id: str, file_path: str) -> Optional[FileInfo]:
        logger.debug(f"Getting file by path from session: {session_id}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT files FROM sessions WHERE session_id = $1', session_id)
        if not row:
            raise ValueError(f"Session {session_id} not found")
        files = json.loads(row['files']) if isinstance(row['files'], str) else (row['files'] or [])
        for f in files:
            if f.get('file_path') == file_path:
                return FileInfo.model_validate(f)
        return None

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        logger.debug(f"Updating status for session: {session_id}")
        async with self.pg.pool.acquire() as conn:
            result = await conn.execute(
                'UPDATE sessions SET status = $1, updated_at = $2 WHERE session_id = $3',
                status.value, datetime.now(UTC), session_id,
            )
        if result == 'UPDATE 0':
            raise ValueError(f"Session {session_id} not found")

    async def update_unread_message_count(self, session_id: str, count: int) -> None:
        logger.debug(f"Updating unread count for session: {session_id}")
        async with self.pg.pool.acquire() as conn:
            result = await conn.execute(
                'UPDATE sessions SET unread_message_count = $1, updated_at = $2 WHERE session_id = $3',
                count, datetime.now(UTC), session_id,
            )
        if result == 'UPDATE 0':
            raise ValueError(f"Session {session_id} not found")

    async def increment_unread_message_count(self, session_id: str) -> None:
        logger.debug(f"Incrementing unread count for session: {session_id}")
        async with self.pg.pool.acquire() as conn:
            result = await conn.execute(
                'UPDATE sessions SET unread_message_count = unread_message_count + 1, updated_at = $1 WHERE session_id = $2',
                datetime.now(UTC), session_id,
            )
        if result == 'UPDATE 0':
            raise ValueError(f"Session {session_id} not found")

    async def decrement_unread_message_count(self, session_id: str) -> None:
        logger.debug(f"Decrementing unread count for session: {session_id}")
        async with self.pg.pool.acquire() as conn:
            result = await conn.execute(
                'UPDATE sessions SET unread_message_count = GREATEST(unread_message_count - 1, 0), updated_at = $1 WHERE session_id = $2',
                datetime.now(UTC), session_id,
            )
        if result == 'UPDATE 0':
            raise ValueError(f"Session {session_id} not found")

    async def update_shared_status(self, session_id: str, is_shared: bool) -> None:
        logger.debug(f"Updating shared status for session: {session_id}")
        async with self.pg.pool.acquire() as conn:
            result = await conn.execute(
                'UPDATE sessions SET is_shared = $1, updated_at = $2 WHERE session_id = $3',
                is_shared, datetime.now(UTC), session_id,
            )
        if result == 'UPDATE 0':
            raise ValueError(f"Session {session_id} not found")

    async def delete(self, session_id: str) -> None:
        logger.debug(f"Deleting session: {session_id}")
        async with self.pg.pool.acquire() as conn:
            await conn.execute('DELETE FROM sessions WHERE session_id = $1', session_id)

    async def get_all(self) -> List[Session]:
        logger.debug("Getting all sessions")
        async with self.pg.pool.acquire() as conn:
            rows = await conn.fetch('SELECT * FROM sessions ORDER BY latest_message_at DESC NULLS LAST')
        return [self._row_to_session(row) for row in rows]
