# Game development reference

<https://stuart6854.github.io/gamedev-reference/>

Personal reference site for game-development notes: maths, graphics, physics, gameplay, Unity, engine architecture, and optimisation. Built with [MkDocs](https://www.mkdocs.org/) and [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).

## Preview locally

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdocs serve
```

Open <http://127.0.0.1:8000>. `mkdocs build --strict` writes the static site to `site/` and fails if the build warns.

## Publishing

Pushes to `main` build the site and deploy it with GitHub Actions. Pages is already set to **GitHub Actions**, and the live site is <https://stuart6854.github.io/gamedev-reference/>.

## Version pills

An engine page states which engine and which versions it was written for. Put that in the page frontmatter:

```yaml
---
engine: Unity
version: 6+
---
```

`engine` and `version` each take one value or a list. `hooks/version_pills.py` renders them as pills directly under the page title, and `docs/stylesheets/extra.css` styles them in the teal and amber theme for both colour schemes. A page with neither key is left unchanged.

For now, engine pages target only the current generation: Unity 6 and later. Unreal 5.x and Godot 4.x will use the same frontmatter when those sections exist. Do not add a page aimed at an older editor.
