import { requestContactOpen } from "../lib/contactPanel";

export function Footer() {
  return (
    <footer className="mx-auto mt-12 w-full max-w-4xl border-t border-slate-200 px-4 py-6 text-sm text-slate-600 sm:px-8">
      <p>
        Hosted on GoDaddy · Built with Claude ·{" "}
        {/* The link still works as a plain anchor. The click also opens the collapsed form. */}
        <a href="#contact" className="underline" onClick={() => requestContactOpen()}>
          Contact
        </a>
      </p>
    </footer>
  );
}
