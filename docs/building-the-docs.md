# Building the docs

This site is built by Sphinx from the `docs/` folder of the repository.

- Pages are Markdown files (MyST flavour).
- The API reference is generated from the source files by sphinx-autoapi. It reads
  the files without importing them, so the build needs no lab environment. The
  `kexp/experiments/` folder is left out of the API reference.

## Build locally

From the repository root:

```
uvx --with-requirements docs/requirements.txt --from sphinx sphinx-build docs docs/_build/html
```

Then open `docs/_build/html/index.html`. The command runs in a throwaway
environment and does not change the lab's Python environment.

## Publishing

`.github/workflows/docs.yml` builds the site for every pull request and publishes
it to GitHub Pages on every push to `main`.

## Adding a page

Add a Markdown file under `docs/` and list it in a `toctree` block, for example
the one in `docs/index.md`.
