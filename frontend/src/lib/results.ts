import type { AnalyzeBody } from "../api/analyze";
import { explainOwn } from "../api/analyze";
import { explainScenario } from "../api/demo";
import type { Analysis, DemoRun, Explanation } from "../api/demo";

/** Everything the results area needs, whether the analysis came from a demo or the owner's idea. */
export interface ResultView {
  title: string;
  notice: string | null;
  analysis: Analysis;
  loadExplanation: (signal: AbortSignal) => Promise<Explanation>;
}

export function demoResult(run: DemoRun): ResultView {
  return {
    title: run.scenario.title,
    notice: run.notice,
    analysis: run.analysis,
    loadExplanation: async (signal) => (await explainScenario(run.scenario.id, signal)).explanation,
  };
}

export function ownResult(body: AnalyzeBody, analysis: Analysis): ResultView {
  return {
    title: "Your idea",
    notice:
      "Based on the figures you entered. Anything you left blank was assumed, and is flagged under “Before you rely on this”.",
    analysis,
    loadExplanation: (signal) => explainOwn(body, signal),
  };
}
