"""Render a StorefrontConfig into a page. The only template: text in, escaped HTML out.

Every piece of user text goes through `html.escape`. The page has no script, image, form or inline
style (the site's security policy forbids inline styles), and its only links are our own stylesheet
and the footer link home. The contact address is plain text, never a link. Every page says
noindex and carries an "example page" banner, because it is public on a domain that is not the
owner's.
"""

from html import escape

from app.schemas.storefront import Product, StorefrontConfig
from app.services.scoring import rupees

STYLESHEET_PATH = "/api/storefront/style.css"
# The site's own icons, served by Caddy from the built frontend. Local paths only.
ICON_LINKS = (
    ("icon", "/favicon.ico"),
    ("icon", "/favicon-32.png"),
    ("apple-touch-icon", "/apple-touch-icon.png"),
)
_ICON_TAGS = "".join(f'<link rel="{rel}" href="{href}">\n' for rel, href in ICON_LINKS)
BANNER_TEXT = "Example page made with LaunchWise"
FOOTER_TEXT = "Made with LaunchWise"
FSSAI_NOTE = "Selling food from home requires FSSAI registration before you start."

_DAYS = {
    "mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat",
    "sun": "Sun",
}  # fmt: skip


def _text(value: str) -> str:
    return escape(value, quote=True)


def _product(product: Product) -> str:
    description = (
        f'<p class="description">{_text(product.description)}</p>' if product.description else ""
    )
    return (
        '<section class="offer">'
        f"<h2>{_text(product.name)}</h2>"
        f'<p class="price">{_text(rupees(product.price))}</p>'
        f"{description}"
        "</section>"
    )


def _optional_parts(config: StorefrontConfig) -> str:
    parts: list[str] = []
    if config.availability is not None:
        days = ", ".join(_DAYS[day] for day in config.availability.days)
        parts.append(f'<p class="muted">Available: {_text(days)}</p>')
        if config.availability.note:
            parts.append(f'<p class="muted">{_text(config.availability.note)}</p>')
    if config.capacity_note:
        parts.append(f'<p class="muted">{_text(config.capacity_note)}</p>')
    return "".join(parts)


def render_page(config: StorefrontConfig) -> str:
    tagline = f'<p class="tagline">{_text(config.tagline)}</p>' if config.tagline else ""
    description = (
        f'<p class="description">{_text(config.description)}</p>' if config.description else ""
    )
    products = "".join(_product(p) for p in config.products)
    contact = (
        f'<p class="contact">Contact: {_text(config.contact_email)}</p>'
        if config.contact_email
        else ""
    )
    notice = f'<p class="notice">{_text(FSSAI_NOTE)}</p>' if config.food_notice else ""
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<meta name="color-scheme" content="light dark">\n'
        '<meta name="robots" content="noindex, nofollow">\n'
        f"<title>{_text(config.brand)} · Example page</title>\n"
        f"{_ICON_TAGS}"
        f'<link rel="stylesheet" href="{STYLESHEET_PATH}">\n'
        "</head>\n"
        "<body>\n"
        '<div class="page">\n'
        f'<div class="banner" role="note">{BANNER_TEXT}</div>\n'
        "<main>\n"
        f"<h1>{_text(config.brand)}</h1>\n"
        f"{tagline}{description}\n"
        f"{products}\n"
        f"{_optional_parts(config)}"
        f"{contact}"
        f"{notice}\n"
        "</main>\n"
        f'<footer><a href="/">{FOOTER_TEXT}</a></footer>\n'
        "</div>\n"
        "</body>\n"
        "</html>\n"
    )


UNAVAILABLE_TEXT = (
    "This example page is not available. Example pages made with LaunchWise last 7 days."
)


def render_unavailable() -> str:
    """The one answer for every address that is not a live page: unknown, expired or taken down."""
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<meta name="color-scheme" content="light dark">\n'
        '<meta name="robots" content="noindex, nofollow">\n'
        "<title>Page not available · LaunchWise</title>\n"
        f"{_ICON_TAGS}"
        f'<link rel="stylesheet" href="{STYLESHEET_PATH}">\n'
        "</head>\n"
        "<body>\n"
        '<div class="page">\n'
        "<main>\n"
        "<h1>Page not available</h1>\n"
        f"<p>{_text(UNAVAILABLE_TEXT)}</p>\n"
        "</main>\n"
        f'<footer><a href="/">{FOOTER_TEXT}</a></footer>\n'
        "</div>\n"
        "</body>\n"
        "</html>\n"
    )
