import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode, Ref } from "react";
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
import { MAX_DESCRIPTION, clearMark } from "../lib/intakeDraft";
import type { Mark, Marks } from "../lib/intakeDraft";
import { fillFromDescription } from "../lib/intakeFlow";
import { revealContact } from "../lib/contactPanel";
import { ownResult } from "../lib/results";
import { applySuggestion } from "../lib/suggestion";
import type { SuggestionInfo } from "../api/demo";
import type { ResultView } from "../lib/results";

const INPUT = "mt-1 w-full rounded border border-slate-300 px-3 py-2 text-slate-900";

interface FieldProps {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  mark?: Mark;
  children: (aria: { "aria-invalid"?: true; "aria-describedby"?: string }) => ReactNode;
}

const MARK_TEXT: Record<Mark, string> = {
  from_description: "from your description",
  please_fill: "please fill in",
};
const MARK_STYLE: Record<Mark, string> = {
  from_description: "bg-emerald-100 text-emerald-900",
  please_fill: "bg-amber-100 text-amber-900",
};

/** A label, a hint, the control, and a fixed error message linked to it for screen readers. */
function Field({ id, label, hint, error, mark, children }: FieldProps) {
  const errorId = `${id}-error`;
  const markId = `${id}-mark`;
  const describedBy = [error ? errorId : null, mark ? markId : null].filter(Boolean).join(" ");
  const aria: { "aria-invalid"?: true; "aria-describedby"?: string } = {};
  if (error) aria["aria-invalid"] = true;
  if (describedBy) aria["aria-describedby"] = describedBy;
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {mark && (
        <span id={markId} className={`ml-2 rounded px-1.5 py-0.5 text-xs ${MARK_STYLE[mark]}`}>
          {MARK_TEXT[mark]}
        </span>
      )}
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
      {children(aria)}
      {error && (
        <p id={errorId} className="mt-1 text-sm text-red-800">
          {error}
        </p>
      )}
    </div>
  );
}

export interface IntakeUi {
  text: string;
  running: boolean;
  message: { kind: "info" | "error"; text: string } | null;
  /** True once the server said describing is not available, so the button stays off. */
  unavailable: boolean;
}

