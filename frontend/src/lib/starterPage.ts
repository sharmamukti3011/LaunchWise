import type { Analysis } from "../api/demo";
import type { StarterBody, StarterFieldError } from "../api/storefront";
import { parseMoney } from "./ownIdea";
import { hasControlOrLineBreak } from "./text";

export interface StarterForm {
  name: string;
  description: string;
  email: string;
  offerTitle: string;
  offerPrice: string;
}

export const EMPTY_STARTER: StarterForm = {
  name: "",
  description: "",
  email: "",
  offerTitle: "",
  offerPrice: "",
};

export type StarterField = keyof StarterForm;
export type StarterErrors = Partial<Record<StarterField | "form", string>>;

// The same limits the server enforces.
const MAX_NAME = 60;
const MAX_DESCRIPTION = 300;
const MAX_EMAIL = 254;
const MAX_OFFER = 60;
const MAX_PRICE = 100_000;

// Fixed text only. A refusal never says which rule or which word matched.
export const STARTER_TEXT = {
  name: "Enter your business name, up to 60 characters.",
  description: "Keep the description to 300 characters or fewer.",
  email: "Enter a plain email address, or leave this blank.",
  offerTitle: "Enter what you offer, up to 60 characters.",
  offerPrice: "Enter a price in rupees from 1 to 1,00,000, for example 500.",
  no_links_or_markup:
    "Please remove links, email addresses and markup from this text.",
  not_allowed: "That text isn't allowed on a public page. Please change it.",
  form: "Please check the highlighted fields and try again.",
} as const;

// ---- the same link and markup check as the server ---------------------------------------------

const ENTITY = /&(?:#\d+|#x[0-9a-f]+|[a-z]+);/i;
const SCHEME = /\b[a-z][a-z0-9+.-]*\s*:\s*\/\//i;
const RISKY_SCHEME = /\b(?:javascript|data|vbscript|mailto|tel)\s*:/i;
const WWW = /\bw\s*w\s*w\s*\./i;
const TLDS =
  "com|net|org|in|co|io|me|app|dev|xyz|info|biz|shop|store|site|online|ly|uk|us|ai|edu|gov|tv|cc|club|link|click|top";
// A dot that is plain ("example.com") or spaced on both sides; "nine. In the evening" is prose.
const DOMAIN = new RegExp(
  `\\b[\\w-]+(?:\\.[\\w-]+)*(?:\\.|\\s\\.\\s)(?:${TLDS})\\b`,
  "i",
);

function looksLikeMarkupOrLink(text: string): boolean {
  const plain = text.normalize("NFKC");
  return (
    plain.includes("<") ||
    plain.includes(">") ||
    plain.includes("@") ||
    plain.includes("](") ||
    ENTITY.test(plain) ||
    SCHEME.test(plain) ||
    RISKY_SCHEME.test(plain) ||
    WWW.test(plain) ||
    DOMAIN.test(plain)
  );
}

const EMAIL = /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/;

/** Offer title and price from the recommended option, or null when there is no recommendation. */
export function prefillFrom(
  analysis: Analysis,
): { offerTitle: string; offerPrice: string } | null {
  const id = analysis.ranking.recommended_id;
  const option = analysis.options.find((o) => o.option_id === id);
  if (!id || !option) return null;
  const price = option.feasibility.inputs.price.value;
  const [whole, paise = ""] = price.split(".");
  return {
    offerTitle: option.title.slice(0, MAX_OFFER),
    offerPrice: /^0*$/.test(paise) ? whole : price,
  };
}

function badText(text: string, min: number, max: number): string | null {
  const trimmed = text.trim();
  if (
    trimmed.length < min ||
    trimmed.length > max ||
    hasControlOrLineBreak(trimmed)
  )
    return "length";
  return looksLikeMarkupOrLink(trimmed) ? "markup" : null;
}

export function validateStarter(form: StarterForm): StarterErrors {
  const errors: StarterErrors = {};
  const fields: [StarterField, number, number][] = [
    ["name", 1, MAX_NAME],
    ["description", 0, MAX_DESCRIPTION],
    ["offerTitle", 1, MAX_OFFER],
  ];
  for (const [field, min, max] of fields) {
    const problem = badText(form[field], min, max);
    if (problem === "markup") errors[field] = STARTER_TEXT.no_links_or_markup;
    else if (problem) errors[field] = STARTER_TEXT[field];
  }
  const email = form.email.trim();
  if (
    email !== "" &&
    (email.length > MAX_EMAIL ||
      hasControlOrLineBreak(email) ||
      !EMAIL.test(email))
  ) {
    errors.email = STARTER_TEXT.email;
  }
  const price = parseMoney(form.offerPrice);
  if (price === null || Number(price) < 1 || Number(price) > MAX_PRICE)
    errors.offerPrice = STARTER_TEXT.offerPrice;
  return errors;
}

export function buildStarterBody(
  form: StarterForm,
  foodBusiness: boolean,
): StarterBody {
  const body: StarterBody = {
    business_name: form.name.trim(),
    description: form.description.trim(),
    offer_title: form.offerTitle.trim(),
    offer_price: parseMoney(form.offerPrice) ?? "0",
    food_business: foodBusiness,
  };
  if (form.email.trim() !== "") body.contact_email = form.email.trim();
  return body;
}

const FIELD_FOR: Record<string, StarterField> = {
  business_name: "name",
  description: "description",
  contact_email: "email",
  offer_title: "offerTitle",
  offer_price: "offerPrice",
};

/** Fixed text per field and code. The server's own wording is never shown. */
export function mapStarterErrors(errors: StarterFieldError[]): StarterErrors {
  const mapped: StarterErrors = {};
  let unmapped = errors.length === 0;
  for (const error of errors) {
    const field = FIELD_FOR[error.field];
    if (!field) {
      unmapped = true;
    } else if (error.code === "invalid") {
      mapped[field] = STARTER_TEXT[field];
    } else {
      mapped[field] = STARTER_TEXT[error.code];
    }
  }
  if (unmapped) mapped.form = STARTER_TEXT.form;
  return mapped;
}

// ---- the unpublish link -------------------------------------------------------------------------

const HASH_SLUG = /^[a-z0-9][a-z0-9-]{0,79}$/;
const HASH_TOKEN = /^[A-Za-z0-9_-]{20,128}$/;

/** The secret goes after "#": a browser never sends that part to any server, so it stays out of logs. */
export function unpublishLink(
  origin: string,
  slug: string,
  token: string,
): string {
  return `${origin}/#unpublish/${slug}/${token}`;
}

export function parseUnpublishHash(
  hash: string,
): { slug: string; token: string } | null {
  const parts = hash.replace(/^#/, "").split("/");
  if (parts.length !== 3 || parts[0] !== "unpublish") return null;
  const [, slug, token] = parts;
  return HASH_SLUG.test(slug) && HASH_TOKEN.test(token)
    ? { slug, token }
    : null;
}
