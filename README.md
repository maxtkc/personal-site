# Personal Site

Built with [Zola](https://www.getzola.org/) using the [duckquill](https://codeberg.org/duckquill/duckquill) theme.

## Theme Modifications

Template overrides live in `templates/` and take precedence over the theme's versions in `themes/duckquill/templates/`.

### `templates/article.html`

Override of `themes/duckquill/templates/article.html`.

- **Fix list structure**: The "tags:" label link inside `<ul class="tags">` was a direct child of `<ul>` without being wrapped in `<li>`, which is invalid HTML and breaks screen reader list announcements. Wrapped it in `<li>`.
- **LCP optimization**: Added `fetchpriority="high"` to the banner `<img>` to reduce LCP resource load delay.

## Static File Overrides

Local files in `static/` override theme files at the same path.

### `static/katex.css`

Override of `themes/duckquill/static/katex.css`.

- **FCP optimization**: Added `font-display: swap` to all `@font-face` blocks to eliminate render-blocking font load delay.

### `templates/partials/articles.html`

Override of `themes/duckquill/templates/partials/articles.html`.

- **Fix empty link**: The article card anchor (`<a href="..."></a>`) had no text content or accessible name, making it undescribable to screen readers. Added `aria-label="{{ page.title }}"`.
- **Fix list structure**: Same "tags:" label link issue as in `article.html` — wrapped in `<li>`.
- **Fix heading order**: Article card titles used `<h3>`, skipping `<h2>` after the section `<h1>`, which disrupts screen reader heading navigation. Changed to `<h2>`.
