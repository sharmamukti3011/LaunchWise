import type { Feasibility, Source } from "../api/demo";
import { formatRupees } from "./labels";

export interface FigureRow {
  label: string;
  value: string;
  source: Source;
}

const units = (n: number) => `${n} ${n === 1 ? "unit" : "units"}`;

/** The figures behind one option, each with the source tag the engine gave it. */
export function keyFigures(f: Feasibility): FigureRow[] {
  const check = f.budget_check;
  const weeks = f.break_even.medium.weeks;
  const rows: FigureRow[] = [
    { label: "Startup cost", value: formatRupees(f.startup_cost.value), source: f.startup_cost.source },
    {
      label: "Margin per unit",
      value: formatRupees(f.contribution_margin.value),
      source: f.contribution_margin.source,
    },
    {
      label: "Margin",
      value: f.contribution_margin_pct.value === null ? "—" : `${f.contribution_margin_pct.value}%`,
      source: f.contribution_margin_pct.source,
    },
    { label: "Weekly capacity", value: units(f.weekly_capacity.value), source: f.weekly_capacity.source },
    {
      label: "Most you could sell a week",
      value: formatRupees(f.max_weekly_revenue.value),
      source: f.max_weekly_revenue.source,
    },
    {
      label: "Break-even sales",
      value: f.break_even_units.value === null ? "not reached" : units(f.break_even_units.value),
      source: f.break_even_units.source,
    },
    {
      label: "Weeks to break even (50% demand)",
      value: weeks.value === null ? "not reached" : `${weeks.value} ${weeks.value === 1 ? "week" : "weeks"}`,
      source: weeks.source,
    },
  ];
  if (check.working_capital) {
    rows.push({
      label: "Working capital reserve",
      value: formatRupees(check.working_capital.value),
      source: check.working_capital.source,
    });
  }
  rows.push({
    label: "Total needed up front",
    value: formatRupees(check.total_required.value),
    source: check.total_required.source,
  });
  rows.push(
    check.within_budget
      ? { label: "Left in budget", value: formatRupees(check.headroom.value), source: check.headroom.source }
      : { label: "Short of budget by", value: formatRupees(check.shortfall.value), source: check.shortfall.source },
  );
  return rows;
}
