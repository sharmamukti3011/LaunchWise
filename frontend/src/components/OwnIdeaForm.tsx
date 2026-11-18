import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { AnalyzeFailure, FAILURE_TEXT, analyzeOwn, fetchEvidenceChoices } from "../api/analyze";
import type { EvidenceChoice } from "../api/analyze";
import {
  EMPTY_FORM,
  buildAnalyzeBody,
  mapServerErrors,
  setField,
  validateOwnIdea,
} from "../lib/ownIdea";
import type { FieldKey, FormErrors, OwnIdeaForm } from "../lib/ownIdea";
import { ownResult } from "../lib/results";
import type { ResultView } from "../lib/results";

const INPUT = "mt-1 w-full rounded border border-slate-300 px-3 py-2 text-slate-900";

interface FieldProps {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: (aria: { "aria-invalid"?: true; "aria-describedby"?: string }) => ReactNode;
}

/** A label, a hint, the control, and a fixed error message linked to it for screen readers. */
function Field({ id, label, hint, error, children }: FieldProps) {
  const errorId = `${id}-error`;
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
      {children(error ? { "aria-invalid": true, "aria-describedby": errorId } : {})}
      {error && (
        <p id={errorId} className="mt-1 text-sm text-red-800">
          {error}
        </p>
      )}
    </div>
  );
}

