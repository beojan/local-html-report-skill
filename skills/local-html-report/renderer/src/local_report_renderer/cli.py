from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import html
import io
import json
import mimetypes
import os
import re
import shlex
import signal
import socket
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit
from urllib.request import urlopen

import markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, guess_lexer_for_filename


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VENDOR_ROOT = PROJECT_ROOT / "assets" / "vendor"
VENDORED_FONT_ROOT = PROJECT_ROOT / "assets" / "fonts"
JS_ROOT = PROJECT_ROOT / "assets" / "js"
CHART_RUNTIME = "report-charts.js"
FORM_RUNTIME = "report-forms.js"
RUNTIME_ROOT = Path(os.environ.get("LOCAL_REPORT_STATE_DIR") or Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "local-report")
RESPONSES_ROOT = RUNTIME_ROOT / "responses"
FONT_FACES = (
    ("Report Iosevka", "iosevka-regular.woff2", "400", "normal"),
    ("Report Iosevka", "iosevka-bold.woff2", "700", "normal"),
    ("Report Iosevka", "iosevka-italic.woff2", "400", "italic"),
    ("Source Sans 3", "source-sans-3-var.woff2", "200 900", "normal"),
    ("Source Sans 3", "source-sans-3-italic-var.woff2", "200 900", "italic"),
)
MAX_CODE_FILE_BYTES = 4 * 1024 * 1024
VENDOR_URLS = {
    "bootstrap/css/bootstrap.min.css": "https://cdn.jsdelivr.net/npm/bootstrap@5/dist/css/bootstrap.min.css",
    "bootstrap/js/bootstrap.bundle.min.js": "https://cdn.jsdelivr.net/npm/bootstrap@5/dist/js/bootstrap.bundle.min.js",
    "fontawesome/css/all.min.css": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@latest/css/all.min.css",
    "fontawesome/webfonts/fa-brands-400.woff2": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@latest/webfonts/fa-brands-400.woff2",
    "fontawesome/webfonts/fa-regular-400.woff2": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@latest/webfonts/fa-regular-400.woff2",
    "fontawesome/webfonts/fa-solid-900.woff2": "https://cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@latest/webfonts/fa-solid-900.woff2",
    "d3/d3.min.js": "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js",
    "plot/plot.umd.min.js": "https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6.17/dist/plot.umd.min.js",
}

