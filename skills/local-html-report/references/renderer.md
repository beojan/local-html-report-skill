# Renderer conventions

Read for command syntax, source excerpts, styling, or interactive components.

## Source layout

Keep the source outside the project tree:

```text
report-name/
  index.md
  findings.md
  assets/
    architecture.svg
```

Use relative Markdown links such as `[Findings](findings.md)` and relative asset
links such as `![Architecture](assets/architecture.svg)`. An optional front
matter block can supply `title` and `description`.

## Procedure

1. Target Firefox and local-only delivery. Keep Markdown, assets, and any static rendered snapshot out of the project tree.
2. Store all authored report material in Markdown and `assets/`, never only in generated HTML. Create a portable static snapshot with:

   ```sh
   scripts/local-report render /path/to/report-name
   ```

3. For a local preview, use the renderer's built-in on-demand server:

   ```sh
   scripts/local-report serve /path/to/report-name
   ```

   It renders requested Markdown pages on demand and serves only the report
   source, renderer-owned frontend assets, and renderer-owned fonts on
   `127.0.0.1`. It does not create a site to preview. Keep the delivered preview running; stop it when it is no longer needed or the user requests it. Do
   not use `python -m http.server`, lighttpd, nginx, or a separate `serve.sh`.
   Commands in this file are written relative to the skill directory, so run
   `<skill-dir>/scripts/local-report` (the directory that holds `SKILL.md`). The wrapper
   needs `uv`. In a sandbox where the default uv cache is not writable, set
   `LOCAL_REPORT_UV_CACHE_DIR` to a writable directory.

   Port `8000` is often held by an earlier report's preview. Pass `--port 0` to
   bind a free loopback port, or an unused port such as `--port 8001` after an
   `[Errno 98] Address already in use` error, and never stop another report's
   server to claim `8000`. The startup line
   `Serving <source> on demand at http://127.0.0.1:<port>/` gives the port. The
   server answers `HEAD` with `405`, so inspect served HTML with `curl -fsS URL`,
   not `curl -I`.

   After changing the report, renderer, assets, or source-backed excerpts, use
   one command to verify and refresh an existing preview:

   ```sh
   scripts/local-report restart --port 8000
   ```

   This is the preferred update path: it repeats the full report and source-link
   verification before signalling the server, retains the existing loopback
   listening socket across the process replacement, and advances the recorded
   generation only after the refreshed server is ready. If verification fails,
   it reports the problem and leaves the running generation untouched. Do not
   kill and relaunch the server merely to pick up an update. The runtime
   state (server records and the form response queue) lives outside the skill, in
   `$LOCAL_REPORT_STATE_DIR`, or else `$XDG_STATE_HOME/local-report`, or else
   `~/.local/state/local-report`.

   To validate without refreshing a server, run:

   ```sh
   scripts/local-report verify /path/to/report-name --code-root /path/to/source-tree
   ```
4. The renderer ships local Bootstrap 5 and Font Awesome Free. Refresh their vendored copies, when needed, with:

   ```sh
   scripts/local-report update-assets
   ```

   Generated reports must not request CDN assets.
