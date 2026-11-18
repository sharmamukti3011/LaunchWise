import type { AnalyzeBody, BodyOption, ServerFieldError } from "../api/analyze";
import { hasControlOrLineBreak } from "./text";

// ---- the form ---------------------------------------------------------------------------------

export interface OptionForm {
  title: string;
  price: string;
  cost: string;
  startup: string;
  minutes: string;
}

export interface AltForm extends OptionForm {
  evidenceId: string;
}

export interface OwnIdeaForm {
  budget: string;
  unitsPerDay: string;
  daysPerWeek: string;
  hoursPerWeek: string;
  skills: string;
  equipment: string;
  location: string;
  category: string;
  original: OptionForm;
  alt: AltForm;
}

const BLANK_OPTION: OptionForm = { title: "", price: "", cost: "", startup: "", minutes: "" };

export const EMPTY_FORM: OwnIdeaForm = {
  budget: "",
  unitsPerDay: "",
  daysPerWeek: "",
  hoursPerWeek: "",
  skills: "",
  equipment: "",
  location: "",
  category: "",
  original: BLANK_OPTION,
  alt: { ...BLANK_OPTION, evidenceId: "" },
};

export type FieldKey =
  | "budget"
  | "unitsPerDay"
  | "daysPerWeek"
  | "hoursPerWeek"
  | "skills"
  | "equipment"
  | "location"
  | "category"
  | `original.${keyof OptionForm}`
  | `alt.${keyof AltForm}`;

export type FieldErrors = Partial<Record<FieldKey, string>>;
export type FormErrors = FieldErrors & { form?: string };

/** Set one field by its key ("budget" or "alt.price"), without touching the rest. */
export function setField(form: OwnIdeaForm, key: FieldKey, value: string): OwnIdeaForm {
  if (key.startsWith("original.")) {
    return { ...form, original: { ...form.original, [key.slice(9)]: value } };
  }
  if (key.startsWith("alt.")) return { ...form, alt: { ...form.alt, [key.slice(4)]: value } };
  return { ...form, [key]: value };
}

// ---- limits: the same as the server's ---------------------------------------------------------

const MAX_MONEY = 10_000_000; // ₹1 crore
const MAX_UNITS_PER_DAY = 10_000;
const MAX_HOURS = 168;
const MAX_MINUTES = 1_440;
const MAX_LIST_ITEMS = 20;
const MAX_ITEM = 60;
const MAX_TITLE = 80;
const MAX_PLACE = 80;
const MAX_CATEGORY = 60;

const MONEY = /^(?:\d{1,3}(?:,\d{2,3})*|\d+)(?:\.\d{1,2})?$/;

/** "₹10,000", "10,000" and "10000" all become "10000". Anything else is null. */
export function parseMoney(input: string): string | null {
  const text = input.trim().replace(/^₹\s*/, "");
  if (!MONEY.test(text)) return null;
  const plain = text.replace(/,/g, "");
  return Number(plain) <= MAX_MONEY ? plain : null;
}

function parseWhole(input: string, max: number): number | null {
  const text = input.trim();
  if (!/^\d+$/.test(text)) return null;
  const n = Number(text);
  return n <= max ? n : null;
}

function validText(input: string, max: number): boolean {
  const text = input.trim();
  return text.length >= 1 && text.length <= max && !hasControlOrLineBreak(text);
}

function splitList(input: string): string[] {
  return input
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item !== "");
}

function validList(input: string): boolean {
  const items = splitList(input);
  return items.length <= MAX_LIST_ITEMS && items.every((i) => i.length <= MAX_ITEM && !hasControlOrLineBreak(i));
}

// ---- fixed messages ---------------------------------------------------------------------------

const MONEY_TEXT = "Enter an amount in rupees, up to ₹1 crore, for example 500.";
const TITLE_TEXT = "Enter a name, up to 80 characters.";
const MINUTES_TEXT = "Leave this blank, or enter whole minutes from 0 to 1,440.";
const LIST_TEXT = "List up to 20 items separated by commas, each up to 60 characters.";

export const FIELD_TEXT: Record<FieldKey, string> = {
  budget: "Enter your budget in rupees, for example 10000.",
  unitsPerDay: "Enter a whole number from 0 to 10,000.",
  daysPerWeek: "Enter a whole number from 0 to 7.",
  hoursPerWeek: "Leave this blank, or enter a whole number from 0 to 168.",
  skills: LIST_TEXT,
  equipment: LIST_TEXT,
  location: "Enter a place, up to 80 characters.",
  category: "Enter the kind of business, up to 60 characters.",
  "original.title": TITLE_TEXT,
  "original.price": MONEY_TEXT,
  "original.cost": MONEY_TEXT,
  "original.startup": MONEY_TEXT,
  "original.minutes": MINUTES_TEXT,
  "alt.title": TITLE_TEXT,
  "alt.price": MONEY_TEXT,
  "alt.cost": MONEY_TEXT,
  "alt.startup": MONEY_TEXT,
  "alt.minutes": MINUTES_TEXT,
  "alt.evidenceId": "Choose the market evidence this alternative is based on.",
};

export const GENERAL_ERROR = "Please check the highlighted fields and try again.";

// ---- validation -------------------------------------------------------------------------------