STYLESHEET = r"""
__FONT_FACES__
:root { --paper: #eeeeee; --ink: #444444; --blue: #005f87; --heading: #003f5a; --panel: #e4e4e4; --panel-muted: #dadada; --plot-panel: #ffffff; --code: #e4e4e4; --line: #bcbcbc; --important: #5f00af; --warning: #b58900; --danger: #d70000; --success: #5f8700; --prio-p0: #af0000; --prio-p1: #d70000; --prio-p2: #d75f00; --prio-p3: #005f87; --prio-p4: #5f00af; --prio-done: #5f8700; --radius: .45rem; }
body[data-theme="dark"] { --paper: #002b36; --ink: #93a1a1; --blue: #268bd2; --heading: #b58900; --panel: #073642; --panel-muted: #0b3c47; --plot-panel: #ffffff; --code: #073642; --line: #586e75; --important: #6c71c4; --warning: #b58900; --danger: #dc322f; --success: #859900; --prio-p0: #dc322f; --prio-p1: #dc322f; --prio-p2: #cb4b16; --prio-p3: #268bd2; --prio-p4: #6c71c4; --prio-done: #859900; --close-filter: invert(1); }
body { background: var(--paper); color: var(--ink); font: 1.08rem/1.55 "Source Sans 3", "Source Sans Pro", sans-serif; }
.report-shell { max-width: 76rem; } h1, h2, h3, h4 { color: var(--heading); line-height: 1.2; text-wrap: pretty; } h1 { font-size: clamp(2rem, 5vw, 2.75rem); letter-spacing: -.02em; } h2 { margin-top: 2.5rem; } h3 { margin-top: 1.8rem; }
.priority-tag.badge { --prio-color: var(--blue); display: inline-flex; align-items: stretch; vertical-align: middle; padding: 0; background: color-mix(in srgb, var(--prio-color) 13%, var(--panel)); border: 1px solid color-mix(in srgb, var(--prio-color) 55%, var(--line)); border-radius: .42rem; overflow: hidden; font: 700 .78rem/1.15 "Source Sans 3", "Source Sans Pro", sans-serif; letter-spacing: .025em; font-variant-numeric: tabular-nums; white-space: nowrap; box-shadow: 0 1px 2px color-mix(in srgb, var(--ink) 12%, transparent); }
.priority-tag.priority-p0 { --prio-color: var(--prio-p0); } .priority-tag.priority-p1 { --prio-color: var(--prio-p1); } .priority-tag.priority-p2 { --prio-color: var(--prio-p2); } .priority-tag.priority-p3 { --prio-color: var(--prio-p3); } .priority-tag.priority-p4 { --prio-color: var(--prio-p4); } .priority-tag.priority-done { --prio-color: var(--prio-done); }
.priority-tag .priority-tier { display: inline-flex; align-items: center; gap: .34em; padding: .32em .84em .32em .58em; color: #ffffff; background: linear-gradient(135deg, var(--prio-color), color-mix(in srgb, var(--prio-color) 78%, #000000)); text-transform: uppercase; clip-path: polygon(0 0, calc(100% - .36em) 0, 100% 50%, calc(100% - .36em) 100%, 0 100%); box-shadow: inset 0 1px 0 rgba(255, 255, 255, .22); }
.priority-tag .priority-kind { display: inline-flex; align-items: center; gap: .34em; padding: .32em .66em .32em .3em; color: color-mix(in srgb, var(--prio-color) 84%, var(--ink)); font-weight: 600; letter-spacing: .015em; }
h1 .priority-tag.badge, h2 .priority-tag.badge, h3 .priority-tag.badge, h4 .priority-tag.badge, h5 .priority-tag.badge, h6 .priority-tag.badge { font-size: .52em; margin-right: .6rem; transform: translateY(-.1em); }
.priority-heading { display: flex; align-items: flex-start; column-gap: .6rem; } .priority-heading > .priority-tag.badge { flex: 0 0 auto; margin: .18em 0 0; transform: none; } .priority-heading-body { flex: 1 1 auto; min-width: 0; }
a { color: var(--blue); text-underline-offset: .14em; } .navbar { --bs-navbar-color: var(--ink); --bs-navbar-hover-color: var(--blue); --bs-navbar-active-color: var(--heading); border-bottom: .18rem solid var(--blue); background: var(--paper); box-shadow: 0 .1rem .25rem color-mix(in srgb, var(--ink) 7%, transparent); } .navbar-brand { color: var(--heading) !important; font-weight: 700; } .nav-link { color: var(--ink) !important; border-radius: 0; border-bottom: .18rem solid transparent; } .nav-link:hover { color: var(--blue) !important; border-bottom-color: color-mix(in srgb, var(--blue) 45%, transparent); } .nav-link.active { color: var(--heading) !important; border-bottom-color: var(--blue); } .navbar-toggler { border-color: var(--line); color: var(--heading); } .description { font-size: 1.18rem; color: color-mix(in srgb, var(--ink) 88%, var(--heading)); } .btn-outline-primary { --bs-btn-color: var(--blue); --bs-btn-border-color: var(--blue); --bs-btn-hover-bg: var(--blue); --bs-btn-hover-border-color: var(--blue); --bs-btn-active-bg: var(--blue); --bs-btn-active-border-color: var(--blue); }
.breadcrumb { --bs-breadcrumb-divider: "›"; --bs-breadcrumb-divider-color: var(--line); --bs-breadcrumb-item-active-color: var(--ink); margin-bottom: 1.3rem; } .breadcrumb a { text-decoration: none; } .breadcrumb a:hover { text-decoration: underline; } .report-page-head { padding-bottom: 1.4rem; border-bottom: 1px solid var(--line); margin-bottom: 1.8rem; }
code, pre, .highlight, .code-file { font-family: "Report Iosevka", Iosevka, monospace; font-variant-ligatures: common-ligatures contextual; font-feature-settings: "calt" 1, "liga" 1; }
code { color: var(--ink); background: transparent; padding: 0; border-radius: 0; }
pre { overflow-x: auto; padding: 1rem; background: var(--code); border: 1px solid var(--line); border-left: .28rem solid var(--blue); border-radius: var(--radius); } pre code { padding: 0; background: transparent; }
.highlight { margin: 1.35rem 0; overflow: hidden; background: var(--code); border: 1px solid var(--line); border-left: .28rem solid var(--blue); border-radius: var(--radius); } .code-header { display: flex; min-height: 1.8rem; align-items: center; justify-content: space-between; gap: .75rem; padding: .42rem .75rem; color: var(--blue); background: var(--panel-muted); border-bottom: 1px solid var(--line); font: 600 .72rem/1.2 "Source Sans 3", sans-serif; letter-spacing: .045em; } .code-language { margin-left: auto; text-transform: uppercase; } .code-source { min-width: 0; overflow-wrap: anywhere; color: var(--ink); font-family: "Report Iosevka", Iosevka, monospace; font-weight: 400; letter-spacing: 0; text-decoration: none; } .code-source:hover { color: var(--blue); text-decoration: none; } .highlight pre { margin: 0; }
table.highlighttable { width: 100%; margin: 0; border-collapse: collapse; background: var(--code); border: 0; } table.highlighttable td { padding: 0; border: 0; background: var(--code); vertical-align: top; } table.highlighttable td.linenos { width: 1%; background: var(--panel-muted); border-right: 1px solid var(--line); user-select: none; } table.highlighttable .linenos pre { padding: 1rem .7rem; color: color-mix(in srgb, var(--ink) 58%, transparent); text-align: right; border: 0; border-radius: 0; } table.highlighttable .linenos a { color: inherit; text-decoration: none; } table.highlighttable .linenos a:hover { color: var(--blue); text-decoration: underline; } table.highlighttable .code { width: 100%; } table.highlighttable .code pre { padding: 1rem 1.1rem; border: 0; border-radius: 0; }
.highlight .c, .highlight .c1, .highlight .cm, .code-file .c, .code-file .c1, .code-file .cm { color: #8a8a8a; font-style: italic; } .highlight .s, .highlight .s1, .highlight .s2, .code-file .s, .code-file .s1, .code-file .s2 { color: #5f8700; } .highlight .m, .highlight .mi, .highlight .mf, .code-file .m, .code-file .mi, .code-file .mf { color: #d75f00; } .highlight .k, .highlight .kc, .highlight .kd, .highlight .kn, .highlight .kr, .code-file .k, .code-file .kc, .code-file .kd, .code-file .kn, .code-file .kr { color: #af005f; } .highlight .o, .highlight .p, .code-file .o, .code-file .p { color: #0087af; } .highlight .n, .highlight .nf, .highlight .nn, .code-file .n, .code-file .nf, .code-file .nn { color: #005f87; } .highlight .err, .code-file .err { color: #d70000; }
body[data-theme="dark"] .highlight .c, body[data-theme="dark"] .highlight .c1, body[data-theme="dark"] .highlight .cm, body[data-theme="dark"] .code-file .c, body[data-theme="dark"] .code-file .c1, body[data-theme="dark"] .code-file .cm { color: #839496; } body[data-theme="dark"] .highlight .s, body[data-theme="dark"] .highlight .s1, body[data-theme="dark"] .highlight .s2, body[data-theme="dark"] .code-file .s, body[data-theme="dark"] .code-file .s1, body[data-theme="dark"] .code-file .s2 { color: #859900; } body[data-theme="dark"] .highlight .m, body[data-theme="dark"] .highlight .mi, body[data-theme="dark"] .highlight .mf, body[data-theme="dark"] .code-file .m, body[data-theme="dark"] .code-file .mi, body[data-theme="dark"] .code-file .mf { color: #cb4b16; } body[data-theme="dark"] .highlight .k, body[data-theme="dark"] .highlight .kc, body[data-theme="dark"] .highlight .kd, body[data-theme="dark"] .highlight .kn, body[data-theme="dark"] .highlight .kr, body[data-theme="dark"] .code-file .k, body[data-theme="dark"] .code-file .kc, body[data-theme="dark"] .code-file .kd, body[data-theme="dark"] .code-file .kn, body[data-theme="dark"] .code-file .kr { color: #d33682; } body[data-theme="dark"] .highlight .o, body[data-theme="dark"] .highlight .p, body[data-theme="dark"] .code-file .o, body[data-theme="dark"] .code-file .p { color: #2aa198; } body[data-theme="dark"] .highlight .n, body[data-theme="dark"] .highlight .nf, body[data-theme="dark"] .highlight .nn, body[data-theme="dark"] .code-file .n, body[data-theme="dark"] .code-file .nf, body[data-theme="dark"] .code-file .nn { color: #268bd2; }
.table-frame { margin: 1.35rem 0; overflow: auto; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); } .table-frame table { width: 100%; margin: 0; border: 0; border-collapse: separate; border-spacing: 0; --bs-table-bg: transparent; --bs-table-color: var(--ink); --bs-table-border-color: var(--line); --bs-table-hover-bg: color-mix(in srgb, var(--blue) 7%, transparent); --bs-table-hover-color: var(--ink); }
.report-shell .table-frame table > :not(caption) > * > * { padding: .7rem .85rem; color: var(--ink); background: transparent; border-bottom-color: var(--line); vertical-align: top; } .report-shell .table-frame thead > tr > * { color: var(--heading); background: var(--panel-muted); font-weight: 700; border-bottom-width: 1px; } .report-shell .table-frame tbody > tr:last-child > * { border-bottom: 0; }
main.report-shell img, main.report-shell svg { max-width: 100%; height: auto; background: var(--plot-panel); border: 1px solid var(--line); border-radius: var(--radius); } blockquote { padding: .65rem 1rem; border-left: .28rem solid var(--blue); background: color-mix(in srgb, var(--panel) 72%, transparent); border-radius: var(--radius); }
.report-shell .alert, .report-shell .card { color: var(--ink); background: var(--panel); border-color: var(--line); border-radius: var(--radius); overflow: hidden; } .report-shell .alert { border-left-width: .28rem; } .report-shell .alert-info { background: color-mix(in srgb, var(--blue) 8%, var(--panel)); border-left-color: var(--blue); } .report-shell .alert-primary { background: color-mix(in srgb, var(--important) 8%, var(--panel)); border-left-color: var(--important); } .report-shell .alert-warning { background: color-mix(in srgb, var(--warning) 9%, var(--panel)); border-left-color: var(--warning); } .report-shell .alert-danger { background: color-mix(in srgb, var(--danger) 8%, var(--panel)); border-left-color: var(--danger); } .report-shell .alert-success { background: color-mix(in srgb, var(--success) 8%, var(--panel)); border-left-color: var(--success); } .admonition-title { font-weight: 700; } .alert-info .admonition-title { color: var(--blue); } .alert-primary .admonition-title { color: var(--important); } .alert-warning .admonition-title { color: var(--warning); } .alert-danger .admonition-title { color: var(--danger); } .alert-success .admonition-title { color: var(--success); }
.report-shell details.card { padding: 0; overflow: clip; } .report-shell details.card > summary { padding: .75rem 1rem; color: var(--heading); font-weight: 700; cursor: pointer; } .report-shell details.card > :not(summary) { margin-left: 1rem; margin-right: 1rem; } .report-shell details.card > :last-child { margin-bottom: 1rem; }
.report-shell .nav-tabs { border-bottom-color: var(--line); } .report-shell .nav-tabs .nav-link { color: var(--ink); } .report-shell .nav-tabs .nav-link:hover { border-color: var(--line) var(--line) transparent; } .report-shell .nav-tabs .nav-link.active { color: var(--heading); background: var(--panel); border-color: var(--line) var(--line) var(--panel); } .report-shell .tab-content { padding: 1rem; background: var(--panel); border: 1px solid var(--line); border-top: 0; }
.report-shell .modal-content, .source-code-modal .modal-content { color: var(--ink); background: var(--panel); border-color: var(--line); border-radius: var(--radius); overflow: hidden; } .report-shell .modal-header, .report-shell .modal-footer, .source-code-modal .modal-header { border-color: var(--line); } .report-shell .btn-close, .source-code-modal .btn-close { filter: var(--close-filter, none); }
.source-code-modal .modal-dialog { width: calc(100% - 2rem); max-width: 96rem; height: calc(100% - 2rem); margin: 1rem auto; } .source-code-modal .modal-content { height: 100%; } .source-code-modal .modal-header { flex: 0 0 auto; background: var(--panel-muted); } .source-code-modal .modal-title { min-width: 0; margin: 0; overflow: hidden; color: var(--heading); font-size: 1rem; text-overflow: ellipsis; white-space: nowrap; } .source-code-modal .modal-body { min-height: 0; padding: 0; overflow: hidden; background: var(--code); } .source-code-frame { display: block; width: 100%; height: 100%; border: 0; background: var(--paper); }
.report-shell .progress { background: color-mix(in srgb, var(--code) 82%, var(--ink)); } .report-shell .form-control, .report-shell .form-select { color: var(--ink); background: var(--panel); border-color: var(--line); } .report-shell .form-control:focus, .report-shell .form-select:focus { color: var(--ink); background: var(--panel); border-color: var(--blue); box-shadow: 0 0 0 .2rem color-mix(in srgb, var(--blue) 22%, transparent); } .report-shell .form-check-input { background-color: var(--panel); border-color: var(--line); }
.tooltip { --bs-tooltip-bg: var(--heading); --bs-tooltip-color: var(--panel); } main.report-shell .collapse, main.report-shell .collapsing { background: var(--panel); } .report-shell .carousel { background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; } .report-shell .carousel-caption { background: color-mix(in srgb, var(--heading) 88%, transparent); border-radius: calc(var(--radius) * .75); padding: .5rem .75rem; } .report-shell .carousel-control-prev-icon, .report-shell .carousel-control-next-icon { filter: drop-shadow(0 1px 2px #000); }
/* Chart fences follow the page colour scheme. These tokens are the light theme (white plot panel with the PaperColor accents) and the dark theme (Solarized). The chart runtime reads them when it draws, and draws again when the theme changes. */
:root { --chart-panel: #ffffff; --chart-ink: #444444; --chart-muted: #666666; --chart-grid: #d0d0d0; --chart-1: #008700; --chart-2: #af0000; --chart-3: #005f87; --chart-4: #d75f00; --chart-5: #8700af; --chart-6: #0087af; --chart-7: #5f7800; }
body[data-theme="dark"] { --chart-panel: #073642; --chart-ink: #93a1a1; --chart-muted: #839496; --chart-grid: #14505e; --chart-1: #859900; --chart-2: #dc322f; --chart-3: #268bd2; --chart-4: #cb4b16; --chart-5: #6c71c4; --chart-6: #2aa198; --chart-7: #b58900; }
main.report-shell .report-chart-canvas svg { background: var(--chart-panel); --plot-background: var(--chart-panel); }
.report-chart { margin: 1.35rem 0; } .report-chart-title { color: var(--heading); font-weight: 600; margin-bottom: .35rem; } .report-chart-caption { color: var(--ink); font-size: .95rem; margin-top: .4rem; }
.report-chart-canvas { color: var(--chart-ink); font-family: inherit; font-size: inherit; line-height: inherit; font-variant-numeric: tabular-nums; width: 100%; } .report-chart-canvas svg { display: block; } .report-chart-canvas [class*="-swatches"] { color: var(--ink) !important; font-family: inherit !important; font-size: inherit !important; } main.report-shell .report-chart-canvas [class*="-swatches"] svg { display: inline-block; background: none; border: 0; border-radius: 0; }
/* Response forms send the reader's answers back to the agent that wrote the report. */
.report-shell .btn-primary { --bs-btn-bg: var(--blue); --bs-btn-border-color: var(--blue); --bs-btn-hover-bg: color-mix(in srgb, var(--blue) 85%, #000000); --bs-btn-hover-border-color: color-mix(in srgb, var(--blue) 85%, #000000); --bs-btn-active-bg: color-mix(in srgb, var(--blue) 75%, #000000); --bs-btn-disabled-bg: var(--blue); --bs-btn-disabled-border-color: var(--blue); } .report-shell .btn-outline-secondary { --bs-btn-color: var(--ink); --bs-btn-border-color: var(--line); --bs-btn-hover-color: var(--paper); --bs-btn-hover-bg: var(--ink); --bs-btn-hover-border-color: var(--ink); }
.report-form .card-body { padding: 1rem 1.1rem; } .report-form-title { color: var(--heading); font-weight: 700; font-size: 1.15rem; margin-bottom: .4rem; } .report-form fieldset legend { font-size: inherit; font-weight: 600; margin-bottom: .3rem; } .report-form .form-label { font-weight: 600; margin-bottom: .3rem; } .report-form .form-text { color: color-mix(in srgb, var(--ink) 78%, transparent); } .report-form .form-check-input:checked { background-color: var(--blue); border-color: var(--blue); } .report-form .form-range::-moz-range-thumb { background: var(--blue); } .report-form .form-range::-moz-range-track { background: var(--line); } .report-form-field { margin-bottom: 1rem; } /* A form-fields block sits under the paragraph it answers, so it is compact and has no card. */ .report-form-part { margin: -.4rem 0 1.1rem; padding: .1rem 0 .1rem .8rem; border-left: .2rem solid var(--line); } .report-form-part .report-form-field { margin-bottom: .45rem; } .report-form-part .report-form-field:last-child { margin-bottom: .1rem; } .report-form-status:empty { display: none; } .report-form-status textarea { font-family: "Report Iosevka", Iosevka, monospace; font-size: .9rem; } .report-form { --bs-form-invalid-color: var(--danger); --bs-form-invalid-border-color: var(--danger); } /* Only missing answers are marked. Valid fields keep their ordinary look rather than Bootstrap's green. */ .report-form.was-validated .form-check-input:valid ~ .form-check-label { color: inherit; } .report-form.was-validated .form-check-input:valid { border-color: var(--line); } .report-form.was-validated .form-check-input:valid:checked { background-color: var(--blue); border-color: var(--blue); } .report-form.was-validated .form-check-input:valid:focus { box-shadow: 0 0 0 .2rem color-mix(in srgb, var(--blue) 22%, transparent); } .report-form.was-validated .form-control:valid, .report-form.was-validated .form-select:valid { border-color: var(--line); background-image: none; padding-right: .75rem; }
.report-chart-error { color: var(--danger); margin: 0; } .report-chart .report-chart-data-table { margin-top: .6rem; }
@media print { @page { size: auto; margin: .65in; } body { font-size: 12pt; print-color-adjust: exact; -webkit-print-color-adjust: exact; } nav, .theme-toggle, .source-code-modal, .report-form-actions, .report-form-status { display: none !important; } a { color: var(--ink); text-decoration: none; } h1, h2, h3 { break-after: avoid; } table thead { display: table-header-group; } tr, figure, img, pre, blockquote, .highlight, .table-frame, .alert, .card { break-inside: avoid; } .table-frame { overflow: visible; } }
"""


