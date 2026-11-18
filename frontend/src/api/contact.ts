export interface ContactValues {
  name: string;
  email: string;
  message: string;
  /** The honeypot. Real visitors never see it, so it is always empty for them. */
  website: string;
}

export type ContactOutcome =
  | "sent"
  | "invalid"
  | "rate_limited"
  | "send_failed"
  | "unavailable"
  | "failed";

// Fixed text only. Nothing the server says, and nothing about why, is ever shown.
export const CONTACT_TEXT: Record<ContactOutcome, string> = {
  sent: "Thanks, your message has been sent.",
  invalid: "Please check your name, email and message, then try again.",
  rate_limited: "Too many messages. Please try again later.",
  send_failed: "We could not send your message. Please try again later.",
  unavailable: "The contact form is not available right now.",
  failed: "Something went wrong. Please try again later.",
};

const BY_STATUS: Record<number, ContactOutcome> = {
  200: "sent",
  422: "invalid",
  429: "rate_limited",
  502: "send_failed",
  503: "unavailable",
};

export async function sendContact(values: ContactValues, signal?: AbortSignal): Promise<ContactOutcome> {
  try {
    const response = await fetch("/api/contact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
      signal,
    });
    return BY_STATUS[response.status] ?? "failed";
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    return "failed";
  }
}
