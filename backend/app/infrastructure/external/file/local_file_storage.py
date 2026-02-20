import os
import io
import uuid
import json
import logging
import aiofiles
from typing import BinaryIO, Optional, Dict, Any, Tuple
from datetime import datetime, UTC
from functools import lru_cache

from app.domain.external.file import FileStorage
from app.domain.models.file import FileInfo
from app.infrastructure.storage.postgresql import get_postgresql

logger = logging.getLogger(__name__)

UPLOAD_DIR = "/home/runner/workspace/uploads"


class LocalFileStorage(FileStorage):

    def __init__(self):
        self.pg = get_postgresql()
        os.makedirs(UPLOAD_DIR, exist_ok=True)

    async def upload_file(self, file_data: BinaryIO, filename: str, user_id: str,
                          content_type: Optional[str] = None,
                          metadata: Optional[Dict[str, Any]] = None) -> FileInfo:
        file_id = uuid.uuid4().hex[:16]
        file_path = os.path.join(UPLOAD_DIR, file_id)
        content = file_data.read()

        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)

        now = datetime.now(UTC)
        async with self.pg.pool.acquire() as conn:
            await conn.execute(
                '''INSERT INTO uploaded_files (file_id, filename, file_path, content_type, file_size, upload_date, metadata, user_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)''',
                file_id, filename, file_path, content_type, len(content), now,
                json.dumps(metadata or {}), user_id,
            )

        logger.info(f"File uploaded successfully: {filename} (ID: {file_id}) for user {user_id}")
        return FileInfo(
            file_id=file_id, filename=filename, file_path=file_path,
            content_type=content_type, size=len(content), upload_date=now,
            metadata=metadata, user_id=user_id,
        )

    async def download_file(self, file_id: str, user_id: Optional[str] = None) -> Tuple[BinaryIO, FileInfo]:
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM uploaded_files WHERE file_id = $1', file_id)
        if not row:
            raise FileNotFoundError(f"File not found: {file_id}")
        if user_id and row['user_id'] != user_id:
            raise PermissionError(f"Access denied")

        async with aiofiles.open(row['file_path'], 'rb') as f:
            content = await f.read()

        file_info = FileInfo(
            file_id=row['file_id'], filename=row['filename'], file_path=row['file_path'],
            content_type=row['content_type'], size=row['file_size'], upload_date=row['upload_date'],
            metadata=json.loads(row['metadata']) if row['metadata'] else None, user_id=row['user_id'],
        )
        return io.BytesIO(content), file_info

    async def delete_file(self, file_id: str, user_id: str) -> bool:
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM uploaded_files WHERE file_id = $1', file_id)
            if not row or row['user_id'] != user_id:
                return False
            await conn.execute('DELETE FROM uploaded_files WHERE file_id = $1', file_id)

        try:
            os.remove(row['file_path'])
        except Exception:
            logger.warning(f"Failed to remove file from disk: {row['file_path']}")

        logger.info(f"File deleted successfully: {file_id} by user {user_id}")
        return True

    async def get_file_info(self, file_id: str, user_id: Optional[str] = None) -> Optional[FileInfo]:
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM uploaded_files WHERE file_id = $1', file_id)
        if not row:
            return None
        if user_id and row['user_id'] != user_id:
            return None
        return FileInfo(
            file_id=row['file_id'], filename=row['filename'], file_path=row['file_path'],
            content_type=row['content_type'], size=row['file_size'], upload_date=row['upload_date'],
            metadata=json.loads(row['metadata']) if row['metadata'] else None, user_id=row['user_id'],
        )


@lru_cache()
def get_local_file_storage() -> FileStorage:
    return LocalFileStorage()
