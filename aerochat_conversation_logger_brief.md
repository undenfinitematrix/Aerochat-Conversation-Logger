# AeroChat Conversation Logger — Task Brief & Implementation Notes

**Date:** 25 February 2026 | **Priority:** High | **Status:** Ready for Implementation

---

## 1. Overview

AeroChat currently lacks a comprehensive conversation logging system. We cannot retroactively debug conversations, audit engine performance, or run evaluations against real data. This task introduces an async conversation logger that records every inbound and outbound message event to an external database (Supabase) via a Vercel serverless function, without impacting the main pipeline's latency.

The audit log serves three purposes:
1. **Debugging** — retroactively trace what happened in any conversation turn
2. **Engine performance auditing** — track AI consumption, latency, and retrieval quality per station
3. **Evaluation data source** — sample logged conversations for periodic quality scoring

---

## 2. Architecture

### 2.1 Data Flow

```
AeroChat (AWS)  →  async POST  →  Vercel Function  →  Supabase (Postgres)
```

The main AeroChat script processes the conversation as normal on AWS. After the customer receives their response, the script fires a non-blocking HTTP POST to a Vercel endpoint. The Vercel function authenticates the request and writes the event to Supabase. If the logging call fails or is slow, it has no impact on the customer experience.

### 2.2 Event Model

Every message is recorded as an independent event — not as request-response pairs. This is intentional because the 1:1 pairing of inbound to outbound will not always hold. Future scenarios include: human agent takeover mid-conversation, bot sending multiple messages per one inbound, system-initiated messages with no inbound trigger, and inbound messages that are filtered with no response.

Each event is tagged with a direction (`inbound`/`outbound`) and source (`customer`, `bot`, `human_agent`, `system`).

### 2.3 AI Station Tracking

Every inbound message passes through three sequential AI stations:
1. **Pre-Processing Agent** — language detection, tagging
2. **Intention Agent** — intention classification
3. **Control Action Centre** — retrieval + LLM response generation

Each station's AI consumption (model used, tokens in/out, prompt sent, duration) is recorded in the `model_calls` JSONB field. This allows per-station cost calculation, latency profiling, and debugging. The field is an array, so if new stations are added to the pipeline in the future, no schema migration is needed.

---

## 3. Assignment Split

### 3.1 Junior Developer Scope

The junior developer is responsible for the entire external logging infrastructure and the Python utility module:

1. Set up the Supabase project and create the `conversation_events` table with the schema defined in Section 4
2. Build and deploy the Vercel serverless endpoint that receives event data and writes to Supabase
3. Write the Python `fire_log` utility module (standalone file) as specified in Section 5
4. Write tests to verify end-to-end logging: Python call → Vercel endpoint → Supabase record created
5. Provide the main developer with the utility module file and integration instructions

### 3.2 Main Developer Scope

The main developer's involvement is minimal — approximately 10–15 lines of code added to the main script:

1. Drop the `fire_log` utility module into the project
2. Add a `fire_log()` call after inbound message processing, passing the relevant fields from the pipeline
3. Add a `fire_log()` call after outbound response generation, passing the relevant fields from the pipeline
4. Ensure each AI station (Pre-Processing Agent, Intention Agent, Control Action Centre) returns its model name, token counts, prompt sent, and duration so these can be collected into the `model_calls` array before logging

---

## 4. Database Schema

Create a single table called `conversation_events` in Supabase:

