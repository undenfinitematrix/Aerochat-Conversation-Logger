import type { VercelRequest, VercelResponse } from "@vercel/node";

export default function handler(req: VercelRequest, res: VercelResponse) {
  return res.status(200).json({
    service: "AeroChat Conversation Logger",
    status: "running",
    endpoint: "POST /api/log-event",
  });
}
