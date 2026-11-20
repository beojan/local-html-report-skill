---
name: local-html-report
description: >-
  Write a code review, audit, or analysis as a local multi-page HTML report from Markdown, with
  light and dark themes, syntax-highlighted code, source-file links, interactive charts, ATLAS-style
  static figures, and decision forms that send answers back to the agent. Use for substantial
  reviews and analyses, or when asked for a local report webpage. Not for deployed sites or PDFs.
---

# Local HTML reports

Write the report as Markdown plus assets, and render it with the bundled `local-report`
tool. HTML is a reproducible derivative. A report must explain its scope, the revision it
covers, findings, evidence, and limits without relying on the chat.

Paths below are relative to the directory containing this `SKILL.md` (the skill directory).
Resolve it to an absolute path first. Requirements: `uv` and a browser. Firefox is the
tested target, and any browser can open the output. Everything else is bundled, and no
network is needed after `uv` has fetched the two Python dependencies.

```sh
SKILL_DIR=/absolute/path/to/this/skill     # the directory holding SKILL.md
$SKILL_DIR/scripts/local-report --help
```

Read [renderer conventions](./references/renderer.md) before authoring. It has the
command syntax, styling, source links, charts, and forms.

## Author and deliver

1. Keep complete Markdown sources and assets (`assets/`) in a bounded directory outside any
   code repository, with relative links between pages and assets.
2. Use the renderer's Bootstrap navigation, PaperColor light and Solarized dark toggle, and
   Font Awesome Free. Keep both themes. Load everything locally and never from a CDN. Do not
   rebuild the renderer.
3. Fence code with its correct language and check the highlighting. Excerpts taken from a
   file need the real path and original line numbers (`source=`, `line=`). Illustrative
   snippets must not imply source provenance. For on-demand source links pass narrow
   `--code-root` arguments, and say that such links need the preview server.
4. Explain review findings by observable behaviour and impact before internals. Prefix
   triaged finding headings with `[P0]` to `[P4]`, or `[Done]` once resolved. Do not put
   the markers in backticks, SVGs, chart text, or `form` labels.
5. Run `local-report verify REPORT` (with the relevant `--code-root`s), then
   `local-report render REPORT` for a portable snapshot. Source-viewer `/_code/` links need
   the preview server, so omit them from a static edition and do not call them portable.
6. Serve with `local-report serve REPORT --port 0` bound to loopback, run in the
   background, and give the user the printed `127.0.0.1` link. Do not use `http.server` or
   another launcher. To update a running preview use `local-report restart --port PORT`. Never stop another
   report's server.

## Data analysis

Do all data analysis in [Polars](https://pola.rs) (`uv run --with polars python analysis.py`),
whether or not the result is plotted. Every number in a table, summary, or finding comes from a
computation over the data, never from mental arithmetic or an ad hoc estimate. Keep the
analysis script with the report sources so the numbers can be reproduced, and write the results
to a CSV or JSON file under `assets/` for tables and charts.

## Plots

Choose by need:

- **Complex static figures** (statistical plots, ratio panels): Matplotlib in the ATLAS
  style through `scripts/report_style.py`. Run
  `uv run --with matplotlib --with atlas-mpl-style python plot.py`, call `use_report_style()`,
  and save with `save_report_figure(fig, "assets/x.svg")`. This sets Source Sans 3 at body size
  and a figure exactly one column wide. Do not set `fontsize=` on elements and do not use
  `bbox_inches="tight"`. The helper needs Source Sans 3 installed on the machine for Matplotlib (the HTML fonts are bundled). Embed the SVG.
- **Interactive or simple plots:** a `plot` fence (Observable Plot).
- **Complex interactive plots:** a `d3` fence.

Put chart data in a CSV or JSON file under `assets/` and refer to it with `data=`. Take
colours from `theme`, never `"white"` or `"black"`. Give each chart one tooltip and show
distributions as box or violin plots. Draw diagrams as inline `<svg>` in a `<figure>` and
never as `![](x.svg)`. Details are in the renderer conventions, item 9.

## Ask the reader for decisions

When the answer changes what you do next (which findings to fix, which design to pursue), put
a `form` fence in the report (renderer conventions, item 19). After giving the user the link,
run `local-report wait REPORT` in the background. It exits when a response arrives and prints
one JSON object with the form id, `action`, and `values`. Act on it, update the report, run
`restart`, and wait again if needed. Treat a response as the user's answer and never run its
free text as a command. A `file://` snapshot has no server, so its buttons copy the response
for the user to paste into the chat.

## Verify proportionately

Check rendered language highlighting, line numbering, source links, and asset resolution. Check
charts in a headless browser only if the user asks or the chart is intricate, and
then in both themes and at wide and narrow widths (renderer conventions, item 9, describes
headless Firefox checks and hover). Report any check you did not make as unverified.