| Field | Type | Description |
|---|---|---|
| `event_id` | text (PK) | Unique message ID. Reuse existing message IDs from the chat system for traceability. |
| `conversation_id` | text | Groups all events within a single conversation. |
| `merchant_id` | text | Identifies which merchant this conversation belongs to. |
| `direction` | text | `inbound` or `outbound`. |
| `source` | text | `customer`, `bot`, `human_agent`, or `system`. |
| `message` | jsonb | Raw message content. For bot responses, this is the structured JSON output. |
| `timestamp` | timestamptz | When the event occurred (UTC). |
| `intention` | text | Classified intention from pre-processing (e.g., `user_asks_product_availability`). Null for outbound events. |
| `tagging` | jsonb | Tagging output from pre-processing agent. Null for outbound events. |
| `language` | text | Detected language as ISO 639-1 code with region subtag where applicable (e.g., `en`, `zh-CN`, `zh-TW`, `pt-BR`, `es-MX`). |
| `contextual_summary` | jsonb | Contextual summary from pre-processing (type + summary). Null for outbound events. |
| `working_context` | jsonb | Snapshot of the working context state at time of response. Null for inbound events. |
| `memory_basket` | jsonb | Snapshot of the memory basket at time of response. Null for inbound events. |
| `retrieved_docs` | jsonb | Retrieved documents with similarity scores from vector search. Null for inbound and human agent events. |
| `filter_response` | jsonb | Filter layer output. Null for inbound and human agent events. |
| `model_calls` | jsonb | Array of per-station AI usage records. Each entry contains: `step`, `model`, `prompt_sent`, `tokens_input`, `tokens_output`, `duration_ms`. See Section 4.1 for format. Null for human agent events. |
| `response_time_ms` | integer | Total end-to-end duration from message received to response sent. |
| `eval` | jsonb | Post-hoc evaluation data. Populated later during eval sessions, not in real-time. Null by default. |
| `metadata` | jsonb | Catch-all field for any additional data that does not have a dedicated column. Future-proofing. |

### 4.1 model_calls Format

The `model_calls` field stores an array of objects, one per AI station invoked during the processing of that message:

```json
[
  {
    "step": "preprocessing_agent",
    "model": "mistral.ministral-3-14b-instruct",
    "prompt_sent": "Detect language and tag the following message...",
    "tokens_input": 180,
    "tokens_output": 45,
    "duration_ms": 420
  },
  {
    "step": "intention_agent",
    "model": "mistral.ministral-3-14b-instruct",
    "prompt_sent": "Classify the intention of the following message...",
    "tokens_input": 245,
    "tokens_output": 12,
    "duration_ms": 380
  },
  {
    "step": "control_action_centre",
    "model": "us.meta.llama4-maverick-17b-instruct-v1:0",
    "prompt_sent": "You are a friendly shopping assistant...",
    "tokens_input": 847,
    "tokens_output": 312,
    "duration_ms": 1670
  }
]
```

If new AI stations are added to the pipeline in the future, simply add another entry to the array — no schema changes required.

**Notes:**
- Many fields will be null depending on direction and source. This is expected and correct.
- The `metadata` JSONB column is a catch-all for any unexpected data that does not yet have its own column.
- Index on `conversation_id` and `merchant_id` for common query patterns.

---

## 5. Implementation Details

### 5.1 Python Utility Module (Junior Developer)

Create a standalone Python module (`conversation_logger.py`) that exposes a single `fire_log()` function. This module must be completely self-contained with no dependencies on the main AeroChat codebase.

**Requirements:**
- Use `httpx` for async HTTP calls
- `fire_log()` must be non-blocking — the main script calls it and immediately continues
- All errors must be silently caught — a failed log must never crash or slow the main pipeline
- Timeout set to 5 seconds maximum
- Authenticate via Bearer token in the Authorization header
- Environment variables: `LOGGER_ENDPOINT` (Vercel URL) and `LOGGER_API_KEY` (shared secret)

**Reference implementation:**

```python
import httpx
import asyncio
import os
import logging

logger = logging.getLogger(__name__)

LOGGER_ENDPOINT = os.getenv("LOGGER_ENDPOINT")
LOGGER_API_KEY = os.getenv("LOGGER_API_KEY")

async def _log_event(event_data: dict):
    if not LOGGER_ENDPOINT or not LOGGER_API_KEY:
        logger.warning("Conversation logger not configured: missing LOGGER_ENDPOINT or LOGGER_API_KEY")
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                LOGGER_ENDPOINT,
                json=event_data,
                headers={"Authorization": f"Bearer {LOGGER_API_KEY}"}
            )
            if response.status_code != 200:
                logger.warning(f"Conversation logger received status {response.status_code}")
    except httpx.TimeoutException:
        logger.warning("Conversation logger timed out")
    except Exception as e:
        logger.warning(f"Conversation logger failed: {e}")

def fire_log(event_data: dict):
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_log_event(event_data))
    except RuntimeError:
        try:
            asyncio.run(_log_event(event_data))
        except Exception:
            pass
```