function optionErrors(prefix: "original" | "alt", option: OptionForm): FieldErrors {
  const errors: FieldErrors = {};
  const bad = (field: keyof OptionForm) => {
    errors[`${prefix}.${field}` as FieldKey] = FIELD_TEXT[`${prefix}.${field}` as FieldKey];
  };
  if (!validText(option.title, MAX_TITLE)) bad("title");
  for (const field of ["price", "cost", "startup"] as const) {
    if (parseMoney(option[field]) === null) bad(field);
  }
  if (option.minutes.trim() !== "" && parseWhole(option.minutes, MAX_MINUTES) === null) bad("minutes");
  return errors;
}

function altIsBlank(alt: AltForm): boolean {
  return Object.values(alt).every((value) => value.trim() === "");
}

export function validateOwnIdea(form: OwnIdeaForm): FieldErrors {
  const errors: FieldErrors = {};
  if (parseMoney(form.budget) === null) errors.budget = FIELD_TEXT.budget;
  if (parseWhole(form.unitsPerDay, MAX_UNITS_PER_DAY) === null) errors.unitsPerDay = FIELD_TEXT.unitsPerDay;
  if (parseWhole(form.daysPerWeek, 7) === null) errors.daysPerWeek = FIELD_TEXT.daysPerWeek;
  if (form.hoursPerWeek.trim() !== "" && parseWhole(form.hoursPerWeek, MAX_HOURS) === null) {
    errors.hoursPerWeek = FIELD_TEXT.hoursPerWeek;
  }
  if (!validList(form.skills)) errors.skills = FIELD_TEXT.skills;
  if (!validList(form.equipment)) errors.equipment = FIELD_TEXT.equipment;
  if (!validText(form.location, MAX_PLACE)) errors.location = FIELD_TEXT.location;
  if (!validText(form.category, MAX_CATEGORY)) errors.category = FIELD_TEXT.category;
  Object.assign(errors, optionErrors("original", form.original));
  // An alternative is optional, but once started it must be complete.
  if (!altIsBlank(form.alt)) Object.assign(errors, optionErrors("alt", form.alt));
  return errors;
}

// ---- the request ------------------------------------------------------------------------------

function bodyOption(id: string, isOriginal: boolean, option: OptionForm): BodyOption {
  const body: BodyOption = {
    id,
    title: option.title.trim(),
    is_original: isOriginal,
    price: parseMoney(option.price) ?? "0",
    variable_cost_per_unit: parseMoney(option.cost) ?? "0",
    fixed_startup_costs: parseMoney(option.startup) ?? "0",
  };
  // Left blank, the figure is not sent at all: the server then assumes it and says so.
  if (option.minutes.trim() !== "") {
    body.minutes_per_unit = { value: Number(option.minutes.trim()), source: "user_provided" };
  }
  return body;
}

/** Build the /analyze request from a form that passed `validateOwnIdea`. */
export function buildAnalyzeBody(form: OwnIdeaForm): AnalyzeBody {
  const body: AnalyzeBody = {
    profile: {
      budget: parseMoney(form.budget) ?? "0",
      units_per_day: Number(form.unitsPerDay.trim()),
      days_per_week: Number(form.daysPerWeek.trim()),
      skills: splitList(form.skills),
      equipment: splitList(form.equipment),
      location: form.location.trim(),
    },
    category: form.category.trim(),
    options: [bodyOption("original", true, form.original)],
  };
  if (form.hoursPerWeek.trim() !== "") {
    body.profile.hours_per_week = { value: Number(form.hoursPerWeek.trim()), source: "user_provided" };
  }
  if (!altIsBlank(form.alt)) {
    const alternative = bodyOption("alternative", false, form.alt);
    if (form.alt.evidenceId.trim() !== "") alternative.opportunity_id = form.alt.evidenceId.trim();
    body.options.push(alternative);
  }
  return body;
}

// ---- server errors ----------------------------------------------------------------------------

const OPTION_FIELDS: Record<string, keyof OptionForm | "evidenceId"> = {
  title: "title",
  price: "price",
  variable_cost_per_unit: "cost",
  fixed_startup_costs: "startup",
  minutes_per_unit: "minutes",
  opportunity_id: "evidenceId",
};

/** Which form field a server error path ("options.1.price") belongs to, if any. */
export function serverFieldToKey(field: string): FieldKey | null {
  const direct: Record<string, FieldKey> = {
    "profile.budget": "budget",
    "profile.units_per_day": "unitsPerDay",
    "profile.days_per_week": "daysPerWeek",
    "profile.location": "location",
    category: "category",
  };
  if (field in direct) return direct[field];
  if (field.startsWith("profile.hours_per_week")) return "hoursPerWeek";
  if (field.startsWith("profile.skills")) return "skills";
  if (field.startsWith("profile.equipment")) return "equipment";
  const match = /^options\.(\d+)\.([a-z_]+)/.exec(field);
  if (!match) return null;
  const target = OPTION_FIELDS[match[2]];
  if (!target) return null;
  if (match[1] === "0" && target !== "evidenceId") return `original.${target}` as FieldKey;
  if (match[1] === "1") return `alt.${target}` as FieldKey;
  return null;
}

/** Fixed text per field. The server's own wording is never shown. */
export function mapServerErrors(errors: ServerFieldError[]): FormErrors {
  const mapped: FormErrors = {};
  let unmapped = errors.length === 0;
  for (const error of errors) {
    const key = serverFieldToKey(error.field);
    if (key) mapped[key] = FIELD_TEXT[key];
    else unmapped = true;
  }
  if (unmapped) mapped.form = GENERAL_ERROR;
  return mapped;
}
