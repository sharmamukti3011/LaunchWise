import { useEffect, useState } from "react";
import { explainScenario } from "../api/demo";
import type { DemoRun } from "../api/demo";
import { ExplanationPanel } from "./ExplanationPanel";
import { Recommendation } from "./Recommendation";
import type { ExplanationState } from "./ExplanationPanel";
import { EvidenceAndCaveats } from "./EvidenceAndCaveats";
import { ScoreTable } from "./ScoreTable";
import { StepLog } from "./StepLog";

const STEP_DELAY_MS = 700;

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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

  // Fetched at once, so it is usually ready by the time the replay finishes.
  const [explanation, setExplanation] = useState<ExplanationState>({ status: "loading" });
  const scenarioId = run.scenario.id;
  useEffect(() => {
    const controller = new AbortController();
    explainScenario(scenarioId, controller.signal)
      .then((result) => setExplanation({ status: "ready", explanation: result.explanation }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setExplanation({ status: "error" });
      });
    return () => controller.abort();
  }, [scenarioId]);

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
          <ExplanationPanel state={explanation} />
          <ScoreTable analysis={run.analysis} />
          <EvidenceAndCaveats analysis={run.analysis} />
        </>
      )}
    </div>
  );
}
