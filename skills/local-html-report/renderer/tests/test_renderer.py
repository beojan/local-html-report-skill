from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
import json
import threading
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from local_report_renderer.cli import STYLESHEET, OnDemandHandler, Page, code_document, command_restart, command_wait, document, markdown_html, page_forms, read_responses, render_priority_badge, validate_response, verify_report


class SourceSnippetTests(TestCase):
    def test_source_snippet_uses_source_lines_and_links(self) -> None:
        excerpt = "\n".join(f"line_{number}();" for number in range(11))
        page = Page(
            source=Path("finding.md"),
            relative=Path("finding.md"),
            title="Finding",
            description=None,
            body=f'''```cpp {{source="src/core/filter.cpp" line=68 root=1}}
{excerpt}
```
''',
        )

        rendered = markdown_html(page)

        self.assertIn('/_code/1/src/core/filter.cpp#L68', rendered)
        self.assertIn('src/core/filter.cpp:68', rendered)
        self.assertEqual(
            [str(line) for line in range(68, 79)],
            re.findall(r'class="code-line-link source-view-link"[^>]*>(\d+)</a>', rendered),
        )
        self.assertNotIn('<span class="normal">', rendered)
        self.assertIn('data-bs-target="#source-code-modal"', rendered)
        self.assertIn('data-source-line="68"', rendered)

    def test_document_provides_sandboxed_source_modal(self) -> None:
        page = Page(Path("finding.md"), Path("finding.md"), "Finding", None, "Report body.\n")

        rendered = document(page, [page])

        self.assertIn('id="source-code-modal"', rendered)
        self.assertIn('class="source-code-frame"', rendered)
        self.assertIn('sandbox="allow-same-origin"', rendered)
        self.assertIn("eu.searchParams.set('embed','1')", rendered)
        self.assertIn("line.scrollIntoView({block:'center'})", rendered)

    def test_embedded_code_view_omits_document_chrome(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.cpp"
            path.write_text("int value = 1;\n", encoding="utf-8")

            rendered = code_document(path, Path("sample.cpp"), embedded=True, theme="dark", selected_line=1)

        self.assertIn('class="embedded-code" data-theme="dark"', rendered)
        self.assertIn('class="code-line source-selected" id="L1" tabindex="-1" autofocus', rendered)
        self.assertNotIn('<nav class="navbar', rendered)
        self.assertNotIn('class="report-page-head"', rendered)

    def test_full_page_code_view_scrolls_to_fragment_after_load(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.cpp"
            path.write_text("int value = 1;\n", encoding="utf-8")

            rendered = code_document(path, Path("sample.cpp"))

        self.assertIn("scrollIntoView({block:'center'})", rendered)

    def test_generated_snippet_keeps_one_based_unlinked_lines(self) -> None:
        page = Page(Path("example.md"), Path("example.md"), "Example", None, "```python\nprint('generated')\n```\n")

        rendered = markdown_html(page)

        self.assertNotIn("code-source", rendered)
        self.assertIn('<span class="normal">1</span>', rendered)

    def test_source_metadata_requires_a_line(self) -> None:
        page = Page(Path("bad.md"), Path("bad.md"), "Bad", None, '```cpp {source="file.cpp"}\nvalue();\n```\n')

        with self.assertRaisesRegex(ValueError, "requires both source= and line="):
            markdown_html(page)

    def gutter(self, rendered: str) -> list[str]:
        return re.findall(r'<span class="normal">(\d+)</span>', rendered)

    def test_numbers_attribute_sets_gutter_of_plain_fence(self) -> None:
        page = Page(Path("a.md"), Path("a.md"), "A", None, '```text {numbers="2217,2248,2420-2421"}\na\nb\nc\nd\n```\n')
        self.assertEqual(["2217", "2248", "2420", "2421"], self.gutter(markdown_html(page)))

    def test_line_alone_numbers_a_plain_fence_from_that_line(self) -> None:
        page = Page(Path("a.md"), Path("a.md"), "A", None, "```text {line=40}\na\nb\n```\n")
        self.assertEqual(["40", "41"], self.gutter(markdown_html(page)))

    def test_numbers_count_must_match_lines(self) -> None:
        page = Page(Path("a.md"), Path("a.md"), "A", None, '```text {numbers="1,2,3"}\na\nb\n```\n')
        with self.assertRaisesRegex(ValueError, "lists 3 numbers= but has 2 lines"):
            markdown_html(page)

    def test_numbers_cannot_combine_with_source(self) -> None:
        page = Page(Path("a.md"), Path("a.md"), "A", None, '```cpp {source="a.cpp" line=1 numbers="1"}\nint x;\n```\n')
        with self.assertRaisesRegex(ValueError, "cannot combine numbers="):
            markdown_html(page)


class ReportVerificationTests(TestCase):
    def test_demo_report_and_source_link_verify(self) -> None:
        source = Path(__file__).parents[1] / "examples" / "demo-report"

        result = verify_report(source, (source,))

        self.assertEqual({"pages": 2, "source_files": 1, "source_links": 1, "forms": 0}, result)

    def test_missing_source_link_fails_verification(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "index.md").write_text(
                '```cpp {source="missing.cpp" line=12}\nvalue();\n```\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "does not exist"):
                verify_report(source, (source,))

    def test_failed_restart_verification_does_not_signal_server(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "index.md").write_text(
                '```cpp {source="missing.cpp" line=12}\nvalue();\n```\n',
                encoding="utf-8",
            )
            state = {
                "pid": 43210,
                "generation": 7,
                "source": str(source),
                "code_roots": [str(source)],
            }

            with patch("local_report_renderer.cli.read_runtime_state", return_value=state), patch(
                "local_report_renderer.cli.os.kill"
            ) as kill:
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    command_restart(Namespace(port=8000, timeout=0.1))

            kill.assert_not_called()


class ChartFenceTests(TestCase):
    PLOT = '```plot {data="assets/times.csv" title="Times" caption="Request times."}\nreturn {marks: [Plot.dot(data, {x: "cfg", y: "t"})]};\n```\n'

    def make_report(self, directory: str, body: str, csv_text: str = "cfg,t\nA,1\nB,2\n") -> Page:
        source = Path(directory)
        (source / "assets").mkdir()
        (source / "assets" / "times.csv").write_text(csv_text, encoding="utf-8")
        (source / "index.md").write_text(body, encoding="utf-8")
        return Page(source / "index.md", Path("index.md"), "Report", None, body)

    def test_plot_fence_becomes_figure_with_inline_data_and_table(self) -> None:
        with TemporaryDirectory() as directory:
            page = self.make_report(directory, self.PLOT)
            rendered = markdown_html(page)
            self.assertIn('<figure class="report-chart" id="report-chart-1" data-chart-kind="plot"', rendered)
            self.assertIn('reportCharts.add("report-chart-1"', rendered)
            self.assertIn('"format": "csv"', rendered)
            self.assertIn("<td>B</td>", rendered)
            self.assertIn("Request times.", rendered)

    def test_libraries_load_only_on_chart_pages(self) -> None:
        with TemporaryDirectory() as directory:
            chart_page = self.make_report(directory, self.PLOT)
            plain_page = Page(Path("plain.md"), Path("plain.md"), "Plain", None, "No charts.\n")
            self.assertIn("vendor/d3/d3.min.js", document(chart_page, [chart_page]))
            self.assertIn("js/report-charts.js", document(chart_page, [chart_page]))
            self.assertNotIn("d3.min.js", document(plain_page, [plain_page]))

    def test_data_is_escaped_inside_script(self) -> None:
        with TemporaryDirectory() as directory:
            page = self.make_report(directory, self.PLOT, "cfg,t\n</script><b>,1\n")
            rendered = markdown_html(page)
            self.assertNotIn("</script><b>", rendered)
            self.assertIn("<\\/script>", rendered)

    def test_chart_fence_mixes_with_source_fence(self) -> None:
        with TemporaryDirectory() as directory:
            body = self.PLOT + '\n```cpp {source="a.cpp" line=3}\nint x;\n```\n'
            rendered = markdown_html(self.make_report(directory, body))
            self.assertEqual(1, rendered.count('class="report-chart"'))
            self.assertIn("a.cpp:3", rendered)

    def test_several_tip_marks_in_one_plot_warn(self) -> None:
        body = '```plot\nreturn {marks: [Plot.dot(data, {x: "cfg", y: "t", tip: true}), Plot.dot(data, {x: "cfg", y: "t", tip: true})]};\n```\n'
        with TemporaryDirectory() as directory, patch("sys.stderr") as stderr:
            markdown_html(self.make_report(directory, body))
            written = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertIn("sets tip: true on several marks", written)

    def test_one_tip_mark_does_not_warn(self) -> None:
        body = '```plot\nreturn {marks: [Plot.dot(data, {x: "cfg", y: "t", tip: true})]};\n```\n'
        with TemporaryDirectory() as directory, patch("sys.stderr") as stderr:
            markdown_html(self.make_report(directory, body))
            written = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertNotIn("tip: true", written)

    def test_bad_chart_input_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            for body, message in (
                ('```plot {data="../x.csv"}\nreturn {};\n```\n', "without '..'"),
                ('```plot {data="assets/missing.csv"}\nreturn {};\n```\n', "does not exist"),
                ("```plot\nreturn {}; // </script>\n```\n", "must not contain"),
                ("```plot\nreturn {};\n", "Unclosed"),
                ("```plot\n\n```\n", "is empty"),
                ("- item\n\n  ```plot\n  return {};\n  ```\n", None),
            ):
                with self.subTest(body=body):
                    with TemporaryDirectory() as sub:
                        page = self.make_report(sub, body)
                        if message is None:
                            self.assertNotIn('class="report-chart"', markdown_html(page))  # indented fences are not charts
                        else:
                            with self.assertRaisesRegex(ValueError, message):
                                markdown_html(page)

    def test_verify_reports_invalid_json_data(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "index.md").write_text('```plot {data="data.json"}\nreturn {};\n```\n', encoding="utf-8")
            (source / "data.json").write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not valid JSON"):
                verify_report(source, (source,))


FORM_BODY = '''Intro.

```form {id="fixes" title="Which fixes should I apply?"}
{
  "description": "Pick the findings to fix.",
  "fields": [
    {"name": "findings", "type": "checkbox", "label": "Findings", "options": ["P1-leak", {"value": "P2-race", "label": "P2 race"}], "required": true},
    {"name": "style", "type": "radio", "label": "Approach", "options": ["narrow", "broad"], "default": "narrow"},
    {"name": "tests", "type": "switch", "label": "Add tests", "default": true},
    {"name": "budget", "type": "range", "label": "Effort", "min": 1, "max": 5},
    {"name": "notes", "type": "textarea", "label": "Notes", "help": "Anything else."}
  ],
  "actions": [{"value": "apply", "label": "Apply"}, {"value": "stop", "label": "Stop here", "style": "outline-secondary"}]
}
```
'''


SPLIT_FORM_BODY = '''### [P1] Leak

The buffer leaks.

```form-fields {form="review"}
{"fields": [
  {"name": "fix-leak", "type": "checkbox", "label": "Fix this"},
  {"name": "leak-notes", "type": "textarea", "label": "Notes"}
]}
```

### [P2] Race

The counter races.

```form-fields {form="review"}
{"fields": [
  {"name": "fix-race", "type": "checkbox", "label": "Fix this"},
  {"name": "race-scope", "type": "radio", "label": "Scope", "options": ["narrow", "broad"], "required": true}
]}
```

```form {id="review" title="Send my choices"}
{"fields": [{"name": "overall", "type": "text", "label": "Anything else"}], "actions": [{"value": "apply", "label": "Apply"}]}
```
'''


class FormFenceTests(TestCase):
    def page(self, body: str = FORM_BODY) -> Page:
        return Page(Path("index.md"), Path("index.md"), "Report", None, body)

    def test_form_fence_renders_labelled_bootstrap_controls(self) -> None:
        rendered = document(self.page(), [self.page()])

        self.assertIn('<form class="report-form card mb-3" id="report-form-fixes" data-form-id="fixes" data-report-page="index.md"', rendered)
        self.assertIn('data-field-kind="list" data-required="true"', rendered)
        self.assertIn('<label class="form-check-label" for="rf-fixes-findings-1">P2 race</label>', rendered)
        self.assertIn('value="narrow" checked><label', rendered)
        self.assertIn('role="switch" id="rf-fixes-tests" name="tests" checked', rendered)
        self.assertIn('aria-describedby="rf-fixes-notes-help"', rendered)
        self.assertIn('<button type="submit" class="btn btn-outline-secondary" name="action" value="stop">Stop here</button>', rendered)
        self.assertIn("_renderer/js/report-forms.js", rendered)
        self.assertNotIn("plot.umd.min.js", rendered)

    def test_pages_without_forms_omit_the_runtime(self) -> None:
        page = self.page("Just prose.\n")
        self.assertNotIn("report-forms.js", document(page, [page]))

    def test_bad_forms_are_rejected(self) -> None:
        cases = {
            '```form\n{"fields": [{"name": "a", "label": "A"}]}\n```\n': "needs an id=",
            '```form {id="x"}\n{"fields": [{"name": "a", "type": "radio", "label": "A"}]}\n```\n': "needs options",
            '```form {id="x"}\n{"fields": [{"name": "a", "type": "colour", "label": "A"}]}\n```\n': "unknown type",
            '```form {id="x"}\nnot json\n```\n': "not valid JSON",
            '```form {id="x"}\n{"fields": []}\n```\n': "at least one field or two actions",
            '```form {id="x"}\n{"fields": [{"name": "a", "label": "A"}]}\n```\n\n```form {id="x"}\n{"fields": [{"name": "a", "label": "A"}]}\n```\n': "more than once",
        }
        for body, message in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                markdown_html(self.page(body))

    def test_existing_form_markup_is_unchanged(self) -> None:
        rendered = markdown_html(self.page())

        self.assertNotIn("report-form-part", rendered)
        self.assertNotIn(' form="', rendered)
        self.assertEqual(["findings", "style", "tests", "budget", "notes"], [field.name for field in page_forms(self.page())["fixes"].fields])

    def test_form_fields_render_inline_and_join_their_form(self) -> None:
        page = self.page(SPLIT_FORM_BODY)
        rendered = markdown_html(page)

        self.assertEqual(2, rendered.count('<div class="report-form report-form-part" data-form-part="review" role="group" aria-label="Part of Send my choices">'))
        self.assertIn('id="rf-review-fix-leak" name="fix-leak" form="report-form-review">', rendered)
        self.assertIn('name="leak-notes" form="report-form-review" rows="2">', rendered)
        self.assertIn('name="race-scope" form="report-form-review" id="rf-review-race-scope-0"', rendered)
        self.assertLess(rendered.index("The buffer leaks."), rendered.index("rf-review-fix-leak"))
        self.assertLess(rendered.index("rf-review-fix-leak"), rendered.index("The counter races."))
        # The card holds only its own field, and the blocks have no buttons of their own.
        card = rendered[rendered.index('<form class="report-form card'):]
        self.assertIn('name="overall"', card)
        self.assertNotIn('name="fix-leak"', card)
        self.assertEqual(1, rendered.count('<button type="submit"'))
        self.assertIn("report-forms.js", document(page, [page]))

        spec = page_forms(page)["review"]
        self.assertEqual(["fix-leak", "leak-notes", "fix-race", "race-scope", "overall"], [field.name for field in spec.fields])
        values = {"fix-leak": True, "leak-notes": "", "fix-race": False, "race-scope": "narrow", "overall": ""}
        self.assertEqual(("apply", values), validate_response(spec, "apply", values))
        with self.assertRaisesRegex(ValueError, "required"):
            validate_response(spec, "apply", {**values, "race-scope": None})

    def test_a_form_may_keep_all_its_fields_in_form_fields_blocks(self) -> None:
        body = '```form-fields {form="go"}\n{"fields": [{"name": "ok", "type": "checkbox", "label": "OK"}]}\n```\n\n```form {id="go"}\n{}\n```\n'
        self.assertEqual(["ok"], [field.name for field in page_forms(self.page(body))["go"].fields])

    def test_bad_form_fields_are_rejected(self) -> None:
        form = '```form {id="r"}\n{"fields": [{"name": "a", "label": "A"}]}\n```\n'
        cases = {
            '```form-fields {form="r"}\n{"fields": [{"name": "a", "label": "Again"}]}\n```\n\n' + form: "field name 'a' more than once",
            '```form-fields {form="r"}\n{"fields": [{"name": "b", "label": "B"}]}\n```\n\n```form-fields {form="r"}\n{"fields": [{"name": "b", "label": "B"}]}\n```\n\n' + form: "field name 'b' more than once",
            '```form-fields {form="missing"}\n{"fields": [{"name": "b", "label": "B"}]}\n```\n\n' + form: "not on the page: missing",
            '```form-fields\n{"fields": [{"name": "b", "label": "B"}]}\n```\n\n' + form: "needs a form=",
            '```form-fields {form="r"}\n{"fields": []}\n```\n\n' + form: "at least one field",
            '```form-fields {form="r"}\n{"fields": [{"name": "b", "label": "B"}], "actions": []}\n```\n\n' + form: "unknown keys: actions",
        }
        for body, message in cases.items():
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                markdown_html(self.page(body))

    def test_verify_reports_an_orphan_form_fields_fence(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "index.md").write_text('# Report\n\n```form-fields {form="nowhere"}\n{"fields": [{"name": "a", "label": "A"}]}\n```\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not on the page: nowhere"):
                verify_report(source, (source,))

    def test_choice_buttons_alone_make_a_form(self) -> None:
        body = '```form {id="go"}\n{"actions": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]}\n```\n'
        self.assertIn('value="no">No</button>', markdown_html(self.page(body)))

    def test_response_validation(self) -> None:
        spec = page_forms(self.page())["fixes"]
        good = {"findings": ["P2-race"], "style": "broad", "tests": False, "budget": 3, "notes": ""}

        self.assertEqual(("apply", good), validate_response(spec, "apply", good))
        for change, message in [
            ({"findings": []}, "required"),
            ({"findings": ["P9"]}, "invalid value"),
            ({"style": "sideways"}, "invalid value"),
            ({"budget": "3"}, "invalid value"),
            ({"extra": 1}, "exactly the fields"),
        ]:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                validate_response(spec, "apply", {**good, **change})
        with self.assertRaisesRegex(ValueError, "Unknown action"):
            validate_response(spec, "delete", good)


class ResponseEndpointTests(TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        root = Path(self.directory.name)
        self.source = root / "report"
        self.source.mkdir()
        (self.source / "index.md").write_text(FORM_BODY, encoding="utf-8")
        self.patch = patch("local_report_renderer.cli.RESPONSES_ROOT", root / "responses")
        self.patch.start()
        handler = type("H", (OnDemandHandler,), {"source_root": self.source.resolve(), "pages": [], "code_roots": ()})
        handler.log_message = lambda *args: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.patch.stop()
        self.directory.cleanup()

    def post(self, payload: object, origin: str | None = None, content_type: str = "application/json") -> tuple[int, dict]:
        connection = HTTPConnection("127.0.0.1", self.port)
        headers = {"Content-Type": content_type, "Origin": origin or f"http://127.0.0.1:{self.port}"}
        connection.request("POST", "/_respond", body=json.dumps(payload), headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read() or b"{}")

    def test_valid_response_is_queued_and_delivered_once(self) -> None:
        values = {"findings": ["P1-leak"], "style": "narrow", "tests": True, "budget": 2, "notes": "ok"}
        self.assertEqual((201, {"seq": 1}), self.post({"page": "index.md", "form": "fixes", "action": "apply", "values": values}))
        self.assertEqual((201, {"seq": 2}), self.post({"page": "index.md", "form": "fixes", "action": "stop", "values": values}))

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, command_wait(Namespace(source=self.source, timeout=1)))
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([1, 2], [record["seq"] for record in records])
        self.assertEqual("Stop here", records[1]["action_label"])
        self.assertEqual(values, records[0]["values"])
        with redirect_stderr(io.StringIO()):
            self.assertEqual(3, command_wait(Namespace(source=self.source, timeout=0.2)))
        self.assertEqual(2, len(read_responses(self.source)))

    def test_cross_origin_and_invalid_requests_are_refused(self) -> None:
        values = {"findings": ["P1-leak"], "style": "narrow", "tests": True, "budget": 2, "notes": ""}
        good = {"page": "index.md", "form": "fixes", "action": "apply", "values": values}
        self.assertEqual(403, self.post(good, origin="http://evil.example")[0])
        self.assertEqual(415, self.post(good, content_type="text/plain")[0])
        self.assertEqual(400, self.post({**good, "page": "../index.md"})[0])
        self.assertEqual(400, self.post({**good, "form": "other"})[0])
        self.assertEqual(400, self.post({**good, "values": {**values, "findings": []}})[0])
        self.assertEqual([], read_responses(self.source))

    def test_form_fields_are_validated_and_queued_together(self) -> None:
        (self.source / "split.md").write_text(SPLIT_FORM_BODY, encoding="utf-8")
        values = {"fix-leak": True, "leak-notes": "keep the API", "fix-race": False, "race-scope": "broad", "overall": ""}
        good = {"page": "split.md", "form": "review", "action": "apply", "values": values}
        self.assertEqual((201, {"seq": 1}), self.post(good))
        # Only the card's own field, or a missing required answer in a block, is refused.
        self.assertEqual(400, self.post({**good, "values": {"overall": ""}})[0])
        self.assertEqual(400, self.post({**good, "values": {**values, "race-scope": None}})[0])

        [record] = read_responses(self.source)
        self.assertEqual("review", record["form"])
        self.assertEqual(values, record["values"])
        self.assertEqual(list(values), list(record["values"]))


class PriorityBadgeTests(TestCase):
    def page(self, body: str) -> Page:
        return Page(Path("index.md"), Path("index.md"), "Report", None, body)

    def test_lowercase_badge_kinds_capitalize_while_acronyms_keep_case(self) -> None:
        design = render_priority_badge("3", "design")
        self.assertIn("fa-compass-drafting", design)
        self.assertIn("<span>Design</span>", design)

        docs = render_priority_badge("3", "docs & UX")
        self.assertIn("<span>Docs &amp; UX</span>", docs)

        ci_failure = render_priority_badge("1", "CI failure")
        self.assertIn("<span>CI failure</span>", ci_failure)

        api_contract = render_priority_badge("2", "API contract")
        self.assertIn("<span>API contract</span>", api_contract)

        done_detail = render_priority_badge("1", "merged")
        self.assertIn("priority-done", done_detail)
        self.assertIn("<span>Merged</span>", done_detail)

    def test_badged_headings_use_hanging_body_wrapper_and_preserve_inline_code(self) -> None:
        rendered = markdown_html(
            self.page("### [P2: bug] Invalid `name` handling in [graph](https://example.com)\n")
        )
        self.assertIn(
            '<h3 id="p2-invalid-name-handling-in-graph" class="priority-heading">',
            rendered,
        )
        self.assertIn("<span>Bug</span>", rendered)
        self.assertIn(
            '<span class="priority-heading-body">Invalid <code>name</code> handling in '
            '<a href="https://example.com">graph</a></span></h3>',
            rendered,
        )

    def test_inline_and_code_badges_stay_isolated_from_heading_wrapper(self) -> None:
        rendered = markdown_html(
            self.page("| [P3] | `[P1: skipped]` |\n| --- | --- |\n| [Done] | ok |\n")
        )
        self.assertNotIn("priority-heading-body", rendered)
        self.assertIn("<span>Normal</span>", rendered)
        self.assertIn("<span>Complete</span>", rendered)
        self.assertIn("<code>[P1: skipped]</code>", rendered)

    def test_stylesheet_avoids_early_balanced_wrapping_and_hangs_badged_headings(self) -> None:
        self.assertIn("text-wrap: pretty", STYLESHEET)
        self.assertNotIn("text-wrap: balance", STYLESHEET)
        self.assertIn(".priority-heading { display: flex;", STYLESHEET)
        self.assertIn(".priority-heading-body { flex: 1 1 auto;", STYLESHEET)



class LayoutTests(TestCase):
    """The CSS and scripts/report_style.py must derive their sizes from assets/layout.json."""

    @staticmethod
    def report_style():
        import importlib.util

        path = Path(__file__).resolve().parents[2] / "scripts" / "report_style.py"
        spec = importlib.util.spec_from_file_location("report_style", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_stylesheet_uses_layout_values(self) -> None:
        from local_report_renderer.cli import LAYOUT

        self.assertIn(f"max-width: {LAYOUT['column_max_rem']:g}rem", STYLESHEET)
        self.assertIn(f"font: {LAYOUT['body_rem']:g}rem/", STYLESHEET)
        self.assertIn(f"--bs-gutter-x: {LAYOUT['gutter_rem']:g}rem", STYLESHEET)

    def test_plot_helper_matches_stylesheet(self) -> None:
        from local_report_renderer.cli import LAYOUT

        style = self.report_style()
        column_rem = LAYOUT["column_max_rem"] - LAYOUT["gutter_rem"]
        self.assertAlmostEqual(style.COLUMN_PX, column_rem * LAYOUT["root_px"])
        self.assertIn(f"min-width: {column_rem:g}rem", STYLESHEET)
        self.assertAlmostEqual(style.BODY_PT, LAYOUT["body_rem"] * LAYOUT["root_px"] * 0.75)

    def test_stylesheet_has_no_unfilled_placeholders(self) -> None:
        self.assertNotRegex(STYLESHEET, r"__[A-Z_]+REM__")

    def test_svg_images_are_wrapped_for_scrolling(self) -> None:
        page = Page(source=Path("p.md"), relative=Path("p.md"), title="P", description=None, body="![Plot](assets/a.svg)\n\n![Photo](assets/b.png)\n")
        rendered = markdown_html(page)
        self.assertIn('<span class="figure-scroll"><img', rendered)
        self.assertEqual(1, rendered.count("figure-scroll"))