interface ViewProps {
  form: OwnIdeaForm;
  errors: FormErrors;
  marks: Marks;
  intake: IntakeUi;
  evidence: EvidenceChoice[];
  running: boolean;
  onChange: (key: FieldKey, value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onIntakeText: (text: string) => void;
  onIntakeSubmit: () => void;
  /** Whether the section is open, so a suggestion can open it. */
  open: boolean;
  onToggle: (open: boolean) => void;
  /** A status message, such as "Filled from LaunchWise's suggestion". */
  notice: string | null;
  detailsRef?: Ref<HTMLDetailsElement>;
}

export function OwnIdeaFormView({
  form,
  errors,
  marks,
  intake,
  evidence,
  running,
  onChange,
  onSubmit,
  onIntakeText,
  onIntakeSubmit,
  open,
  onToggle,
  notice,
  detailsRef,
}: ViewProps) {
  const text = (key: FieldKey, id: string, value: string, extra: Record<string, unknown> = {}) =>
    function Input(aria: object) {
      return (
        <input
          id={id}
          type="text"
          value={value}
          onChange={(e) => onChange(key, e.target.value)}
          className={marks[key] === "please_fill" ? `${INPUT} border-amber-500 bg-amber-50` : INPUT}
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
        <Field id={`own-${prefix}-title`} label={titleLabel} error={errors[`${prefix}.title`]} mark={marks[`${prefix}.title`]}>
          {text(`${prefix}.title`, `own-${prefix}-title`, data.title, { maxLength: 80 })}
        </Field>
      </div>
      <Field id={`own-${prefix}-price`} label="Price per item (₹)" error={errors[`${prefix}.price`]} mark={marks[`${prefix}.price`]}>
        {money(`${prefix}.price`, `own-${prefix}-price`, data.price)}
      </Field>
      <Field id={`own-${prefix}-cost`} label="Cost to make each item (₹)" error={errors[`${prefix}.cost`]} mark={marks[`${prefix}.cost`]}>
        {money(`${prefix}.cost`, `own-${prefix}-cost`, data.cost)}
      </Field>
      <Field id={`own-${prefix}-startup`} label="Startup costs (₹)" error={errors[`${prefix}.startup`]} mark={marks[`${prefix}.startup`]}>
        {money(`${prefix}.startup`, `own-${prefix}-startup`, data.startup)}
      </Field>
      <Field
        id={`own-${prefix}-minutes`}
        label="Minutes per item (optional)"
        hint="Leave blank and we will assume it and say so."
        error={errors[`${prefix}.minutes`]} mark={marks[`${prefix}.minutes`]}
      >
        {whole(`${prefix}.minutes`, `own-${prefix}-minutes`, data.minutes)}
      </Field>
    </div>
  );

  return (
    <details
      ref={detailsRef}
      open={open}
      onToggle={(event) => onToggle(event.currentTarget.open)}
      className="mt-6 rounded-lg border border-slate-200 bg-white p-4"
    >
      <summary className="cursor-pointer text-lg font-semibold">Try your own idea</summary>
      <section aria-labelledby="own-description-heading" className="mt-4 rounded border border-slate-200 p-3">
        <h3 id="own-description-heading" className="font-medium">
          Describe your idea
        </h3>
        <p className="text-sm text-slate-600">
          Write a few sentences in your own words. Claude only drafts the form from what you wrote:
          you check and edit every field, then click Run analysis.
        </p>
        <label htmlFor="own-description" className="mt-2 block text-sm font-medium">
          Your idea, in your own words
        </label>
        <textarea
          id="own-description"
          rows={4}
          maxLength={MAX_DESCRIPTION}
          value={intake.text}
          onChange={(e) => onIntakeText(e.target.value)}
          className={INPUT}
        />
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs text-slate-500">
            {intake.text.length.toLocaleString("en-IN")} / {MAX_DESCRIPTION.toLocaleString("en-IN")}
          </span>
          <button
            type="button"
            onClick={onIntakeSubmit}
            disabled={intake.running || intake.unavailable || intake.text.trim() === ""}
            className="rounded border border-emerald-700 px-3 py-1.5 text-sm font-medium text-emerald-800 hover:bg-emerald-50 disabled:opacity-60"
          >
            {intake.running ? "Reading…" : "Fill the form for me"}
          </button>
        </div>
        {intake.message && (
          <p
            role={intake.message.kind === "error" ? "alert" : "status"}
            className={`mt-2 text-sm ${intake.message.kind === "error" ? "text-red-800" : "text-emerald-800"}`}
          >
            {intake.message.text}
          </p>
        )}
      </section>
      <form onSubmit={onSubmit} aria-busy={running} noValidate className="mt-4 space-y-6">
        <fieldset className="space-y-3">
          <legend className="font-medium">About you</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="own-budget" label="Budget (₹)" error={errors.budget} mark={marks.budget}>
              {money("budget", "own-budget", form.budget)}
            </Field>
            <Field id="own-location" label="Location" error={errors.location} mark={marks.location}>
              {text("location", "own-location", form.location, { maxLength: 80 })}
            </Field>
            <Field id="own-unitsPerDay" label="Items you can make per day" error={errors.unitsPerDay} mark={marks.unitsPerDay}>
              {whole("unitsPerDay", "own-unitsPerDay", form.unitsPerDay)}
            </Field>
            <Field id="own-daysPerWeek" label="Days per week" error={errors.daysPerWeek} mark={marks.daysPerWeek}>
              {whole("daysPerWeek", "own-daysPerWeek", form.daysPerWeek)}
            </Field>
            <Field
              id="own-hoursPerWeek"
              label="Hours per week (optional)"
              hint="Leave blank and we will assume it and say so."
              error={errors.hoursPerWeek} mark={marks.hoursPerWeek}
            >
              {whole("hoursPerWeek", "own-hoursPerWeek", form.hoursPerWeek)}
            </Field>
            <Field id="own-category" label="Kind of business" error={errors.category} mark={marks.category}>
              {text("category", "own-category", form.category, { maxLength: 60 })}
            </Field>
            <Field id="own-skills" label="Skills you have" hint="Separate with commas." error={errors.skills} mark={marks.skills}>
              {text("skills", "own-skills", form.skills)}
            </Field>
            <Field id="own-equipment" label="Equipment you have" hint="Separate with commas." error={errors.equipment} mark={marks.equipment}>
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

        {notice && (
          <p role="status" className="text-sm text-violet-900">
            {notice}
          </p>
        )}
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

/** A request to copy one of LaunchWise's suggestions into the form. `key` is new for each click. */
export interface SuggestionRequest {
  key: number;
  title: string;
  suggestion: SuggestionInfo;
}

const SUGGESTION_NOTICE =
  "Filled from LaunchWise's suggestion. Edit anything, then click Run analysis.";

export function OwnIdeaSection({
  onResult,
  suggestionRequest,
}: {
  onResult: (result: ResultView) => void;
  suggestionRequest: SuggestionRequest | null;
}) {
  const [form, setForm] = useState<OwnIdeaForm>(EMPTY_FORM);
  const [errors, setErrors] = useState<FormErrors>({});
  const [marks, setMarks] = useState<Marks>({});
  const [running, setRunning] = useState(false);
  const [evidence, setEvidence] = useState<EvidenceChoice[]>([]);
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [seenSuggestion, setSeenSuggestion] = useState(0);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const [intake, setIntake] = useState<IntakeUi>({
    text: "",
    running: false,
    message: null,
    unavailable: false,
  });

  // A new suggestion request copies it into the alternative's fields and opens the section.
  // Done while rendering (React's "adjust state when a prop changes"), not in an effect.
  if (suggestionRequest && suggestionRequest.key !== seenSuggestion) {
    setSeenSuggestion(suggestionRequest.key);
    setForm((current) => applySuggestion(current, suggestionRequest.title, suggestionRequest.suggestion));
    setMarks((current) => {
      const next = { ...current };
      for (const key of ["alt.title", "alt.price", "alt.cost", "alt.startup", "alt.minutes"] as const) {
        delete next[key];
      }
      return next;
    });
    setErrors({});
    setOpen(true);
    setNotice(SUGGESTION_NOTICE);
  }

  // After the copy, scroll to the form and put focus on the alternative's name.
  useEffect(() => {
    if (seenSuggestion > 0) revealContact(detailsRef.current, document.getElementById("own-alt-title"));
  }, [seenSuggestion]);

  useEffect(() => {
    const controller = new AbortController();
    fetchEvidenceChoices(controller.signal)
      .then(setEvidence)
      .catch(() => undefined); // aborted: nothing to do
    return () => controller.abort();
  }, []);

  function onChange(key: FieldKey, value: string) {
    setForm((current) => setField(current, key, value));
    setNotice(null);
    // Editing a field clears its own message and its own mark, not the others.
    setMarks((current) => clearMark(current, key));
    setErrors((current) => {
      if (!(key in current)) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  }

  // "Fill the form for me": drafts the form only. It never runs the analysis.
  async function onIntakeSubmit() {
    if (intake.running) return;
    setIntake((current) => ({ ...current, running: true, message: null }));
    try {
      const outcome = await fillFromDescription(intake.text, form);
      if (outcome.kind === "drafted") {
        setForm(outcome.form);
        setMarks(outcome.marks);
        setErrors({});
      }
      setIntake((current) => ({
        ...current,
        running: false,
        unavailable: outcome.unavailable,
        message: { kind: outcome.kind === "drafted" ? "info" : "error", text: outcome.message },
      }));
    } catch {
      setIntake((current) => ({ ...current, running: false })); // aborted: nothing to show
    }
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
      marks={marks}
      intake={intake}
      evidence={evidence}
      running={running}
      onChange={onChange}
      onSubmit={(event) => void onSubmit(event)}
      onIntakeText={(text) => setIntake((current) => ({ ...current, text }))}
      onIntakeSubmit={() => void onIntakeSubmit()}
      open={open}
      onToggle={setOpen}
      notice={notice}
      detailsRef={detailsRef}
    />
  );
}