interface ViewProps {
  form: OwnIdeaForm;
  errors: FormErrors;
  evidence: EvidenceChoice[];
  running: boolean;
  onChange: (key: FieldKey, value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}

export function OwnIdeaFormView({ form, errors, evidence, running, onChange, onSubmit }: ViewProps) {
  const text = (key: FieldKey, id: string, value: string, extra: Record<string, unknown> = {}) =>
    function Input(aria: object) {
      return (
        <input
          id={id}
          type="text"
          value={value}
          onChange={(e) => onChange(key, e.target.value)}
          className={INPUT}
          {...extra}
          {...aria}
        />
      );
    };
  const money = (key: FieldKey, id: string, value: string) =>
    text(key, id, value, { inputMode: "decimal", autoComplete: "off" });
  const whole = (key: FieldKey, id: string, value: string) =>
    text(key, id, value, { inputMode: "numeric", autoComplete: "off" });

  const option = (prefix: "original" | "alt", data: OwnIdeaForm["original"], titleLabel: string) => (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <Field id={`own-${prefix}-title`} label={titleLabel} error={errors[`${prefix}.title`]}>
          {text(`${prefix}.title`, `own-${prefix}-title`, data.title, { maxLength: 80 })}
        </Field>
      </div>
      <Field id={`own-${prefix}-price`} label="Price per item (₹)" error={errors[`${prefix}.price`]}>
        {money(`${prefix}.price`, `own-${prefix}-price`, data.price)}
      </Field>
      <Field id={`own-${prefix}-cost`} label="Cost to make each item (₹)" error={errors[`${prefix}.cost`]}>
        {money(`${prefix}.cost`, `own-${prefix}-cost`, data.cost)}
      </Field>
      <Field id={`own-${prefix}-startup`} label="Startup costs (₹)" error={errors[`${prefix}.startup`]}>
        {money(`${prefix}.startup`, `own-${prefix}-startup`, data.startup)}
      </Field>
      <Field
        id={`own-${prefix}-minutes`}
        label="Minutes per item (optional)"
        hint="Leave blank and we will assume it and say so."
        error={errors[`${prefix}.minutes`]}
      >
        {whole(`${prefix}.minutes`, `own-${prefix}-minutes`, data.minutes)}
      </Field>
    </div>
  );

  return (
    <details className="mt-6 rounded-lg border border-slate-200 bg-white p-4">
      <summary className="cursor-pointer text-lg font-semibold">Try your own idea</summary>
      <form onSubmit={onSubmit} aria-busy={running} noValidate className="mt-4 space-y-6">
        <fieldset className="space-y-3">
          <legend className="font-medium">About you</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="own-budget" label="Budget (₹)" error={errors.budget}>
              {money("budget", "own-budget", form.budget)}
            </Field>
            <Field id="own-location" label="Location" error={errors.location}>
              {text("location", "own-location", form.location, { maxLength: 80 })}
            </Field>
            <Field id="own-unitsPerDay" label="Items you can make per day" error={errors.unitsPerDay}>
              {whole("unitsPerDay", "own-unitsPerDay", form.unitsPerDay)}
            </Field>
            <Field id="own-daysPerWeek" label="Days per week" error={errors.daysPerWeek}>
              {whole("daysPerWeek", "own-daysPerWeek", form.daysPerWeek)}
            </Field>
            <Field
              id="own-hoursPerWeek"
              label="Hours per week (optional)"
              hint="Leave blank and we will assume it and say so."
              error={errors.hoursPerWeek}
            >
              {whole("hoursPerWeek", "own-hoursPerWeek", form.hoursPerWeek)}
            </Field>
            <Field id="own-category" label="Kind of business" error={errors.category}>
              {text("category", "own-category", form.category, { maxLength: 60 })}
            </Field>
            <Field id="own-skills" label="Skills you have" hint="Separate with commas." error={errors.skills}>
              {text("skills", "own-skills", form.skills)}
            </Field>
            <Field id="own-equipment" label="Equipment you have" hint="Separate with commas." error={errors.equipment}>
              {text("equipment", "own-equipment", form.equipment)}
            </Field>
          </div>
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="font-medium">Your idea</legend>
          {option("original", form.original, "What is your idea?")}
        </fieldset>

        <fieldset className="space-y-3">
          <legend className="font-medium">One alternative (optional)</legend>
          {option("alt", form.alt, "Alternative idea")}
          <Field
            id="own-alt-evidenceId"
            label="Market evidence it is based on"
            hint="Optional. With no market evidence, its market score is a neutral 50."
            error={errors["alt.evidenceId"]}
          >
            {(aria) => (
              <select
                id="own-alt-evidenceId"
                value={form.alt.evidenceId}
                onChange={(e) => onChange("alt.evidenceId", e.target.value)}
                className={INPUT}
                {...aria}
              >
                <option value="">No market evidence</option>
                {evidence.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {`${entry.title} (${entry.source_name})${entry.direction === "against" ? " · argues against" : ""}`}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </fieldset>

        {errors.form && (
          <p role="alert" className="text-sm text-red-800">
            {errors.form}
          </p>
        )}
        <button
          type="submit"
          disabled={running}
          className="rounded bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:opacity-60"
        >
          {running ? "Analysing…" : "Run analysis"}
        </button>
      </form>
    </details>
  );
}

export function OwnIdeaSection({ onResult }: { onResult: (result: ResultView) => void }) {
  const [form, setForm] = useState<OwnIdeaForm>(EMPTY_FORM);
  const [errors, setErrors] = useState<FormErrors>({});
  const [running, setRunning] = useState(false);
  const [evidence, setEvidence] = useState<EvidenceChoice[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    fetchEvidenceChoices(controller.signal)
      .then(setEvidence)
      .catch(() => undefined); // aborted: nothing to do
    return () => controller.abort();
  }, []);

  function onChange(key: FieldKey, value: string) {
    setForm((current) => setField(current, key, value));
    // Editing a field clears its own message, not the others.
    setErrors((current) => {
      if (!(key in current)) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (running) return;
    const problems = validateOwnIdea(form);
    if (Object.keys(problems).length > 0) {
      setErrors(problems);
      return;
    }
    setErrors({});
    setRunning(true);
    const body = buildAnalyzeBody(form);
    try {
      onResult(ownResult(body, await analyzeOwn(body)));
    } catch (error) {
      if (error instanceof AnalyzeFailure) {
        setErrors(
          error.kind === "invalid" ? mapServerErrors(error.fields) : { form: FAILURE_TEXT[error.kind] },
        );
      } else {
        setErrors({ form: FAILURE_TEXT.server });
      }
    } finally {
      setRunning(false);
    }
  }

  return (
    <OwnIdeaFormView
      form={form}
      errors={errors}
      evidence={evidence}
      running={running}
      onChange={onChange}
      onSubmit={(event) => void onSubmit(event)}
    />
  );
}
