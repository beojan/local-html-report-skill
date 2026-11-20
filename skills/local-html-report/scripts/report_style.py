"""Matplotlib setup for static figures embedded in local HTML reports (local-report).

Figures use the ATLAS Matplotlib style (`atlas-mpl-style`) with its own fonts and colours. The plotting
script declares its dependencies in a PEP 723 header, so `uv run plot.py` is all that is needed:

    # /// script
    # requires-python = ">=3.11"
    # dependencies = ["matplotlib", "atlas-mpl-style", "polars"]
    # ///

Text uses the ATLAS style's sans-serif font (Tex Gyre Heros, Helvetica, or a similar fallback)
and outlines it in the SVG, so the figure looks the same on any machine. The page's system sans
font may differ in face but is set to the same size.

The page layout (body text size, column width) is read from `renderer/assets/layout.json`, the same
file the renderer builds its CSS from. A figure exactly one column wide with body-size text shows
its labels at the body text size and lines up with interactive charts. `save_report_figure` removes
the fixed width and height from an SVG and keeps its `viewBox`, so the figure fills the column at
any root font size or page zoom, with its text scaling along with the body text. In a window
narrower than the column the renderer keeps the figure at full column width inside a horizontally
scrollable box, so the text never drops below body size.

Use it in place of a bare `use_atlas_style` call, after the header above:

    import sys
    sys.path.insert(0, "<skill-dir>/scripts")
    from report_style import save_report_figure, use_report_style

    use_report_style()
    ...
    save_report_figure(fig, "assets/figure.svg")

Do not set `fontsize=` on individual text, legends, or ticks. Leave them to inherit the body-size
default so that every label matches the body text.
"""

import json
from pathlib import Path

# The page layout comes from the renderer, so the figure size cannot drift from the CSS.
_LAYOUT = json.loads((Path(__file__).resolve().parents[1] / "renderer" / "assets" / "layout.json").read_text(encoding="utf-8"))
BODY_PT = _LAYOUT["body_rem"] * _LAYOUT["root_px"] * 0.75  # rem to px to pt
COLUMN_PX = (_LAYOUT["column_max_rem"] - _LAYOUT["gutter_rem"]) * _LAYOUT["root_px"]  # content column
WIDTH_IN = COLUMN_PX / 96  # an SVG renders at 96 px per inch, so this fills the column


def use_report_style(height_in: float = 6.0) -> None:
    """Activate the base style, then set the report text size and width.

    The base style is ATLAS. `height_in` sets the default figure height
    in inches. Fonts are left to the style, so nothing needs to be installed.
    """
    import matplotlib.pyplot as plt
    import matplotlib.style as mpl_style

    # Keep compatibility with older atlas_mpl_style builds when Matplotlib lacks style.core.
    if not hasattr(mpl_style, "core"):
        mpl_style.core = mpl_style
    import atlas_mpl_style as ampl

    ampl.use_atlas_style(usetex=False)
    plt.rcParams.update(
        {
            "font.size": BODY_PT,
            "axes.labelsize": BODY_PT,
            "axes.titlesize": BODY_PT,
            "xtick.labelsize": BODY_PT,
            "ytick.labelsize": BODY_PT,
            "legend.fontsize": BODY_PT,
            "legend.title_fontsize": BODY_PT,
            "figure.titlesize": BODY_PT,
            "figure.figsize": (WIDTH_IN, height_in),
            # Convert text to outlines so the SVG renders identically inside an <img> element.
            "svg.fonttype": "path",
        }
    )


def save_report_figure(fig, path, **kwargs) -> None:
    """Save `fig` so that the output file is exactly as wide as the report's content column.

    A plain `bbox_inches="tight"` crops every figure to a different width, preventing figures
    from lining up with one another or with interactive charts. This helper crops to the tight
    content bounds and pads the left and right sides equally out to `WIDTH_IN`. Raises
    `ValueError` if the content exceeds the column width, indicating that the layout needs
    shorter labels or fewer horizontal elements rather than downscaling.
    """
    from matplotlib.transforms import Bbox

    fig.canvas.draw()
    tight = fig.get_tightbbox(fig.canvas.get_renderer()).padded(0.04)
    pad = WIDTH_IN - tight.width
    if pad < -0.01:
        raise ValueError(f"Figure content is {tight.width:.2f} in wide, wider than the {WIDTH_IN:.2f} in column")
    box = Bbox.from_extents(tight.x0 - pad / 2, tight.y0, tight.x1 + pad / 2, tight.y1)
    fig.savefig(path, bbox_inches=box, **kwargs)
    if str(path).endswith(".svg"):
        _fill_column(path)


def _fill_column(path) -> None:
    """Remove fixed `width` and `height` attributes from an SVG while keeping its `viewBox`.

    Because the report's column is sized in rem, it exceeds 1192 px when the browser's root font
    size is larger than 16 px. An `<img>` whose SVG declares only a `viewBox` fills the column at
    any root font size, keeping its labels proportional to the rem-sized body text.
    """
    import re
    from pathlib import Path

    file = Path(path)
    text = file.read_text(encoding="utf-8")
    start = text.index("<svg")
    end = text.index(">", start)
    tag = text[start : end + 1]
    if "viewBox" not in tag:
        raise ValueError(f"{path} has no viewBox, so it cannot scale to the column")
    tag = re.sub(r'\s(?:width|height)="[^"]*"', "", tag)
    file.write_text(text[:start] + tag + text[end + 1 :], encoding="utf-8")