@dataclass(frozen=True)
class Page:
    source: Path
    relative: Path
    title: str
    description: str | None
    body: str


@dataclass(frozen=True)
class Snippet:
    language: str
    source: Path | None = None
    line: int = 1
    root: int = 0
    numbers: tuple[int, ...] = ()


def parse_page(path: Path, source_root: Path) -> Page:
    text = path.read_text(encoding="utf-8")
    metadata: dict[str, str] = {}
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            for line in text[4:end].splitlines():
                key, separator, value = line.partition(":")
                if separator and key.strip() in {"title", "description"}:
                    metadata[key.strip()] = value.strip().strip('"')
            text = text[end + 5 :]
    title = metadata.get("title") or path.stem.replace("-", " ").replace("_", " ").title()
    return Page(path, path.relative_to(source_root), title, metadata.get("description"), text)


PRIORITY_TIERS: dict[str, tuple[str, str, str, str]] = {
    "0": ("p0", "P0", "fa-fire", "Blocker"),
    "1": ("p1", "P1", "fa-triangle-exclamation", "High"),
    "2": ("p2", "P2", "fa-bolt", "Medium"),
    "3": ("p3", "P3", "fa-circle-info", "Normal"),
    "4": ("p4", "P4", "fa-layer-group", "Low"),
    "done": ("done", "Done", "fa-circle-check", "Complete"),
}

PRIORITY_KIND_ICONS: dict[str, str] = {
    "blocker": "fa-fire",
    "high": "fa-arrow-up",
    "medium": "fa-grip-lines",
    "normal": "fa-minus",
    "low": "fa-arrow-down",
    "complete": "fa-check",
    "bug": "fa-bug",
    "hazard": "fa-shield-halved",
    "design": "fa-compass-drafting",
    "feature": "fa-cube",
    "research": "fa-flask",
    "refactor": "fa-screwdriver-wrench",
    "spec": "fa-scale-balanced",
    "discussion": "fa-comments",
    "blocked": "fa-lock",
    "hygiene": "fa-broom",
    "done": "fa-code-merge",
    "pr": "fa-code-merge",
    "merged": "fa-code-merge",
}


def render_priority_badge(tier: str, detail: str | None = None, *, extra_class: str = "") -> str:
    css_key, tier_label, tier_icon, default_kind = PRIORITY_TIERS[tier]
    kind_text = (detail or "").strip().lstrip(":-").strip() or default_kind
    first_word = re.split(r"[\s()/+-]+", kind_text.lower())[0]
    if first_word in {"done", "merged", "complete"} and tier != "done":
        css_key = "done"
        tier_icon = "fa-circle-check"
    if kind_text and kind_text.split()[0].islower():
        kind_text = kind_text[0].upper() + kind_text[1:]
    kind_icon = PRIORITY_KIND_ICONS.get(first_word)
    icon_html = f'<i class="fa-solid {kind_icon}" aria-hidden="true"></i>' if kind_icon else ""
    classes = f"badge priority-tag priority-{css_key}" + (f" {extra_class}" if extra_class else "")
    return (
        f'<span class="{classes}">'
        f'<span class="priority-tier"><i class="fa-solid {tier_icon}" aria-hidden="true"></i><span>{html.escape(tier_label)}</span></span>'
        f'<span class="priority-kind">{icon_html}<span>{html.escape(kind_text)}</span></span>'
        f"</span>"
    )


CHART_LANGUAGES = {"plot", "d3"}
FORM_LANGUAGE = "form"
FORM_FIELDS_LANGUAGE = "form-fields"
EMBED_LANGUAGES = CHART_LANGUAGES | {FORM_LANGUAGE, FORM_FIELDS_LANGUAGE}
MAX_CHART_DATA_BYTES = 2 * 1024 * 1024
CHART_TABLE_ROWS = 25


@dataclass(frozen=True)
class Chart:
    kind: str
    code: str
    attributes: dict[str, str]


def extract_charts(page: Page, body: str) -> tuple[str, list[Chart]]:
    """Replace each top-level ```plot, ```d3, ```form or ```form-fields fence with a placeholder paragraph.

    Fences nested inside another fence, such as a documentation example in a
    longer fence, are left alone."""
    opener = re.compile(r"^(?P<fence>`{3,}|~{3,})[ \t]*(?P<language>[A-Za-z0-9_+-]*)(?:[ \t]+\{(?P<attributes>[^}\n]*)\})?[ \t]*$")
    output: list[str] = []
    charts: list[Chart] = []
    open_fence: str | None = None
    chart_lines: list[str] | None = None
    chart_header: tuple[str, dict[str, str]] | None = None
    for line in body.split("\n"):
        if open_fence is None:
            match = opener.match(line)
            if not match:
                output.append(line)
                continue
            open_fence = match.group("fence")
            if match.group("language") in EMBED_LANGUAGES:
                try:
                    pairs = [token.partition("=") for token in shlex.split(match.group("attributes") or "")]
                except ValueError as error:
                    raise ValueError(f"{match.group('language').title()} fence in {page.relative} has malformed attributes: {error}") from error
                chart_header = (match.group("language"), {key: value for key, separator, value in pairs if separator})
                chart_lines = []
            else:
                output.append(line)
            continue
        closing = re.match(r"^(`{3,}|~{3,})[ \t]*$", line)
        if closing and closing.group(1)[0] == open_fence[0] and len(closing.group(1)) >= len(open_fence):
            if chart_lines is not None and chart_header is not None:
                charts.append(Chart(chart_header[0], "\n".join(chart_lines), chart_header[1]))
                output.extend(["", f"REPORTCHARTPLACEHOLDER{len(charts) - 1}X", ""])
                chart_lines, chart_header = None, None
            else:
                output.append(line)
            open_fence = None
            continue
        if chart_lines is not None:
            chart_lines.append(line)
        else:
            output.append(line)
    if chart_lines is not None:
        raise ValueError(f"Unclosed {chart_header[0] if chart_header else 'chart'} fence in {page.relative}")
    return "\n".join(output), charts


