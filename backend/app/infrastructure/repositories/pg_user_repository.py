import logging
from typing import List, Optional
from datetime import datetime, UTC

from app.domain.models.user import User, UserRole
from app.domain.repositories.user_repository import UserRepository
from app.infrastructure.storage.postgresql import get_postgresql

logger = logging.getLogger(__name__)


class PgUserRepository(UserRepository):

    def __init__(self):
        self.pg = get_postgresql()

    def _row_to_user(self, row) -> User:
        return User(
            id=row['user_id'],
            fullname=row['fullname'],
            email=row['email'],
            password_hash=row['password_hash'],
            role=UserRole(row['role']),
            is_active=row['is_active'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            last_login_at=row['last_login_at'],
        )

    async def create_user(self, user: User) -> User:
        logger.info(f"Creating user: {user.fullname}")
        async with self.pg.pool.acquire() as conn:
            await conn.execute(
                '''INSERT INTO users (user_id, fullname, email, password_hash, role, is_active, created_at, updated_at, last_login_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)''',
                user.id, user.fullname, user.email, user.password_hash,
                user.role.value, user.is_active, user.created_at, user.updated_at, user.last_login_at,
            )
        logger.info(f"User created successfully: {user.id}")
        return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        logger.debug(f"Getting user by ID: {user_id}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
        if not row:
            logger.debug(f"User not found: {user_id}")
            return None
        return self._row_to_user(row)

    async def get_user_by_fullname(self, fullname: str) -> Optional[User]:
        logger.debug(f"Getting user by fullname: {fullname}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM users WHERE fullname = $1', fullname)
        if not row:
            logger.debug(f"User not found: {fullname}")
            return None
        return self._row_to_user(row)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        logger.debug(f"Getting user by email: {email}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM users WHERE email = $1', email.lower())
        if not row:
            logger.debug(f"User not found: {email}")
            return None
        return self._row_to_user(row)

    async def update_user(self, user: User) -> User:
        logger.info(f"Updating user: {user.id}")
        async with self.pg.pool.acquire() as conn:
            result = await conn.execute(
                '''UPDATE users SET fullname = $1, email = $2, password_hash = $3, role = $4,
                   is_active = $5, updated_at = $6, last_login_at = $7
                   WHERE user_id = $8''',
                user.fullname, user.email, user.password_hash, user.role.value,
                user.is_active, datetime.now(UTC), user.last_login_at, user.id,
            )
        if result == 'UPDATE 0':
            raise ValueError(f"User not found: {user.id}")
        logger.info(f"User updated successfully: {user.id}")
        return user

    async def delete_user(self, user_id: str) -> bool:
        logger.info(f"Deleting user: {user_id}")
        async with self.pg.pool.acquire() as conn:
            result = await conn.execute('DELETE FROM users WHERE user_id = $1', user_id)
        deleted = result != 'DELETE 0'
        if deleted:
            logger.info(f"User deleted successfully: {user_id}")
        else:
            logger.warning(f"User not found for deletion: {user_id}")
        return deleted

    async def list_users(self, limit: int = 100, offset: int = 0) -> List[User]:
        logger.debug(f"Listing users: limit={limit}, offset={offset}")
        async with self.pg.pool.acquire() as conn:
            rows = await conn.fetch('SELECT * FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2', limit, offset)
        users = [self._row_to_user(row) for row in rows]
        logger.debug(f"Found {len(users)} users")
        return users

    async def fullname_exists(self, fullname: str) -> bool:
        logger.debug(f"Checking if fullname exists: {fullname}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT 1 FROM users WHERE fullname = $1', fullname)
        exists = row is not None
        logger.debug(f"Fullname exists: {exists}")
        return exists

    async def email_exists(self, email: str) -> bool:
        logger.debug(f"Checking if email exists: {email}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT 1 FROM users WHERE email = $1', email.lower())
        exists = row is not None
        logger.debug(f"Email exists: {exists}")
        return exists
