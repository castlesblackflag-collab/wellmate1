# Tools

Each tool is one file with one class that subclasses `Tool` from `base.py`:

```python
class LiteratureSearch(Tool):
    name = "literature_search"
    description = "Search PubMed for studies. Use when the user asks what the research says."

    class Input(BaseModel):
        query: str = Field(min_length=3, max_length=300)
        max_results: int = Field(default=5, ge=1, le=10)

    async def run(self, args, ctx):
        ...
        return ToolResult(content=..., citations=[...])
```

The description matters more than it looks. It's how Sage decides when to reach for the
tool, so write it the way you'd explain it to a new teammate.

A few things every tool should do:

- Scope every read and write to `ctx.user_id`.
- Set `writes_user_data = True` if the tool changes anything about the user.
- Return sources in `citations` whenever the content came from somewhere checkable.
- Raise or return `is_error=True` on failure, never return empty results that hide a problem.
- Come with a test in `tests/`.

## Planned tools

| Tool | What it does | Workstream |
|---|---|---|
| `knowledge_search` | Searches our cleaned Q&A corpus and curated sources in pgvector | WS3 |
| `literature_search` | PubMed search with PMIDs as citations | WS3 |
| `web_search` | Current information from trusted sites | WS3 |
| `user_profile` | Reads what Sage knows about the user | WS4 |
| `remember` | Saves a new fact or preference the user shared | WS4 |
| `agewell_snapshot` | Trends, recent logs, minutes earned (reads only; scoring stays in the Age Well engine) | WS4 |
| `goals` | Reads and updates goals and reflections | WS4 |
| `find_provider` | Provider Finder, ported from the existing Places + NPI logic | WS4 |
