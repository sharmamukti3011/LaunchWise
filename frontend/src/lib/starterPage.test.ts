import { describe, expect, it } from "vitest";
import type { Analysis } from "../api/demo";
import {
  EMPTY_STARTER,
  STARTER_TEXT,
  buildStarterBody,
  mapStarterErrors,
  prefillFrom,
  validateStarter,
} from "./starterPage";
import type { StarterForm } from "./starterPage";

function analysis(
  over: {
    id?: string | null;
    title?: string;
    price?: string;
    food?: boolean;
  } = {},
): Analysis {
  const id = over.id === undefined ? "alt" : over.id;
  return {
    food_business: over.food ?? true,
    options: [
      {
        option_id: "orig",
        title: "Everyday cakes",
        feasibility: { inputs: { price: { value: "500.00" } } },
      },
      {
        option_id: "alt",
        title: over.title ?? "Custom celebration cakes",
        feasibility: { inputs: { price: { value: over.price ?? "1200.00" } } },
      },
    ],
    ranking: { recommended_id: id },
  } as unknown as Analysis;
}

const GOOD: StarterForm = {
  name: "Aarti's Home Bakery",
  description: "Fresh cakes, made to order.",
  email: "aarti@example.com",
  offerTitle: "Custom celebration cakes",
  offerPrice: "1200",
};

describe("prefillFrom", () => {
  it("takes the offer title and price from the recommended option", () => {
    expect(prefillFrom(analysis())).toEqual({
      offerTitle: "Custom celebration cakes",
      offerPrice: "1200",
    });
  });

  it("keeps paise only when the price is not a whole rupee", () => {
    expect(prefillFrom(analysis({ price: "899.50" }))?.offerPrice).toBe(
      "899.50",
    );
    expect(prefillFrom(analysis({ price: "1200.00" }))?.offerPrice).toBe(
      "1200",
    );
  });

  it("cuts a long title to the 60 characters a page allows", () => {
    expect(
      prefillFrom(analysis({ title: "t".repeat(80) }))?.offerTitle,
    ).toHaveLength(60);
  });

  it("offers nothing when there is no recommendation", () => {
    expect(prefillFrom(analysis({ id: null }))).toBeNull();
  });

  it("offers nothing when the recommended option cannot be found", () => {
    expect(prefillFrom(analysis({ id: "ghost" }))).toBeNull();
  });
});

describe("validateStarter", () => {
  it("accepts a complete form and a form with only the required fields", () => {
    expect(validateStarter(GOOD)).toEqual({});
    expect(validateStarter({ ...GOOD, description: "", email: "" })).toEqual(
      {},
    );
  });

  it("requires a business name, an offer title and a price", () => {
    const errors = validateStarter({ ...EMPTY_STARTER });
    for (const key of ["name", "offerTitle", "offerPrice"] as const)
      expect(errors[key]).toBeDefined();
    expect(errors.description).toBeUndefined();
    expect(errors.email).toBeUndefined();
  });

  it("matches the server's limits: 60, 300, 254 and 60", () => {
    expect(
      validateStarter({ ...GOOD, name: "n".repeat(60) }).name,
    ).toBeUndefined();
    expect(
      validateStarter({ ...GOOD, name: "n".repeat(61) }).name,
    ).toBeDefined();
    expect(
      validateStarter({ ...GOOD, description: "d".repeat(300) }).description,
    ).toBeUndefined();
    expect(
      validateStarter({ ...GOOD, description: "d".repeat(301) }).description,
    ).toBeDefined();
    expect(
      validateStarter({ ...GOOD, offerTitle: "o".repeat(61) }).offerTitle,
    ).toBeDefined();
    expect(
      validateStarter({ ...GOOD, email: `${"x".repeat(250)}@example.com` })
        .email,
    ).toBeDefined();
  });

  it.each([
    "<b>x</b>",
    "see https://example.com",
    "visit example.com",
    "me@example.com",
    "[x](y)",
    "a > b",
  ])("refuses markup, links and emails in free text: %s", (bad) => {
    for (const field of ["name", "description", "offerTitle"] as const) {
      expect(validateStarter({ ...GOOD, [field]: bad })[field]).toBe(
        STARTER_TEXT.no_links_or_markup,
      );
    }
  });

  it("does not mistake ordinary prose for a web address", () => {
    expect(
      validateStarter({
        ...GOOD,
        description: "We open at nine. In the evening we close.",
      }),
    ).toEqual({});
    expect(
      validateStarter({ ...GOOD, offerTitle: "Cake (1 kg), Rs.500" }),
    ).toEqual({});
  });

  it("refuses control characters and line breaks", () => {
    expect(validateStarter({ ...GOOD, name: "a\nb" }).name).toBeDefined();
    expect(
      validateStarter({ ...GOOD, description: "a b" }).description,
    ).toBeDefined();
  });

  it.each(["nope", "a@b", "a@@b.com", "a b@example.com", "<a@b.com>"])(
    "refuses the email %s",
    (bad) => {
      expect(validateStarter({ ...GOOD, email: bad }).email).toBe(
        STARTER_TEXT.email,
      );
    },
  );

  it.each(["0", "-5", "100001", "1.234", "abc", ""])(
    "refuses the price %j",
    (bad) => {
      expect(validateStarter({ ...GOOD, offerPrice: bad }).offerPrice).toBe(
        STARTER_TEXT.offerPrice,
      );
    },
  );

  it.each(["1", "899.50", "₹1,200", "100000"])(
    "accepts the price %j",
    (good) => {
      expect(
        validateStarter({ ...GOOD, offerPrice: good }).offerPrice,
      ).toBeUndefined();
    },
  );
});

