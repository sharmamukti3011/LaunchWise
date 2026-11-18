import { useEffect, useState } from "react";
import type { ResultView } from "../lib/results";
import { EvidenceAndCaveats } from "./EvidenceAndCaveats";
import { ExplanationPanel } from "./ExplanationPanel";
import type { ExplanationState } from "./ExplanationPanel";
import { Recommendation } from "./Recommendation";
import { ScoreTable } from "./ScoreTable";
import { StepLog } from "./StepLog";

const STEP_DELAY_MS = 700;

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * The results for a demo scenario or for the owner's own idea. Mount with a fresh `key` per
 * result: the replay state then starts clean without an effect reset.
 */
export function RunView({ result }: { result: ResultView }) {
  const { analysis, loadExplanation } = result;
  const steps = analysis.steps;
  const [visible, setVisible] = useState(() => (prefersReducedMotion() ? steps.length : 0));

  useEffect(() => {
    if (visible >= steps.length) return;
    const timer = window.setTimeout(() => setVisible((n) => n + 1), STEP_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [visible, steps.length]);

  // Fetched at once, so it is usually ready by the time the replay finishes.
  const [explanation, setExplanation] = useState<ExplanationState>({ status: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    loadExplanation(controller.signal)
      .then((loaded) => setExplanation({ status: "ready", explanation: loaded }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setExplanation({ status: "error" });
      });
    return () => controller.abort();
  }, [loadExplanation]);

  const done = visible >= steps.length;
  return (
    <div className="mt-6 space-y-4">
      {result.notice && (
        <p role="note" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
          <strong>{result.title}.</strong> {result.notice}
        </p>
      )}
      <StepLog steps={steps} visible={visible} onSkip={() => setVisible(steps.length)} />
      {done && (
        <>
          <Recommendation analysis={analysis} />
          <ExplanationPanel state={explanation} />
          <ScoreTable analysis={analysis} />
          <EvidenceAndCaveats analysis={analysis} />
        </>
      )}
    </div>
  );
}
