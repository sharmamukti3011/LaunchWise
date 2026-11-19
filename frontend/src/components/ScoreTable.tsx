import type { Analysis, DimensionScore, OptionAnalysis, SuggestedFigure, SuggestionInfo } from "../api/demo";
import { keyFigures } from "../lib/figures";
import { formatRupees, statusOf } from "../lib/labels";
import { SourceTag } from "./SourceTag";

const DIMENSIONS: { key: DimensionScore["dimension"]; label: string }[] = [
  { key: "margin", label: "Margin" },
  { key: "budget", label: "Budget" },
  { key: "capacity", label: "Capacity" },
  { key: "skill_equipment", label: "Skills & equipment" },
  { key: "market_signal", label: "Market signal" },
];

function Figures({ option }: { option: OptionAnalysis }) {
  return (
    <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
      {keyFigures(option.feasibility).map((row) => (
        <div key={row.label} className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
          <dt className="text-slate-600">{row.label}</dt>
          <dd>
            <span className="mr-2 font-medium">{row.value}</span>
            <SourceTag source={row.source} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function figureValue(figure: SuggestedFigure): string {
  return figure.field === "minutes_per_unit" ? `${figure.value} minutes` : formatRupees(figure.value);
}

/** The four figures LaunchWise suggested, each marked as stated by the source or assumed. */
function SuggestedFigures({
  suggestion,
  onUse,
}: {
  suggestion: SuggestionInfo;
  onUse: (() => void) | null;
}) {
  return (
    <div className="rounded border border-violet-200 bg-violet-50 p-3">
      <h4 className="font-medium">Suggested figures</h4>
      <p className="text-sm text-slate-700">
        Built by LaunchWise from market data, not your own idea. Check every figure.
      </p>
      <dl className="mt-2 space-y-1">
        {suggestion.figures.map((figure) => (
          <div key={figure.field} className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
            <dt className="text-slate-600">{figure.label}</dt>
            <dd>
              <span className="mr-2 font-medium">{figureValue(figure)}</span>
              {figure.basis === "from_source" ? (
                <>
                  <SourceTag source="from_source" />
                  <span className="ml-1 text-xs text-slate-600">{suggestion.source_name}</span>
                  {figure.quote && <q className="ml-1 text-xs text-slate-500">{figure.quote}</q>}
                </>
              ) : (
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">assumed</span>
              )}
            </dd>
          </div>
        ))}
      </dl>
      {onUse && (
        <button
          type="button"
          onClick={onUse}
          className="mt-3 rounded border border-violet-700 px-3 py-1.5 text-sm font-medium text-violet-900 hover:bg-violet-100"
        >
          Use this as my alternative
        </button>
      )}
    </div>
  );
}

interface ScoreTableProps {
  analysis: Analysis;
  /** Copies a suggestion into the form. Without it, the button is not shown. */
  onUseSuggestion?: (title: string, suggestion: SuggestionInfo) => void;
}

export function ScoreTable({ analysis, onUseSuggestion }: ScoreTableProps) {
  const { ranked, recommended_id } = analysis.ranking;
  const byId = new Map(analysis.options.map((o) => [o.option_id, o]));
  return (
    <section aria-labelledby="scores-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="scores-heading" className="text-lg font-semibold">
        How the options compare
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        Scores run from 0 to 100 and are calculated by the engine from your inputs, not written by an AI.
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-slate-600">
              <th scope="col" className="py-2 pr-3">
                Option
              </th>
              {DIMENSIONS.map((d) => (
                <th key={d.key} scope="col" className="px-2 py-2 text-right">
                  {d.label}
                </th>
              ))}
              <th scope="col" className="px-2 py-2 text-right">
                Total
              </th>
              <th scope="col" className="py-2 pl-3">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((row) => {
              const recommended = row.option_id === recommended_id;
              return (
                <tr
                  key={row.option_id}
                  className={`border-b border-slate-100 ${recommended ? "bg-emerald-50 font-medium" : ""}`}
                >
                  <th scope="row" className="py-2 pr-3 font-medium">
                    {row.title}
                    {row.is_original && <span className="ml-2 text-xs font-normal text-slate-500">(your idea)</span>}
                    {row.is_suggested && (
                      <span className="ml-2 rounded bg-violet-100 px-1.5 py-0.5 text-xs font-normal text-violet-900">
                        Suggested by LaunchWise
                      </span>
                    )}
                  </th>
                  {DIMENSIONS.map((d) => (
                    <td key={d.key} className="px-2 py-2 text-right tabular-nums">
                      {row.scores.find((s) => s.dimension === d.key)?.score ?? "—"}
                    </td>
                  ))}
                  <td className="px-2 py-2 text-right tabular-nums">{row.total}</td>
                  <td className="py-2 pl-3">
                    <span className={recommended ? "text-emerald-800" : row.viable ? "" : "text-red-800"}>
                      {recommended && <span aria-hidden="true">★ </span>}
                      {statusOf(row, recommended_id)}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-4 space-y-2">
        {ranked.map((row) => {
          const option = byId.get(row.option_id);
          return (
            <details key={row.option_id} className="rounded border border-slate-200 p-3">
              <summary className="cursor-pointer font-medium">Figures and reasons: {row.title}</summary>
              {option?.suggestion && (
                <div className="mt-3">
                  <SuggestedFigures
                    suggestion={option.suggestion}
                    onUse={onUseSuggestion ? () => onUseSuggestion(option.title, option.suggestion!) : null}
                  />
                </div>
              )}
              {option && (
                <div className="mt-3">
                  <Figures option={option} />
                </div>
              )}
              <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-700">
                {row.scores.map((s) => (
                  <li key={s.dimension}>
                    <span className="font-medium">{DIMENSIONS.find((d) => d.key === s.dimension)?.label}:</span>{" "}
                    {s.reason}
                  </li>
                ))}
              </ul>
            </details>
          );
        })}
      </div>
    </section>
  );
}
