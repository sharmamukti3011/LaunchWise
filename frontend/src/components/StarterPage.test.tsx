import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Analysis } from "../api/demo";
import type { PreviewResult } from "../api/storefront";
import { EMPTY_STARTER } from "../lib/starterPage";
import type { StarterErrors, StarterForm } from "../lib/starterPage";
import {
  PreviewView,
  StarterFormView,
  StarterPageSection,
} from "./StarterPage";

const noop = () => undefined;

function analysis(recommended: string | null): Analysis {
  return {
    food_business: true,
    options: [
      {
        option_id: "alt",
        title: "Custom cakes",
        feasibility: { inputs: { price: { value: "1200.00" } } },
      },
    ],
    ranking: { recommended_id: recommended },
  } as unknown as Analysis;
}

describe("StarterPageSection", () => {
  it("offers 'Create a starter page for this idea' when there is a recommendation", () => {
    const html = renderToStaticMarkup(
      <StarterPageSection analysis={analysis("alt")} />,
    );
    expect(html).toContain("Create a starter page for this idea");
    expect(html).toMatch(/<button[^>]*type="button"/);
  });

  it("shows nothing when nothing is recommended", () => {
    expect(
      renderToStaticMarkup(<StarterPageSection analysis={analysis(null)} />),
    ).toBe("");
  });
});

function form(
  over: Partial<{
    values: StarterForm;
    errors: StarterErrors;
    loading: boolean;
  }> = {},
): string {
  return renderToStaticMarkup(
    <StarterFormView
      values={over.values ?? EMPTY_STARTER}
      errors={over.errors ?? {}}
      loading={over.loading ?? false}
      onChange={noop}
      onSubmit={noop}
      onCancel={noop}
    />,
  );
}

describe("StarterFormView", () => {
  it("has labelled fields with the server's limits", () => {
    const html = form();
    for (const id of [
      "starter-name",
      "starter-description",
      "starter-email",
      "starter-offerTitle",
      "starter-offerPrice",
    ]) {
      expect(html).toMatch(new RegExp(`<label[^>]*for="${id}"`));
      expect(html).toContain(`id="${id}"`);
    }
    expect(html).toMatch(
      /id="starter-name"[^>]*maxLength="60"|maxLength="60"[^>]*id="starter-name"/,
    );
    expect(html).toMatch(/<textarea[^>]*maxLength="300"/);
    expect(html).toMatch(
      /id="starter-email"[^>]*maxLength="254"|maxLength="254"[^>]*id="starter-email"/,
    );
  });

  it("marks the description and the email optional, and says the email is shown publicly as text", () => {
    const html = form();
    expect(html).toMatch(/Short description[^<]*\(optional\)/);
    expect(html).toMatch(/Contact email[^<]*\(optional\)/);
    expect(html).toMatch(
      /shown (on|as)[^<]*(public )?page[^<]*plain text|plain text[^<]*public page/i,
    );
  });

  it("says nothing is public until the owner has seen a preview", () => {
    expect(form()).toMatch(/Nothing is public/i);
  });

  it("shows the prefilled offer title and price", () => {
    const html = form({
      values: {
        ...EMPTY_STARTER,
        offerTitle: "Custom cakes",
        offerPrice: "1200",
      },
    });
    expect(html).toContain('value="Custom cakes"');
    expect(html).toContain('value="1200"');
    expect(html).toContain("₹");
  });

  it("shows a fixed message under a field and links it for screen readers", () => {
    const html = form({
      errors: { name: "Enter your business name, up to 60 characters." },
    });
    expect(html).toContain("Enter your business name");
    expect(html).toMatch(
      /id="starter-name"[^>]*aria-invalid="true"|aria-invalid="true"[^>]*id="starter-name"/,
    );
    expect(html).toContain('aria-describedby="starter-name-error"');
  });

  it("shows a general error as an alert", () => {
    expect(form({ errors: { form: "Something went wrong." } })).toMatch(
      /role="alert"[^>]*>[^<]*Something went wrong/,
    );
  });

  it("has a Preview button that is disabled and says so while working", () => {
    expect(form()).toMatch(/<button[^>]*type="submit"[^>]*>Preview the page</);
    const html = form({ loading: true });
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*\sdisabled(=|\s|>)/);
    expect(html).toContain("Building the preview…");
  });

  it("shows typed text escaped", () => {
    const html = form({
      values: { ...EMPTY_STARTER, name: "<img src=x onerror=alert(1)>" },
    });
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });
});

