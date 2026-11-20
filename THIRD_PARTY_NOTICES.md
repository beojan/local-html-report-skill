# Third-party components

The files below are vendored unmodified in `skills/local-html-report/renderer/assets/vendor/`.
Each keeps its licence banner. Run `local-report update-assets` to refresh them.

| Component | Version | Licence |
| --- | --- | --- |
| [Bootstrap](https://getbootstrap.com/) | 5.3.8 | MIT |
| [Font Awesome Free](https://fontawesome.com/license/free) | 7.3.1 | Icons CC BY 4.0, fonts SIL OFL 1.1, code MIT |
| [D3](https://d3js.org/) | 7.9.0 | ISC |
| [Observable Plot](https://observablehq.com/plot/) | 0.6.17 | ISC |

Python dependencies (Markdown, Pygments) are installed by `uv` at run time and are not bundled.

Fonts in `skills/local-html-report/renderer/assets/fonts/`, both under SIL OFL 1.1 (texts in `OFL-*.txt` beside them):

| Font | Files | Notes |
| --- | --- | --- |
| [Source Sans 3](https://github.com/adobe-fonts/source-sans) | `source-sans-3-var.woff2`, `source-sans-3-italic-var.woff2` | Adobe, 3.052. Format conversion only, no glyph changes. |
| [Iosevka](https://typeof.net/Iosevka/) | `iosevka-regular.woff2`, `iosevka-bold.woff2`, `iosevka-italic.woff2` | Version 34.3.0, subset to Latin, Greek, punctuation, arrows, maths and box drawing. |
