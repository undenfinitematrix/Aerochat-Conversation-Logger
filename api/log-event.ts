import { createClient } from "@supabase/supabase-js";
import type { VercelRequest, VercelResponse } from "@vercel/node";

const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_KEY!
);

const LOGGER_API_KEY = process.env.LOGGER_API_KEY!;

export default async function handler(req: VercelRequest, res: VercelResponse) {
  // Only accept POST
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  // Authenticate
  const authHeader = req.headers.authorization;
  if (!authHeader || authHeader !== `Bearer ${LOGGER_API_KEY}`) {
    return res.status(401).json({ error: "Unauthorized" });
  }

  // Validate required fields
  const event = req.body;
  if (!event || !event.event_id || !event.conversation_id || !event.merchant_id) {
    return res.status(400).json({ error: "Missing required fields: event_id, conversation_id, merchant_id" });
  }

  // Insert into Supabase
  const { error } = await supabase.from("conversation_events").insert({
    event_id: event.event_id,
    conversation_id: event.conversation_id,
    merchant_id: event.merchant_id,
    direction: event.direction || null,
    source: event.source || null,
    message: event.message || null,
    timestamp: event.timestamp || new Date().toISOString(),
    intention: event.intention || null,
    tagging: event.tagging || null,
    language: event.language || null,
    contextual_summary: event.contextual_summary || null,
    working_context: event.working_context || null,
    memory_basket: event.memory_basket || null,
    retrieved_docs: event.retrieved_docs || null,
    filter_response: event.filter_response || null,
    model_calls: event.model_calls || null,
    response_time_ms: event.response_time_ms || null,
    eval: event.eval || null,
    metadata: event.metadata || null,
  });

  if (error) {
    console.error("Supabase write failed:", error);
    return res.status(500).json({ error: error.message });
  }

  return res.status(200).json({ ok: true });
}