def load_chart_data(page: Page, value: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Read a chart's data file and return the inline payload and rows for its table."""
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Chart data in {page.relative} must be a relative path without '..': {value}")
    if relative.suffix not in {".csv", ".json"}:
        raise ValueError(f"Chart data in {page.relative} must be a .csv or .json file: {value}")
    source_root = page.source.resolve().parents[len(page.relative.parts) - 1]
    candidate = (page.source.resolve().parent / relative).resolve()
    try:
        candidate.relative_to(source_root)
    except ValueError as error:
        raise ValueError(f"Chart data in {page.relative} escapes the report source: {value}") from error
    if not candidate.is_file():
        raise ValueError(f"Chart data file in {page.relative} does not exist: {value}")
    if candidate.stat().st_size > MAX_CHART_DATA_BYTES:
        raise ValueError(f"Chart data file exceeds the 2 MiB inline limit: {value}")
    text = candidate.read_text(encoding="utf-8")
    if relative.suffix == ".csv":
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows:
            raise ValueError(f"Chart data file has no rows: {value}")
        return {"format": "csv", "text": text}, rows
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Chart data file is not valid JSON ({value}): {error}") from error
    return {"format": "json", "rows": rows}, [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def render_chart(page: Page, chart: Chart, index: int) -> str:
    code = chart.code.strip("\n")
    if not code.strip():
        raise ValueError(f"Chart fence {index + 1} in {page.relative} is empty")
    if re.search(r"</script|<!--", code, re.IGNORECASE):
        raise ValueError(f"Chart fence {index + 1} in {page.relative} must not contain '</script' or '<!--'")
    attributes = chart.attributes
    if chart.kind == "plot" and len(re.findall(r"\btip\s*:\s*true\b", code)) > 1:
        # Every mark with tip: true gets its own pointer, so on overlapping marks the
        # tooltips stack on top of each other and none sits on the dot under the cursor.
        print(
            f"warning: plot fence {index + 1} in {page.relative} sets tip: true on several marks. "
            "Put the points in one data set and add a single Plot.tip(rows, Plot.pointer({x, y, title})).",
            file=sys.stderr,
        )
    payload: dict[str, object] | None = None
    rows: list[dict[str, object]] = []
    if attributes.get("data"):
        payload, rows = load_chart_data(page, attributes["data"])
    try:
        height = int(attributes.get("height", "320"))
    except ValueError as error:
        raise ValueError(f"Chart fence {index + 1} in {page.relative} has a non-integer height") from error
    figure_id = f"report-chart-{index + 1}"
    title = attributes.get("title")
    caption = attributes.get("caption")
    label = attributes.get("alt") or title or "Chart"
    table = ""
    if rows:
        columns = list(rows[0])
        head = "".join(f"<th>{html.escape(str(column))}</th>" for column in columns)
        body_rows = "".join("<tr>" + "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns) + "</tr>" for row in rows[:CHART_TABLE_ROWS])
        table = (
            f'<details class="card mb-3 report-chart-data-table"><summary>Plotted data (first {min(len(rows), CHART_TABLE_ROWS)} of {len(rows)} rows)</summary>'
            f'<div class="table-responsive table-frame"><table class="table table-hover align-middle"><thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table></div></details>'
        )
    data_json = json.dumps(payload).replace("</", "<\\/")
    return (
        f'<figure class="report-chart" id="{figure_id}" data-chart-kind="{chart.kind}" data-chart-height="{height}">'
        + (f'<div class="report-chart-title">{html.escape(title)}</div>' if title else "")
        + f'<div class="report-chart-canvas" role="img" aria-label="{html.escape(label)}"><noscript>This chart needs JavaScript.</noscript></div>'
        + (f'<figcaption class="report-chart-caption">{html.escape(caption)}</figcaption>' if caption else "")
        + table
        + f'<script type="application/json" class="report-chart-data">{data_json}</script>'
        + f'<script>reportCharts.add("{figure_id}", function (Plot, d3, data, theme) {{\n{code}\n}});</script></figure>'
    )


FORM_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
FORM_FIELD_TYPES = {"text", "textarea", "number", "range", "select", "radio", "checkbox", "switch"}
FORM_CHOICE_TYPES = {"select", "radio", "checkbox"}
FORM_BUTTON_STYLES = {"primary", "secondary", "success", "danger", "warning", "outline-primary", "outline-secondary", "outline-danger"}
MAX_RESPONSE_BYTES = 64 * 1024
MAX_RESPONSE_TEXT = 20000


@dataclass(frozen=True)
class FormField:
    """One reader control in a ```form fence, after validation.

    ``kind`` is how the response stores its value: ``string``, ``number``, ``boolean``,
    ``choice`` (one option value or null) or ``list`` (the checked option values)."""

    name: str
    type: str
    label: str
    kind: str
    options: tuple[tuple[str, str], ...] = ()
    help: str | None = None
    required: bool = False
    default: object = None
    placeholder: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    rows: int = 4


@dataclass(frozen=True)
class FormSpec:
    """A validated form: its id, prose, fields and submit buttons ``(value, label, style)``.

    ``fields`` holds every field of the form on its page in page order, whether it sits in
    the ```form fence itself or in a ```form-fields fence that names the form."""

    id: str
    title: str | None
    description: str | None
    fields: tuple[FormField, ...]
    actions: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class FormBlock:
    """The fields that one ```form or ```form-fields fence renders, and the form they belong to."""

    form_id: str
    fields: tuple[FormField, ...]


def parse_form_body(where: str, chart: Chart, allowed: set[str]) -> dict[str, object]:
    """Parse the JSON object body of a form fence. Raises ``ValueError`` for invalid JSON or unknown keys."""
    try:
        body = json.loads(chart.code) if chart.code.strip() else {}
    except json.JSONDecodeError as error:
        raise ValueError(f"{where} is not valid JSON: {error}") from error
    if not isinstance(body, dict):
        raise ValueError(f"{where} must be a JSON object")
    unknown = set(body) - allowed
    if unknown:
        raise ValueError(f"{where} has unknown keys: {', '.join(sorted(unknown))}")
    return body


def parse_fields(where: str, entries: object, *, default_rows: int = 4) -> tuple[FormField, ...]:
    """Validate a JSON ``fields`` list and return its fields in order.

    ``where`` names the fence in error messages, and ``default_rows`` is the height of a
    textarea that does not set ``rows``. Raises ``ValueError`` for a malformed field or a
    name repeated within the list."""
    if not isinstance(entries, list):
        raise ValueError(f"{where} needs fields to be a JSON list")

    def optional_number(entry: dict[str, object], key: str) -> float | None:
        value = entry.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{where} field {entry.get('name')!r} needs a number for {key}")
        return float(value)

    fields: list[FormField] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{where} has a field that is not a JSON object")
        name, kind_name, label = entry.get("name"), entry.get("type", "text"), entry.get("label")
        if not isinstance(name, str) or not FORM_ID_PATTERN.fullmatch(name):
            raise ValueError(f"{where} has a field without a valid name: {name!r}")
        if any(field.name == name for field in fields) or name == "action":
            raise ValueError(f"{where} repeats or reserves the field name {name!r}")
        if kind_name not in FORM_FIELD_TYPES:
            raise ValueError(f"{where} field {name!r} has unknown type {kind_name!r}")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{where} field {name!r} needs a label")
        options: list[tuple[str, str]] = []
        for option in entry.get("options", []):
            if isinstance(option, str):
                options.append((option, option))
            elif isinstance(option, dict) and isinstance(option.get("value"), str):
                options.append((option["value"], str(option.get("label", option["value"]))))
            else:
                raise ValueError(f"{where} field {name!r} has an option that is neither a string nor {{value, label}}")
        if len({value for value, _ in options}) != len(options):
            raise ValueError(f"{where} field {name!r} repeats an option value")
        if kind_name in {"select", "radio"} and not options:
            raise ValueError(f"{where} field {name!r} of type {kind_name} needs options")
        if kind_name not in FORM_CHOICE_TYPES and options:
            raise ValueError(f"{where} field {name!r} of type {kind_name} cannot have options")
        kind = {"number": "number", "range": "number", "radio": "choice", "switch": "boolean"}.get(kind_name, "string")
        if kind_name == "checkbox":
            kind = "list" if options else "boolean"
        try:
            rows = int(entry.get("rows", default_rows))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{where} field {name!r} needs an integer rows") from error
        fields.append(
            FormField(
                name=name,
                type=kind_name,
                label=label.strip(),
                kind=kind,
                options=tuple(options),
                help=str(entry["help"]) if entry.get("help") else None,
                required=bool(entry.get("required", False)),
                default=entry.get("default"),
                placeholder=str(entry["placeholder"]) if entry.get("placeholder") else None,
                minimum=optional_number(entry, "min"),
                maximum=optional_number(entry, "max"),
                step=optional_number(entry, "step"),
                rows=max(rows, 1),
            )
        )
    return tuple(fields)


def parse_form(page: Page, chart: Chart) -> FormSpec:
    """Validate a ```form fence and return its specification, holding only its own fields.

    The fence needs an ``id`` attribute that is unique on the page and a JSON object body
    with an optional ``fields`` list, ``description`` and ``actions``. Raises ``ValueError``
    naming the page and the problem when the fence is malformed. Whether the form has
    anything to answer depends on its ```form-fields fences too, so ``collect_forms`` checks it."""
    where = f"Form fence in {page.relative}"
    form_id = chart.attributes.get("id", "")
    if not FORM_ID_PATTERN.fullmatch(form_id):
        raise ValueError(f"{where} needs an id= of letters, digits, '_', '.' or '-': {form_id!r}")
    where = f"Form {form_id!r} in {page.relative}"
    body = parse_form_body(where, chart, {"description", "fields", "actions"})
    fields = parse_fields(where, body.get("fields", []))
    actions: list[tuple[str, str, str]] = []
    for entry in body.get("actions") or [{"value": "submit", "label": "Send to agent", "style": "primary"}]:
        if not isinstance(entry, dict) or not isinstance(entry.get("value"), str) or not FORM_ID_PATTERN.fullmatch(entry["value"]):
            raise ValueError(f"{where} has an action without a valid value")
        style = str(entry.get("style", "primary"))
        if style not in FORM_BUTTON_STYLES:
            raise ValueError(f"{where} action {entry['value']!r} has unknown style {style!r}")
        if any(value == entry["value"] for value, _, _ in actions):
            raise ValueError(f"{where} repeats the action {entry['value']!r}")
        actions.append((entry["value"], str(entry.get("label", entry["value"])), style))
    description = body.get("description")
    return FormSpec(form_id, chart.attributes.get("title"), str(description) if description else None, fields, tuple(actions))


def parse_form_fields(page: Page, chart: Chart, index: int) -> FormBlock:
    """Validate the ``index``-th (from 0) ```form-fields fence of a page.

    The fence needs a ``form`` attribute naming a form on the page and a JSON object body
    with a non-empty ``fields`` list. Its textareas default to two rows, so a short answer
    sits under the paragraph it refers to. Raises ``ValueError`` when the fence is malformed."""
    where = f"Form-fields fence {index + 1} in {page.relative}"
    form_id = chart.attributes.get("form", "")
    if not FORM_ID_PATTERN.fullmatch(form_id):
        raise ValueError(f"{where} needs a form= naming a form id: {form_id!r}")
    where = f"Form-fields fence {index + 1} (form {form_id!r}) in {page.relative}"
    body = parse_form_body(where, chart, {"fields"})
    fields = parse_fields(where, body.get("fields", []), default_rows=2)
    if not fields:
        raise ValueError(f"{where} needs at least one field")
    return FormBlock(form_id, fields)


def collect_forms(page: Page, embeds: list[Chart]) -> tuple[dict[str, FormSpec], dict[int, FormBlock]]:
    """Validate every form of a page and join each form's fields from all its fences.

    Returns the forms by id, each with all of its fields in page order, and, by embed index,
    the fields that each ```form or ```form-fields fence renders. Raises ``ValueError`` for a
    repeated form id, a field name used twice in one form, a ```form-fields fence that names
    no form on the page, or a form with no fields and fewer than two actions."""
    headers: dict[str, FormSpec] = {}
    blocks: dict[int, FormBlock] = {}
    part_count = 0
    for index, embed in enumerate(embeds):
        if embed.kind == FORM_LANGUAGE:
            spec = parse_form(page, embed)
            if spec.id in headers:
                raise ValueError(f"Form id {spec.id!r} is used more than once in {page.relative}")
            headers[spec.id] = spec
            blocks[index] = FormBlock(spec.id, spec.fields)
        elif embed.kind == FORM_FIELDS_LANGUAGE:
            blocks[index] = parse_form_fields(page, embed, part_count)
            part_count += 1
    orphans = sorted({block.form_id for block in blocks.values()} - set(headers))
    if orphans:
        raise ValueError(f"A form-fields fence in {page.relative} names a form that is not on the page: {', '.join(orphans)}")
    fields: dict[str, list[FormField]] = {form_id: [] for form_id in headers}
    for block in blocks.values():
        for field in block.fields:
            if any(other.name == field.name for other in fields[block.form_id]):
                raise ValueError(f"Form {block.form_id!r} in {page.relative} uses the field name {field.name!r} more than once")
            fields[block.form_id].append(field)
    forms: dict[str, FormSpec] = {}
    for form_id, spec in headers.items():
        if not fields[form_id] and len(spec.actions) < 2:
            # A form without fields is a set of choice buttons, so one button would carry no answer.
            raise ValueError(f"Form {form_id!r} in {page.relative} needs at least one field or two actions")
        forms[form_id] = FormSpec(spec.id, spec.title, spec.description, tuple(fields[form_id]), spec.actions)
    return forms, blocks


def page_forms(page: Page) -> dict[str, FormSpec]:
    """Return the validated forms of a page by id, each with all of its fields. Raises ``ValueError`` for a malformed form."""
    _, embeds = extract_charts(page, page.body)
    return collect_forms(page, embeds)[0]


def render_form_field(spec: FormSpec, field: FormField, *, detached: bool = False) -> str:
    """Return the Bootstrap markup of one form field, wrapped in an element the form runtime reads.

    A ``detached`` field sits outside the ``<form>`` element, in a ```form-fields block, so
    each of its controls names the form with the HTML ``form`` attribute. The browser then
    validates it and groups its radio buttons with the form's other controls."""
    base = f"rf-{spec.id}-{field.name}"
    owner = f' form="report-form-{spec.id}"' if detached else ""
    help_html = f'<div class="form-text" id="{base}-help">{html.escape(field.help)}</div>' if field.help else ""
    described = f' aria-describedby="{base}-help"' if field.help else ""
    required = " required" if field.required else ""
    wrapper = f'<div class="report-form-field" data-field-name="{html.escape(field.name)}" data-field-kind="{field.kind}"{" data-required=\"true\"" if field.required else ""}>'
    label = html.escape(field.label) + (' <span class="text-danger" aria-hidden="true">*</span>' if field.required else "")
    invalid = '<div class="invalid-feedback">This answer is required.</div>' if field.required else ""
    default = field.default
    if field.type in {"radio", "checkbox"} and field.options:
        chosen = set(default) if isinstance(default, list) else {default}
        input_type = "radio" if field.type == "radio" else "checkbox"
        choices = "".join(
            f'<div class="form-check"><input class="form-check-input" type="{input_type}" name="{html.escape(field.name)}"{owner} id="{base}-{index}" value="{html.escape(value)}"'
            f'{" checked" if value in chosen else ""}{required if input_type == "radio" else ""}><label class="form-check-label" for="{base}-{index}">{html.escape(text)}</label>'
            + (invalid if index == len(field.options) - 1 else "")
            + "</div>"
            for index, (value, text) in enumerate(field.options)
        )
        return f'{wrapper}<fieldset{described}><legend>{label}</legend>{choices}{help_html}</fieldset></div>'
    if field.type in {"switch", "checkbox"}:
        switch = " form-switch" if field.type == "switch" else ""
        role = ' role="switch"' if field.type == "switch" else ""
        return (
            f'{wrapper}<div class="form-check{switch}"><input class="form-check-input" type="checkbox"{role} id="{base}" name="{html.escape(field.name)}"{owner}'
            f'{" checked" if default is True else ""}{required}{described}><label class="form-check-label" for="{base}">{label}</label>{invalid}</div>{help_html}</div>'
        )
    placeholder = f' placeholder="{html.escape(field.placeholder)}"' if field.placeholder else ""
    label_html = f'<label class="form-label" for="{base}">{label}</label>'
    if field.type == "select":
        blank = "" if default is not None and field.required else '<option value="">Choose…</option>'
        choices = "".join(f'<option value="{html.escape(value)}"{" selected" if value == default else ""}>{html.escape(text)}</option>' for value, text in field.options)
        control = f'<select class="form-select" id="{base}" name="{html.escape(field.name)}"{owner}{required}{described}>{blank}{choices}</select>'
    elif field.type == "textarea":
        control = f'<textarea class="form-control" id="{base}" name="{html.escape(field.name)}"{owner} rows="{field.rows}"{placeholder}{required}{described}>{html.escape(str(default)) if default is not None else ""}</textarea>'
    else:
        limits = "".join(f' {key}="{value:g}"' for key, value in (("min", field.minimum), ("max", field.maximum), ("step", field.step)) if value is not None)
        input_type = {"number": "number", "range": "range"}.get(field.type, "text")
        css = "form-range" if field.type == "range" else "form-control"
        value = f' value="{html.escape(str(default))}"' if default is not None else ""
        control = f'<input class="{css}" type="{input_type}" id="{base}" name="{html.escape(field.name)}"{owner}{limits}{value}{placeholder}{required}{described}>'
        if field.type == "range":
            label_html = f'<label class="form-label" for="{base}">{label}: <output for="{base}" class="report-form-range-value"></output></label>'
    return f"{wrapper}{label_html}{control}{invalid}{help_html}</div>"


def render_form(page: Page, spec: FormSpec, fields: tuple[FormField, ...] | None = None) -> str:
    """Return the Bootstrap card for a form, holding ``fields`` (by default all of its fields).

    The form runtime sends the card's fields and those of the form's ```form-fields blocks
    to ``/_respond``."""
    title = f'<div class="report-form-title" id="rf-{spec.id}-title">{html.escape(spec.title)}</div>' if spec.title else ""
    labelled = f' aria-labelledby="rf-{spec.id}-title"' if spec.title else ' aria-label="Response form"'
    description = f'<p class="report-form-description">{html.escape(spec.description)}</p>' if spec.description else ""
    buttons = "".join(
        f'<button type="submit" class="btn btn-{style}" name="action" value="{html.escape(value)}">{html.escape(label)}</button>'
        for value, label, style in spec.actions
    )
    return (
        f'<form class="report-form card mb-3" id="report-form-{spec.id}" data-form-id="{spec.id}" data-report-page="{html.escape(page.relative.as_posix())}"{labelled} novalidate>'
        f'<div class="card-body">{title}{description}{"".join(render_form_field(spec, field) for field in (spec.fields if fields is None else fields))}'
        f'<div class="report-form-actions d-flex flex-wrap gap-2">{buttons}</div>'
        f'<div class="report-form-status mt-3" role="status" aria-live="polite"></div></div></form>'
    )


def render_form_part(spec: FormSpec, fields: tuple[FormField, ...]) -> str:
    """Return a ```form-fields block: ``fields`` of ``spec`` laid out inline, outside the form's card.

    The block has no buttons. The form's own buttons collect and send its fields."""
    label = f"Part of {spec.title}" if spec.title else "Part of a response form"
    return (
        f'<div class="report-form report-form-part" data-form-part="{spec.id}" role="group" aria-label="{html.escape(label)}">'
        + "".join(render_form_field(spec, field, detached=True) for field in fields)
        + "</div>"
    )


def validate_response(spec: FormSpec, action: object, values: object) -> tuple[str, dict[str, object]]:
    """Check a submitted response against its form and return ``(action, values)``.

    Every field of the form must be present with a value of its kind, chosen values must be
    options of the field, and required fields must be answered. Raises ``ValueError`` with a
    reason the reader can be shown."""
    if not isinstance(action, str) or action not in {value for value, _, _ in spec.actions}:
        raise ValueError(f"Unknown action {action!r}")
    if not isinstance(values, dict):
        raise ValueError("Values must be a JSON object")
    names = {field.name for field in spec.fields}
    if set(values) != names:
        raise ValueError(f"Values must hold exactly the fields {', '.join(sorted(names)) or '(none)'}")
    checked: dict[str, object] = {}
    for field in spec.fields:
        value = values[field.name]
        allowed = {option for option, _ in field.options}
        if field.kind == "boolean":
            ok = isinstance(value, bool)
            empty = value is not True
        elif field.kind == "number":
            ok = value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))
            empty = value is None
        elif field.kind == "list":
            ok = isinstance(value, list) and all(isinstance(item, str) and item in allowed for item in value)
            empty = not value
        elif field.kind == "choice":
            ok = value is None or (isinstance(value, str) and value in allowed)
            empty = value is None
        else:
            ok = isinstance(value, str) and len(value) <= MAX_RESPONSE_TEXT and (not allowed or value in allowed or value == "")
            empty = not (isinstance(value, str) and value.strip())
        if not ok:
            raise ValueError(f"Field {field.name!r} has an invalid value")
        if field.required and empty:
            raise ValueError(f"Field {field.name!r} is required")
        checked[field.name] = value
    return action, checked


def responses_path(source: Path) -> Path:
    """Return the queue file that holds the form responses of a report source directory.

    The queue lives in the renderer's private runtime directory, so the report source and its
    rendered snapshots stay free of reader state."""
    key = hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()[:16]
    return RESPONSES_ROOT / f"{key}.jsonl"


def append_response(source: Path, record: dict[str, object]) -> int:
    """Append a response record to the report's queue and return its sequence number (from 1).

    An exclusive lock on the queue makes concurrent submissions take distinct numbers."""
    path = responses_path(source)
    RESPONSES_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "a+", encoding="utf-8") as queue:
        os.chmod(path, 0o600)
        fcntl.flock(queue, fcntl.LOCK_EX)
        queue.seek(0)
        sequence = sum(1 for line in queue if line.strip()) + 1
        queue.write(json.dumps({"seq": sequence, **record}, ensure_ascii=False) + "\n")
        queue.flush()
    return sequence


