"""The agent loop: one user message in, a streamed reply out.

    save message -> crisis screen -> build context -> model (-> tools -> model ...) -> save -> log

Sage decides for itself when to use tools. The engine's job is to supply context and tools,
enforce the rails (crisis screen first, validated tool calls, everything scoped to this user),
and record what happened.
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from engine import __version__
from engine.context import ContextBuilder
from engine.conversations import Conversation, ConversationStore
from engine.errors import NotFoundError, SageError, error_body
from engine.model_adapter import ModelAdapter
from engine.settings import Settings
from engine.turn_log import TurnLogger, TurnRecord, compute_cost
from engine.types import (
    ChatMessage,
    Citation,
    ModelStop,
    StreamEvent,
    TextDelta,
    ToolUseRequested,
    Usage,
)
from safety.crisis import CrisisScreen, RiskLevel
from tools.base import ToolContext, ToolRegistry

log = logging.getLogger("sage.agent")


def _dedupe(citations: list[Citation]) -> list[Citation]:
    seen, out = set(), []
    for c in citations:
        key = (c.source_type, c.identifier or c.url or c.title)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


class Sage:
    def __init__(
        self,
        *,
        settings: Settings,
        model: ModelAdapter,
        tools: ToolRegistry,
        conversations: ConversationStore,
        context: ContextBuilder,
        screen: CrisisScreen,
        turn_logger: TurnLogger,
    ):
        self.settings = settings
        self.model = model
        self.tools = tools
        self.conversations = conversations
        self.context = context
        self.screen = screen
        self.turn_logger = turn_logger

    async def open_conversation(self, user_id: str, conversation_id: uuid.UUID | None) -> Conversation:
        """Runs before streaming starts, so a bad conversation ID gets a normal 404."""
        if conversation_id is None:
            return await self.conversations.create(user_id, chat_model=self.model.model, engine_version=__version__)
        conversation = await self.conversations.get(user_id, conversation_id)
        if conversation is None:
            raise NotFoundError(f"conversation {conversation_id} not found for this user")
        return conversation

    async def run_turn(
        self,
        *,
        user_id: str,
        conversation: Conversation,
        message: str,
        request_id: str,
        client_context: dict | None = None,
    ) -> AsyncIterator[StreamEvent]:
        started = time.monotonic()
        first_token_ms: int | None = None
        usage = Usage()
        tools_used: list[str] = []
        citations: list[Citation] = []
        safety_level: str | None = None
        error_code: str | None = None

        def mark_first_token():
            nonlocal first_token_ms
            if first_token_ms is None:
                first_token_ms = int((time.monotonic() - started) * 1000)

        yield StreamEvent(event="conversation", data={"conversation_id": str(conversation.id)})
        try:
            await self.conversations.add_messages(user_id, conversation.id, [ChatMessage(role="user", text=message)])

            # Rail 1: the crisis screen sees every message before the model does.
            screen = await self.screen.screen(user_id, message)
            safety_level = screen.level.value
            if screen.level == RiskLevel.CRISIS:
                log.warning("crisis screen fired", extra={"screener": screen.screener, "reasons": screen.reasons})
                yield StreamEvent(event="safety", data={"level": "crisis", "resources": screen.resources})
                reply = screen.response_text or ""
                if reply:
                    mark_first_token()
                    yield StreamEvent(event="text", data={"delta": reply})
                await self.conversations.add_messages(
                    user_id, conversation.id, [ChatMessage(role="assistant", text=reply)]
                )
                yield StreamEvent(event="done", data={"request_id": request_id})
                return

            system = await self.context.system_prompt(
                user_id=user_id, screen=screen, now=datetime.now(UTC), client_context=client_context
            )
            history = await self.conversations.history(user_id, conversation.id, self.settings.history_messages)
            new_messages: list[ChatMessage] = []
            tool_ctx = ToolContext(user_id=user_id, request_id=request_id, settings=self.settings)

            for round_no in range(self.settings.max_tool_rounds + 1):
                # On the last round Sage gets no tools, so it has to answer with what it has.
                offer_tools = round_no < self.settings.max_tool_rounds
                text_parts: list[str] = []
                calls = []
                async for event in self.model.stream(
                    system=system,
                    messages=history + new_messages,
                    tools=self.tools.specs() if offer_tools else [],
                    max_tokens=self.settings.max_output_tokens,
                ):
                    if isinstance(event, TextDelta):
                        mark_first_token()
                        text_parts.append(event.text)
                        yield StreamEvent(event="text", data={"delta": event.text})
                    elif isinstance(event, ToolUseRequested):
                        calls.append(event.call)
                    elif isinstance(event, ModelStop):
                        usage = Usage(
                            input_tokens=usage.input_tokens + event.usage.input_tokens,
                            output_tokens=usage.output_tokens + event.usage.output_tokens,
                            cache_read_tokens=usage.cache_read_tokens + event.usage.cache_read_tokens,
                        )
                        if event.reason == "max_tokens":
                            log.warning("model reply hit max_tokens")

                new_messages.append(ChatMessage(role="assistant", text="".join(text_parts) or None, tool_calls=calls))
                if not calls:
                    break

                # Rail 2: every tool call is validated and scoped to this user by the registry.
                for call in calls:
                    tools_used.append(call.name)
                    tool = self.tools.get(call.name)
                    yield StreamEvent(
                        event="activity", data={"label": tool.activity_label if tool else "Looking into that"}
                    )
                    result = await self.tools.invoke(call.name, call.arguments, tool_ctx)
                    citations.extend(result.citations)
                    new_messages.append(
                        ChatMessage(role="tool", tool_call_id=call.id, tool_name=call.name, tool_result=result)
                    )

            await self.conversations.add_messages(user_id, conversation.id, new_messages)
            if citations:
                yield StreamEvent(
                    event="citations", data={"items": [c.model_dump(mode="json") for c in _dedupe(citations)]}
                )
            yield StreamEvent(event="done", data={"request_id": request_id})

        except SageError as exc:
            error_code = exc.code
            log.error("turn failed: %s", exc.detail or exc.code, exc_info=True)
            yield StreamEvent(event="error", data=error_body(exc.code, exc.user_message))
        except Exception:
            error_code = SageError.code
            log.exception("turn failed unexpectedly")
            yield StreamEvent(event="error", data=error_body(SageError.code, SageError.user_message))
        finally:
            await self.turn_logger.log(
                TurnRecord(
                    conversation_id=conversation.id,
                    user_id=user_id,
                    request_id=request_id,
                    model=self.model.model,
                    usage=usage,
                    cost_usd=compute_cost(self.model.model, usage, self.settings.model_prices),
                    first_token_ms=first_token_ms,
                    total_ms=int((time.monotonic() - started) * 1000),
                    tools_used=tools_used,
                    safety_level=safety_level,
                    error_code=error_code,
                )
            )
