"""Build docs/uses.md from the `uses` frontmatter of every page.

`uses` names must come from USES below, so the same use reads the same on every page.
Run with --check in CI: it fails if a name is unknown or docs/uses.md is out of date.
"""

from pathlib import Path
import sys
import tomllib

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUTPUT = DOCS / "uses.md"

# Name: one line shown under its heading on the browse page.
USES = {
    "Top-down survival": "Scavenging, threats in the dark, and buildings to hide in, seen from above.",
    "Hordes and crowds": "Many agents at once: zombies, swarms, armies, and pedestrians.",
    "Stealth": "Being seen, being heard, and staying out of sight.",
    "Shooters": "Guns, projectiles, aiming, and the enemies that shoot back.",
    "Melee action": "Swings, combos, hit feedback, and close-range fights.",
    "Strategy and tactics": "RTS, 4X, and tactics games: selecting, commanding, and seeing the map.",
    "RPGs": "Stats, items, loot, and characters that grow.",
    "Roguelikes": "Runs, grids, randomness, and remembered maps.",
    "Platformers": "Jumps, slopes, and precise movement.",
    "Life and colony sims": "Needs, schedules, and building a place to live.",
    "Base building": "Placing, upgrading, and defending structures.",
    "Open worlds": "Large maps, streaming, and a world that runs while you are away.",
    "Wildlife": "Animals, flocks, and herds.",
    "Companions and NPCs": "Allies and characters with needs and opinions.",
    "Multiplayer": "Several players, one world.",
}


def excluded_prefixes():
    project = tomllib.loads((ROOT / "zensical.toml").read_text())["project"]
    return [line.strip().rstrip("/") + "/" for line in project.get("exclude_docs", "").splitlines() if line.strip()]


def read_page(path):
    text = path.read_text(encoding="utf-8")
    meta = {}
    body = text
    if text.startswith("---\n"):
        end = text.index("\n---", 4)
        meta = yaml.safe_load(text[4:end]) or {}
        body = text[end + 4:]
    title = next((line[2:].strip() for line in body.splitlines() if line.startswith("# ")), path.stem)
    return meta, title


def collect():
    excluded = excluded_prefixes()
    by_use = {name: [] for name in USES}
    problems = []

    for path in sorted(DOCS.rglob("*.md")):
        relative = path.relative_to(DOCS).as_posix()
        if relative == OUTPUT.name or any(relative.startswith(prefix) for prefix in excluded):
            continue

        meta, title = read_page(path)
        seen = set()
        for entry in meta.get("uses") or []:
            if not isinstance(entry, dict) or "name" not in entry or "text" not in entry:
                problems.append(f"docs/{relative}: each use needs a name and a text")
                continue
            name = entry["name"]
            if name not in USES:
                problems.append(f"docs/{relative}: unknown use '{name}'. Pick one from USES in scripts/gen_uses.py")
                continue
            if name in seen:
                problems.append(f"docs/{relative}: '{name}' is listed twice")
                continue
            seen.add(name)
            by_use[name].append((title, relative, entry["text"]))

    return by_use, problems


def render(by_use):
    lines = [
        "# Browse by use",
        "",
        "Pages grouped by what they are useful for. Each page lists its uses under its title; "
        "this page is generated from those lists by `scripts/gen_uses.py`.",
        "",
    ]
    used = [name for name in USES if by_use[name]]
    lines += [f"- [{name}](#{slug(name)}) ({len(by_use[name])})" for name in used]

    for name in used:
        lines += ["", f"## {name}", "", USES[name], ""]
        for title, relative, text in sorted(by_use[name], key=lambda item: item[0].lower()):
            lines.append(f"- [{title}]({relative}) — {text}")

    return "\n".join(lines) + "\n"


def slug(name):
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-").replace("--", "-")


def main():
    by_use, problems = collect()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(1)

    content = render(by_use)
    if "--check" in sys.argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != content:
            print("docs/uses.md is out of date. Run: python scripts/gen_uses.py", file=sys.stderr)
            sys.exit(1)
        print("Uses page OK.")
        return

    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
