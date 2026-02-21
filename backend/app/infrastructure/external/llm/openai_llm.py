from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from app.domain.external.llm import LLM
from app.core.config import get_settings
import logging
import asyncio
import json
import uuid
import re

logger = logging.getLogger(__name__)

TOOL_CALL_SYSTEM_PROMPT = """
You have access to the following tools. To use a tool, respond with EXACTLY this JSON format:

```tool_call
{{"name": "<function_name>", "arguments": {{<arguments_object>}}}}
```

IMPORTANT RULES:
- You MUST use tools to complete tasks. Do NOT just describe what you would do.
- When you need to write a file, use the file_write tool. When you need to run a command, use shell_exec tool.
- Only call ONE tool at a time, then wait for the result.
- After receiving a tool result, you may call another tool or provide your final answer.
- If you want to respond to the user WITHOUT calling a tool, just write your response normally without the tool_call block.
- The sandbox working directory is /home/ubuntu. Use absolute paths starting with /home/ubuntu/.

Available tools:
{tools_description}
"""


def _format_tools_for_prompt(tools: List[Dict[str, Any]]) -> str:
    lines = []
    for tool_def in tools:
        if tool_def.get("type") == "function":
            func = tool_def["function"]
            name = func["name"]
            desc = func.get("description", "")
            params = func.get("parameters", {})
            props = params.get("properties", {})
            required = params.get("required", [])

            param_lines = []
            for pname, pinfo in props.items():
                req_marker = " (required)" if pname in required else " (optional)"
                param_lines.append(f"    - {pname}: {pinfo.get('type', 'string')} - {pinfo.get('description', '')}{req_marker}")

            lines.append(f"### {name}")
            lines.append(f"Description: {desc}")
            if param_lines:
                lines.append("Parameters:")
                lines.extend(param_lines)
            lines.append("")
    return "\n".join(lines)


def _parse_tool_call_from_text(text: str) -> Optional[Dict[str, Any]]:
    patterns = [
        r'```tool_call\s*\n?(.*?)\n?```',
        r'```json\s*tool_call\s*\n?(.*?)\n?```',
        r'```\s*\n?\s*\{["\']name["\'].*?\}\s*\n?```',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            json_str = match.group(1).strip() if match.lastindex else match.group(0).strip('`').strip()
            try:
                parsed = json.loads(json_str)
                if "name" in parsed and "arguments" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

    try:
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start >= 0 and brace_end > brace_start:
            candidate = text[brace_start:brace_end + 1]
            parsed = json.loads(candidate)
            if "name" in parsed and "arguments" in parsed:
                func_name = parsed["name"]
                if any(keyword in func_name for keyword in ["shell_", "file_", "browser_", "search_", "message_"]):
                    return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    return None


class OpenAILLM(LLM):
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.api_base
        )

        self._model_name = settings.model_name
        self._temperature = settings.temperature
        self._max_tokens = settings.max_tokens
        self._provider = settings.llm_provider
        logger.info(f"Initialized OpenAI LLM with model: {self._model_name}, provider: {self._provider}")

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def _inject_tools_into_messages(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        tools_desc = _format_tools_for_prompt(tools)
        tool_system = TOOL_CALL_SYSTEM_PROMPT.format(tools_description=tools_desc)

        new_messages = []
        system_injected = False
        for msg in messages:
            if msg.get("role") == "system" and not system_injected:
                new_messages.append({
                    "role": "system",
                    "content": msg["content"] + "\n\n" + tool_system,
                })
                system_injected = True
            elif msg.get("role") == "tool":
                tool_result_content = msg.get("content", "")
                fn_name = msg.get("function_name", "unknown")
                new_messages.append({
                    "role": "user",
                    "content": f"[Tool Result for {fn_name}]:\n{tool_result_content}\n\nBased on this result, continue with the next step. If you need to use another tool, use the tool_call format. If the task is complete, provide your final response.",
                })
            else:
                role = msg.get("role", "user")
                if role not in ("system", "user", "assistant"):
                    role = "user"
                content = msg.get("content", "")
                if msg.get("tool_calls"):
                    tc = msg["tool_calls"][0]
                    fn = tc.get("function", {})
                    content = (content or "") + f'\n```tool_call\n{{"name": "{fn.get("name", "")}", "arguments": {fn.get("arguments", "{}")}}}\n```'
                new_messages.append({"role": role, "content": content})

        if not system_injected:
            new_messages.insert(0, {"role": "system", "content": tool_system})

        return new_messages

    def _convert_text_to_tool_calls(self, text: str) -> Optional[List[Dict[str, Any]]]:
        parsed = _parse_tool_call_from_text(text)
        if parsed:
            tool_call_id = f"call_{uuid.uuid4().hex[:24]}"
            args = parsed["arguments"]
            if isinstance(args, dict):
                args_str = json.dumps(args)
            else:
                args_str = str(args)

            return [{
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": parsed["name"],
                    "arguments": args_str,
                }
            }]
        return None

    async def ask(self, messages: List[Dict[str, str]],
                tools: Optional[List[Dict[str, Any]]] = None,
                response_format: Optional[Dict[str, Any]] = None,
                tool_choice: Optional[str] = None) -> Dict[str, Any]:
        max_retries = 3
        base_delay = 1.0

        use_text_tools = bool(tools) and tool_choice != "none"

        if use_text_tools:
            api_messages = self._inject_tools_into_messages(messages, tools)
        else:
            api_messages = messages

        for attempt in range(max_retries + 1):
            response = None
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.info(f"Retrying API request (attempt {attempt + 1}/{max_retries + 1}) after {delay}s delay")
                    await asyncio.sleep(delay)

                extra_body = {"provider": self._provider}

                logger.debug(f"Sending request, model: {self._model_name}, provider: {self._provider}, tools_in_prompt: {use_text_tools}, attempt: {attempt + 1}")

                send_format = None
                if response_format and not use_text_tools:
                    send_format = response_format

                response = await self.client.chat.completions.create(
                    model=self._model_name,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                    messages=api_messages,
                    response_format=send_format,
                    extra_body=extra_body,
                )

                if not response or not response.choices:
                    error_msg = f"API returned invalid response (no choices) on attempt {attempt + 1}"
                    logger.error(error_msg)
                    if attempt == max_retries:
                        raise ValueError(f"Failed after {max_retries + 1} attempts: {error_msg}")
                    continue

                result = response.choices[0].message.model_dump()

                if use_text_tools and result.get("content"):
                    text_content = result["content"]
                    tool_calls = self._convert_text_to_tool_calls(text_content)
                    if tool_calls:
                        clean_content = re.sub(r'```tool_call\s*\n?.*?\n?```', '', text_content, flags=re.DOTALL).strip()
                        result["content"] = clean_content or None
                        result["tool_calls"] = tool_calls
                        logger.info(f"Parsed text-based tool call: {tool_calls[0]['function']['name']}")

                return result

            except Exception as e:
                error_msg = f"Error calling API on attempt {attempt + 1}: {str(e)}"
                logger.error(error_msg)
                if attempt == max_retries:
                    raise e
                continue
