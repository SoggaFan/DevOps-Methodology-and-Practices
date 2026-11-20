#!/usr/bin/env python3
"""Read-only post-deployment checks for the pre-production API."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def get_json(base_url: str, path: str) -> object:
    url = f"{base_url.rstrip('/')}{path}"
    try:
        with urlopen(url, timeout=8) as response:
            if response.status != 200:
                raise RuntimeError(f"{path}: expected HTTP 200, got {response.status}")
            return json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"{path}: request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path}: response is not valid JSON") from exc


def get_web_page(base_url: str) -> str:
    url = f"{base_url.rstrip('/')}/"
    try:
        with urlopen(url, timeout=8) as response:
            if response.status != 200:
                raise RuntimeError(f"/: expected HTTP 200, got {response.status}")
            return response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"/: request failed: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18000")
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()

    page = get_web_page(args.url)
    if "<html" not in page.lower():
        raise RuntimeError("/ did not return the application HTML page")
    print("[PASS] web interface /")

    health = get_json(args.url, "/health")
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise RuntimeError("/health did not report status=ok")
    print("[PASS] /health")

    version = get_json(args.url, "/version")
    if not isinstance(version, dict):
        raise RuntimeError("/version did not return a JSON object")
    if version.get("version") != args.expected_version:
        raise RuntimeError(
            f"/version mismatch: expected {args.expected_version}, got {version.get('version')}"
        )
    if version.get("commit") != args.expected_commit:
        raise RuntimeError(
            "/version commit mismatch: "
            f"expected {args.expected_commit}, got {version.get('commit')}"
        )
    print(f"[PASS] /version ({args.expected_version})")

    # Read-only endpoints below are the data-loading calls used by the main web UI.
    for endpoint in ("/api/boats", "/api/crews", "/api/fish-types"):
        payload = get_json(args.url, endpoint)
        if not isinstance(payload, list) or not payload:
            raise RuntimeError(f"{endpoint} did not return a non-empty JSON list")
        print(f"[PASS] {endpoint} ({len(payload)} records)")

    trips = get_json(args.url, "/api/trips")
    if not isinstance(trips, list):
        raise RuntimeError("/api/trips did not return a JSON list")
    print(f"[PASS] /api/trips ({len(trips)} records)")

    report = get_json(args.url, "/api/reports/catch-by-period")
    required_report_fields = {"trip_count", "total_weight_kg", "total_cans"}
    if not isinstance(report, dict) or not required_report_fields.issubset(report):
        raise RuntimeError("catch-by-period report has an unexpected response shape")
    print("[PASS] /api/reports/catch-by-period")

    print("[PASS] release smoke test completed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
