import { useCallback, useEffect, useRef, useState } from "react";
import { DemoError, fetchScenarios, runScenario } from "./api/demo";
import type { DemoScenario, SuggestionInfo } from "./api/demo";
import { ContactForm } from "./components/ContactForm";
import { Footer } from "./components/Footer";
import { OwnIdeaSection } from "./components/OwnIdeaForm";
import type { SuggestionRequest } from "./components/OwnIdeaForm";
import { RunView } from "./components/RunView";
import { UnpublishView } from "./components/StarterPage";
import { ScenarioPicker } from "./components/ScenarioPicker";
import { UnpublishFailure, unpublishPage } from "./api/storefront";
import { demoResult } from "./lib/results";
import { parseUnpublishHash } from "./lib/starterPage";
import type { ResultView } from "./lib/results";

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function messageFor(error: unknown): string {
  return error instanceof DemoError
    ? error.message
    : "Something went wrong. Please try again.";
}

type UnpublishState = "ready" | "working" | "done" | "failed";

export default function App() {
  // A private unpublish link (#unpublish/<slug>/<token>) opens a confirmation instead of the app.
  const [unpublishRequest] = useState(() =>
    typeof window === "undefined"
      ? null
      : parseUnpublishHash(window.location.hash),
  );
  const [unpublishState, setUnpublishState] = useState<UnpublishState>("ready");
  const [unpublishMessage, setUnpublishMessage] = useState("");
  useEffect(() => {
    // Take the secret out of the address bar and the history as soon as it has been read.
    if (unpublishRequest)
      window.history.replaceState(null, "", window.location.pathname);
  }, [unpublishRequest]);
  const onUnpublish = useCallback(() => {
    if (!unpublishRequest) return;
    setUnpublishState("working");
    unpublishPage(unpublishRequest.slug, unpublishRequest.token)
      .then(() => setUnpublishState("done"))
      .catch((e: unknown) => {
        setUnpublishMessage(
          e instanceof UnpublishFailure
            ? e.message
            : "Something went wrong. Please try again.",
        );
        setUnpublishState("failed");
      });
  }, [unpublishRequest]);

  const [scenarios, setScenarios] = useState<DemoScenario[] | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [result, setResult] = useState<ResultView | null>(null);
  const [suggestionRequest, setSuggestionRequest] =
    useState<SuggestionRequest | null>(null);
  const [runCount, setRunCount] = useState(0);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const runController = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

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

  // A new result, from a demo or from the owner's own idea, scrolls into view.
  useEffect(() => {
    if (runCount > 0) resultRef.current?.scrollIntoView({ block: "start" });
  }, [runCount]);

  const copySuggestion = useCallback(
    (title: string, suggestion: SuggestionInfo) => {
      setSuggestionRequest((previous) => ({
        key: (previous?.key ?? 0) + 1,
        title,
        suggestion,
      }));
    },
    [],
  );

  const showResult = useCallback((next: ResultView) => {
    setResult(next);
    setRunCount((n) => n + 1);
  }, []);

  const onRun = useCallback(() => {
    runController.current?.abort();
    const controller = new AbortController();
    runController.current = controller;
    setRunning(true);
    setError(null);
    runScenario(selectedId, controller.signal)
      .then((run) => showResult(demoResult(run)))
      .catch((e: unknown) => {
        if (!isAbort(e)) setError(messageFor(e));
      })
      .finally(() => {
        if (runController.current === controller) setRunning(false);
      });
  }, [selectedId, showResult]);

  return (
    <div className="flex min-h-dvh flex-col">
      <main className="mx-auto w-full max-w-4xl flex-1 p-4 sm:p-8">
        <h1 className="text-3xl font-semibold">LaunchWise</h1>
        <p className="mt-2 text-slate-600">
          Test a business idea against your real budget, time and skills before
          you spend anything.
        </p>

        {unpublishRequest ? (
          <div className="mt-6">
            <UnpublishView
              state={unpublishState}
              message={unpublishMessage}
              onConfirm={onUnpublish}
            />
          </div>
        ) : (
          <>
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
              <div
                role="alert"
                className="mt-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-900"
              >
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

            <OwnIdeaSection
              onResult={showResult}
              suggestionRequest={suggestionRequest}
            />

            <div ref={resultRef}>
              {result && (
                <RunView
                  key={runCount}
                  result={result}
                  onUseSuggestion={copySuggestion}
                />
              )}
            </div>

            <ContactForm />
          </>
        )}
      </main>
      <Footer />
    </div>
  );
}
