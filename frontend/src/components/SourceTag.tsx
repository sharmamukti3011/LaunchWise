import type { Source } from "../api/demo";
import { sourceLabel } from "../lib/labels";

const STYLES: Record<Source, string> = {
  user_provided: "bg-sky-100 text-sky-900",
  derived: "bg-emerald-100 text-emerald-900",
  assumption: "bg-amber-100 text-amber-900",
  estimate: "bg-orange-100 text-orange-900",
};

export function SourceTag({ source }: { source: Source }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs whitespace-nowrap ${STYLES[source]}`}>
      {sourceLabel(source)}
    </span>
  );
}
