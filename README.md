# local-html-report

An agent skill that turns a code review, audit, or analysis into a local, multi-page HTML
report. The agent writes Markdown, and a bundled renderer produces a themed site with
syntax-highlighted code, links into source files, interactive charts (Observable Plot and D3),
and forms that send the reader's decisions back to the agent. It works offline, with light and
dark themes, and the report can be previewed on loopback or saved as a static snapshot.

It follows the open Agent Skills layout (`SKILL.md` plus `scripts/` and `references/`), so the
same folder works in Claude Code, Codex, and Antigravity.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) (runs the renderer and any analysis or plotting scripts)
- A browser. Firefox is the tested target.

No fonts need installing. Report pages use the system sans font and a bundled Iosevka for code.

## Install

**Claude Code (plugin):**

```
/plugin marketplace add beojan/local-html-report-skill
/plugin install local-html-report --marketplace beojan/local-html-report-skill
```

**Any of the tools (skill folder):**

```sh
git clone https://github.com/beojan/local-html-report-skill && cd local-html-report-skill
./install.sh                      # Claude Code, Codex and Antigravity, user level
./install.sh --claude             # or choose tools: --codex, --antigravity
./install.sh --project ~/my-repo  # project level instead
./install.sh --link               # symlink to this checkout so that updates apply immediately
```

| Tool | User-level folder | Project-level folder |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` | `.claude/skills/` |
| Codex | `~/.agents/skills/` | `.agents/skills/` |
| Antigravity | `~/.gemini/config/skills/` | `.agents/skills/` |

You can also copy `skills/local-html-report/` into one of those folders yourself. Restart the
tool afterwards. If Antigravity does not list the skill, check the Customizations menu, and try
the older `~/.gemini/antigravity/skills/` location. Recent Codex releases also still read
`~/.codex/skills/`.

## Use

Ask for a report, for example "review this branch and write it up as a local HTML report". The
skill tells the agent how to author, verify, and serve it. To try the renderer by hand:

```sh
skills/local-html-report/scripts/local-report serve skills/local-html-report/renderer/examples/demo-report --port 0
```

Data analysis is done in [Polars](https://pola.rs), and static figures use Matplotlib with
[`atlas-mpl-style`](https://pypi.org/project/atlas-mpl-style/), both declared in each script's
PEP 723 header and run with `uv run script.py`.

## Layout

```
skills/local-html-report/
  SKILL.md              instructions for the agent
  references/renderer.md  syntax and conventions
  scripts/local-report    wrapper around the renderer
  scripts/report_style.py Matplotlib setup for report figures
  renderer/             the renderer (Python, vendored Bootstrap, D3, Observable Plot)
```

Run the renderer tests with
`uv run --project skills/local-html-report/renderer python -m unittest discover -s skills/local-html-report/renderer/tests`.

## Licence

MIT, see [LICENSE](LICENSE). Vendored components are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
