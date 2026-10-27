"""Render engine, version, and package frontmatter as pills under the page title."""

from html import escape
import re

_H1_END = re.compile(r"</h1>", re.IGNORECASE)


def _labels(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _pills(page):
    meta = page.meta or {}
    engines = _labels(meta.get("engine"))
    versions = _labels(meta.get("version"))
    packages = _labels(meta.get("package"))
    if not engines and not versions and not packages:
        return ""

    parts = ['<p class="version-pills">']
    for label in engines:
        parts.append(
            f'<span class="version-pill version-pill--engine">{escape(label)}</span>'
        )
    for label in versions:
        parts.append(
            f'<span class="version-pill version-pill--version">{escape(label)}</span>'
        )
    for label in packages:
        parts.append(
            f'<span class="version-pill version-pill--package">{escape(label)}</span>'
        )
    parts.append("</p>")
    return "".join(parts)


def on_page_content(html, page, config, files):
    pills = _pills(page)
    if not pills:
        return html

    # The title is the first h1 in the page body. Place the pills immediately
    # after it so they sit under the heading in both the static build and
    # instant navigation.
    match = _H1_END.search(html)
    if match is None:
        return pills + html
    index = match.end()
    return html[:index] + pills + html[index:]
