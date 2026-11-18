import { useEffect, useReducer, useRef } from "react";
import type { FormEvent, Ref } from "react";
import { CONTACT_TEXT, sendContact } from "../api/contact";
import type { ContactValues } from "../api/contact";
import { LIMITS, contactReducer, initialState, validateContact } from "../lib/contactForm";
import type { ContactState } from "../lib/contactForm";
import {
  OPEN_CONTACT_EVENT,
  initialPanelState,
  panelReducer,
  revealContact,
} from "../lib/contactPanel";

const FIELD = "mt-1 w-full rounded border border-slate-300 px-3 py-2 text-slate-900";

interface ViewProps {
  state: ContactState;
  open: boolean;
  onToggle: () => void;
  onChange: (field: keyof ContactValues, value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  sectionRef?: Ref<HTMLElement>;
  nameRef?: Ref<HTMLInputElement>;
}

export function ContactFormView({ state, open, onToggle, onChange, onSubmit, sectionRef, nameRef }: ViewProps) {
  const { values, status, outcome } = state;
  const sending = status === "sending";
  return (
    <section
      id="contact"
      ref={sectionRef}
      aria-labelledby="contact-heading"
      className="mt-10 rounded-lg border border-slate-200 bg-white p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="contact-heading" className="text-base font-semibold">
            Contact us
          </h2>
          <p className="text-sm text-slate-600">Questions or feedback? We would like to hear from you.</p>
        </div>
        <button
          type="button"
          aria-expanded={open}
          aria-controls="contact-form-panel"
          onClick={onToggle}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50"
        >
          {open ? "Hide form" : "Write to us"}
        </button>
      </div>
      {/* Outside the collapsible part, so a sent message stays visible even if the form is hidden. */}
      {status === "sent" && outcome && (
        <p role="status" className="mt-3 text-sm text-emerald-800">
          {CONTACT_TEXT[outcome]}
        </p>
      )}
      <div id="contact-form-panel" hidden={!open}>
        <form onSubmit={onSubmit} aria-busy={sending} className="mt-3 space-y-3">
          <div>
            <label htmlFor="contact-name" className="text-sm font-medium">
              Your name
            </label>
            <input
              id="contact-name"
              ref={nameRef}
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
          {status === "error" && outcome && (
            <p role="alert" className="text-sm text-red-800">
              {CONTACT_TEXT[outcome]}
            </p>
          )}
        </form>
      </div>
    </section>
  );
}

export function ContactForm() {
  const [state, dispatch] = useReducer(contactReducer, initialState);
  const [panel, panelDispatch] = useReducer(panelReducer, undefined, () =>
    initialPanelState(typeof window === "undefined" ? "" : window.location.hash),
  );
  const controller = useRef<AbortController | null>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => controller.current?.abort(), []);

  // Opening the page at #contact, following a #contact link, or clicking the footer's Contact link.
  useEffect(() => {
    const onHash = () => panelDispatch({ type: "hash", hash: window.location.hash });
    const onOpen = () => panelDispatch({ type: "open" });
    window.addEventListener("hashchange", onHash);
    window.addEventListener(OPEN_CONTACT_EVENT, onOpen);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener(OPEN_CONTACT_EVENT, onOpen);
    };
  }, []);

  // Every request to show the form scrolls to it and moves focus to the first field.
  useEffect(() => {
    if (panel.requests > 0) revealContact(sectionRef.current, nameRef.current);
  }, [panel.requests]);

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
      open={panel.open}
      onToggle={() => panelDispatch({ type: panel.open ? "close" : "open" })}
      onChange={(field, value) => dispatch({ type: "change", field, value })}
      onSubmit={(event) => void onSubmit(event)}
      sectionRef={sectionRef}
      nameRef={nameRef}
    />
  );
}
