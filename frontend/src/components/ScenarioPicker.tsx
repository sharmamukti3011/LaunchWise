import type { DemoScenario } from "../api/demo";

interface Props {
  scenarios: DemoScenario[];
  selectedId: string;
  running: boolean;
  onSelect: (id: string) => void;
  onRun: () => void;
}

export function ScenarioPicker({ scenarios, selectedId, running, onSelect, onRun }: Props) {
  return (
    <section aria-labelledby="picker-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="picker-heading" className="text-lg font-semibold">
        Try a scenario
      </h2>
      <fieldset className="mt-3 space-y-2" disabled={running}>
        <legend className="sr-only">Demo scenario</legend>
        {scenarios.map((s) => (
          <label
            key={s.id}
            className={`flex cursor-pointer gap-3 rounded border p-3 ${
              s.id === selectedId ? "border-emerald-600 bg-emerald-50" : "border-slate-200"
            }`}
          >
            <input
              type="radio"
              name="scenario"
              className="mt-1"
              checked={s.id === selectedId}
              onChange={() => onSelect(s.id)}
            />
            <span>
              <span className="block font-medium">{s.title}</span>
              <span className="block text-sm text-slate-600">{s.summary}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <button
        type="button"
        onClick={onRun}
        disabled={running}
        className="mt-4 rounded bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:opacity-60"
      >
        {running ? "Running…" : "Run guided demo"}
      </button>
    </section>
  );
}