5. Both PaperColor light and Solarized dark are first-class themes. The rendered Bootstrap navigation contains a persistent user-controlled toggle, active-page state, responsive collapse control, and breadcrumbs. Use concise, descriptive Markdown page titles so the navigation and breadcrumb trail remain useful. Do not choose one as the only report theme.
6. The renderer renders every fenced block with a language badge and line numbers. Prose uses the system sans font (`system-ui` and common fallbacks), so no font has to be installed. Code uses Iosevka (regular, bold, italic; Latin, Greek, punctuation, arrows, maths and box-drawing glyphs), bundled as `woff2` in `renderer/assets/fonts/`. Iosevka's `calt` ligatures are on. Icons come from Font Awesome Free, so no Nerd or Powerline glyphs are needed. Iosevka is SIL OFL 1.1 and its licence text sits beside it. Fence code with the correct language. Cite the displayed line numbers when discussing an excerpt. Use an unfenced or neutral block if the grammar is uncertain rather than applying a wrong language label.

   A longer excerpt copied from a specific file must declare its relative source path, first source line, and code-root index (root `0` is the default):

   ````markdown
   ```cpp {source="src/core/filter.cpp" line=68 root=0}
   if (decision) {
     release_data();
   }
   ```
   ````

   The renderer continues the visible numbering from line 68. The `path:line`
   header and every snippet line number open the built-in source modal at the
   corresponding full-file line; the modal provides an explicit full-page link
   without replacing the report. Do not hand-author another modal or paste
   manual line numbers into the code. Generated, illustrative, or synthesized
   snippets must omit `source`, `line`, `root`, and `numbers`; they retain ordinary 1-based
   numbering and no provenance link.

   Lines copied from something that is not a source file, such as a log, keep the line
   numbers they have there. Set the gutter with `numbers="2217,2248,2420-2421"` (one number per
   displayed line, as a comma list that may hold ranges) or with `line=2217` alone when the
   lines are contiguous. Never type the numbers into the code text, because the gutter would
   then show a second set. The count in `numbers=` must equal the number of lines, or
   rendering fails. These fences get no provenance link, and `numbers=` cannot be combined
   with `source=`.
7. To show a real source file on demand, serve the report with an explicit root for each code tree that must be viewable:

   ```sh
   local-report serve /path/to/report --code-root /path/to/source-tree
   ```

   Link to a file with `/_code/0/relative/path.cpp#L68`; root index `0` is the first `--code-root`, and `#L68` scrolls to and highlights line 68. Source-backed snippet links invoke the renderer's large, sandboxed Bootstrap modal automatically. The modal embeds a chrome-free view of the full file and retains a new-tab full-page fallback. The viewer syntax-highlights the file, adds line numbers, and permits files only below the named roots. It is on-demand only: do not use these links in a static rendered site. Keep code-root scope narrow and link only to files that readers are authorised to inspect.
