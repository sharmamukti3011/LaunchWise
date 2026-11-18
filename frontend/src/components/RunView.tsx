import { useEffect, useState } from "react";
import type { DemoRun } from "../api/demo";
import { EvidenceAndCaveats } from "./EvidenceAndCaveats";
import { ScoreTable } from "./ScoreTable";
import { StepLog } from "./StepLog";

const STEP_DELAY_MS = 700;

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function Recommendation({ run }: { run: DemoRun }) {
  const { ranking, options } = run.analysis;
  const title = options.find((o) => o.option_id === ranking.recommended_id)?.title;
  let message: string;
  if (!title) message = "None of these options is viable with your constraints yet.";
  else if (ranking.keep_original) message = `Keep your original idea: ${title}.`;
  else message = `Switch to: ${title}.`;
  return (
    <section aria-labelledby="rec-heading" className="rounded-lg border-2 border-emerald-600 bg-emerald-50 p-4">
      <h2 id="rec-heading" className="text-sm font-medium text-emerald-900">
        Recommendation
      </h2>
      <p className="mt-1 text-xl font-semibold">{message}</p>
      <p className="mt-1 text-sm text-slate-700">A suggestion from deterministic math, not a promise of profit.</p>
    </section>
  );
}

/** Mount with a fresh `key` per run: the replay state then starts clean without an effect reset. */
export function RunView({ run }: { run: DemoRun }) {
  const steps = run.analysis.steps;
  const [visible, setVisible] = useState(() => (prefersReducedMotion() ? steps.length : 0));

  useEffect(() => {
    if (visible >= steps.length) return;
    const timer = window.setTimeout(() => setVisible((n) => n + 1), STEP_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [visible, steps.length]);

  const done = visible >= steps.length;
  return (
    <div className="mt-6 space-y-4">
      <p role="note" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
        <strong>{run.scenario.title}.</strong> {run.notice}
      </p>
      <StepLog steps={steps} visible={visible} onSkip={() => setVisible(steps.length)} />
      {done && (
        <>
          <Recommendation run={run} />
          <ScoreTable analysis={run.analysis} />
          <EvidenceAndCaveats analysis={run.analysis} />
        </>
      )}
    </div>
  );
}
