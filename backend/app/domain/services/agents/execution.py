from typing import AsyncGenerator, Optional, List
from app.domain.models.plan import Plan, Step, ExecutionStatus
from app.domain.models.file import FileInfo
from app.domain.models.message import Message
from app.domain.services.agents.base import BaseAgent
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.browser import Browser
from app.domain.external.search import SearchEngine
from app.domain.external.file import FileStorage
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.services.prompts.system import SYSTEM_PROMPT
from app.domain.services.prompts.execution import EXECUTION_SYSTEM_PROMPT, EXECUTION_PROMPT, SUMMARIZE_PROMPT
from app.domain.models.event import (
    BaseEvent,
    StepEvent,
    StepStatus,
    ErrorEvent,
    MessageEvent,
    DoneEvent,
    ToolEvent,
    ToolStatus,
    WaitEvent,
)
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.shell import ShellTool
from app.domain.services.tools.browser import BrowserTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.message import MessageTool
from app.domain.utils.json_parser import JsonParser
import logging
import uuid

logger = logging.getLogger(__name__)


class ExecutionAgent(BaseAgent):
    name: str = "execution"
    system_prompt: str = SYSTEM_PROMPT + EXECUTION_SYSTEM_PROMPT
    format: str = "json_object"
    tool_choice: Optional[str] = None

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        tools: List[BaseTool],
        json_parser: JsonParser,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            json_parser=json_parser,
            tools=tools
        )
        self._sandbox = None
        for tool in tools:
            if isinstance(tool, FileTool):
                self._sandbox = tool.sandbox
                break
            elif isinstance(tool, ShellTool):
                self._sandbox = tool.sandbox
                break
    
    async def _auto_execute_operations(self, parsed_response: dict) -> List[str]:
        results = []
        
        file_ops = parsed_response.get("file_operations", [])
        if file_ops and self._sandbox:
            for op in file_ops:
                try:
                    action = op.get("action", "write")
                    path = op.get("path", "")
                    content = op.get("content", "")
                    if not path or not content:
                        continue
                    
                    append = (action == "append")
                    result = await self._sandbox.file_write(
                        file=path,
                        content=content,
                        append=append,
                        leading_newline=False,
                        trailing_newline=True,
                        sudo=False
                    )
                    logger.info(f"Auto-executed file {action} to {path}: {result.success}")
                    results.append(f"File {action} to {path}: {'success' if result.success else result.message}")
                except Exception as e:
                    logger.error(f"Auto file operation failed for {path}: {e}")
                    results.append(f"File operation failed for {path}: {str(e)}")
        
        shell_cmds = parsed_response.get("shell_commands", [])
        if shell_cmds and self._sandbox:
            for cmd in shell_cmds:
                try:
                    command = cmd.get("command", "")
                    exec_dir = cmd.get("exec_dir", "/home/ubuntu")
                    if not command:
                        continue
                    
                    if exec_dir.startswith("/home/ubuntu"):
                        from app.infrastructure.external.sandbox.local_sandbox import SANDBOX_WORKDIR
                        exec_dir = exec_dir.replace("/home/ubuntu", SANDBOX_WORKDIR, 1)
                    
                    shell_id = str(uuid.uuid4())[:8]
                    result = await self._sandbox.exec_command(shell_id, exec_dir, command)
                    logger.info(f"Auto-executed shell command: {command}: {result.success}")
                    results.append(f"Shell command '{command}': {'success' if result.success else result.message}")
                except Exception as e:
                    logger.error(f"Auto shell command failed: {e}")
                    results.append(f"Shell command failed: {str(e)}")
        
        return results
    
    async def execute_step(self, plan: Plan, step: Step, message: Message) -> AsyncGenerator[BaseEvent, None]:
        prompt = EXECUTION_PROMPT.format(
            step=step.description, 
            message=message.message,
            attachments="\n".join(message.attachments),
            language=plan.language
        )
        step.status = ExecutionStatus.RUNNING
        yield StepEvent(status=StepStatus.STARTED, step=step)
        async for event in self.execute(prompt):
            if isinstance(event, ErrorEvent):
                step.status = ExecutionStatus.FAILED
                step.error = event.error
                yield StepEvent(status=StepStatus.FAILED, step=step)
            elif isinstance(event, MessageEvent):
                step.status = ExecutionStatus.COMPLETED
                try:
                    parsed_response = await self.json_parser.parse(event.message)
                    if not isinstance(parsed_response, dict):
                        logger.warning(f"Parsed response is {type(parsed_response).__name__}, wrapping as dict")
                        parsed_response = {
                            "success": True,
                            "result": str(parsed_response) if parsed_response else event.message,
                            "attachments": []
                        }
                except (ValueError, Exception) as parse_err:
                    logger.warning(f"JSON parsing failed for step response, using text as result: {parse_err}")
                    parsed_response = {
                        "success": True,
                        "result": event.message,
                        "attachments": []
                    }
                
                exec_results = await self._auto_execute_operations(parsed_response)
                if exec_results:
                    logger.info(f"Auto-execution results: {exec_results}")
                
                try:
                    new_step = Step.model_validate(parsed_response)
                    step.success = new_step.success
                    step.result = new_step.result
                    step.attachments = new_step.attachments
                except Exception as validate_err:
                    logger.warning(f"Step validation failed, using raw result: {validate_err}")
                    step.success = True
                    step.result = parsed_response.get("result", event.message) if isinstance(parsed_response, dict) else event.message
                    step.attachments = parsed_response.get("attachments", []) if isinstance(parsed_response, dict) else []
                yield StepEvent(status=StepStatus.COMPLETED, step=step)
                if step.result:
                    yield MessageEvent(message=step.result)
                continue
            elif isinstance(event, ToolEvent):
                if event.function_name == "message_ask_user":
                    if event.status == ToolStatus.CALLING:
                        yield MessageEvent(message=event.function_args.get("text", ""))
                    elif event.status == ToolStatus.CALLED:
                        yield WaitEvent()
                        return
                    continue
            yield event
        step.status = ExecutionStatus.COMPLETED

    async def summarize(self) -> AsyncGenerator[BaseEvent, None]:
        prompt = SUMMARIZE_PROMPT
        async for event in self.execute(prompt):
            if isinstance(event, MessageEvent):
                logger.debug(f"Execution agent summary: {event.message}")
                try:
                    parsed_response = await self.json_parser.parse(event.message)
                    msg = Message.model_validate(parsed_response)
                    attachments = [FileInfo(file_path=file_path) for file_path in msg.attachments]
                    yield MessageEvent(message=msg.message, attachments=attachments)
                except (ValueError, Exception) as e:
                    logger.warning(f"Failed to parse summary as JSON, using text: {e}")
                    yield MessageEvent(message=event.message)
                continue
            yield event
