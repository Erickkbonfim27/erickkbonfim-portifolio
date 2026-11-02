import { ApiError } from "../api/client";

export const MESSAGES = {
  invalid: "Please check the fields and try again.",
  rateLimited: "You've sent several messages today. Try again tomorrow, or email me directly.",
  network: "Couldn't send right now. Check your connection and try again.",
  sent: "Thanks. Your message reached me, and I'll reply to the contact you left.",
} as const;

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.kind === "invalid") return error.detail ? `${capitalize(error.detail)}.` : MESSAGES.invalid;
    if (error.kind === "rate_limited") return MESSAGES.rateLimited;
  }
  return MESSAGES.network;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
