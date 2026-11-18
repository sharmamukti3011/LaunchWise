import type { Step } from "../api/demo";

interface Props {
  steps: Step[];
  visible: number;
  onSkip: () => void;
}

export function StepLog({ steps, visible, onSkip }: Props) {
  const done = visible >= steps.length;
  return (
    <section aria-labelledby="steps-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="steps-heading" className="text-lg font-semibold">
          What the agent did
        </h2>
        <span className="text-xs text-slate-500">replay of recorded steps</span>
      </div>
      <ol className="mt-3 space-y-2" aria-live="polite">
        {steps.slice(0, visible).map((step) => (
          <li key={step.index} className="flex gap-3 text-sm">
            <span className="mt-0.5 text-emerald-700" aria-hidden="true">
              ✓
            </span>
            <span>
              <code className="rounded bg-slate-100 px-1 text-xs">{step.tool}</code>
              <span className="ml-2">{step.title}</span>
            </span>
          </li>
        ))}
      </ol>
      {!done && (
        <button type="button" onClick={onSkip} className="mt-3 text-sm text-emerald-800 underline">
          Skip to results
        </button>
      )}
    </section>
  );
}
