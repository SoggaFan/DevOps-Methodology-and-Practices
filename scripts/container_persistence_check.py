#!/usr/bin/env python3
"""Interactive Linux-VM acceptance check for DB-volume persistence and SIGTERM."""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "http://127.0.0.1"
created_registration: str | None = None
api_stopped = False


def run(args: list[str], *, input_text: str | None = None, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{result.stderr.strip()}")
    return result


def compose_config() -> dict[str, Any]:
    result = run(["docker", "compose", "config", "--format", "json"])
    return json.loads(result.stdout)


def app_url() -> str:
    ports = compose_config()["services"]["api"].get("ports", [])
    if not ports:
        raise RuntimeError("The base API service has no host port; this check is for normal Compose mode.")
    return f"{BASE_URL}:{int(ports[0]['published'])}"


def request_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def wait_for_health(url: str, timeout_seconds: int = 90) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "not ready"
    while time.monotonic() < deadline:
        try:
            status, body = request_json(f"{url}/health")
            if status == 200 and body.get("status") == "ok":
                return
            last_error = f"HTTP {status}: {body}"
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"API did not become healthy: {last_error}")


def cleanup_marker() -> None:
    global created_registration
    if not created_registration:
        return
    sql = f"DELETE FROM boats WHERE registration_no = '{created_registration}';\n"
    cleanup = run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
        ],
        input_text=sql,
        check=False,
    )
    if cleanup.returncode == 0:
        print("[PASS] Temporary persistence marker removed.")
    else:
        print("[WARN] Could not remove the temporary marker; inspect the database before rerunning.", file=sys.stderr)
        print(cleanup.stderr.strip(), file=sys.stderr)


def ensure_api_running(url: str) -> None:
    global api_stopped
    if api_stopped:
        run(["docker", "compose", "start", "api"], check=False)
        wait_for_health(url)
        api_stopped = False


def main() -> int:
    global created_registration, api_stopped
    print("This acceptance check briefly restarts the database and API containers.")
    print("Run it only in the Lab 4 test VM; it creates and then removes one temporary boat row.")
    if not sys.stdin.isatty():
        if __import__("os").environ.get("CONFIRM_CONTAINER_PERSISTENCE") != "YES":
            print("Refusing non-interactive run. Set CONFIRM_CONTAINER_PERSISTENCE=YES to confirm explicitly.", file=sys.stderr)
            return 2
    else:
        answer = input("Type YES to continue: ").strip()
        if answer != "YES":
            print("Cancelled; no containers or data were changed.")
            return 2

    # First ensure the current environment passes the required safety and runtime gate.
    gate = run([sys.executable, "scripts/container_check.py"], check=False)
    print(gate.stdout, end="")
    if gate.returncode != 0:
        print("container-check failed; not performing lifecycle changes.", file=sys.stderr)
        return gate.returncode

    url = app_url()
    wait_for_health(url)
    token = secrets.token_hex(5).upper()
    created_registration = f"LR4-PERSIST-{token}"
    status, created = request_json(
        f"{url}/api/boats",
        method="POST",
        payload={"name": "LR4 Persistence Check", "registration_no": created_registration, "capacity_kg": "1.00"},
    )
    if status != 201:
        raise RuntimeError(f"Could not create persistence marker: HTTP {status}")
    print(f"[PASS] Temporary row created (boat id {created.get('id')}).")

    try:
        print("Rebuilding the API image and recreating both DB/API containers without deleting volumes...")
        run(["docker", "compose", "up", "--build", "--force-recreate", "-d", "db", "api"], timeout=600)
        wait_for_health(url)
        _, boats = request_json(f"{url}/api/boats")
        if not any(boat.get("registration_no") == created_registration for boat in boats):
            raise RuntimeError("The temporary row disappeared after DB/API container recreation.")
        print("[PASS] Test row persisted after image rebuild and DB/API container recreation.")

        print("Stopping API with SIGTERM and checking its exit code...")
        run(["docker", "compose", "stop", "--timeout", "20", "api"])
        api_stopped = True
        container_id = run(["docker", "compose", "ps", "-a", "-q", "api"]).stdout.strip().splitlines()[0]
        inspect = json.loads(run(["docker", "inspect", container_id]).stdout)[0]
        state = inspect.get("State", {})
        exit_code = state.get("ExitCode")
        logs = run(
            ["docker", "compose", "logs", "--no-color", "--tail", "100", "api"],
            check=False,
        ).stdout

        graceful_shutdown = (
            "Shutting down" in logs
            and "Application shutdown complete." in logs
            and "Finished server process" in logs
        )

        clean_stop = state.get("Status") == "exited" and (
            exit_code == 0 or (exit_code == 143 and graceful_shutdown)
        )

        if not clean_stop:
            raise RuntimeError(
                f"API did not exit cleanly after SIGTERM: "
                f"status={state.get('Status')}, exit={exit_code}, "
                f"graceful_shutdown_logs={graceful_shutdown}"
            )

        if exit_code == 143:
            print(
                "[PASS] SIGTERM triggered graceful Uvicorn shutdown "
                "(exit 143 with shutdown logs)."
            )
        else:
            print("[PASS] API container stopped with exit code 0 after SIGTERM.")
        run(["docker", "compose", "start", "api"])
        api_stopped = False
        wait_for_health(url)
        print("[PASS] API restarted and became healthy again.")
        return 0
    finally:
        try:
            if api_stopped:
                ensure_api_running(url)
        finally:
            cleanup_marker()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError, RuntimeError, KeyError, IndexError, ValueError, urllib.error.URLError) as exc:
        print(f"[FAIL] Container acceptance check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
