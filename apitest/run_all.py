"""Discover and run HTTP contract checks, then write a local HTML report."""

import html
import importlib.util
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APITEST_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APITEST_ROOT))


def discover_cases():
    cases = []
    for path in sorted((APITEST_ROOT / "cases").rglob("*.py")):
        if path.name.upper() not in {"GET.PY", "POST.PY", "PUT.PY", "PATCH.PY", "DELETE.PY"}:
            continue
        cases.append(path)
    return cases


def load_case(path, index):
    module_name = f"campusclaw_apitest_case_{index}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load API case")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "run", None)):
        raise RuntimeError("API case must expose run()")
    return module


def create_report(results, report_path):
    rows = []
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        css_class = "pass" if result["passed"] else "fail"
        rows.append(
            "<tr>"
            f"<td class='{css_class}'>{status}</td>"
            f"<td><code>{html.escape(result['case'])}</code></td>"
            f"<td>{html.escape(result['detail'])}</td>"
            f"<td>{result['duration']:.2f}s</td>"
            "</tr>"
        )
    passed = sum(1 for result in results if result["passed"])
    failed = len(results) - passed
    generated = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    title = "CampusClaw API Contract Test Report"
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
body{{font:14px/1.6 system-ui,"Microsoft YaHei",sans-serif;margin:32px auto;padding:0 18px;max-width:1100px;color:#20312a;background:#f5f8f6}}
h1{{font-size:24px;color:#176b58}}.summary{{padding:14px;background:white;border:1px solid #dce8e1;border-radius:8px;margin:16px 0}}
table{{width:100%;border-collapse:collapse;background:white;border:1px solid #dce8e1}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #e5eee9;vertical-align:top}}
th{{background:#eff5f1}}.pass{{color:#19704f;font-weight:700}}.fail{{color:#b43d32;font-weight:700}}code{{overflow-wrap:anywhere}}
</style></head><body><h1>{title}</h1><div class="summary">Generated: {html.escape(generated)}<br>
Passed: {passed} · Failed: {failed} · Total: {len(results)}</div>
<table><thead><tr><th>Result</th><th>Case (URL / Method)</th><th>Verification</th><th>Duration</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></body></html>"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(document, encoding="utf-8")


def main():
    cases = discover_cases()
    if not cases:
        print("No API cases found under apitest/cases.", file=sys.stderr)
        return 2
    results = []
    for index, path in enumerate(cases, start=1):
        relative = path.relative_to(APITEST_ROOT / "cases").as_posix()
        label = "/" + relative.rsplit("/", 1)[0] + " · " + path.stem.upper()
        started = time.perf_counter()
        try:
            module = load_case(path, index)
            detail = module.run()
            if not isinstance(detail, str):
                detail = "HTTP response and SQLite state verified"
            result = {"case": label, "passed": True, "detail": detail, "duration": time.perf_counter() - started}
        except Exception as error:  # Each case is isolated so the full report is still produced.
            result = {
                "case": label,
                "passed": False,
                "detail": f"{type(error).__name__}: {error}",
                "duration": time.perf_counter() - started,
            }
        results.append(result)
        print(f"{'PASS' if result['passed'] else 'FAIL'} {label}: {result['detail']}")

    from support import logout_cached_tokens

    for account, status in logout_cached_tokens():
        print(f"{'PASS' if status == 200 else 'FAIL'} logout temporary {account} token: HTTP {status}")
        if status != 200:
            results.append({
                "case": f"/logout · POST ({account} cleanup)",
                "passed": False,
                "detail": f"Created API-test token could not be revoked (HTTP {status})",
                "duration": 0.0,
            })

    configured_report = Path(os.getenv("APITEST_REPORT_PATH", "apitest/reports/index.html"))
    report_path = configured_report if configured_report.is_absolute() else ROOT / configured_report
    create_report(results, report_path)
    failed = sum(1 for result in results if not result["passed"])
    print(f"API test report: {report_path}")
    print(f"API tests: {len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
