/** What POST /api/storefront/preview takes. Money travels as an exact string. */
export interface StarterBody {
  business_name: string;
  description: string;
  contact_email?: string;
  offer_title: string;
  offer_price: string;
  food_business: boolean;
}

export interface PreviewResult {
  draft_id: string;
  slug: string;
  public_path: string;
  /** Binds the owner's approval to exactly this page. Publishing must present it. */
  config_hash: string;
  expires_in_minutes: number;
  /** The page, already rendered and escaped by the server. */
  preview_html: string;
}

export type StarterErrorCode = "not_allowed" | "no_links_or_markup" | "invalid";

export interface StarterFieldError {
  field: string;
  code: StarterErrorCode;
}

export type PreviewFailureKind =
  "invalid" | "rate_limited" | "server" | "network";

// Fixed text only. Nothing the server says is ever shown.
export const PREVIEW_FAILURE_TEXT: Record<PreviewFailureKind, string> = {
  invalid: "Please check the highlighted fields and try again.",
  rate_limited: "Too many requests. Please try again in a moment.",
  server: "Something went wrong on our side. Please try again shortly.",
  network: "Could not reach the server. Check your connection and try again.",
};

export class StorefrontFailure extends Error {
  readonly kind: PreviewFailureKind;
  readonly fields: StarterFieldError[];
  constructor(kind: PreviewFailureKind, fields: StarterFieldError[] = []) {
    super(PREVIEW_FAILURE_TEXT[kind]);
    this.name = "StorefrontFailure";
    this.kind = kind;
    this.fields = fields;
  }
}

/** Reduce a server error to the field and a fixed code: the server's wording is never kept. */
function codeOf(message: string): StarterErrorCode {
  if (message.includes("not_allowed")) return "not_allowed";
  if (message.includes("no_links_or_markup")) return "no_links_or_markup";
  return "invalid";
}

function fieldErrors(body: unknown): StarterFieldError[] {
  const errors = (body as { errors?: unknown } | null)?.errors;
  if (!Array.isArray(errors)) return [];
  return errors
    .filter(
      (e): e is { field: string; message?: string } =>
        typeof (e as { field?: unknown })?.field === "string",
    )
    .map((e) => ({ field: e.field, code: codeOf(String(e.message ?? "")) }));
}

export async function previewStarterPage(
  body: StarterBody,
  signal?: AbortSignal,
): Promise<PreviewResult> {
  let response: Response;
  try {
    response = await fetch("/api/storefront/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new StorefrontFailure("network");
  }
  if (response.ok) return (await response.json()) as PreviewResult;
  if (response.status === 422) {
    throw new StorefrontFailure(
      "invalid",
      fieldErrors(await response.json().catch(() => null)),
    );
  }
  if (response.status === 413) throw new StorefrontFailure("invalid");
  if (response.status === 429) throw new StorefrontFailure("rate_limited");
  throw new StorefrontFailure("server");
}

// ---- approve and publish, and unpublish --------------------------------------------------------

export interface PublishedPage {
  slug: string;
  public_path: string;
  /** Shown once. The server keeps only a hash of it. */
  unpublish_token: string;
  expires_in_days: number;
}

export type PublishFailureKind =
  "expired" | "changed" | "full" | "rate_limited" | "server" | "network";

// Fixed text only. Nothing the server says is ever shown.
export const PUBLISH_FAILURE_TEXT: Record<PublishFailureKind, string> = {
  expired: "This preview has expired. Please preview the page again.",
  changed: "The page changed since you previewed it. Please preview it again.",
  full: "Too many example pages are live right now. Please try again later.",
  rate_limited:
    "You have published a few pages recently. Please try again later.",
  server: "Something went wrong on our side. Please try again shortly.",
  network: "Could not reach the server. Check your connection and try again.",
};

export class PublishFailure extends Error {
  readonly kind: PublishFailureKind;
  constructor(kind: PublishFailureKind) {
    super(PUBLISH_FAILURE_TEXT[kind]);
    this.name = "PublishFailure";
    this.kind = kind;
  }
}

async function post(
  url: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<Response | null> {
  try {
    return await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    return null; // a network failure
  }
}

const PUBLISH_STATUS: Record<number, PublishFailureKind> = {
  404: "expired",
  409: "changed",
  503: "full",
  429: "rate_limited",
};

/** "Approve and publish": the hash is the one of the page the owner was just shown. */
export async function publishStarterPage(
  draftId: string,
  configHash: string,
  signal?: AbortSignal,
): Promise<PublishedPage> {
  const response = await post(
    "/api/storefront/publish",
    { draft_id: draftId, config_hash: configHash },
    signal,
  );
  if (response === null) throw new PublishFailure("network");
  if (response.ok) return (await response.json()) as PublishedPage;
  throw new PublishFailure(PUBLISH_STATUS[response.status] ?? "server");
}

export type UnpublishFailureKind =
  "invalid" | "rate_limited" | "server" | "network";

export const UNPUBLISH_FAILURE_TEXT: Record<UnpublishFailureKind, string> = {
  invalid: "That unpublish link is not valid, or the page is already down.",
  rate_limited: "Too many attempts. Please try again later.",
  server: "Something went wrong on our side. Please try again shortly.",
  network: "Could not reach the server. Check your connection and try again.",
};

export class UnpublishFailure extends Error {
  readonly kind: UnpublishFailureKind;
  constructor(kind: UnpublishFailureKind) {
    super(UNPUBLISH_FAILURE_TEXT[kind]);
    this.name = "UnpublishFailure";
    this.kind = kind;
  }
}

export async function unpublishPage(
  slug: string,
  token: string,
  signal?: AbortSignal,
): Promise<void> {
  const response = await post(
    "/api/storefront/unpublish",
    { slug, token },
    signal,
  );
  if (response === null) throw new UnpublishFailure("network");
  if (response.ok) return;
  throw new UnpublishFailure(
    response.status === 404
      ? "invalid"
      : response.status === 429
        ? "rate_limited"
        : "server",
  );
}
