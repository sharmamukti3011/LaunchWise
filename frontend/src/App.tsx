import { useCallback, useEffect, useRef, useState } from "react";
import { DemoError, fetchScenarios, runScenario } from "./api/demo";
import type { DemoRun, DemoScenario } from "./api/demo";
import { Footer } from "./components/Footer";
import { RunView } from "./components/RunView";
import { ScenarioPicker } from "./components/ScenarioPicker";

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function messageFor(error: unknown): string {
  return error instanceof DemoError ? error.message : "Something went wrong. Please try again.";
}

export default function App() {
  const [scenarios, setScenarios] = useState<DemoScenario[] | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [run, setRun] = useState<DemoRun | null>(null);
  const [runCount, setRunCount] = useState(0);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const runController = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchScenarios(controller.signal)
      .then((list) => {
        setScenarios(list);
        setSelectedId((current) => current || list[0]?.id || "");
      })
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(messageFor(e));
      });
    return () => controller.abort();
  }, [loadAttempt]);

  useEffect(() => () => runController.current?.abort(), []);

  const onRun = useCallback(() => {
    runController.current?.abort();
    const controller = new AbortController();
    runController.current = controller;
    setRunning(true);
    setError(null);
    runScenario(selectedId, controller.signal)
      .then((result) => {
        setRun(result);
        setRunCount((n) => n + 1);
      })
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(messageFor(e));
      })
      .finally(() => {
        if (runController.current === controller) setRunning(false);
      });
  }, [selectedId]);

  return (
    <div className="flex min-h-dvh flex-col">
      <main className="mx-auto w-full max-w-4xl flex-1 p-4 sm:p-8">
        <h1 className="text-3xl font-semibold">LaunchWise</h1>
        <p className="mt-2 text-slate-600">
          Test a business idea against your real budget, time and skills before you spend anything.
        </p>

        <div className="mt-6">
          {scenarios ? (
            <ScenarioPicker
              scenarios={scenarios}
              selectedId={selectedId}
              running={running}
              onSelect={setSelectedId}
              onRun={onRun}
            />
          ) : error ? null : (
            <p className="text-sm text-slate-600">Loading scenarios…</p>
          )}
        </div>

        {error && (
          <div role="alert" className="mt-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-900">
            {error}
            {!scenarios && (
              <button
                type="button"
                className="ml-3 underline"
                onClick={() => {
                  setError(null);
                  setLoadAttempt((n) => n + 1);
                }}
              >
                Try again
              </button>
            )}
          </div>
        )}

        {run && <RunView key={runCount} run={run} />}
      </main>
      <Footer />
    </div>
  );
}