def read_responses(source: Path) -> list[dict[str, object]]:
    """Return every stored response of a report source, oldest first (an empty list if none)."""
    try:
        text = responses_path(source).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def markdown_html(page: Page) -> str:
    body = page.body
    # The renderer owns the document H1. Permit a source page to repeat its
    # front-matter title for GitHub readability without duplicating it in HTML.
    leading_h1 = re.match(r"\A\s*#\s+([^\n]+)\s*\n(?:\s*\n)?", body)
    if leading_h1 and leading_h1.group(1).strip() == page.title:
        body = body[leading_h1.end() :]
    body, charts = extract_charts(page, body)
    snippets: list[Snippet] = []
    fence_pattern = re.compile(r"^(?P<fence>`{3,}|~{3,})[ \t]*(?P<language>[A-Za-z0-9_+-]+)(?:[ \t]+\{(?P<attributes>[^}\n]*)\})?[ \t]*$", re.MULTILINE)

    def prepare_fence(match: re.Match[str]) -> str:
        attributes: dict[str, str] = {}
        for token in shlex.split(match.group("attributes") or ""):
            key, separator, value = token.partition("=")
            if separator:
                attributes[key] = value
        source_value = attributes.get("source") or attributes.get("file")
        line_value = attributes.get("line")
        if source_value and not line_value:
            raise ValueError(f"Source-backed fence in {page.relative} requires both source= and line= attributes")
        # numbers="2217,2248,2420-2421" sets the gutter numbers of a plain fence line by line,
        # for example to show the line numbers of a log the lines were copied from. A plain
        # fence may also give line=N alone, which numbers its lines from N.
        numbers: tuple[int, ...] = ()
        if attributes.get("numbers"):
            if source_value:
                raise ValueError(f"Fence in {page.relative} cannot combine numbers= with source=")
            try:
                parsed: list[int] = []
                for part in attributes["numbers"].split(","):
                    low, dash, high = part.strip().partition("-")
                    parsed.extend(range(int(low), int(high) + 1) if dash else [int(low)])
            except ValueError as error:
                raise ValueError(f"Fence in {page.relative} has a malformed numbers= list") from error
            if not parsed or min(parsed) < 1:
                raise ValueError(f"Fence in {page.relative} requires numbers= to hold positive integers")
            numbers = tuple(parsed)
        source = Path(source_value) if source_value else None
        if source and (source.is_absolute() or ".." in source.parts):
            raise ValueError(f"Source-backed fence in {page.relative} must use a relative source path without '..'")
        try:
            line = int(line_value) if line_value else 1
            root = int(attributes.get("root", "0"))
        except ValueError as error:
            raise ValueError(f"Source-backed fence in {page.relative} has a non-integer line or root") from error
        if line < 1 or root < 0:
            raise ValueError(f"Source-backed fence in {page.relative} requires line >= 1 and root >= 0")
        snippets.append(Snippet(match.group("language"), source, line, root, numbers))
        return f'{match.group("fence")}{match.group("language")}'

    body = fence_pattern.sub(prepare_fence, body)
    heading_badges: list[tuple[str, str | None]] = []
    heading_badge_pattern = re.compile(
        r"^(?P<hashes>#{1,6}[ \t]+)\[(?:P(?P<prio>[0-4])|(?P<done>Done))(?:[ \t:]+(?P<detail>[^\]]+))?\][ \t]*",
        re.MULTILINE,
    )

    def prepare_heading_badge(match: re.Match[str]) -> str:
        tier = "done" if match.group("done") else match.group("prio")
        heading_badges.append((tier, match.group("detail")))
        token = "[Done]" if tier == "done" else f"[P{tier}]"
        return f'{match.group("hashes")}{token} '

    fenced_split = re.split(r"(^`{3,}.*?^`{3,}|^~{3,}.*?^~{3,})", body, flags=re.MULTILINE | re.DOTALL)
    body = "".join(
        heading_badge_pattern.sub(prepare_heading_badge, part) if idx % 2 == 0 else part
        for idx, part in enumerate(fenced_split)
    )
    renderer = markdown.Markdown(extensions=["extra", "sane_lists", "toc", "codehilite", "admonition", "meta"], extension_configs={"codehilite": {"css_class": "highlight", "guess_lang": False, "linenos": "table"}})
    rendered = renderer.convert(body)
    blocks = rendered.split('<div class="highlight">')
    if len(blocks) - 1 != len(snippets):
        raise ValueError(f"Could not associate every fenced code block with its metadata in {page.relative}")
    labels = {"cpp": "C++", "cxx": "C++", "c++": "C++", "c": "C", "python": "Python", "haskell": "Haskell", "rust": "Rust", "bash": "Shell", "sh": "Shell", "shell": "Shell", "json": "JSON", "html": "HTML", "css": "CSS", "sql": "SQL"}
    rendered_parts = [blocks[0]]
    for snippet, block in zip(snippets, blocks[1:]):
        language = snippet.language.lower()
        language_class = "cpp" if language == "c++" else re.sub(r"[^a-z0-9_-]", "-", language)
        header = f'<div class="code-header"><span class="code-language">{html.escape(labels.get(language, language.replace("-", " ")))}</span></div>'
        if snippet.source:
            source_path = snippet.source.as_posix()
            base_href = f'/_code/{snippet.root}/{quote(source_path, safe="/")}'
            source_label = f'{source_path}:{snippet.line}'
            modal_attributes = f'data-bs-toggle="modal" data-bs-target="#source-code-modal" data-source-path="{html.escape(source_path)}"'
            header = f'<div class="code-header"><a class="code-source source-view-link" href="{html.escape(base_href)}#L{snippet.line}" {modal_attributes} data-source-line="{snippet.line}" title="Open the full file at line {snippet.line}"><i class="fa-solid fa-file-code me-1" aria-hidden="true"></i>{html.escape(source_label)}</a><span class="code-language">{html.escape(labels.get(language, language.replace("-", " ")))}</span></div>'
            next_line = snippet.line

            def source_line(match: re.Match[str]) -> str:
                nonlocal next_line
                line = next_line
                next_line += 1
                return f'<a class="code-line-link source-view-link" href="{html.escape(base_href)}#L{line}" {modal_attributes} data-source-line="{line}" title="Open {html.escape(source_path)} at line {line}">{line}</a>'

            block = re.sub(r'<span class="normal">[ \t]*\d+</span>', source_line, block)
        elif snippet.numbers or snippet.line != 1:
            gutter = re.compile(r'<span class="normal">[ \t]*\d+</span>')
            lines = len(gutter.findall(block))
            if snippet.numbers and len(snippet.numbers) != lines:
                raise ValueError(f"Fence in {page.relative} lists {len(snippet.numbers)} numbers= but has {lines} lines")
            labels_iter = iter(snippet.numbers or range(snippet.line, snippet.line + lines))
            block = gutter.sub(lambda _match: f'<span class="normal">{next(labels_iter)}</span>', block)
        rendered_parts.append(f'<div class="highlight language-{language_class}">{header}{block}')
    rendered = "".join(rendered_parts)
    heading_badge_iter = iter(heading_badges)

    def replace_heading_badge(match: re.Match[str]) -> str:
        tag, attrs, token, title_html = match.group("tag", "attrs", "token", "body")
        tier, detail = next(heading_badge_iter, ("done" if token == "Done" else token[1:], None))
        if re.search(r'\bclass="', attrs):
            attrs = re.sub(r'\bclass="([^"]*)"', r'class="\1 priority-heading"', attrs, count=1)
        else:
            attrs = f'{attrs} class="priority-heading"'
        return f'<{tag}{attrs}>{render_priority_badge(tier, detail)}<span class="priority-heading-body">{title_html}</span></{tag}>'

    rendered = re.sub(
        r"<(?P<tag>h[1-6])(?P<attrs>(?:\s[^>]*)?)>\[(?P<token>P[0-4]|Done)\]\s*(?P<body>.*?)</(?P=tag)>",
        replace_heading_badge,
        rendered,
        flags=re.DOTALL,
    )
    inline_badge_pattern = re.compile(r"\[(?:P(?P<prio>[0-4])|(?P<done>Done))(?:[ \t:]+(?P<detail>[^\]]+))?\]")

    def replace_inline_badge(match: re.Match[str]) -> str:
        tier = "done" if match.group("done") else match.group("prio")
        return render_priority_badge(tier, match.group("detail"))

    html_chunks = re.split(r"(<pre\b.*?</pre>|<code\b.*?</code>)", rendered, flags=re.DOTALL)
    rendered = "".join(
        inline_badge_pattern.sub(replace_inline_badge, chunk) if idx % 2 == 0 else chunk
        for idx, chunk in enumerate(html_chunks)
    )
    alert_classes = {"note": "info", "important": "primary", "warning": "warning", "danger": "danger", "tip": "success"}
    rendered = re.sub(r'<div class="admonition (note|important|warning|danger|tip)">', lambda match: f'<div class="alert alert-{alert_classes[match.group(1)]}" role="alert">', rendered)
    rendered = re.sub(r"<table>(.*?)</table>", r'<div class="table-responsive table-frame"><table class="table table-hover align-middle">\1</table></div>', rendered, flags=re.DOTALL)
    rendered = rendered.replace("<details>", '<details class="card mb-3">')
    forms, form_blocks = collect_forms(page, charts)
    chart_index = 0
    for index, chart in enumerate(charts):
        token = f"REPORTCHARTPLACEHOLDER{index}X"
        if f"<p>{token}</p>" not in rendered:
            raise ValueError(f"{chart.kind.title()} fence {index + 1} in {page.relative} must be a top-level block, not nested in a list or quote")
        if chart.kind == FORM_LANGUAGE:
            block = form_blocks[index]
            rendered = rendered.replace(f"<p>{token}</p>", render_form(page, forms[block.form_id], block.fields))
        elif chart.kind == FORM_FIELDS_LANGUAGE:
            block = form_blocks[index]
            rendered = rendered.replace(f"<p>{token}</p>", render_form_part(forms[block.form_id], block.fields))
        else:
            rendered = rendered.replace(f"<p>{token}</p>", render_chart(page, chart, chart_index))
            chart_index += 1
    return re.sub(r'href="([^"?#]+)\.md(?=([?#][^"]*)?")', r'href="\1.html', rendered)


