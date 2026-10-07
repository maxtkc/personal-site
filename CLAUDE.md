# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
zola serve    # Development server with live reload
zola build    # Build static site to public/
zola check    # Validate content and links
```

CI/CD (GitHub Actions) runs `zola build` on push to `main` and deploys to GitHub Pages at `max.kcfam.us`.

## Architecture

**Stack:** Zola v0.22.1 static site generator + Duckquill theme (git submodule in `themes/duckquill/`). Content is Markdown with TOML front matter; templates are Tera (Jinja-like).

**Template overrides:** Custom templates in `templates/` override the theme's defaults. `article.html` and `partials/articles.html` fix accessibility issues from the base theme (aria-labels, heading hierarchy, valid `<ul>` structure). When the theme updates, these overrides may need to be re-synced.

**Interactive visualizations:** The TGTG blog post (`content/blog/mapping-tgtg/`) uses four D3.js + Leaflet visualizations (map, calendar, galaxy, radial) implemented as Zola shortcodes in `templates/shortcodes/`. Data flow:
1. `static/tgtg-viz-init.js` fetches `tgtg_history.geojson`, `cities.json`, and world topology from CDN, exposing `window.tgtgDataPromise`
2. Each viz shortcode's JS awaits that promise before rendering
3. Shared tooltip utilities (`tip`, `moveTip`, `hideTip`, `counter`) are defined in `tgtg-viz-init.js`

**Config:** `zola.toml` controls everything — theme, feeds, search index, CSP headers, GoatCounter analytics, Mastodon identity, and Duckquill-specific options (accent colors, social links, etc.).
