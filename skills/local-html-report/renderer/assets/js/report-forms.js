// Sends the answers in a report's ```form fences back to the agent that wrote the report.
// A form's fields can also sit in ```form-fields blocks elsewhere on the page. Their
// controls name the form with the HTML form attribute, and a submission collects them
// together with the form's own fields in page order.
// On the preview server a submission is POSTed to /_respond, which queues it for
// `local-report wait`. A static snapshot opened over file:// has no server, so the
// response is copied to the clipboard for the reader to paste into the chat instead.
(function () {
  "use strict";

  // The form's card and its form-fields blocks, in page order.
  function parts(form) {
    const id = form.dataset.formId;
    return Array.from(document.querySelectorAll('form.report-form[data-form-id="' + id + '"], .report-form-part[data-form-part="' + id + '"]'));
  }

  // The field wrappers of a form, wherever they are on the page, in page order.
  function wrappers(form, selector) {
    return parts(form).flatMap(function (part) { return Array.from(part.querySelectorAll(selector)); });
  }

  // Reads each field by the kind the renderer recorded on its wrapper.
  function collect(form) {
    const values = {};
    wrappers(form, "[data-field-name]").forEach(function (wrapper) {
      const name = wrapper.dataset.fieldName;
      const inputs = Array.from(wrapper.querySelectorAll("input, select, textarea"));
      switch (wrapper.dataset.fieldKind) {
        case "list":
          values[name] = inputs.filter(function (input) { return input.checked; }).map(function (input) { return input.value; });
          break;
        case "choice": {
          const chosen = inputs.find(function (input) { return input.checked; });
          values[name] = chosen ? chosen.value : null;
          break;
        }
        case "boolean":
          values[name] = inputs[0].checked;
          break;
        case "number":
          values[name] = inputs[0].value === "" ? null : Number(inputs[0].value);
          break;
        default:
          values[name] = inputs[0].value;
      }
    });
    return values;
  }

  // A required checkbox group needs at least one ticked box, which HTML validation cannot express.
  function checkGroups(form) {
    wrappers(form, '[data-field-kind="list"][data-required="true"]').forEach(function (wrapper) {
      const boxes = Array.from(wrapper.querySelectorAll("input[type=checkbox]"));
      const message = boxes.some(function (box) { return box.checked; }) ? "" : "Choose at least one option.";
      boxes.forEach(function (box) { box.setCustomValidity(message); });
    });
  }

  function status(form, kind, text, detail) {
    const box = form.querySelector(".report-form-status");
    box.replaceChildren();
    const alert = document.createElement("div");
    alert.className = "alert alert-" + kind + " mb-0";
    const message = document.createElement("div");
    message.textContent = text;
    alert.appendChild(message);
    if (detail) {
      const area = document.createElement("textarea");
      area.className = "form-control mt-2";
      area.readOnly = true;
      area.rows = Math.min(12, detail.split("\n").length);
      area.value = detail;
      area.setAttribute("aria-label", "Response to paste into the chat");
      alert.appendChild(area);
      area.addEventListener("focus", function () { area.select(); });
    }
    box.appendChild(alert);
  }

  function offline(form, payload, reason) {
    const text = JSON.stringify({ report_response: payload }, null, 2);
    const done = function (copied) {
      status(form, "warning", reason + (copied
        ? " The response has been copied to the clipboard. Paste it into the chat with the agent."
        : " Copy the response below and paste it into the chat with the agent."), text);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); });
    } else {
      done(false);
    }
  }

  function submit(event) {
    const form = event.currentTarget;
    event.preventDefault();
    checkGroups(form);
    // checkValidity covers the controls in form-fields blocks too, through their form attribute.
    const controls = Array.from(form.elements);
    if (!form.checkValidity()) {
      const invalid = controls.filter(function (control) { return control.willValidate && !control.checkValidity(); });
      controls.forEach(function (control) {
        if (invalid.indexOf(control) >= 0) control.setAttribute("aria-invalid", "true");
        else control.removeAttribute("aria-invalid");
      });
      parts(form).forEach(function (part) { part.classList.add("was-validated"); });
      status(form, "danger", "Some answers are missing. Fill in the marked fields and send again.");
      if (invalid.length) invalid[0].focus();
      return;
    }
    controls.forEach(function (control) { control.removeAttribute("aria-invalid"); });
    parts(form).forEach(function (part) { part.classList.remove("was-validated"); });
    const button = event.submitter || form.querySelector("button[type=submit]");
    const payload = {
      page: form.dataset.reportPage,
      form: form.dataset.formId,
      action: button ? button.value : "submit",
      values: collect(form),
    };
    if (location.protocol === "file:") {
      offline(form, payload, "This copy of the report has no server, so it cannot send the response.");
      return;
    }
    const buttons = form.querySelectorAll("button[type=submit]");
    buttons.forEach(function (b) { b.disabled = true; });
    fetch("/_respond", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (body) {
          if (!response.ok) throw new Error(body.error || ("The server answered " + response.status + "."));
          const label = button ? button.textContent.trim() : "Response";
          status(form, "success", "“" + label + "” was sent to the agent as response " + body.seq + ". It will pick it up the next time it checks. You can change your answers and send again.");
        });
      })
      .catch(function (error) {
        offline(form, payload, "The response could not be sent: " + error.message);
      })
      .finally(function () {
        buttons.forEach(function (b) { b.disabled = false; });
      });
  }

  function showRange(input) {
    const output = input.closest(".report-form-field").querySelector(".report-form-range-value");
    if (output) output.textContent = input.value;
  }

  function init() {
    document.querySelectorAll("form.report-form").forEach(function (form) {
      form.addEventListener("submit", submit);
      parts(form).forEach(function (part) {
        part.addEventListener("change", function () { if (form.classList.contains("was-validated")) checkGroups(form); });
        part.querySelectorAll("input[type=range]").forEach(function (input) {
          showRange(input);
          input.addEventListener("input", function () { showRange(input); });
        });
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