def font_faces(url_for) -> str:
    """Return `@font-face` rules for the bundled fonts present in `assets/fonts`.

    Source Sans 3 is declared under its own name, so the bundled copy wins over an installed one.
    """
    return "\n".join(
        f'@font-face {{ font-family: "{family}"; src: url("{url_for(filename)}") format("woff2"); font-weight: {weight}; font-style: {style}; font-display: swap; }}'
        for family, filename, weight, style in FONT_FACES
        if (VENDORED_FONT_ROOT / filename).is_file()
    )


def page_href(current: Page, target: Page) -> str:
    return Path("../" * len(current.relative.parent.parts), target.relative.with_suffix(".html")).as_posix()


def support_href(page: Page, name: str) -> str:
    return Path("../" * len(page.relative.parent.parts), "_renderer", name).as_posix()


def breadcrumb(page: Page, index: Page, pages: list[Page]) -> str:
    page_by_relative = {candidate.relative: candidate for candidate in pages}
    crumbs = [f'<li class="breadcrumb-item"><a href="{html.escape(page_href(page, index))}"><i class="fa-solid fa-house" aria-hidden="true"></i><span class="visually-hidden">Home</span></a></li>']
    parents = page.relative.parent.parts
    for depth, segment in enumerate(parents):
        relative_index = Path(*parents[: depth + 1]) / "index.md"
        parent_page = page_by_relative.get(relative_index)
        label = html.escape(segment.replace("-", " ").title())
        crumbs.append(f'<li class="breadcrumb-item"><a href="{html.escape(page_href(page, parent_page))}">{label}</a></li>' if parent_page else f'<li class="breadcrumb-item">{label}</li>')
    crumbs.append(f'<li class="breadcrumb-item active" aria-current="page">{html.escape(page.title)}</li>')
    return '<nav aria-label="Breadcrumb"><ol class="breadcrumb">' + "".join(crumbs) + "</ol></nav>"


def document(page: Page, pages: list[Page]) -> str:
    nav = "".join(f'<li class="nav-item"><a class="nav-link{" active" if candidate.relative == page.relative else ""}" href="{html.escape(page_href(page, candidate))}"{" aria-current=\"page\"" if candidate.relative == page.relative else ""}>{html.escape(candidate.title)}</a></li>' for candidate in pages)
    description = f'<p class="description">{html.escape(page.description)}</p>' if page.description else ""
    body_html = markdown_html(page)
    chart_scripts = (
        f'<script src="{support_href(page, "vendor/d3/d3.min.js")}"></script><script src="{support_href(page, "vendor/plot/plot.umd.min.js")}"></script><script src="{support_href(page, "js/" + CHART_RUNTIME)}"></script>'
        if 'class="report-chart"' in body_html
        else ""
    )
    form_script = f'<script src="{support_href(page, "js/" + FORM_RUNTIME)}" defer></script>' if 'class="report-form ' in body_html else ""
    stylesheet = STYLESHEET.replace("__FONT_FACES__", font_faces(lambda name: support_href(page, f"fonts/{name}")))
    bootstrap = support_href(page, "vendor/bootstrap/css/bootstrap.min.css")
    fontawesome = support_href(page, "vendor/fontawesome/css/all.min.css")
    bootstrap_js = support_href(page, "vendor/bootstrap/js/bootstrap.bundle.min.js")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(page.title)}</title><link rel="stylesheet" href="{bootstrap}"><link rel="stylesheet" href="{fontawesome}"><style>{stylesheet}</style>{chart_scripts}{form_script}</head>