8. Light mode follows NLKNguyen PaperColor: system sans for prose; Iosevka for code; background `#eeeeee`; ink `#444444`; blue accent `#005f87`; heading blue-black around `#003f5a`; PaperColor-derived ordinary panels and white plot panels. Let ordinary paragraphs use the same available content width as tables, code, and other primary components; do not impose a narrower global prose column. Inline code is plain full-ink Iosevka with no fill, outline, or underline. Long code blocks and plots have a subtle border. Code on coloured panels uses a transparent or panel-derived background.
9. If plots are needed, pick by complexity and interactivity. Make complex static plots with Matplotlib in the ATLAS style (`uv run --with matplotlib --with atlas-mpl-style python plot.py`) and save them as SVG or PNG in `assets/`. Set the style up with `use_report_style()` from `<skill-dir>/scripts/report_style.py`, which calls `ampl.use_atlas_style()` and `plt.style.use("print")` (with a warning and Matplotlib's default style if `atlas-mpl-style` is missing) and then sets a 13 pt text size and a figure width of exactly the content column (1192 px, 12.42 in). An SVG is displayed at its natural size up to the width of the column, so its text then has the size of the body text (1.08 rem) and the figure is as wide as the interactive charts. Do not set `fontsize=` on individual text, ticks or legends, because that breaks the match. Save with `save_report_figure(fig, path)` from the same module, not with `bbox_inches="tight"`, which crops every figure to a different width (it also strips the SVG's fixed width and height, so the figure fills the column, which is sized in rem, at any root font size), and redesign a figure whose content is wider than the column instead of scaling it. Embed the SVG, and use a PNG only for inspection, because a PNG is scaled down to the column width and its text shrinks. Make interactive and simple plots with a `plot` fence (Observable Plot) and complex interactive plots with a `d3` fence. The renderer loads the pinned local libraries only on pages with a chart, inlines the `data=` file (CSV or JSON, up to 2 MiB, relative to the page, no `..`), applies the report fonts, ink colour, and print-theme palette (`--chart-1` to `--chart-7` tokens), and adds a collapsed table of the first 25 rows. Charts sit on the same white plot panel as images in both themes.

   ````markdown
   ```plot {data="assets/times.csv" title="Request time" caption="One dot per run." height=320}
   return {
     x: {label: "Run"}, y: {label: "Request time [ms]", grid: true},
     color: {legend: true},
     marks: [Plot.dot(data, {x: "run", y: "t", fill: "cfg", tip: true})]
   };
   ```
   ````

   The body is a function of `(Plot, d3, data, theme)` and must `return`. A `plot` fence returns a Plot options object, and a `d3` fence returns a DOM node built with `theme.width`, `theme.height`, `theme.font`, and `theme.palette`. Set `color: {scheme: "blues"}` for continuous colour, because the palette applies only to categorical scales. Fences must be top level. Avoid `d3.csvParse`, which the Content Security Policy blocks. The tested render covers the served page and the `file://` snapshot in light and dark themes.

   **Colour scheme.** Interactive charts follow the page theme. The chart panel, ink, grid and palette are the `--chart-*` tokens, which differ between the light theme (white panel, PaperColor accents) and the dark theme (Solarized panel and accents), and the charts are drawn again when the theme is toggled. In a fence take colours from `theme` (`theme.ink`, `theme.panel`, `theme.muted`, `theme.grid`, `theme.palette`) and never write `"white"`, `"black"` or a hex colour, because that stays fixed when the theme changes. Static ATLAS-style figures keep the white plot panel in both themes, so they match the interactive charts in the light theme.

   **Font, size and width.** Interactive charts take the font family and size of the body text, and fill the width of the content column. They are drawn again when that width changes, for example when the window is resized. `theme.fontSize` is the body size in pixels and `theme.width` is the column width. Heights and margins that a fence gives (the `height=` attribute, `marginLeft` and so on) are written for a 13 px body font, and the renderer scales them by the page's font size, so the chart keeps its proportions.

   **Tooltips.** Give a chart one tooltip. Every mark with `tip: true` gets its own pointer,
   so on overlapping marks the tooltips stack up and none sits on the dot under the cursor.
   The renderer prints a warning for a fence that sets `tip: true` on several marks. Put all
   points of a chart in one long-format data file (a `kind` column) and add a single
   `Plot.tip(data, Plot.pointer({x: "x", y: "y", title: d => ...}))`. Use `Plot.pointerX` when
   only the x position matters.

   **Distributions.** Show the spread of a quantity as a box plot (`Plot.boxX` or `Plot.boxY`),
   a violin or a ridgeline, not as a table of quantiles. Put the numbers in the tooltip or in
   the collapsed data table. Keep one scale per fence, so quantities with different units go
   in separate fences.

   **Checking hover without a browser window.** Load a temporary copy of the rendered snapshot
   with a `window` `load` script that picks the plot `svg` with the most `circle` elements,
   dispatches `pointerenter` and `pointermove` (`new PointerEvent(type, {clientX, clientY,
   bubbles: true, pointerType: "mouse"})`) at one dot, and then take a screenshot with
   `firefox --headless -no-remote -profile TEMPDIR --window-size W,H --screenshot ABSOLUTE.png file://...`.
   Use a window tall enough to avoid scrolling and a separate profile, because a running
   Firefox refuses a second headless instance. Count the `[aria-label=tip]` groups in the svg.
   More than one means the tooltips overlap.

   **Architecture and flow diagrams.** Never embed a hand-authored diagram with `![...](assets/x.svg)`. An SVG loaded through `<img>` is an isolated document: it cannot read `body[data-theme="dark"]`, the page's CSS variables, or the vendored Iosevka `@font-face` rules, and `main.report-shell img` gives it the static white `--plot-panel` meant for static ATLAS-style figures, so it stays in light mode. Use an inline `<svg>` in a `<figure>` instead, with no blank lines inside the `<figure>` so Python-Markdown passes it through, `style="display: block; width: 100%; background: var(--chart-panel);"`, `rx` as an SVG attribute, and colours from `var(--heading)`, `var(--chart-ink)`, `var(--chart-muted)`, `var(--blue)`, `var(--chart-1)` to `var(--chart-7)`, `var(--danger)`, `var(--line)` or `color-mix(in srgb, ...)`. A `d3` fence that reads `theme` also works. Both follow the theme toggle.

