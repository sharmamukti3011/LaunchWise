import type { Explanation } from "../api/demo";
import { AI_NOTICE, ENGINE_NOTE, panelCopy } from "../lib/explanation";

export type ExplanationState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; explanation: Explanation };

export function ExplanationPanel({ state }: { state: ExplanationState }) {
  if (state.status === "loading") {
    return (
      <section aria-labelledby="explain-heading" className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 id="explain-heading" className="text-lg font-semibold">
          Explanation
        </h2>
        <p className="mt-2 text-sm text-slate-600" role="status">
          Writing a plain-language explanation…
        </p>
      </section>
    );
  }
  if (state.status === "error") {
    return (
      <section aria-labelledby="explain-heading" className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 id="explain-heading" className="text-lg font-semibold">
          Explanation
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          The explanation is not available right now. The numbers below are not affected.
        </p>
      </section>
    );
  }
  const copy = panelCopy(state.explanation);
  const ai = state.explanation.source === "claude";
  return (
    <section aria-labelledby="explain-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="explain-heading" className="text-lg font-semibold">
          {copy.title}
        </h2>
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            ai ? "bg-violet-100 text-violet-900" : "bg-slate-100 text-slate-700"
          }`}
        >
          {copy.badge}
        </span>
      </div>
      <p className="mt-2 text-slate-800">{state.explanation.summary}</p>
      <p className="mt-3 text-xs text-slate-600">{ENGINE_NOTE}</p>
      {ai && <p className="mt-1 text-xs text-slate-600">{AI_NOTICE}</p>}
    </section>
  );
}
