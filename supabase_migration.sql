-- AeroChat Conversation Logger
-- Run this in the Supabase SQL Editor to create the conversation_events table

CREATE TABLE conversation_events (
    event_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    direction TEXT CHECK (direction IN ('inbound', 'outbound')),
    source TEXT CHECK (source IN ('customer', 'bot', 'human_agent', 'system')),
    message JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    intention TEXT,
    tagging JSONB,
    language TEXT,
    contextual_summary JSONB,
    working_context JSONB,
    memory_basket JSONB,
    retrieved_docs JSONB,
    filter_response JSONB,
    model_calls JSONB,
    response_time_ms INTEGER,
    eval JSONB,
    metadata JSONB
);

-- Indexes for common query patterns
CREATE INDEX idx_conversation_events_conversation_id ON conversation_events (conversation_id);
CREATE INDEX idx_conversation_events_merchant_id ON conversation_events (merchant_id);
CREATE INDEX idx_conversation_events_timestamp ON conversation_events (timestamp DESC);
CREATE INDEX idx_conversation_events_direction ON conversation_events (direction);
CREATE INDEX idx_conversation_events_intention ON conversation_events (intention);

-- Composite index for merchant + time range queries
CREATE INDEX idx_conversation_events_merchant_time ON conversation_events (merchant_id, timestamp DESC);
