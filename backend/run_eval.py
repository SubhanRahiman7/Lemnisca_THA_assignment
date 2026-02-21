#!/usr/bin/env python3
"""
Eval harness: run test queries against the running API and report pass/fail.
Usage: start the backend (python main.py), then from backend/ run:
  python run_eval.py [--base-url http://localhost:8000]
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path


def load_cases(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def check_answer(case: dict, answer: str) -> tuple[bool, str]:
    """Return (passed, reason)."""
    expected_in = case.get("expected_in") or []
    expect_refusal = case.get("expect_refusal_or_unknown", False)
    answer_lower = (answer or "").strip().lower()

    if not answer_lower:
        return False, "empty answer"

    if expect_refusal:
        # Pass if model didn't confidently state a wrong fact (e.g. "Paris" for capital of France)
        wrong_fact = "paris" in answer_lower and "france" in answer_lower
        refusal_phrases = ["don't have", "not in", "not mentioned", "cannot find", "documentation", "outside"]
        has_refusal = any(p in answer_lower for p in refusal_phrases)
        if wrong_fact and not has_refusal:
            return False, "stated out-of-scope fact"
        return True, "refusal or hedged"

    # Pass if at least one expected phrase is present in the answer
    for required in expected_in:
        if required.lower() in answer_lower:
            return True, "ok"
    if expected_in:
        return False, f"missing any of {expected_in!r}"
    return True, "ok"


def run_eval(base_url: str, cases_path: Path) -> dict:
    results = []
    base_url = base_url.rstrip("/")
    url = f"{base_url}/query"

    for case in load_cases(cases_path):
        q = case.get("query", "")
        case_id = case.get("id", "unknown")
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps({"question": q}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            answer = data.get("answer", "")
        except Exception as e:
            err_str = str(e)
            if "401" in err_str and "invalid_api_key" in err_str.lower():
                reason = "Invalid Groq API key. Set a valid GROQ_API_KEY and restart the backend (see README)."
            else:
                reason = f"request failed: {e}"
            results.append({
                "id": case_id,
                "query": q[:50] + "..." if len(q) > 50 else q,
                "pass": False,
                "reason": reason,
                "answer_preview": "",
            })
            continue

        passed, reason = check_answer(case, answer)
        results.append({
            "id": case_id,
            "query": q[:50] + "..." if len(q) > 50 else q,
            "pass": passed,
            "reason": reason,
            "answer_preview": (answer or "")[:120] + "..." if len(answer or "") > 120 else (answer or ""),
        })

    return {"results": results, "total": len(results), "passed": sum(1 for r in results if r["pass"])}


def main():
    parser = argparse.ArgumentParser(description="Run eval harness against Clearpath chatbot API")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--queries", type=Path, default=Path(__file__).parent / "eval_queries.json", help="JSON test cases")
    parser.add_argument("--json", action="store_true", help="Output only JSON report")
    args = parser.parse_args()

    if not args.queries.exists():
        print(f"Queries file not found: {args.queries}", file=sys.stderr)
        sys.exit(1)

    report = run_eval(args.base_url, args.queries)

    if args.json:
        print(json.dumps(report, indent=2))
        sys.exit(0 if report["passed"] == report["total"] else 1)

    # Human-readable report
    print("=" * 60)
    print("EVAL HARNESS REPORT")
    print("=" * 60)
    for r in report["results"]:
        status = "PASS" if r["pass"] else "FAIL"
        print(f"  [{status}] {r['id']}: {r['reason']}")
        print(f"       Query: {r['query']}")
        if not r["pass"] and r["answer_preview"]:
            print(f"       Answer: {r['answer_preview']}")
        print()
    print("=" * 60)
    print(f"Total: {report['passed']}/{report['total']} passed")
    print("=" * 60)
    sys.exit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    main()
