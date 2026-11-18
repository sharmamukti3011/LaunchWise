/** Open/closed state of the collapsed Contact section, kept pure so it can be tested. */

/** Sent by the footer link, so a second click on "Contact" opens and scrolls again. */
export const OPEN_CONTACT_EVENT = "launchwise:open-contact";

export interface PanelState {
  open: boolean;
  /** Counts every request to show the form. Each new count means "scroll and focus again". */
  requests: number;
}

export type PanelAction = { type: "open" } | { type: "close" } | { type: "hash"; hash: string };

export function isContactHash(hash: string): boolean {
  return hash === "#contact";
}

export function initialPanelState(hash: string): PanelState {
  return isContactHash(hash) ? { open: true, requests: 1 } : { open: false, requests: 0 };
}

export function panelReducer(state: PanelState, action: PanelAction): PanelState {
  switch (action.type) {
    case "open":
      return { open: true, requests: state.requests + 1 };
    case "close":
      return { ...state, open: false };
    case "hash":
      // Following a link to #contact opens the form. Any other hash leaves it as it is.
      return isContactHash(action.hash) ? { open: true, requests: state.requests + 1 } : state;
  }
}

export function requestContactOpen(target: EventTarget = window): void {
  target.dispatchEvent(new Event(OPEN_CONTACT_EVENT));
}

/** Scroll the section to the top of the screen, then focus the first field without scrolling again. */
export function revealContact(
  section: { scrollIntoView(options?: ScrollIntoViewOptions): void } | null,
  field: { focus(options?: FocusOptions): void } | null,
): void {
  section?.scrollIntoView({ block: "start" });
  field?.focus({ preventScroll: true });
}
