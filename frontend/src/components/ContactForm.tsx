import { useEffect, useReducer, useRef } from "react";
import type { FormEvent } from "react";
import { CONTACT_TEXT, sendContact } from "../api/contact";
import type { ContactValues } from "../api/contact";
import { LIMITS, contactReducer, initialState, validateContact } from "../lib/contactForm";
import type { ContactState } from "../lib/contactForm";

const FIELD = "mt-1 w-full rounded border border-slate-300 px-3 py-2 text-slate-900";

interface ViewProps {
  state: ContactState;
  onChange: (field: keyof ContactValues, value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

export function ContactFormView({ state, onChange, onSubmit }: ViewProps) {
  const { values, status, outcome } = state;
  const sending = status === "sending";
  return (
    <section id="contact" aria-labelledby="contact-heading" className="mt-12 rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="contact-heading" className="text-lg font-semibold">
        Contact
      </h2>
      <p className="mt-1 text-sm text-slate-600">Questions or feedback? Send us a message.</p>
      <form onSubmit={onSubmit} aria-busy={sending} className="mt-3 space-y-3">
        <div>
          <label htmlFor="contact-name" className="text-sm font-medium">
            Your name
          </label>
          <input
            id="contact-name"
            name="name"
            type="text"
            autoComplete="name"
            required
            maxLength={LIMITS.name}
            value={values.name}
            onChange={(e) => onChange("name", e.target.value)}
            className={FIELD}
          />
        </div>
        <div>
          <label htmlFor="contact-email" className="text-sm font-medium">
            Your email
          </label>
          <input
            id="contact-email"
            name="email"
            type="email"
            autoComplete="email"
            required
            maxLength={LIMITS.email}
            value={values.email}
            onChange={(e) => onChange("email", e.target.value)}
            className={FIELD}
          />
        </div>
        <div>
          <label htmlFor="contact-message" className="text-sm font-medium">
            Message
          </label>
          <textarea
            id="contact-message"
            name="message"
            rows={5}
            required
            maxLength={LIMITS.message}
            value={values.message}
            onChange={(e) => onChange("message", e.target.value)}
            className={FIELD}
          />
        </div>
        {/* Honeypot: off-screen (not display:none, which bots skip), hidden from screen readers,
            and out of the tab order. Only a bot fills it, and then nothing is sent. */}
        <div aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
          <label htmlFor="contact-website">Leave this field empty</label>
          <input
            id="contact-website"
            name="website"
            type="text"
            tabIndex={-1}
            autoComplete="off"
            value={values.website}
            onChange={(e) => onChange("website", e.target.value)}
          />
        </div>
        <button
          type="submit"
          disabled={sending}
          className="rounded bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:opacity-60"
        >
          {sending ? "Sending…" : "Send message"}
        </button>
        {status === "sent" && outcome && (
          <p role="status" className="text-sm text-emerald-800">
            {CONTACT_TEXT[outcome]}
          </p>
        )}
        {status === "error" && outcome && (
          <p role="alert" className="text-sm text-red-800">
            {CONTACT_TEXT[outcome]}
          </p>
        )}
      </form>
    </section>
  );
}

export function ContactForm() {
  const [state, dispatch] = useReducer(contactReducer, initialState);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (state.status === "sending") return;
    if (validateContact(state.values) !== null) {
      dispatch({ type: "result", outcome: "invalid" });
      return;
    }
    dispatch({ type: "submit" });
    controller.current = new AbortController();
    try {
      dispatch({ type: "result", outcome: await sendContact(state.values, controller.current.signal) });
    } catch {
      // Aborted because the page went away: nothing to show.
    }
  }

  return (
    <ContactFormView
      state={state}
      onChange={(field, value) => dispatch({ type: "change", field, value })}
      onSubmit={(event) => void onSubmit(event)}
    />
  );
}
