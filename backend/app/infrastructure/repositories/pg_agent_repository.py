import json
import logging
from typing import Optional
from datetime import datetime, UTC

from app.domain.models.agent import Agent
from app.domain.models.memory import Memory
from app.domain.repositories.agent_repository import AgentRepository
from app.infrastructure.storage.postgresql import get_postgresql

logger = logging.getLogger(__name__)


class PgAgentRepository(AgentRepository):

    def __init__(self):
        self.pg = get_postgresql()

    def _row_to_agent(self, row) -> Agent:
        return Agent(
            id=row['agent_id'],
            model_name=row['model_name'],
            temperature=row['temperature'],
            max_tokens=row['max_tokens'],
            memories={k: Memory.model_validate(v) for k, v in json.loads(row['memories'] or '{}').items()},
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )

    async def save(self, agent: Agent) -> None:
        logger.info(f"Saving agent: {agent.id}")
        memories_json = json.dumps(
            {k: v.model_dump() for k, v in agent.memories.items()},
            default=str,
        )
        async with self.pg.pool.acquire() as conn:
            await conn.execute(
                '''INSERT INTO agents (agent_id, model_name, temperature, max_tokens, memories, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                   ON CONFLICT (agent_id) DO UPDATE SET
                       model_name = $2, temperature = $3, max_tokens = $4,
                       memories = $5::jsonb, updated_at = $7''',
                agent.id, agent.model_name, agent.temperature, agent.max_tokens,
                memories_json, agent.created_at, datetime.now(UTC),
            )

    async def find_by_id(self, agent_id: str) -> Optional[Agent]:
        logger.debug(f"Finding agent by ID: {agent_id}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM agents WHERE agent_id = $1', agent_id)
        if not row:
            return None
        return self._row_to_agent(row)

    async def add_memory(self, agent_id: str, name: str, memory: Memory) -> None:
        logger.debug(f"Adding memory '{name}' to agent: {agent_id}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT memories FROM agents WHERE agent_id = $1', agent_id)
            if not row:
                raise ValueError(f"Agent {agent_id} not found")
            memories = json.loads(row['memories'] or '{}')
            memories[name] = memory.model_dump()
            await conn.execute(
                'UPDATE agents SET memories = $1::jsonb, updated_at = $2 WHERE agent_id = $3',
                json.dumps(memories, default=str), datetime.now(UTC), agent_id,
            )

    async def get_memory(self, agent_id: str, name: str) -> Memory:
        logger.debug(f"Getting memory '{name}' from agent: {agent_id}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT memories FROM agents WHERE agent_id = $1', agent_id)
        if not row:
            raise ValueError(f"Agent {agent_id} not found")
        memories = json.loads(row['memories'] or '{}')
        if name in memories:
            return Memory.model_validate(memories[name])
        return Memory(messages=[])

    async def save_memory(self, agent_id: str, name: str, memory: Memory) -> None:
        logger.debug(f"Saving memory '{name}' for agent: {agent_id}")
        async with self.pg.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT memories FROM agents WHERE agent_id = $1', agent_id)
            if not row:
                raise ValueError(f"Agent {agent_id} not found")
            memories = json.loads(row['memories'] or '{}')
            memories[name] = memory.model_dump()
            await conn.execute(
                'UPDATE agents SET memories = $1::jsonb, updated_at = $2 WHERE agent_id = $3',
                json.dumps(memories, default=str), datetime.now(UTC), agent_id,
            )
