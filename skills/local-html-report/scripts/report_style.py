"""Matplotlib setup for static figures embedded in local HTML reports (local-report).

Figures use the ATLAS Matplotlib style (the public `atlas-mpl-style` package) with its `print`
theme. Run a plotting script with both packages, for example:

    uv run --with matplotlib --with atlas-mpl-style python plot.py

If `atlas_mpl_style` is not installed, a warning is printed and Matplotlib's default style is
used with the same size and width settings. Text uses the style's own sans-serif font, or
Matplotlib's default, so no font has to be installed. The page's system sans font may differ in
face but is set to the same size.

The report's body text is the system sans font at 1.08 rem (17.28 px, or 12.96 pt). An SVG embedded
in the report displays at its natural size up to the width of the content column (about 1192 px),
so a figure that matches the column width with 13 pt text shows its labels at the body text size
and aligns with interactive charts that fill the column. `save_report_figure` also removes the
fixed width and height attributes from an SVG while keeping its `viewBox`, because the column is
sized in rem and grows wider than 1192 px when the browser's root font size exceeds 16 px. The
SVG then fills the column at any root font size while its text scales with the body text.

Use it in place of a bare `use_atlas_style` call:

    import sys
    sys.path.insert(0, "<skill-dir>/scripts")
    from report_style import save_report_figure, use_report_style

    use_report_style()
    ...
    save_report_figure(fig, "assets/figure.svg")

Do not set `fontsize=` on individual text, legends, or ticks. Leave them to inherit the 13 pt
default so that every label matches the body text.
"""

BODY_PT = 13.0  # 1.08 rem is 12.96 pt
COLUMN_PX = 1192  # content column of the report: 76 rem minus the container padding
WIDTH_IN = COLUMN_PX / 96  # 12.42 in: an SVG renders at 96 px per inch, so this fills the column


def use_report_style(height_in: float = 6.0) -> None:
    """Activate the base style, then set the report text size and width.

    The base style is ATLAS with the `print` theme, falling back with a warning to Matplotlib's
    default when `atlas_mpl_style` is missing. `height_in` sets the default figure height in inches.
    Fonts are left to the style, so nothing needs to be installed.
    """
    import matplotlib.pyplot as plt
    import matplotlib.style as mpl_style

    try:
        # Keep compatibility with older atlas_mpl_style builds when Matplotlib lacks style.core.
        if not hasattr(mpl_style, "core"):
            mpl_style.core = mpl_style
        import atlas_mpl_style as ampl

        ampl.use_atlas_style(usetex=False)
        plt.style.use("print")
    except ImportError:
        import warnings

        warnings.warn("atlas_mpl_style is not installed; using Matplotlib's default style. "
                      "Add `--with atlas-mpl-style` to the uv command.", stacklevel=2)
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
