import { useEffect, useState } from "react";
import { fetchHealth } from "./api/health";

type BackendState = "checking" | "online" | "offline";

export default function App() {
  const [backend, setBackend] = useState<BackendState>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then(() => setBackend("online"))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setBackend("offline");
        }
      });
    return () => controller.abort();
  }, []);

  const badge = {
    checking: "bg-slate-200 text-slate-700",
    online: "bg-emerald-100 text-emerald-800",
    offline: "bg-red-100 text-red-800",
  }[backend];

  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-3xl font-semibold">LaunchWise</h1>
      <p className="mt-2 text-slate-600">The Market-Aware Business Builder</p>
      <p className="mt-6 text-sm">
        Backend: <span className={`rounded px-2 py-1 ${badge}`}>{backend}</span>
      </p>
    </main>
  );
}
