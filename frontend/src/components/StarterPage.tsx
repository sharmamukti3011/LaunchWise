import { useState } from "react";
import type { FormEvent } from "react";
import type { Analysis } from "../api/demo";
import {
  PREVIEW_FAILURE_TEXT,
  PublishFailure,
  StorefrontFailure,
  previewStarterPage,
  publishStarterPage,
} from "../api/storefront";
import type { PreviewResult, PublishedPage } from "../api/storefront";
import {
  EMPTY_STARTER,
  buildStarterBody,
  mapStarterErrors,
  prefillFrom,
  unpublishLink,
  validateStarter,
} from "../lib/starterPage";
import type {
  StarterErrors,
  StarterField,
  StarterForm,
} from "../lib/starterPage";

const PUBLISH_FALLBACK =
  "Something went wrong on our side. Please try again shortly.";
const INPUT =
  "mt-1 w-full rounded border border-slate-300 px-3 py-2 text-slate-900";

interface FieldProps {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  children: (aria: {
    "aria-invalid"?: true;
    "aria-describedby"?: string;
  }) => React.ReactNode;
}

function Field({ id, label, hint, error, children }: FieldProps) {
  const errorId = `${id}-error`;
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
      {children(
        error ? { "aria-invalid": true, "aria-describedby": errorId } : {},
      )}
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

export function StarterFormView({
  values,
  errors,
  loading,
  onChange,
  onSubmit,
  onCancel,
}: FormViewProps) {
  const input = (
    field: StarterField,
    max: number,
    extra: Record<string, unknown> = {},
  ) =>
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
    <form
      onSubmit={onSubmit}
      aria-busy={loading}
      noValidate
      className="mt-3 space-y-4"
    >
      <p className="text-sm text-slate-700">
        Nothing is public until you have seen a preview of the page and approved
        it. Everything you type here would appear on the page, so check it
        carefully.
      </p>
      <Field id="starter-name" label="Business name" error={errors.name}>
        {input("name", 60)}
      </Field>
      <Field
        id="starter-description"
        label="Short description (optional)"
        hint="Up to 300 characters."
        error={errors.description}
      >
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
        <Field
          id="starter-offerTitle"
          label="What you offer"
          error={errors.offerTitle}
        >
          {input("offerTitle", 60)}
        </Field>
        <Field
          id="starter-offerPrice"
          label="Price (₹)"
          error={errors.offerPrice}
        >
          {input("offerPrice", 12, {
            inputMode: "decimal",
            autoComplete: "off",
          })}
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
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-slate-300 px-4 py-2 text-sm"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

interface PreviewProps {
  preview: PreviewResult;
  onEdit: () => void;
  onPublish: () => void;
  publishing: boolean;
  error: string | null;
}

export function PreviewView({
  preview,
  onEdit,
  onPublish,
  publishing,
  error,
}: PreviewProps) {
  return (
    <div className="mt-3 space-y-3">
      <p className="text-sm text-slate-700">
        This is a preview of your page, exactly as it would look. Nothing is
        public yet.
      </p>
      {/* A sandbox with no permissions: nothing inside the preview can run a script or navigate. */}
      <iframe
        title="Preview of your starter page"
        sandbox=""
        srcDoc={preview.preview_html}
        className="h-[28rem] w-full rounded border border-slate-300 bg-white"
      />
      <p className="text-sm text-slate-700">
        If you publish, this page becomes public on this site for 7 days. It
        is an example page: it shows a banner saying so, and it is hidden from
        search engines. You will get a private link to take it down at any time.
      </p>
      {error && (
        <p role="alert" className="text-sm text-red-800">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onPublish}
          disabled={publishing}
          className="rounded bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:opacity-60"
        >
          {publishing ? "Publishing…" : "Approve and publish"}
        </button>
        <button
          type="button"
          onClick={onEdit}
          disabled={publishing}
          className="rounded border border-slate-300 px-4 py-2 text-sm"
        >
          Edit details
        </button>
      </div>
    </div>
  );
}

export function PublishedView({
  published,
  origin,
}: {
  published: PublishedPage;
  origin: string;
}) {
  const address = `${origin}${published.public_path}`;
  return (
    <div className="mt-3 space-y-3">
      <p className="font-medium text-emerald-800">Your example page is live.</p>
      <p className="text-sm">
        <a
          href={published.public_path}
          target="_blank"
          rel="noopener noreferrer"
          className="break-all text-emerald-800 underline"
        >
          {address}
        </a>
      </p>
      <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
        <p className="font-medium">Save your unpublish link now.</p>
        <p className="mt-1">
          Open it any time to take the page down. It is shown only once and we
          cannot show it again, because we keep only a scrambled copy.
        </p>
        <p className="mt-2 break-all rounded bg-white p-2 font-mono text-xs">
          {unpublishLink(origin, published.slug, published.unpublish_token)}
        </p>
      </div>
      <p className="text-sm text-slate-600">
        The page goes away by itself after {published.expires_in_days} days.
      </p>
    </div>
  );
}

type UnpublishState = "ready" | "working" | "done" | "failed";

/** What someone sees after opening their private unpublish link. Nothing happens until they click. */
export function UnpublishView({
  state,
  message,
  onConfirm,
}: {
  state: UnpublishState;
  message: string;
  onConfirm: () => void;
}) {
  return (
    <section
      aria-labelledby="unpublish-heading"
      className="rounded-lg border border-slate-200 bg-white p-4"
    >
      <h2 id="unpublish-heading" className="text-lg font-semibold">
        Take down your example page
      </h2>
      {state === "done" ? (
        <>
          <p className="mt-2 text-sm text-emerald-800">
            Your page has been unpublished. It is no longer public.
          </p>
          <a href="/" className="mt-3 inline-block text-sm underline">
            Back to LaunchWise
          </a>
        </>
      ) : (
        <>
          <p className="mt-2 text-sm text-slate-700">
            This takes your example page down straight away.
          </p>
          {state === "failed" && (
            <p role="alert" className="mt-2 text-sm text-red-800">
              {message}
            </p>
          )}
          <button
            type="button"
            onClick={onConfirm}
            disabled={state === "working"}
            className="mt-3 rounded bg-red-700 px-4 py-2 font-medium text-white hover:bg-red-800 disabled:opacity-60"
          >
            {state === "working" ? "Unpublishing…" : "Unpublish this page"}
          </button>
        </>
      )}
    </section>
  );
}

type Phase = "closed" | "editing" | "previewing" | "published";

/** After a result with a recommendation: make a starter page for the idea, and preview it first. */
export function StarterPageSection({ analysis }: { analysis: Analysis }) {
  const [phase, setPhase] = useState<Phase>("closed");
  const [values, setValues] = useState<StarterForm>(EMPTY_STARTER);
  const [errors, setErrors] = useState<StarterErrors>({});
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [published, setPublished] = useState<PublishedPage | null>(null);
  const prefill = prefillFrom(analysis);
  if (!prefill) return null;

  function open() {
    // The offer comes from the recommended option; the owner can change both.
    setValues((current) =>
      current.offerTitle === "" ? { ...current, ...prefill } : current,
    );
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
      setPreview(
        await previewStarterPage(
          buildStarterBody(values, analysis.food_business),
        ),
      );
      setPhase("previewing");
    } catch (error) {
      if (error instanceof StorefrontFailure) {
        setErrors(
          error.kind === "invalid"
            ? mapStarterErrors(error.fields)
            : { form: PREVIEW_FAILURE_TEXT[error.kind] },
        );
      } else {
        setErrors({ form: PREVIEW_FAILURE_TEXT.server });
      }
    } finally {
      setLoading(false);
    }
  }

  async function onPublish() {
    if (!preview || publishing) return;
    setPublishing(true);
    setPublishError(null);
    try {
      // Only this explicit click grants approval, for exactly the page that was previewed.
      setPublished(
        await publishStarterPage(preview.draft_id, preview.config_hash),
      );
      setPhase("published");
    } catch (error) {
      setPublishError(
        error instanceof PublishFailure ? error.message : PUBLISH_FALLBACK,
      );
    } finally {
      setPublishing(false);
    }
  }

  return (
    <section
      aria-labelledby="starter-heading"
      className="rounded-lg border border-slate-200 bg-white p-4"
    >
      <h2 id="starter-heading" className="text-lg font-semibold">
        A starter page for this idea
      </h2>
      {phase === "closed" && (
        <>
          <p className="mt-1 text-sm text-slate-600">
            Make a simple example page for your idea. You will see a preview
            first.
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
      {phase === "previewing" && preview && (
        <PreviewView
          preview={preview}
          onEdit={() => setPhase("editing")}
          onPublish={() => void onPublish()}
          publishing={publishing}
          error={publishError}
        />
      )}
      {phase === "published" && published && (
        <PublishedView published={published} origin={window.location.origin} />
      )}
    </section>
  );
}
