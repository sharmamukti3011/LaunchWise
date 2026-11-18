import type { Analysis, Opportunity } from "../api/demo";
import { AGAINST_BADGE, EVIDENCE_LABELS, evidenceKind, isAgainst, safeHttpUrl } from "../lib/evidence";
import type { EvidenceKind } from "../lib/evidence";

const CARD_STYLES: Record<EvidenceKind, { box: string; note: string }> = {
  placeholder: { box: "border-amber-300 bg-amber-50", note: "text-amber-900" },
  unverified: { box: "border-yellow-300 bg-yellow-50", note: "text-yellow-900" },
  single_source: { box: "border-sky-200 bg-sky-50", note: "text-sky-900" },
  verified: { box: "border-emerald-300 bg-emerald-50", note: "text-emerald-900" },
};

function EvidenceCard({ entry }: { entry: Opportunity }) {
  const kind = evidenceKind(entry);
  const style = CARD_STYLES[kind];
  const link = safeHttpUrl(entry.source_url);
  return (
    <li className={`rounded border p-3 text-sm ${style.box}`}>
      <p className={`mb-1 font-medium ${style.note}`}>
        {EVIDENCE_LABELS[kind]}
        {isAgainst(entry) && (
          <span className="ml-2 rounded bg-red-100 px-2 py-0.5 text-xs text-red-900">
            {AGAINST_BADGE}
          </span>
        )}
      </p>
      <p className="font-medium">{entry.title}</p>
      <p className="mt-1 text-slate-700">{entry.signal_summary}</p>
      <p className="mt-1 text-xs text-slate-600">
        ID <code>{entry.id}</code> · {entry.location} · {entry.category} · status:{" "}
        {entry.verification_status.replace("_", " ")} · signal: {entry.signal_strength} · source:{" "}
        {link ? (
          <a href={link} className="underline" rel="noopener noreferrer" target="_blank">
            {entry.source_name}
          </a>
        ) : (
          entry.source_name
        )}
      </p>
    </li>
  );
}

export function EvidenceAndCaveats({ analysis }: { analysis: Analysis }) {
  const { caveats } = analysis.ranking;
  return (
    <>
      <section aria-labelledby="caveats-heading" className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 id="caveats-heading" className="text-lg font-semibold">
          Before you rely on this
        </h2>
        {caveats.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">No caveats: nothing was recommended.</p>
        ) : (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {caveats.map((c, i) => (
              <li key={`${c.kind}-${i}`}>{c.message}</li>
            ))}
          </ul>
        )}
      </section>
      <section aria-labelledby="evidence-heading" className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 id="evidence-heading" className="text-lg font-semibold">
          Market evidence
        </h2>
        <p className="mt-1 text-sm text-slate-700">{analysis.market_message}</p>
        {analysis.evidence.length > 0 && (
          <ul className="mt-3 space-y-2">
            {analysis.evidence.map((entry) => (
              <EvidenceCard key={entry.id} entry={entry} />
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
