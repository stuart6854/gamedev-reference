# Game development reference

Personal reference site for game-development notes: maths, graphics, physics, gameplay, Unity, engine architecture, and optimisation. Built with [MkDocs](https://www.mkdocs.org/) and [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).

The published URL, once GitHub Pages is pointed at this workflow, is <https://stuart6854.github.io/gamedev-reference/>.

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

Pushes to `main` build the site and deploy it with GitHub Actions. In the repository, set **Settings → Pages → Build and deployment → Source** to **GitHub Actions** before the first deploy can succeed.