<body data-theme="light"><nav class="navbar navbar-expand-lg sticky-top"><div class="container report-shell"><a class="navbar-brand" href="{page_href(page, pages[0])}"><i class="fa-solid fa-file-lines me-1" aria-hidden="true"></i> Report</a><button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#report-nav" aria-controls="report-nav" aria-expanded="false" aria-label="Toggle report navigation"><i class="fa-solid fa-bars"></i></button><div class="collapse navbar-collapse" id="report-nav"><ul class="navbar-nav me-auto">{nav}</ul><button class="btn btn-outline-primary theme-toggle" type="button" aria-label="Toggle colour theme" aria-pressed="false"><i class="fa-solid fa-circle-half-stroke" aria-hidden="true"></i><span class="ms-1">Theme</span></button></div></div></nav>
<main class="container report-shell py-4">{breadcrumb(page, pages[0], pages)}<header class="report-page-head"><h1>{html.escape(page.title)}</h1>{description}</header>{body_html}</main>
<div class="modal fade source-code-modal" id="source-code-modal" tabindex="-1" aria-labelledby="source-code-modal-title" aria-hidden="true"><div class="modal-dialog"><div class="modal-content"><div class="modal-header"><h2 class="modal-title" id="source-code-modal-title">Source file</h2><a class="btn btn-sm btn-outline-primary ms-auto me-2 source-code-full-page" href="#" target="_blank" rel="noopener"><i class="fa-solid fa-up-right-from-square me-1" aria-hidden="true"></i>Open full page</a><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close source file"></button></div><div class="modal-body"><iframe class="source-code-frame" title="Source file" sandbox="allow-same-origin"></iframe></div></div></div></div>
<script src="{bootstrap_js}"></script><script>
const b=document.body,t=document.querySelector('.theme-toggle'),s=localStorage.getItem('local-report-theme')||'light';
b.dataset.theme=s;t.setAttribute('aria-pressed',s==='dark');
t.onclick=()=>{{b.dataset.theme=b.dataset.theme==='light'?'dark':'light';localStorage.setItem('local-report-theme',b.dataset.theme);t.setAttribute('aria-pressed',b.dataset.theme==='dark')}};
document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(e=>new bootstrap.Tooltip(e));
const m=document.getElementById('source-code-modal'),f=m.querySelector('.source-code-frame'),mt=m.querySelector('.modal-title'),fp=m.querySelector('.source-code-full-page');
m.addEventListener('show.bs.modal',e=>{{const a=e.relatedTarget;if(!a)return;const u=new URL(a.href,window.location.href);u.searchParams.set('line',a.dataset.sourceLine);const eu=new URL(u);eu.searchParams.set('embed','1');eu.searchParams.set('theme',b.dataset.theme);mt.textContent=`${{a.dataset.sourcePath}}:${{a.dataset.sourceLine}}`;f.title=`${{a.dataset.sourcePath}} at line ${{a.dataset.sourceLine}}`;fp.href=u.href;f.src=eu.href;}});
f.addEventListener('load',()=>{{if(!f.src)return;const id=new URL(f.src).hash.slice(1),line=f.contentDocument&&f.contentDocument.getElementById(id);if(line){{line.scrollIntoView({{block:'center'}});requestAnimationFrame(()=>line.scrollIntoView({{block:'center'}}));}}}});
m.addEventListener('hidden.bs.modal',()=>{{f.removeAttribute('src');}});
</script></body></html>"""


def code_document(path: Path, display_path: Path, *, embedded: bool = False, theme: str = "light", selected_line: int | None = None) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        lexer = guess_lexer_for_filename(path.name, text)
    except Exception:  # Pygments has no lexer for every filename.
        lexer = TextLexer()
    language = re.sub(r"[^a-z0-9_-]", "-", (lexer.aliases[0] if lexer.aliases else "text").lower())
    language_label = lexer.name
    highlighted = highlight(text, lexer, HtmlFormatter(nowrap=True)).splitlines()
    lines = "".join(
        f'<span class="code-line{" source-selected" if number == selected_line else ""}" id="L{number}"{" tabindex=\"-1\" autofocus" if number == selected_line else ""}>{line or " "}</span>'
        for number, line in enumerate(highlighted, start=1)
    )
    stylesheet = STYLESHEET.replace("__FONT_FACES__", font_faces(lambda name: "/_renderer/fonts/" + name))
    theme = "dark" if theme == "dark" else "light"
    navigation = "" if embedded else f'''<nav class="navbar navbar-expand-lg sticky-top"><div class="container report-shell"><a class="navbar-brand" href="/"><i class="fa-solid fa-file-lines me-1" aria-hidden="true"></i> Report</a><span class="navbar-text text-truncate"><i class="fa-solid fa-code me-1" aria-hidden="true"></i>{html.escape(display_path.as_posix())}</span><button class="btn btn-outline-primary ms-auto theme-toggle" type="button" aria-label="Toggle colour theme" aria-pressed="false"><i class="fa-solid fa-circle-half-stroke" aria-hidden="true"></i><span class="ms-1">Theme</span></button></div></nav>'''
    heading = "" if embedded else f'''<header class="report-page-head"><h1>{html.escape(display_path.name)} <span class="badge text-bg-secondary align-middle">{html.escape(language_label)}</span></h1><p class="description"><code>{html.escape(display_path.as_posix())}</code></p></header>'''
    main_class = "container-fluid p-0" if embedded else "container report-shell py-4"
    theme_script = "" if embedded else '''<script src="/_renderer/vendor/bootstrap/js/bootstrap.bundle.min.js"></script><script>const b=document.body,t=document.querySelector('.theme-toggle'),s=localStorage.getItem('local-report-theme')||'light';b.dataset.theme=s;t.setAttribute('aria-pressed',s==='dark');t.onclick=()=>{b.dataset.theme=b.dataset.theme==='light'?'dark':'light';localStorage.setItem('local-report-theme',b.dataset.theme);t.setAttribute('aria-pressed',b.dataset.theme==='dark')};history.scrollRestoration='manual';const jump=()=>document.getElementById(location.hash.slice(1))?.scrollIntoView({block:'center'});jump();requestAnimationFrame(jump);addEventListener('load',jump);</script>'''
    body_class = "embedded-code" if embedded else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(display_path.name)}</title><link rel="stylesheet" href="/_renderer/vendor/bootstrap/css/bootstrap.min.css"><link rel="stylesheet" href="/_renderer/vendor/fontawesome/css/all.min.css"><style>{stylesheet}
.code-file {{ counter-reset: line; overflow: auto; padding: .75rem 0; background: var(--code); border: 1px solid var(--line); border-left: .28rem solid var(--blue); border-radius: var(--radius); }} .code-line {{ display: block; min-height: 1.55em; padding-right: 1rem; white-space: pre; scroll-margin-top: 5rem; }} .code-line::before {{ counter-increment: line; content: counter(line); display: inline-block; width: 4.25em; margin-right: 1rem; padding-right: .75rem; color: color-mix(in srgb, var(--ink) 58%, transparent); text-align: right; border-right: 1px solid var(--line); user-select: none; }} .code-line:target, .code-line.source-selected {{ background: color-mix(in srgb, var(--blue) 18%, transparent); box-shadow: inset .18rem 0 var(--blue); }} .embedded-code .code-file {{ min-height: 100vh; margin: 0; border: 0; border-radius: 0; }} .embedded-code .code-line {{ scroll-margin-top: 1rem; }}</style></head><body class="{body_class}" data-theme="{theme}">{navigation}<main class="{main_class}">{heading}<pre class="code-file language-{language}"><code>{lines}</code></pre></main>{theme_script}</body></html>'''


def discover_pages(source_root: Path) -> list[Page]:
    paths = sorted(source_root.rglob("*.md"), key=lambda path: (path.relative_to(source_root) != Path("index.md"), path))
    pages = [parse_page(path, source_root) for path in paths]
    if not pages:
        raise ValueError(f"No Markdown files found in {source_root}")
    return pages


def copy_renderer_assets(destination: Path) -> None:
    support = destination / "_renderer"
    shutil.copytree(VENDOR_ROOT, support / "vendor", dirs_exist_ok=True)
    if VENDORED_FONT_ROOT.is_dir():
        shutil.copytree(VENDORED_FONT_ROOT, support / "fonts", dirs_exist_ok=True)
    shutil.copytree(JS_ROOT, support / "js", dirs_exist_ok=True)


def render(source: Path, output: Path) -> Path:
    source = source.resolve()
    if not source.is_dir():
        raise ValueError("The report source must be a directory containing Markdown files and optional assets.")
    if output.resolve() == source:
        raise ValueError("Output directory must not be the source directory.")
    pages = discover_pages(source)
    output.mkdir(parents=True, exist_ok=True)
    for page in pages:
        destination = output / page.relative.with_suffix(".html")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(document(page, pages), encoding="utf-8")
    for asset_dir in (path for path in source.rglob("assets") if path.is_dir()):
        shutil.copytree(asset_dir, output / asset_dir.relative_to(source), dirs_exist_ok=True)
    copy_renderer_assets(output)
    return output


def verify_report(source: Path, code_roots: tuple[Path, ...]) -> dict[str, int]:
    source = source.resolve()
    if not source.is_dir():
        raise ValueError(f"Report source is not a directory: {source}")
    roots = tuple(root.resolve() for root in code_roots) or (source,)
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"Code root is not a directory: {root}")
    missing_assets = [relative for relative in VENDOR_URLS if not (VENDOR_ROOT / relative).is_file()]
    missing_scripts = [name for name in (CHART_RUNTIME, FORM_RUNTIME) if not (JS_ROOT / name).is_file()]
    if missing_assets or missing_scripts:
        missing = ", ".join(missing_assets + missing_scripts)
        raise ValueError(f"Renderer assets are missing: {missing}")
    pages = discover_pages(source)
    if not any(page.relative == Path("index.md") for page in pages):
        raise ValueError("Report source requires index.md")
    source_references: set[tuple[int, str, int]] = set()
    forms = 0
    for page in pages:
        rendered = document(page, pages)
        forms += len(page_forms(page))
        for root_text, encoded_path, line_text in re.findall(r'href="/_code/(\d+)/([^"#]+)#L(\d+)"', rendered):
            source_references.add((int(root_text), unquote(encoded_path), int(line_text)))
    checked_files: set[tuple[int, str]] = set()
    for root_index, relative_text, line in source_references:
        if root_index >= len(roots):
            raise ValueError(f"Source snippet refers to unavailable code root {root_index}: {relative_text}")
        relative = Path(relative_text)
        candidate = (roots[root_index] / relative).resolve()
        try:
            candidate.relative_to(roots[root_index])
        except ValueError as error:
            raise ValueError(f"Source snippet escapes code root {root_index}: {relative_text}") from error
        if not candidate.is_file():
            raise ValueError(f"Source snippet file does not exist under code root {root_index}: {relative_text}")
        if candidate.stat().st_size > MAX_CODE_FILE_BYTES:
            raise ValueError(f"Source snippet file exceeds the 4 MiB display limit: {relative_text}")
        line_count = len(candidate.read_text(encoding="utf-8", errors="replace").splitlines())
        if line > max(line_count, 1):
            raise ValueError(f"Source snippet line {line} exceeds {relative_text}'s {line_count} lines")
        checked_files.add((root_index, relative_text))
    return {"pages": len(pages), "source_files": len(checked_files), "source_links": len(source_references), "forms": forms}


def runtime_state_path(port: int) -> Path:
    return RUNTIME_ROOT / f"server-{port}.json"


def process_start_token(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()[21]
    except (OSError, IndexError):
        return None


def read_runtime_state(port: int) -> dict[str, object]:
    path = runtime_state_path(port)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"No usable local-report server state for port {port}") from error
    pid = int(state.get("pid", 0))
    if pid < 1 or state.get("start_token") != process_start_token(pid):
        raise ValueError(f"Stale local-report server state for port {port}")
    return state


def write_runtime_state(port: int, state: dict[str, object]) -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=RUNTIME_ROOT, delete=False, encoding="utf-8") as temporary:
        json.dump(state, temporary, indent=2, sort_keys=True)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.chmod(0o600)
    temporary_path.replace(runtime_state_path(port))


class OnDemandHandler(SimpleHTTPRequestHandler):
    source_root: Path
    pages: list[Page]
    code_roots: tuple[Path, ...]

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'")
        super().end_headers()

    @staticmethod
    def safe_child(root: Path, relative: Path) -> Path | None:
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return None
        return candidate

    def do_HEAD(self) -> None:  # noqa: N802
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        """Accept a form response at ``/_respond`` and queue it for the agent.

        Only same-origin JSON requests are accepted: the Host header must name the loopback
        server, Origin must match it, and the JSON content type makes another site's request
        need a CORS preflight that this server never grants."""
        if urlsplit(self.path).path != "/_respond":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        port = self.server.server_address[1]
        host = self.headers.get("Host", "")
        if host not in {f"127.0.0.1:{port}", f"localhost:{port}"} or self.headers.get("Origin") != f"http://{host}":
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Responses are accepted only from this report's own pages."})
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Responses must be JSON."})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_json(HTTPStatus.LENGTH_REQUIRED, {"error": "Content-Length is required."})
            return
        if not 0 < length <= MAX_RESPONSE_BYTES:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "The response exceeds 64 KiB."})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or not isinstance(payload.get("page"), str) or not isinstance(payload.get("form"), str):
                raise ValueError("The response needs page and form names")
            relative = Path(payload["page"])
            markdown_path = self.safe_child(self.source_root, relative)
            if relative.is_absolute() or relative.suffix != ".md" or markdown_path is None or not markdown_path.is_file():
                raise ValueError(f"Unknown report page {payload['page']!r}")
            # Validate against the form as the page declares it now, so the agent never
            # receives fields or choices that it did not offer.
            page = parse_page(markdown_path, self.source_root)
            spec = page_forms(page).get(payload["form"])
            if spec is None:
                raise ValueError(f"Page {payload['page']!r} has no form {payload['form']!r}")
            action, values = validate_response(spec, payload.get("action"), payload.get("values"))
        except (ValueError, UnicodeDecodeError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        labels = {value: label for value, label, _ in spec.actions}
        record = {
            "received": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "page": page.relative.as_posix(),
            "form": spec.id,
            "title": spec.title,
            "action": action,
            "action_label": labels[action],
            "values": values,
        }
        sequence = append_response(self.source_root, record)
        self.send_json(HTTPStatus.CREATED, {"seq": sequence})

    def do_GET(self) -> None:  # noqa: N802
        request = urlsplit(self.path)
        request_path = Path(unquote(request.path).lstrip("/"))
        if ".." in request_path.parts:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if request_path.parts[:2] == ("_renderer", "vendor"):
            self.serve_file(self.safe_child(VENDOR_ROOT, Path(*request_path.parts[2:])))
            return
        if request_path.parts[:2] == ("_renderer", "js"):
            self.serve_file(self.safe_child(JS_ROOT, request_path.name))
            return
        if request_path.parts[:2] == ("_renderer", "fonts"):
            self.serve_file(self.safe_child(VENDORED_FONT_ROOT, request_path.name))
            return
        if len(request_path.parts) >= 3 and request_path.parts[0] == "_code":
            try:
                root = self.code_roots[int(request_path.parts[1])]
            except (IndexError, ValueError):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            source_file = self.safe_child(root, Path(*request_path.parts[2:]))
            if source_file is None:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if not source_file.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if source_file.stat().st_size > MAX_CODE_FILE_BYTES:
                self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Code file exceeds the 4 MiB display limit")
                return
            parameters = parse_qs(request.query)
            try:
                selected_line = int(parameters.get("line", [""])[0])
            except ValueError:
                selected_line = None
            if selected_line is not None and selected_line < 1:
                selected_line = None
            body = code_document(
                source_file,
                Path(*request_path.parts[2:]),
                embedded=parameters.get("embed") == ["1"],
                theme=parameters.get("theme", ["light"])[0],
                selected_line=selected_line,
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        relative = Path("index.md") if not request_path.parts or request_path.name == "index.html" else request_path.with_suffix(".md") if request_path.suffix == ".html" else request_path
        markdown_path = self.safe_child(self.source_root, relative)
        if markdown_path is None:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if markdown_path.suffix == ".md" and markdown_path.is_file():
            page = parse_page(markdown_path, self.source_root)
            body = document(page, self.pages).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.serve_file(self.safe_child(self.source_root, request_path))

    def serve_file(self, path: Path | None) -> None:
        if path is None or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def default_output(source: Path) -> Path:
    return source.parent / f"{source.name}-site"


def command_render(args: argparse.Namespace) -> int:
    print(render(args.source, args.output or default_output(args.source)))
    return 0


def command_update_assets(args: argparse.Namespace) -> int:
    manifest: dict[str, str] = {}
    for relative, url in VENDOR_URLS.items():
        destination = VENDOR_ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(url, timeout=30) as response:
            if not response.url.startswith("https://"):
                raise OSError(f"Refusing non-HTTPS asset redirect for {relative}")
            content = response.read(20 * 1024 * 1024 + 1)
            if len(content) > 20 * 1024 * 1024:
                raise OSError(f"Asset exceeds the 20 MiB size limit: {relative}")
            manifest[relative] = response.url
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
        print(f"Updated {relative}")
    (VENDOR_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    source = args.source.resolve()
    code_roots = tuple(path.resolve() for path in (args.code_root or [source]))
    result = verify_report(source, code_roots)
    print(f"Verified {result['pages']} page(s), {result['forms']} form(s), {result['source_files']} source file(s), and {result['source_links']} source link(s).")
    return 0


def command_serve(args: argparse.Namespace) -> int:
    source = args.source.resolve()
    code_roots = tuple(path.resolve() for path in (args.code_root or [source]))
    verification = verify_report(source, code_roots)
    handler = type("ReportHandler", (OnDemandHandler,), {"source_root": source, "pages": discover_pages(source), "code_roots": code_roots})
    if args.socket_fd is None:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    else:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler, bind_and_activate=False)
        server.socket.close()
        server.socket = socket.socket(fileno=args.socket_fd)
        server.server_address = server.socket.getsockname()
    host, port = server.server_address
    previous_generation = 0
    try:
        previous = json.loads(runtime_state_path(port).read_text(encoding="utf-8"))
        if int(previous.get("pid", 0)) == os.getpid():
            previous_generation = int(previous.get("generation", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    state = {
        "pid": os.getpid(),
        "start_token": process_start_token(os.getpid()),
        "generation": previous_generation + 1,
        "port": port,
        "source": str(source),
        "code_roots": [str(root) for root in code_roots],
        "verified": verification,
        "responses": str(responses_path(source)),
    }
    write_runtime_state(port, state)
    restart_requested = threading.Event()
    previous_sighup = signal.getsignal(signal.SIGHUP)
    signal.signal(signal.SIGHUP, lambda signum, frame: restart_requested.set())
    server.timeout = 0.25
    print(f"Serving {source} on demand at http://{host}:{port}/ (generation {state['generation']}; Ctrl-C to stop)", flush=True)
    if verification["forms"]:
        print(f"Form responses: local-report wait {shlex.quote(str(source))}", flush=True)
    try:
        while True:
            server.handle_request()
            if restart_requested.is_set():
                descriptor = server.socket.fileno()
                os.set_inheritable(descriptor, True)
                arguments = [sys.executable, "-m", "local_report_renderer.cli", "serve", str(source), "--port", str(port), "--socket-fd", str(descriptor)]
                for root in code_roots:
                    arguments.extend(("--code-root", str(root)))
                sys.stdout.flush()
                sys.stderr.flush()
                os.execv(sys.executable, arguments)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        signal.signal(signal.SIGHUP, previous_sighup)
        server.server_close()
        try:
            current = json.loads(runtime_state_path(port).read_text(encoding="utf-8"))
            if int(current.get("pid", 0)) == os.getpid():
                runtime_state_path(port).unlink(missing_ok=True)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return 0


def command_restart(args: argparse.Namespace) -> int:
    state = read_runtime_state(args.port)
    source = Path(str(state["source"]))
    code_roots = tuple(Path(str(root)) for root in state.get("code_roots", []))
    verification = verify_report(source, code_roots)
    pid = int(state["pid"])
    generation = int(state.get("generation", 0))
    os.kill(pid, signal.SIGHUP)
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            refreshed = read_runtime_state(args.port)
            if int(refreshed.get("pid", 0)) == pid and int(refreshed.get("generation", 0)) > generation:
                print(f"Verified {verification['pages']} page(s) and atomically restarted port {args.port} at generation {refreshed['generation']}.")
                return 0
        except ValueError:
            pass
        time.sleep(0.05)
    raise ValueError(f"Server on port {args.port} did not confirm its restart within {args.timeout:g} seconds")


def cursor_path(source: Path) -> Path:
    return responses_path(source).with_suffix(".cursor")


def command_wait(args: argparse.Namespace) -> int:
    """Print the responses the agent has not yet received, waiting for one if there are none.

    Each response is one JSON object per line. They are then marked delivered, so the next
    ``wait`` returns only later responses. Exits with status 3 if ``--timeout`` passes first."""
    source = args.source.resolve()
    if not source.is_dir():
        raise ValueError(f"Report source is not a directory: {source}")
    cursor = cursor_path(source)
    try:
        delivered = int(cursor.read_text(encoding="utf-8").strip() or 0)
    except FileNotFoundError:
        delivered = 0
    deadline = time.monotonic() + args.timeout if args.timeout > 0 else None
    while True:
        pending = [record for record in read_responses(source) if int(record["seq"]) > delivered]
        if pending:
            for record in pending:
                print(json.dumps(record, ensure_ascii=False))
            RESPONSES_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
            cursor.write_text(f"{pending[-1]['seq']}\n", encoding="utf-8")
            return 0
        if deadline is not None and time.monotonic() >= deadline:
            print(f"No new response within {args.timeout:g} seconds.", file=sys.stderr)
            return 3
        time.sleep(0.5)


def command_responses(args: argparse.Namespace) -> int:
    """Print every stored response of a report, one JSON object per line, without marking any delivered."""
    for record in read_responses(args.source.resolve()):
        print(json.dumps(record, ensure_ascii=False))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Render Markdown report sites and preview them on loopback.")
    commands = result.add_subparsers(dest="command", required=True)
    render_command = commands.add_parser("render", help="Render a Markdown report directory to HTML.")
    render_command.add_argument("source", type=Path, help="Report source directory.")
    render_command.add_argument("--output", type=Path, help="Rendered site directory.")
    render_command.set_defaults(function=command_render)
    serve_command = commands.add_parser("serve", help="Serve Markdown pages and assets on demand at 127.0.0.1.")
    serve_command.add_argument("source", type=Path, help="Report source directory.")
    serve_command.add_argument("--port", type=int, default=8000, help="Loopback TCP port (default: 8000).")
    serve_command.add_argument("--code-root", type=Path, action="append", help="Allow code viewing from this directory; repeat for more roots (default: report source).")
    serve_command.add_argument("--socket-fd", type=int, help=argparse.SUPPRESS)
    serve_command.set_defaults(function=command_serve)
    verify_command = commands.add_parser("verify", help="Verify report rendering, local assets, and source-file links.")
    verify_command.add_argument("source", type=Path, help="Report source directory.")
    verify_command.add_argument("--code-root", type=Path, action="append", help="Code root used by source-backed snippets; repeat in serving order.")
    verify_command.set_defaults(function=command_verify)
    restart_command = commands.add_parser("restart", help="Verify and atomically replace a running server while retaining its socket.")
    restart_command.add_argument("--port", type=int, default=8000, help="Running loopback server port (default: 8000).")
    restart_command.add_argument("--timeout", type=float, default=10.0, help="Seconds to wait for restart confirmation (default: 10).")
    restart_command.set_defaults(function=command_restart)
    wait_command = commands.add_parser("wait", help="Wait for form responses the agent has not yet received and print them as JSON lines.")
    wait_command.add_argument("source", type=Path, help="Report source directory.")
    wait_command.add_argument("--timeout", type=float, default=0, help="Give up after this many seconds with exit status 3 (default: wait indefinitely).")
    wait_command.set_defaults(function=command_wait)
    responses_command = commands.add_parser("responses", help="Print every stored form response of a report as JSON lines.")
    responses_command.add_argument("source", type=Path, help="Report source directory.")
    responses_command.set_defaults(function=command_responses)
    update_command = commands.add_parser("update-assets", help="Download current Bootstrap and Font Awesome assets.")
    update_command.set_defaults(function=command_update_assets)
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        raise SystemExit(args.function(args))
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
