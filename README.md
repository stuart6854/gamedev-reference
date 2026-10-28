# Game development reference

<https://stuart6854.github.io/gamedev-reference/>

Personal reference site for game-development notes: maths, graphics, physics, gameplay, Unity, engine architecture, and optimisation. Built with [Zensical](https://zensical.org/). The configuration is `zensical.toml`.

## Preview locally

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
zensical serve
```

Open <http://localhost:8000>. `zensical build --clean --strict` writes the static site to `site/` and fails on a broken link or anchor. Zensical does not warn about a page missing from the nav, so add every new page to `nav` in `zensical.toml`.

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

`engine`, `version`, and `package` each take one value or a list. `overrides/partials/content.html` renders them as pills directly under the page title, and `docs/stylesheets/extra.css` styles them in the teal and amber theme for both colour schemes. A page with none of the keys is left unchanged.

`package` names an official package the page actually uses, with the version in the label:

```yaml
package: Cinemachine 3.x
```

For now, engine pages target only the current generation: Unity 6 and later. Unreal 5.x and Godot 4.x will use the same frontmatter when those sections exist. Do not add a page aimed at an older editor.

## Hidden sections

A top-level section with no pages yet (Gameplay and AI, Engine architecture, Optimisation) keeps its outline in `docs/`, but is listed under `exclude_docs` in `zensical.toml`, so it is not built or shown. When its first page is written, remove it from `exclude_docs`, add it to `nav`, and add it to the section list on the home page.

## Roadmap

[docs/roadmap.md](docs/roadmap.md) lists topics that do not have a page yet. When you add a page, delete that topic from the roadmap in the same change. Do not tick it, and do not strike it through. A finished topic is not a roadmap entry.

## Unity pages

A Unity mechanic or camera page is a plain C# implementation. Where an official package makes the setup shorter, the same page also has that variant, as a content tab or a labelled section. The package pill says which one. Cameras use Cinemachine 3 (`Unity.Cinemachine`: `CinemachineCamera`, `CinemachineOrbitalFollow`, `CinemachineRotationComposer`, `CinemachineDeoccluder`). That API is not Cinemachine 2.
