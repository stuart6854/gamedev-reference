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

`engine`, `version`, and `package` each take one value or a list. `hooks/version_pills.py` renders them as pills directly under the page title, and `docs/stylesheets/extra.css` styles them in the teal and amber theme for both colour schemes. A page with none of the keys is left unchanged.

`package` names an official package the page actually uses, with the version in the label:

```yaml
package: Cinemachine 3.x
```

For now, engine pages target only the current generation: Unity 6 and later. Unreal 5.x and Godot 4.x will use the same frontmatter when those sections exist. Do not add a page aimed at an older editor.

## Roadmap

[docs/roadmap.md](docs/roadmap.md) lists topics that do not have a page yet. When you add a page, delete that topic from the roadmap in the same change. Do not tick it, and do not strike it through. A finished topic is not a roadmap entry.

## Unity pages

A Unity mechanic or camera page is a plain C# implementation. Where an official package makes the setup shorter, the same page also has that variant, as a content tab or a labelled section. The package pill says which one. Cameras use Cinemachine 3 (`Unity.Cinemachine`: `CinemachineCamera`, `CinemachineOrbitalFollow`, `CinemachineRotationComposer`, `CinemachineDeoccluder`). That API is not Cinemachine 2.
