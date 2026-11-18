import type { ContactOutcome, ContactValues } from "../api/contact";

/** The same limits the server enforces, so most mistakes are caught before sending. */
export const LIMITS = { name: 100, email: 254, message: 2000 } as const;

export const EMPTY_VALUES: ContactValues = { name: "", email: "", message: "", website: "" };

// Control characters and line separators: in a name or email they could become a mail header.
function hasControlOrLineBreak(text: string): boolean {
  for (const char of text) {
    const code = char.codePointAt(0) ?? 0;
    if (code <= 0x1f || code === 0x7f || code === 0x2028 || code === 0x2029) return true;
  }
  return false;
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateContact(values: ContactValues): "invalid" | null {
  const name = values.name.trim();
  const email = values.email.trim();
  const message = values.message.trim();
  if (!name || name.length > LIMITS.name || hasControlOrLineBreak(name)) return "invalid";
  if (email.length > LIMITS.email || hasControlOrLineBreak(email) || !EMAIL.test(email)) {
    return "invalid";
  }
  if (!message || message.length > LIMITS.message) return "invalid";
  return null;
}

export type ContactStatus = "idle" | "sending" | "sent" | "error";

export interface ContactState {
  values: ContactValues;
  status: ContactStatus;
  outcome: ContactOutcome | null;
}

export const initialState: ContactState = { values: EMPTY_VALUES, status: "idle", outcome: null };

export type ContactAction =
  | { type: "change"; field: keyof ContactValues; value: string }
  | { type: "submit" }
  | { type: "result"; outcome: ContactOutcome };

export function contactReducer(state: ContactState, action: ContactAction): ContactState {
  switch (action.type) {
    case "change":
      return { ...state, values: { ...state.values, [action.field]: action.value } };
    case "submit":
      // A second click while one send is in flight changes nothing.
      return state.status === "sending" ? state : { ...state, status: "sending", outcome: null };
    case "result":
      // Success clears the form. Any failure keeps what was typed, so they can try again.
      return action.outcome === "sent"
        ? { values: EMPTY_VALUES, status: "sent", outcome: "sent" }
        : { ...state, status: "error", outcome: action.outcome };
  }
}