const PREVIEW: PreviewResult = {
  draft_id: "d1",
  slug: "aarti-s-a1b2c3",
  public_path: "/s/aarti-s-a1b2c3",
  config_hash: "f".repeat(64),
  expires_in_minutes: 30,
  preview_html:
    '<!doctype html><html><body><h1>Aarti&#x27;s</h1><script>alert("x")</script></body></html>',
};

describe("PreviewView", () => {
  const html = renderToStaticMarkup(
    <PreviewView
      preview={PREVIEW}
      onEdit={noop}
      onPublish={noop}
      publishing={false}
      error={null}
    />,
  );

  it("shows the page in a fully sandboxed frame, so nothing in it can run", () => {
    const frame = /<iframe[^>]*>/.exec(html)?.[0] ?? "";
    expect(frame).toMatch(/sandbox=""/);
    expect(frame).toMatch(/title="[^"]+"/);
    expect(frame).toContain("srcDoc=");
  });

  it("passes the page as an attribute value, escaped, never as markup in the app", () => {
    expect(html).not.toContain("<script>alert");
    expect(html).toContain("&lt;script&gt;");
  });

  it("says plainly that this is a preview and nothing is public yet", () => {
    expect(html).toMatch(/Preview/);
    expect(html).toMatch(/Nothing is public/i);
  });

  it("lets the owner go back and edit", () => {
    expect(html).toMatch(/<button[^>]*type="button"[^>]*>Edit details</);
  });
});

import { PublishedView, UnpublishView } from "./StarterPage";

describe("PreviewView publishing", () => {
  const view = (over: { publishing?: boolean; error?: string | null } = {}) =>
    renderToStaticMarkup(
      <PreviewView
        preview={PREVIEW}
        onEdit={noop}
        onPublish={noop}
        publishing={over.publishing ?? false}
        error={over.error ?? null}
      />,
    );

  it("has an explicit Approve and publish button", () => {
    expect(view()).toMatch(
      /<button[^>]*type="button"[^>]*>Approve and publish</,
    );
  });

  it("says what publishing does, in plain words", () => {
    const html = view();
    expect(html).toMatch(/public/i);
    expect(html).toMatch(/7 days/);
    expect(html).toMatch(/search engines/i);
    expect(html).toMatch(/example page/i);
  });

  it("disables the button and says so while publishing", () => {
    const html = view({ publishing: true });
    expect(html).toMatch(/<button[^>]*\sdisabled(=|\s|>)[^>]*>Publishing…</);
  });

  it("shows a fixed error as an alert", () => {
    expect(view({ error: "Something went wrong." })).toMatch(
      /role="alert"[^>]*>[^<]*Something went wrong/,
    );
  });
});

describe("PublishedView", () => {
  const token = "T".repeat(43);
  const html = renderToStaticMarkup(
    <PublishedView
      published={{
        slug: "aarti-s-a1b2c3",
        public_path: "/s/aarti-s-a1b2c3",
        unpublish_token: token,
        expires_in_days: 7,
      }}
      origin="https://launchwise.pro"
    />,
  );

  it("links to the live page, opening safely in a new tab", () => {
    expect(html).toMatch(
      /<a[^>]*href="\/s\/aarti-s-a1b2c3"[^>]*rel="noopener noreferrer"/,
    );
    expect(html).toContain("https://launchwise.pro/s/aarti-s-a1b2c3");
  });

  it("shows the unpublish link once and says it cannot be shown again", () => {
    expect(html).toContain(
      `https://launchwise.pro/#unpublish/aarti-s-a1b2c3/${token}`,
    );
    expect(html).toMatch(/only once/i);
    expect(html).toMatch(/cannot (be shown|show)/i);
  });

  it("says when the page goes away by itself", () => {
    expect(html).toMatch(/7 days/);
  });
});

describe("UnpublishView", () => {
  const view = (state: "ready" | "working" | "done" | "failed", message = "") =>
    renderToStaticMarkup(
      <UnpublishView state={state} message={message} onConfirm={noop} />,
    );

  it("asks for a click before anything is taken down", () => {
    expect(view("ready")).toMatch(
      /<button[^>]*type="button"[^>]*>Unpublish this page</,
    );
  });

  it("disables the button while working", () => {
    expect(view("working")).toMatch(/<button[^>]*\sdisabled(=|\s|>)/);
  });

  it("confirms when done, with a link home", () => {
    const html = view("done");
    expect(html).toMatch(/taken down|unpublished/i);
    expect(html).toMatch(/<a[^>]*href="\/"/);
  });

  it("shows a fixed failure as an alert", () => {
    expect(view("failed", "That unpublish link is not valid.")).toMatch(
      /role="alert"[^>]*>[^<]*not valid/,
    );
  });
});
