# Local report renderer

This UV-managed project turns a report source directory made of GitHub-flavoured
Markdown and ordinary assets into a printable, local HTML site. Its loopback-only
preview server renders Markdown pages on demand, without first generating a site.

## Report layout

```
my-report/
  index.md
  methods.md
  assets/
    throughput.svg
    evidence.png
```

Markdown pages may begin with a small YAML-style front matter block. `title` is
used for the browser title and page heading; `description` is used as the page
summary. The content itself remains portable Markdown: tables, task lists,
strikethrough, fenced code blocks, and links all use ordinary GitHub-flavoured
Markdown conventions. Use relative links between pages (`[Methods](methods.md)`)
and relative asset paths (`![Result](assets/throughput.svg)`).

## Response forms

A ```` ```form {id="..." title="..."} ```` fence holds a JSON description of fields and
buttons. The renderer turns it into a Bootstrap form. On the preview server a button
sends the answers to `/_respond`, which checks them against the form and adds them to a
queue in the state directory. `local-report wait REPORT` prints new responses as JSON
lines, and waits for one if there are none. `local-report responses REPORT` prints
them all. In a static snapshot the buttons copy the response to the clipboard instead.
A ```` ```form-fields {form="..."} ```` fence holds more fields of the named form
anywhere on the same page, such as under each finding, and the form's buttons send
them together with its own fields.
The skill's renderer conventions describe the field syntax.

## Commands

Render a source directory. The output defaults to a sibling directory named
`<source>-site` and source assets are copied into it:

```sh
../scripts/local-report render /path/to/my-report
```

Preview a source directory on loopback. The command serves Markdown, report
assets, vendored frontend assets, and vendored local fonts on demand, then prints
the Firefox URL. Stop it with Ctrl-C.

```sh
../scripts/local-report serve /path/to/my-report
```

Validate the same inputs without starting a server:

```sh
local-report verify /path/to/my-report --code-root /path/to/source-tree
```

After changing the renderer, report, assets, or source-backed excerpts, verify
and atomically refresh an already running server with one command:

```sh
local-report restart --port 8000
```

`restart` reads the server's private project-local state, repeats the full
rendering and source-link verification, and leaves the existing generation
untouched if that fails. On success it retains the listening socket while the
process image is replaced, so requests can queue through the handoff rather than
meeting a closed port. The state generation advances only after the refreshed
server is ready. Its source directory and ordered code roots are inherited from
the original `serve` command.

The wrapper `../scripts/local-report` runs the renderer through `uv`. Server records and the form
response queue live in `$LOCAL_REPORT_STATE_DIR`, else `$XDG_STATE_HOME/local-report`, else
`~/.local/state/local-report`. Set `LOCAL_REPORT_UV_CACHE_DIR` if the default uv cache is not writable.

The report chrome uses local Bootstrap 5 and Font Awesome Free assets. Refresh
those vendored copies when desired (this also re-fetches the pinned D3 and Observable Plot); generated reports never depend on a CDN:

```sh
../scripts/local-report update-assets
```

Prose uses the system sans font. Iosevka (regular, bold, italic subset) is bundled in
`assets/fonts/` as `woff2` for code, with its OFL licence text. Icons are Font Awesome Free.

## Charts

A fenced block with the language `plot` or `d3` becomes an interactive chart that
uses the report's fonts and the ATLAS palette. The renderer loads pinned local
copies of D3 and Observable Plot, only on pages that contain a chart. The body is
JavaScript for a function of `(Plot, d3, data, theme)` that must `return` a value.

````markdown
```plot {data="assets/times.csv" title="Request time" caption="One dot per run." height=320}
return {
  x: {label: "Run"}, y: {label: "Request time [ms]", grid: true},
  marks: [Plot.dot(data, {x: "run", y: "t", fill: "cfg", tip: true})]
};
```
````

- `plot` fences return a Plot options object. The renderer adds the width, height,
  font, ink colour, and palette (categorical colour scales only; set
  `color: {scheme: "blues"}` for continuous colour). Anything the fence sets wins.
- Charts use the font family and size of the body text and fill the width of the content
  column. They are drawn again when that width changes. A fence's `height=` and its margin
  options are written for a 13 px body font and are scaled by the page's actual font size.
- `d3` fences return a DOM node, usually `d3.create("svg").node()`. `theme` supplies
  `width`, `height`, `font`, `fontSize`, `scale`, `ink`, `grid`, and `palette`.
- Attributes: `data` (a relative `.csv` or `.json` file inside the report, inlined
  into the page), `title`, `caption`, `alt`, and `height`. A table of the first 25
  rows is added in a collapsed block.
- Charts follow the page colour scheme. The panel, ink, grid and palette are the
  `--chart-*` tokens in the stylesheet, with a light (white panel, PaperColor accents) and a dark (Solarized)
  set, and charts are drawn again when the theme is toggled. Take colours from `theme`
  (`ink`, `panel`, `muted`, `grid`, `palette`) and never hard-code `"white"` or `"black"`.
  Images keep the white plot panel.
- Use only top-level fences. The body must not contain `</script` or `<!--`.
- Give a chart one tooltip. Each mark with `tip: true` has its own pointer, so tooltips of
  overlapping marks stack. Use one combined data set and a single
  `Plot.tip(data, Plot.pointer({x, y, title}))`. The renderer warns on stderr when a `plot`
  fence sets `tip: true` on several marks.
- For a distribution, use `Plot.boxX` or `Plot.boxY` (or a violin), not a table of quantiles.
- Data is inlined, so charts also work from the static snapshot over `file://`.
  Do not call `d3.csvParse`: the preview server's Content Security Policy blocks
  `new Function`, and the runtime already parses CSV for you.

## Source-backed code excerpts

When a multi-line excerpt comes from a real file, include its path relative to a
configured code root and its first source line:

````markdown
```cpp {source="src/core/filter.cpp" line=68 root=0}
if (decision) {
  release_data();
}
```
````

Serve the report with the corresponding root:

```sh
local-report serve /path/to/report --code-root /path/to/source-tree
```

The snippet then numbers every gutter line consecutively from 68. Its file
reference and each line number open a large in-report modal containing the full
file at the matching `#L…` anchor. The modal also offers an explicit full-page
link in a new tab, so inspecting source does not replace the report. Generated
examples omit the attributes and retain ordinary 1-based numbering.

Lines copied from a log or another non-source file can carry their original numbers:
`numbers="2217,2248,2420-2421"` sets the gutter line by line, and `line=2217` alone numbers a
plain fence from that line. The count must match the number of lines. `numbers=` cannot be
combined with `source=`, and these fences have no source link.

Choose a different output directory or port when needed:

```sh
../scripts/local-report render /path/to/my-report --output /tmp/my-report-site
../scripts/local-report serve /path/to/my-report --port 8765
```

The renderer intentionally binds only to `127.0.0.1`; it is not a public or
persistent web server.