describe("buildStarterBody", () => {
  it("sends the fields as the server expects, with the price as an exact string", () => {
    expect(buildStarterBody(GOOD, true)).toEqual({
      business_name: "Aarti's Home Bakery",
      description: "Fresh cakes, made to order.",
      contact_email: "aarti@example.com",
      offer_title: "Custom celebration cakes",
      offer_price: "1200",
      food_business: true,
    });
  });

  it("trims text, normalises the price, and leaves a blank email out", () => {
    const body = buildStarterBody(
      { ...GOOD, name: "  Aarti  ", email: "  ", offerPrice: "₹1,200" },
      false,
    );
    expect(body.business_name).toBe("Aarti");
    expect(body.offer_price).toBe("1200");
    expect("contact_email" in body).toBe(false);
    expect(body.food_business).toBe(false);
  });
});

describe("mapStarterErrors", () => {
  it("maps each server field to the form field with fixed text for its code", () => {
    const errors = mapStarterErrors([
      { field: "business_name", code: "not_allowed" },
      { field: "description", code: "no_links_or_markup" },
      { field: "offer_price", code: "invalid" },
      { field: "contact_email", code: "invalid" },
      { field: "offer_title", code: "invalid" },
    ]);
    expect(errors.name).toBe(STARTER_TEXT.not_allowed);
    expect(errors.description).toBe(STARTER_TEXT.no_links_or_markup);
    expect(errors.offerPrice).toBe(STARTER_TEXT.offerPrice);
    expect(errors.email).toBe(STARTER_TEXT.email);
    expect(errors.offerTitle).toBe(STARTER_TEXT.offerTitle);
  });

  it("falls back to a general message when no field can be named", () => {
    expect(mapStarterErrors([])).toEqual({ form: STARTER_TEXT.form });
    expect(mapStarterErrors([{ field: "request", code: "invalid" }])).toEqual({
      form: STARTER_TEXT.form,
    });
  });

  it("never reveals why text was refused, and never uses a dollar sign", () => {
    const all = JSON.stringify(STARTER_TEXT);
    expect(all).not.toContain("$");
    expect(STARTER_TEXT.not_allowed).not.toMatch(/blocklist|word|term|porn/i);
  });
});

import { parseUnpublishHash, unpublishLink } from "./starterPage";

describe("the unpublish link", () => {
  const token = "Abc_def-123".repeat(4);

  it("keeps the secret in the part after #, which browsers never send to a server", () => {
    const link = unpublishLink("https://launchwise.pro", "aarti-a1b2c3", token);
    expect(link).toBe(
      `https://launchwise.pro/#unpublish/aarti-a1b2c3/${token}`,
    );
    expect(new URL(link).search).toBe("");
    expect(new URL(link).pathname).toBe("/");
  });

  it("round-trips through the parser", () => {
    const hash = new URL(
      unpublishLink("https://x.example", "aarti-a1b2c3", token),
    ).hash;
    expect(parseUnpublishHash(hash)).toEqual({ slug: "aarti-a1b2c3", token });
  });

  it.each([
    "",
    "#",
    "#unpublish",
    "#unpublish/",
    "#unpublish/only-slug",
    "#other/a/b",
    "#unpublish/UPPER/" + "t".repeat(40),
    "#unpublish/a-1/short",
    "#unpublish/a-1/" + "t".repeat(200),
    "#unpublish/a-1/" + "t".repeat(39) + "!",
    "#unpublish/a/b/c",
  ])("refuses a hash that is not exactly an unpublish link: %j", (hash) => {
    expect(parseUnpublishHash(hash)).toBeNull();
  });
});
