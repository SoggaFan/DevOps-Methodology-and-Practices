#!/usr/bin/env python3
"""Exercise the optional Nginx load-balancing and passive failover setup."""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.scale.yml", "--profile", "scale"]


def run(args: list[str], *, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=timeout)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{result.stderr.strip()}")
    return result


def wait_healthy(service: str, timeout_seconds: int = 90) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = run(COMPOSE + ["ps", "-q", service], check=False)
        cid = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if cid:
            inspected = run(["docker", "inspect", cid], check=False)
            if inspected.returncode == 0:
                container = json.loads(inspected.stdout)[0]
                state = container.get("State", {})
                health = state.get("Health", {}).get("Status")
                if health == "healthy":
                    return
                if health == "unhealthy" or state.get("Status") == "exited":
                    raise RuntimeError(f"{service} is not healthy: state={state.get('Status')}, health={health}")
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for {service} to become healthy")


def get_health(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} from {url}")
        body: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        if body.get("status") != "ok":
            raise RuntimeError(f"Unexpected health body: {body}")
        return response.headers.get("X-Instance-ID", "missing")


def main() -> int:
    config = json.loads(run(COMPOSE + ["config", "--format", "json"]).stdout)
    port = int(config["services"]["nginx"]["ports"][0]["published"])
    url = f"http://127.0.0.1:{port}/health"
    wait_healthy("db")
    wait_healthy("api1")
    wait_healthy("api2")
    wait_healthy("nginx")

    for service in ("api1", "api2"):
        result = run(COMPOSE + ["ps", "-q", service])
        container_id = result.stdout.strip().splitlines()[0]
        inspected = json.loads(run(["docker", "inspect", container_id]).stdout)[0]
        port_bindings = inspected.get("HostConfig", {}).get("PortBindings") or {}
        if any(bindings for bindings in port_bindings.values()):
            raise RuntimeError(f"{service} unexpectedly publishes a host port: {port_bindings}")
    print("[PASS] API instances have no published host ports.")

    print("Sending 32 concurrent requests (below the configured burst limit) to check load balancing...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
        futures = [executor.submit(get_health, url) for _ in range(32)]
        instance_ids = [future.result() for future in futures]
    observed = set(instance_ids)
    if not {"api-1", "api-2"}.issubset(observed):
        raise RuntimeError(f"Expected responses from api-1 and api-2, observed: {sorted(observed)}")
    print(f"[PASS] Requests were served by both instances: {sorted(observed)}.")
    # Let the configured Nginx request-rate bucket refill before failover checks.
    time.sleep(2)

    try:
        print("Stopping api1 to test Nginx passive failure detection and retry...")
        run(COMPOSE + ["stop", "--timeout", "20", "api1"])
        observed_after_stop: set[str] = set()
        for _ in range(12):
            observed_after_stop.add(get_health(url))
        if observed_after_stop != {"api-2"}:
            raise RuntimeError(f"Expected only api-2 responses after stopping api1, got: {sorted(observed_after_stop)}")
        print("[PASS] Service stayed healthy through Nginx with api1 stopped; api2 served requests.")
    finally:
        run(COMPOSE + ["start", "api1"], check=False)

    wait_healthy("api1")
    print("[PASS] api1 restarted and is healthy.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError, RuntimeError, KeyError, IndexError, ValueError, urllib.error.URLError, concurrent.futures.TimeoutError) as exc:
        print(f"[FAIL] Scale/failover check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