10. Keep prose labels in the sans font with tabular numerals; use Iosevka only for literal identifiers such as paths, ranks, hashes, hostnames, and protocol tokens.
11. The renderer supplies print rules. When print preview is requested, review it deliberately: use section-aware breaks, keep headings with following content, repeat table headers, avoid splitting short code/figures/cards, hide navigation, and do not add decorative footer boilerplate. Ordinary text must be at least 12 pt; 8 pt is only for genuinely ancillary annotations.
12. In reviews or other triaged comments, begin a finding heading (or inline marker) with `[P0]` through `[P4]`, or `[Done]` once resolved, optionally with a kind label such as `[P1: bug]`. The renderer turns it into a Bootstrap priority badge: P0/P1 danger, P2 warning, P3 information, and P4 secondary. Keep the source marker in Markdown; do not hand-author badge HTML. Badges appear only in ordinary Markdown text (headings, paragraphs, lists, table cells). Do not backtick a marker you want as a badge, and do not put markers in external or inline SVGs, `plot` or `d3` text, or `form` and `form-fields` labels, where they stay literal.
13. Use Bootstrap components only when they clarify a document role. The renderer automatically gives GFM tables Bootstrap table treatment, Markdown admonitions Bootstrap alerts, and native `<details>` blocks disclosure-card treatment. Use `!!! note`, `!!! important`, `!!! warning`, `!!! danger`, or `!!! tip` for a short contextual callout; use `<details><summary>…</summary>…</details>` for optional supporting evidence. Do not add cards, alerts, or badges merely as visual decoration.
14. Bootstrap tabs are appropriate for two or more mutually exclusive views of the same evidence, such as API variants or alternative configurations. Use the standard accessible Bootstrap tab markup and ensure each tab panel has a descriptive label. Use a modal only for optional detail that is already summarized or linked from the normal reading path; it must have a labelled title, a close control, and no essential content trapped inside it.
15. Use a Bootstrap progress bar only for a real measurable value, with `role="progressbar"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, and visible text. Do not hand-author `<form>` markup. A form that asks the reader for a decision is a `form` fence (item 19), which the renderer builds with labels and sends to the agent. A hand-written control is never saved or sent, so it must not suggest that it is.
16. Tooltips, collapse controls, and carousels are locally enabled by the renderer. Use a tooltip only for a short clarification of a visible label; it must not contain essential content or be the only explanation. Use a labelled Bootstrap collapse control for optional detail that can safely remain hidden on first reading, with matching `aria-controls` and `aria-expanded` attributes.
17. Use a carousel only for a small ordered sequence of visual material, such as before/after figures or a guided visual walkthrough. Give every slide meaningful alternative text/caption, provide labelled previous/next controls and indicators, and disable automatic cycling (`data-bs-interval="false"`). Do not put prose sections, review findings, code, or ordinary comparisons in a carousel; use headings, cards, or tabs instead.
18. Do not rely on Firefox CSS margin-box page counters. Do not change persistent browser print preferences without authorization. PDF production is outside this skill.
19. A `form` fence asks the reader a question and sends the answer back to the agent. Use one only when the answer changes what happens next. The renderer builds a Bootstrap card with a label for every control and loads its form script only on pages with a form. The fence takes `id=` (unique on the page, letters, digits, `_`, `.` or `-`) and an optional `title=`. Its body is a JSON object with `fields`, an optional `description`, and optional `actions` (`fields` may be left out when `form-fields` fences hold them, as described below):

   ````markdown
   ```form {id="fix-plan" title="Which findings should I fix?"}
   {
     "description": "I will fix the ticked findings and then refresh this report.",
     "fields": [
       {"name": "findings", "type": "checkbox", "label": "Findings", "required": true,
        "options": [{"value": "p1-leak", "label": "Buffer leak (P1)"}, "p2-race"]},
       {"name": "scope", "type": "radio", "label": "Patch scope", "options": ["narrow", "broad"], "default": "narrow"},
       {"name": "tests", "type": "switch", "label": "Add regression tests", "default": true},
       {"name": "notes", "type": "textarea", "label": "Anything else", "help": "Optional."}
     ],
     "actions": [
       {"value": "apply", "label": "Fix these"},
       {"value": "stop", "label": "Stop here", "style": "outline-secondary"}
     ]
   }
   ```
   ````

   Field types are `text`, `textarea`, `number`, `range`, `select`, `radio`, `checkbox` and `switch`. Every field needs `name` and `label`. Optional keys are `required`, `default`, `help`, `placeholder`, `rows`, and `min`, `max` and `step` for numbers. `select` and `radio` need `options`. A `checkbox` with `options` returns a list of the ticked values, and one without options returns `true` or `false`, as `switch` does. An option is a string or `{"value", "label"}`. Each action becomes a submit button, and its `value` is returned as `action`. Without `actions` the form has one "Send to agent" button. A form may have no fields and two or more actions, which makes it a set of choice buttons. Button styles are `primary` (the default), `secondary`, `success`, `danger`, `warning`, `outline-primary`, `outline-secondary` and `outline-danger`. The fence must be top level, like a chart fence. Text in the fence is shown as plain text, without Markdown.

   To put a form's fields next to the items they refer to, such as one tick box and note under each finding, add a `form-fields` fence after each item and one `form` fence with the buttons where the reader should send the answers, usually at the end. A `form-fields` fence takes `form=`, the id of a `form` fence on the same page, and its body is a JSON object with a non-empty `fields` list in the syntax above. It renders compactly without a card or buttons, and its textareas default to two rows. The `form` fence may then have no fields of its own, or a few general ones:

   ````markdown
   ### [P1] Buffer leak

   `Reader::next` never frees the scratch buffer.

   ```form-fields {form="review"}
   {"fields": [
     {"name": "fix-leak", "type": "checkbox", "label": "Fix this finding"},
     {"name": "leak-notes", "type": "textarea", "label": "Notes"}
   ]}
   ```

   ### [P2] Counter race

   Two workers increment the counter without a lock.

   ```form-fields {form="review"}
   {"fields": [
     {"name": "fix-race", "type": "checkbox", "label": "Fix this finding"},
     {"name": "race-notes", "type": "textarea", "label": "Notes"}
   ]}
   ```

   ```form {id="review" title="Send my choices"}
   {"actions": [{"value": "apply", "label": "Fix the ticked findings"}]}
   ```
   ````

   A button sends every field of its form on the page, and the response has one `values` object with them in page order, here `fix-leak`, `leak-notes`, `fix-race` and `race-notes`. Field names must be unique across all of a form's fences. Rendering and `local-report verify` reject a repeated name and a `form-fields` fence whose `form=` names no form on the page. A form whose only fields are in `form-fields` fences needs just one action.

   On the preview server a button POSTs the answers to `/_respond`. The server accepts only JSON from the report's own loopback origin, checks the answers against the form as the page currently declares it (known action, every field present, options offered, required fields answered), and adds the response to a queue in the renderer's state directory (`responses/` under the location named in item 3). The report source is not changed. `local-report wait REPORT` prints the responses that it has not printed before, one JSON object per line, and waits for one if there are none. `--timeout SECONDS` makes it give up with exit status 3. `local-report responses REPORT` prints every response without marking any. A response looks like this:

   ```json
   {"seq": 1, "received": "2026-11-12T14:16:38-0800", "page": "index.md", "form": "fix-plan", "title": "Which findings should I fix?", "action": "apply", "action_label": "Fix these", "values": {"findings": ["p1-leak"], "scope": "narrow", "tests": true, "notes": ""}}
   ```

   The form tells the reader that the response was sent and stays editable, so a later submission is a new response. A static snapshot over `file://` cannot send, so its buttons copy `{"report_response": {page, form, action, values}}` to the clipboard and show it for the reader to paste into the chat. Printing hides the buttons. To check a form without clicking, add a temporary page whose `load` script fills the fields and calls `form.requestSubmit(button)`, open it with headless Firefox, and read the result with `local-report responses`.
