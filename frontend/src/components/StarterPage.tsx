import { useState } from "react";
import type { FormEvent } from "react";
import type { Analysis } from "../api/demo";
import { PREVIEW_FAILURE_TEXT, StorefrontFailure, previewStarterPage } from "../api/storefront";
import type { PreviewResult } from "../api/storefront";
import { EMPTY_STARTER, buildStarterBody, mapStarterErrors, prefillFrom, validateStarter } from "../lib/starterPage";
import type { StarterErrors, StarterField, StarterForm } from "../lib/starterPage";

const INPUT = "mt-1 w-full rounded border border-slate-300 px-3 py-2 text-slate-900";

interface FieldProps {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: (aria: { "aria-invalid"?: true; "aria-describedby"?: string }) => React.ReactNode;
}

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

interface FormViewProps {
  values: StarterForm;
  errors: StarterErrors;
  loading: boolean;
  onChange: (field: StarterField, value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
}

export function StarterFormView({ values, errors, loading, onChange, onSubmit, onCancel }: FormViewProps) {
  const input = (field: StarterField, max: number, extra: Record<string, unknown> = {}) =>
    function Input(aria: object) {
      return (
        <input
          id={`starter-${field}`}
          type="text"
          maxLength={max}
          value={values[field]}
          onChange={(e) => onChange(field, e.target.value)}
          className={INPUT}
          {...extra}
          {...aria}
        />
      );
    };
  return (
    <form onSubmit={onSubmit} aria-busy={loading} noValidate className="mt-3 space-y-4">
      <p className="text-sm text-slate-700">
        Nothing is public until you have seen a preview of the page and approved it. Everything you type here
        would appear on the page, so check it carefully.
      </p>
      <Field id="starter-name" label="Business name" error={errors.name}>
        {input("name", 60)}
      </Field>
      <Field id="starter-description" label="Short description (optional)" hint="Up to 300 characters." error={errors.description}>
        {(aria) => (
          <textarea
            id="starter-description"
            rows={3}
            maxLength={300}
            value={values.description}
            onChange={(e) => onChange("description", e.target.value)}
            className={INPUT}
            {...aria}
          />
        )}
      </Field>
      <Field
        id="starter-email"
        label="Contact email (optional)"
        hint="If you add one, it is shown as plain text on the public page, so anyone can read it."
        error={errors.email}
      >
        {input("email", 254, { type: "email", autoComplete: "email" })}
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="starter-offerTitle" label="What you offer" error={errors.offerTitle}>
          {input("offerTitle", 60)}
        </Field>
        <Field id="starter-offerPrice" label="Price (₹)" error={errors.offerPrice}>
          {input("offerPrice", 12, { inputMode: "decimal", autoComplete: "off" })}
        </Field>
      </div>
      {errors.form && (
        <p role="alert" className="text-sm text-red-800">
          {errors.form}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:opacity-60"
        >
          {loading ? "Building the preview…" : "Preview the page"}
        </button>
        <button type="button" onClick={onCancel} className="rounded border border-slate-300 px-4 py-2 text-sm">
          Cancel
        </button>
      </div>
    </form>
  );
}

export function PreviewView({ preview, onEdit }: { preview: PreviewResult; onEdit: () => void }) {
  return (
    <div className="mt-3 space-y-3">
      <p className="text-sm text-slate-700">
        This is a preview of your page, exactly as it would look. Nothing is public yet.
      </p>
      {/* A sandbox with no permissions: nothing inside the preview can run a script or navigate. */}
      <iframe
        title="Preview of your starter page"
        sandbox=""
        srcDoc={preview.preview_html}
        className="h-[28rem] w-full rounded border border-slate-300 bg-white"
      />
      <button type="button" onClick={onEdit} className="rounded border border-slate-300 px-4 py-2 text-sm">
        Edit details
      </button>
    </div>
  );
}

type Phase = "closed" | "editing" | "previewing";

/** After a result with a recommendation: make a starter page for the idea, and preview it first. */
export function StarterPageSection({ analysis }: { analysis: Analysis }) {
  const [phase, setPhase] = useState<Phase>("closed");
  const [values, setValues] = useState<StarterForm>(EMPTY_STARTER);
  const [errors, setErrors] = useState<StarterErrors>({});
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const prefill = prefillFrom(analysis);
  if (!prefill) return null;

  function open() {
    // The offer comes from the recommended option; the owner can change both.
    setValues((current) => (current.offerTitle === "" ? { ...current, ...prefill } : current));
    setPhase("editing");
  }

  function onChange(field: StarterField, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => {
      if (!(field in current)) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading) return;
    const problems = validateStarter(values);
    if (Object.keys(problems).length > 0) {
      setErrors(problems);
      return;
    }
    setErrors({});
    setLoading(true);
    try {
      setPreview(await previewStarterPage(buildStarterBody(values, analysis.food_business)));
      setPhase("previewing");
    } catch (error) {
      if (error instanceof StorefrontFailure) {
        setErrors(error.kind === "invalid" ? mapStarterErrors(error.fields) : { form: PREVIEW_FAILURE_TEXT[error.kind] });
      } else {
        setErrors({ form: PREVIEW_FAILURE_TEXT.server });
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="starter-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="starter-heading" className="text-lg font-semibold">
        A starter page for this idea
      </h2>
      {phase === "closed" && (
        <>
          <p className="mt-1 text-sm text-slate-600">
            Make a simple example page for your idea. You will see a preview first.
          </p>
          <button
            type="button"
            onClick={open}
            className="mt-3 rounded bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800"
          >
            Create a starter page for this idea
          </button>
        </>
      )}
      {phase === "editing" && (
        <StarterFormView
          values={values}
          errors={errors}
          loading={loading}
          onChange={onChange}
          onSubmit={(event) => void onSubmit(event)}
          onCancel={() => setPhase("closed")}
        />
      )}
      {phase === "previewing" && preview && <PreviewView preview={preview} onEdit={() => setPhase("editing")} />}
    </section>
  );
}