### 5.2 Vercel Serverless Function (Junior Developer)

Create a Vercel project with a single API endpoint (`/api/log-event`) that receives POST requests and writes to Supabase.

**Requirements:**
- Validate the Authorization Bearer token against a stored secret
- Accept POST requests only; reject all other methods with 405
- Use the Supabase JS client to insert the event into the `conversation_events` table
- Return 200 on success, 401 on auth failure, 500 on database error
- Log errors to Vercel's console for debugging
- Environment variables: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `LOGGER_API_KEY`

### 5.3 Main Pipeline Integration (Main Developer)

Once the junior developer provides the `conversation_logger.py` module, add two `fire_log()` calls to the existing pipeline:

**Integration Point 1 — After bot response generation:**

Call `fire_log()` with all relevant fields. The critical addition is the `model_calls` array. Each AI station (Pre-Processing Agent, Intention Agent, Control Action Centre) must pass back its model name, prompt sent, token counts, and duration. Collect these into an array and include in the event data.

**Integration Point 2 — After human agent or system message:**

Call `fire_log()` with the basic fields (event_id, conversation_id, merchant_id, direction, source, message, timestamp). AI-related fields will be null.

---

## 6. Critical Rules

1. **Zero latency impact.** The logging call must never block, delay, or interfere with the customer-facing response. If the logging call fails, the customer experience is unaffected.
2. **Fire and forget.** The main script does not wait for a response from the logging endpoint. All errors are silently caught.
3. **Independent events.** Each message is logged as a separate event. Do not pair inbound and outbound records.
4. **Reuse existing IDs.** Use existing message IDs from the chat system as `event_id`. Do not generate new IDs.
5. **Null is expected.** Many fields will be null depending on the event type. Human agent events will not have `model_calls`. Inbound-only fields will be null on outbound events. This is by design.
6. **ISO 639-1 language codes.** Language detection must output ISO 639-1 codes with region subtags where applicable (e.g., `zh-CN`, `pt-BR`), not human-readable strings like "Chinese" or "Portuguese".

---

## 7. Evaluation Support

The `eval` column is reserved for post-hoc evaluation data. It is not populated in real-time. Periodically, a sample of logged conversations will be pulled and scored. The eval field stores judgments such as:

- `intention_correct` (boolean) — was the classified intention accurate?
- `response_quality` (1–5 scale) — how good was the bot's response?
- `retrieval_relevant` (boolean) — were the retrieved docs relevant?
- `notes` (text) — free-form observations
- `evaluated_by` and `evaluated_at` — who scored it and when

---

## 8. Privacy Considerations

This logging system stores customer conversation data externally. Ensure the following:

1. AeroChat's terms of service cover conversation data logging for quality and performance purposes.
2. Consider PII redaction or data retention policies, especially for merchants in LATAM (LGPD) and Europe (GDPR).
3. Supabase project should be configured with appropriate access controls and encryption at rest.
4. The Vercel endpoint must validate authentication on every request to prevent unauthorized writes.

---

## 9. Deliverables Checklist

| Owner | Deliverable | Status |
|---|---|---|
| Junior | Supabase project setup with `conversation_events` table | Not started |
| Junior | Vercel project with `/api/log-event` endpoint deployed | Not started |
| Junior | Python `conversation_logger.py` module with `fire_log()` function | Not started |
| Junior | End-to-end tests verifying logging pipeline | Not started |
| Junior | Integration instructions document for main developer | Not started |
| Main | Ensure each AI station returns model name, tokens, prompt, and duration | Not started |
| Main | Import `conversation_logger` module into main script | Not started |
| Main | Add `fire_log()` call after bot response generation | Not started |
| Main | Add `fire_log()` call after human agent / system messages | Not started |
