"""Shared test helpers: an always-clear crisis screen, a crisis screen that always fires,
a tool that cites a source, a fake Supabase client, and an SSE parser."""

import json
from types import SimpleNamespace

from pydantic import BaseModel, Field

from engine.types import Citation, ToolResult
from safety.crisis import CrisisScreen, RiskLevel, ScreenResult
from tools.base import Tool


class ClearScreen(CrisisScreen):
    def __init__(self, level: RiskLevel = RiskLevel.NONE):
        self.level = level
        self.seen: list[str] = []

    async def screen(self, user_id, text):
        self.seen.append(text)
        return ScreenResult(level=self.level, screener="test")


class AlwaysCrisis(CrisisScreen):
    async def screen(self, user_id, text):
        return ScreenResult(
            level=RiskLevel.CRISIS,
            screener="test",
            reasons=["test"],
            response_text="I'm really glad you told me. You deserve support right now.",
            resources=[{"name": "Test line", "contact": "000"}],
        )


class LookupTool(Tool):
    name = "lookup"
    description = "Looks something up."
    activity_label = "Checking the research"

    class Input(BaseModel):
        query: str = Field(min_length=1)

    async def run(self, args, ctx):
        return ToolResult(
            content=f"Findings about {args.query}",
            citations=[
                Citation(title="A study", source_type="pubmed", identifier="PMID:1", url="https://example.org/1")
            ],
        )


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


class FakeQuery:
    def __init__(self, client, table):
        self.client, self.table, self.ops = client, table, []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.ops.append((name, args, kwargs))
            return self

        return record

    def execute(self):
        self.client.queries.append(self)
        data = self.client.responses.pop(0) if self.client.responses else []
        return SimpleNamespace(data=data)

    def filters(self):
        return [(op, args) for op, args, _ in self.ops if op in ("eq", "lt", "is_", "or_")]


class FakeSupabase:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.queries: list[FakeQuery] = []

    def table(self, name):
        return FakeQuery(self, name)
