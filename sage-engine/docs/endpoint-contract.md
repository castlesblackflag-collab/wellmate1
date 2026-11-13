# Endpoint contract

How the Wellmate app talks to the Sage engine. The request side and error format are live
now; the streaming events are the plan for when the agent loop is built, so if anything here
looks awkward from the frontend side, now's the cheapest time to change it.

## Sign-in

Every call to `/v1/*` sends the user's Firebase ID token:

```
Authorization: Bearer <Firebase ID token>
```

The app gets this from `auth.currentUser.getIdToken()`. Tokens last an hour; the Firebase
SDK refreshes them, so call `getIdToken()` right before each request.

## POST /v1/chat

### Request

```json
{
  "conversation_id": "optional UUID; leave out to start a new conversation",
  "message": "The user's message, 1 to 8000 characters",
  "client_context": { "screen": "today", "timezone": "Europe/Madrid" }
}
```

`client_context` is optional and free-form: anything that helps Sage understand where the
user is coming from.

### Response (planned): a stream of Server-Sent Events

Content type `text/event-stream`. Each event is one line of `event:` and one of `data:` (JSON).

| Event | Data | Meaning |
|---|---|---|
| `conversation` | `{"conversation_id": "..."}` | Always first. Save this to continue the conversation. |
| `text` | `{"delta": "..."}` | A piece of Sage's reply. Append in order. |
| `activity` | `{"label": "Searching PubMed"}` | Optional status while a tool runs. Shown briefly, not stored. |
| `citations` | `{"items": [{"title": "...", "url": "...", "source_type": "pubmed", "identifier": "PMID:..."}]}` | Sources behind the reply. |
| `safety` | `{"level": "crisis", "resources": [...]}` | Sent when the crisis screen fires, before any text. |
| `done` | `{"message_id": "..."}` | The reply is complete. |
| `error` | Standard error body (below) | Something failed mid-reply. Show the message, keep what already arrived. |

Today the endpoint answers **501** with the standard error body after checking sign-in and
the request format, so the app can be wired up and tested against it now.

## Errors

Every error, from every endpoint, has the same shape:

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Please sign in again to keep chatting with Sage.",
    "request_id": "4f1c..."
  }
}
```

`message` is written to be shown to the user as-is. `request_id` matches the `X-Request-ID`
response header and the server logs, so including it in a bug report makes it easy to trace.

| HTTP | `code` | When |
|---|---|---|
| 401 | `unauthorized` | Missing, expired or invalid sign-in token |
| 404 | `not_found` | Wrong URL |
| 422 | `invalid_request` | Body doesn't match the request format |
| 500 | `internal_error` | Something unexpected broke on our side |
| 501 | `not_implemented` | That part isn't built yet |
| 502 | `upstream_error` | The model, database or a search service failed |
| 503 | `not_configured` | A required setting or key is missing |

## Health endpoints

- `GET /health`: `{"status": "ok", "version": "...", "environment": "..."}`. No sign-in needed.
- `GET /ready`: which pieces are configured and reachable. 200 when ready, 503 when not.
