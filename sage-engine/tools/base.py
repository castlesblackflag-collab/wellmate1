"""The shape every tool follows, and the registry the agent loop calls through.

The model asks for a tool by name with some arguments. Before any tool code runs, those
arguments are checked against the tool's Input model. If they don't fit, the tool never
runs and the model gets a clear error back so it can try again. This is one of our three
hard rails: nothing the model produces reaches user data without passing validation.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel, ValidationError

from engine.settings import Settings
from engine.types import ToolResult, ToolSpec

log = logging.getLogger("sage.tools")


@dataclass(frozen=True)
class ToolContext:
    user_id: str  # Firebase uid of the signed-in user. Tools must scope every read/write to it.
    request_id: str
    settings: Settings


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    Input: ClassVar[type[BaseModel]]
    writes_user_data: ClassVar[bool] = False

    @abstractmethod
    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult: ...

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, input_schema=self.Input.model_json_schema())


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [self._tools[n].spec() for n in self.names()]

    async def invoke(self, name: str, raw_args: dict, ctx: ToolContext) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            log.warning("unknown tool requested", extra={"tool": name})
            return ToolResult(content=f"There is no tool named {name!r}.", is_error=True)

        try:
            args = tool.Input.model_validate(raw_args)
        except ValidationError as exc:
            log.warning("tool arguments rejected", extra={"tool": name, "errors": exc.errors()})
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'input'}: {e['msg']}" for e in exc.errors())
            return ToolResult(content=f"Invalid arguments for {name}: {problems}", is_error=True)

        try:
            return await tool.run(args, ctx)
        except Exception:
            # Logged in full; the model gets a short message so the conversation can continue.
            log.exception("tool failed", extra={"tool": name})
            return ToolResult(content=f"The {name} tool ran into a problem and couldn't finish.", is_error=True)
