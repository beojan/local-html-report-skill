// Draws the report's ```plot and ```d3 chart fences with the report's own styling.
// The renderer emits one <figure class="report-chart"> per fence and registers the
// fence body with reportCharts.add(); charts are drawn once the page has loaded.
(function () {
  "use strict";
  const registered = [];
  const drawn = [];

  function token(style, name, fallback) {
    return style.getPropertyValue(name).trim() || fallback;
  }

  // Sizes written in a fence (height, margins) assume this body font size in pixels. They are
  // scaled by the page's actual font size so that the chart keeps its proportions.
  const REFERENCE_FONT_PX = 13;
  const MARGINS = ["margin", "marginTop", "marginRight", "marginBottom", "marginLeft"];

  // Chart colours come from the --chart-* CSS tokens so they match the report. The font family
  // and size are those of the body text, and the width is the full width of the content column.
  function theme(figure) {
    const style = getComputedStyle(figure);
    const palette = [];
    for (let i = 1; i <= 7; i += 1) {
      palette.push(token(style, "--chart-" + i, "#005f87"));
    }
    const canvas = figure.querySelector(".report-chart-canvas");
    const body = getComputedStyle(canvas);
    const fontSize = parseFloat(body.fontSize) || REFERENCE_FONT_PX;
    const scale = fontSize / REFERENCE_FONT_PX;
    return {
      panel: token(style, "--chart-panel", "#ffffff"),
      ink: token(style, "--chart-ink", "#444444"),
      muted: token(style, "--chart-muted", "#666666"),
      grid: token(style, "--chart-grid", "#d0d0d0"),
      outline: token(style, "--chart-outline", "#222222"),
      font: body.fontFamily,
      fontSize: fontSize,
      scale: scale,
      palette: palette,
      width: Math.max(Math.round(canvas.clientWidth) || 720, 320),
      height: Math.round((Number(figure.dataset.chartHeight) || 320) * scale),
    };
  }

  function readData(figure) {
    const raw = JSON.parse(figure.querySelector("script.report-chart-data").textContent);
    if (raw === null) return undefined;
    if (raw.format !== "csv") return raw.rows;
    // d3.csvParse builds its row converter with new Function, which the server's
    // Content Security Policy blocks, so parse rows and build the objects here.
    const rows = d3.csvParseRows(raw.text);
    const header = rows.shift();
    return rows.map(function (row) {
      return d3.autoType(Object.fromEntries(header.map(function (name, i) { return [name, row[i]]; })));
    });
  }

  // Applies report defaults to Plot options. Anything the fence sets wins.
  function plotOptions(options, t) {
    const colour = options.color || {};
    const customColour = ["scheme", "range", "interpolate", "type"].some(function (key) { return key in colour; });
    // Leave the SVG background alone so the renderer's white plot panel shows.
    // Default margins leave room for an axis title above the plot and for the x-axis labels.
    const merged = Object.assign({ width: t.width, height: t.height, marginTop: 28, marginBottom: 45 }, options);
    MARGINS.forEach(function (key) {
      if (typeof merged[key] === "number") merged[key] = Math.round(merged[key] * t.scale);
    });
    return Object.assign(merged, {
      style: Object.assign({
        color: t.ink,
        fontFamily: t.font,
        fontSize: t.fontSize + "px",
        fontVariantNumeric: "tabular-nums",
        overflow: "visible",
      }, options.style),
      color: customColour ? colour : Object.assign({ range: t.palette }, colour),
    });
  }

  // Filled marks and legend swatches get a thin outline in the theme's outline colour, so adjacent
  // fills stay distinguishable and each shape has a boundary that contrasts with the panel.
  // A mark that sets its own stroke keeps it. Lines are drawn in palette colours that already
  // meet 3:1 against the panel.
  function outlineFilled(node, t) {
    const marks = "g[aria-label=bar], g[aria-label=rect], g[aria-label=area], g[aria-label=dot], g[aria-label=cell]";
    node.querySelectorAll(marks).forEach(function (group) {
      group.querySelectorAll("rect, path, circle, ellipse").forEach(function (shape) {
        const fill = shape.getAttribute("fill") || group.getAttribute("fill");
        const stroke = shape.getAttribute("stroke") || group.getAttribute("stroke");
        if (!fill || fill === "none" || (stroke && stroke !== "none")) return;
        shape.setAttribute("stroke", t.outline);
        shape.setAttribute("stroke-width", "0.75");
      });
    });
    node.querySelectorAll("[class*=-swatch] svg rect, [class*=-swatch] svg circle").forEach(function (shape) {
      shape.setAttribute("stroke", t.outline);
      shape.setAttribute("stroke-width", "0.75");
    });
  }

  function draw(figure, body) {
    const canvas = figure.querySelector(".report-chart-canvas");
    const t = theme(figure);
    try {
      const result = body(window.Plot, window.d3, readData(figure), t);
      const node = figure.dataset.chartKind === "plot" ? window.Plot.plot(plotOptions(result, t)) : result;
      if (figure.dataset.chartKind === "plot") outlineFilled(node, t);
      canvas.replaceChildren(node);
    } catch (error) {
      const message = document.createElement("p");
      message.className = "report-chart-error";
      message.textContent = "Chart failed to draw: " + error.message;
      canvas.replaceChildren(message);
      console.error(figure.id, error);
    }
  }

  window.reportCharts = {
    add: function (id, body) { registered.push([id, body]); },
  };

  // Redraws a chart when the width of its column changes, so that it keeps filling the body width.
  function follow(figure, body) {
    const canvas = figure.querySelector(".report-chart-canvas");
    let drawn = Math.round(canvas.clientWidth);
    let pending = false;
    new ResizeObserver(function () {
      const width = Math.round(canvas.clientWidth);
      if (pending || Math.abs(width - drawn) < 2) return;
      pending = true;
      requestAnimationFrame(function () {
        pending = false;
        drawn = Math.round(canvas.clientWidth);
        draw(figure, body);
      });
    }).observe(canvas);
  }

  document.addEventListener("DOMContentLoaded", function () {
    registered.forEach(function (entry) {
      const figure = document.getElementById(entry[0]);
      if (!figure) return;
      draw(figure, entry[1]);
      follow(figure, entry[1]);
      drawn.push([figure, entry[1]]);
    });
    // Plot needs resolved colours, so every chart is drawn again when the theme is toggled.
    new MutationObserver(function () {
      drawn.forEach(function (pair) { draw(pair[0], pair[1]); });
    }).observe(document.body, { attributes: true, attributeFilter: ["data-theme"] });
  });
})();
