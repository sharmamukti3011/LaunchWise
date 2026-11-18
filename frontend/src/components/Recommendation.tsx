import type { DemoRun } from "../api/demo";

export type RecommendationTone = "switch" | "keep" | "none";

export function recommendationTone(run: DemoRun): RecommendationTone {
  const { recommended_id, keep_original } = run.analysis.ranking;
  if (recommended_id === null) return "none";
  return keep_original ? "keep" : "switch";
}

// Green is for a recommendation. "Nothing is viable" is a warning, so it is amber.
const STYLES: Record<RecommendationTone, { box: string; heading: string }> = {
  switch: { box: "border-emerald-600 bg-emerald-50", heading: "text-emerald-900" },
  keep: { box: "border-emerald-600 bg-emerald-50", heading: "text-emerald-900" },
  none: { box: "border-amber-500 bg-amber-50", heading: "text-amber-900" },
};

export function Recommendation({ run }: { run: DemoRun }) {
  const { ranking, options } = run.analysis;
  const tone = recommendationTone(run);
  const title = options.find((o) => o.option_id === ranking.recommended_id)?.title;
  let message: string;
  if (tone === "none" || !title) message = "None of these options is viable with your constraints yet.";
  else if (tone === "keep") message = `Keep your original idea: ${title}.`;
  else message = `Switch to: ${title}.`;
  const style = STYLES[tone];
  return (
    <section aria-labelledby="rec-heading" className={`rounded-lg border-2 p-4 ${style.box}`}>
      <h2 id="rec-heading" className={`text-sm font-medium ${style.heading}`}>
        Recommendation
      </h2>
      <p className="mt-1 text-xl font-semibold">{message}</p>
      <p className="mt-1 text-sm text-slate-700">A suggestion from deterministic math, not a promise of profit.</p>
    </section>
  );
}
