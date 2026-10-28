"""Fail if a page in docs/ is missing from the nav, or the nav names a missing page.

Zensical's strict mode checks links and anchors but not the nav, so CI runs this
before the build. Folders listed in exclude_docs are skipped.
"""

from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def nav_pages(items):
    for item in items:
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            for value in item.values():
                yield from nav_pages([value] if isinstance(value, str) else value)


def main():
    project = tomllib.loads((ROOT / "zensical.toml").read_text())["project"]
    excluded = [line.strip().rstrip("/") + "/" for line in project.get("exclude_docs", "").splitlines() if line.strip()]

    in_nav = [page for page in nav_pages(project["nav"]) if not page.startswith(("http://", "https://"))]
    on_disk = {
        path.relative_to(DOCS).as_posix()
        for path in DOCS.rglob("*.md")
        if not any(path.relative_to(DOCS).as_posix().startswith(prefix) for prefix in excluded)
    }

    problems = [f"not in nav: docs/{page}" for page in sorted(on_disk - set(in_nav))]
    problems += [f"in nav but missing: docs/{page}" for page in sorted(set(in_nav) - on_disk)]
    problems += [f"in nav twice: docs/{page}" for page in sorted({p for p in in_nav if in_nav.count(p) > 1})]

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(1)
    print(f"Nav OK: {len(in_nav)} pages.")


if __name__ == "__main__":
    main()
