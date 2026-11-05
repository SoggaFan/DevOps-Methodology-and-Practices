#!/usr/bin/env python3
"""Policy and runtime checks for the base Docker Compose environment (stdlib only)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
checks: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    checks.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def command(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def config_json(args: list[str]) -> dict[str, Any] | None:
    result = command(args + ["config", "--format", "json"])
    if result.returncode != 0:
        record("Compose config", False, result.stderr.strip() or "docker compose config failed")
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        record("Compose config JSON", False, str(exc))
        return None


def explicit_versioned_image(image: str) -> bool:
    # A digest is strongest, but `:latest@sha256:...` is still prohibited by policy.
    tagged_reference = image.split("@", 1)[0]
    tail = tagged_reference.rsplit("/", 1)[-1]
    if ":" not in tail:
        return False
    tag = tail.rsplit(":", 1)[1].lower()
    return tag not in {"", "latest"}


def has_volume_mount(service: dict[str, Any], target: str) -> bool:
    return any(
        isinstance(volume, dict)
        and volume.get("target") == target
        and volume.get("type") == "volume"
        for volume in service.get("volumes", [])
    )


def healthy_probe(service: dict[str, Any]) -> bool:
    probe = service.get("healthcheck", {})
    return bool(probe.get("test")) and probe.get("disable") is not True


def resource_limits(service: dict[str, Any]) -> bool:
    try:
        return bool(service.get("mem_limit")) and float(service.get("cpus", 0) or 0) > 0 and int(service.get("pids_limit", 0) or 0) > 0
    except (TypeError, ValueError):
        return False


def image_inspect(image: str) -> dict[str, Any] | None:
    result = command(["docker", "image", "inspect", image])
    if result.returncode != 0:
        record(f"Image inspect {image}", False, "image not available; run make up first")
        return None
    try:
        return json.loads(result.stdout)[0]
    except (json.JSONDecodeError, IndexError, TypeError) as exc:
        record(f"Image inspect {image}", False, str(exc))
        return None


def get_container(service_name: str) -> tuple[str | None, dict[str, Any] | None]:
    result = command(["docker", "compose", "ps", "-q", service_name])
    container_id = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
    if result.returncode != 0 or not container_id:
        record(f"Container {service_name}", False, "not found; run make up first")
        return None, None
    inspected = command(["docker", "inspect", container_id])
    if inspected.returncode != 0:
        record(f"Inspect {service_name}", False, inspected.stderr.strip())
        return container_id, None
    try:
        return container_id, json.loads(inspected.stdout)[0]
    except (json.JSONDecodeError, IndexError, TypeError) as exc:
        record(f"Inspect {service_name}", False, str(exc))
        return container_id, None


def wait_healthy(
    service_name: str,
    timeout_seconds: int = 90,
    compose_args: list[str] | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    deadline = time.monotonic() + timeout_seconds
    container_id: str | None = None
    details: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        container_id, details = get_container_quiet(service_name, compose_args)
        if details:
            state = details.get("State", {})
            health = state.get("Health", {}).get("Status")
            if health == "healthy":
                record(f"Health {service_name}", True, "container reports healthy")
                return container_id, details
            if state.get("Status") == "exited" or health == "unhealthy":
                record(f"Health {service_name}", False, f"status={state.get('Status')}, health={health}")
                return container_id, details
        time.sleep(2)
    state = (details or {}).get("State", {})
    health = state.get("Health", {}).get("Status", "missing")
    record(f"Health {service_name}", False, f"timed out; state={state.get('Status')}, health={health}")
    return container_id, details


def get_container_quiet(
    service_name: str, compose_args: list[str] | None = None
) -> tuple[str | None, dict[str, Any] | None]:
    result = command((compose_args or ["docker", "compose"]) + ["ps", "-a", "-q", service_name])
    if result.returncode != 0 or not result.stdout.strip():
        return None, None
    container_id = result.stdout.strip().splitlines()[0]
    inspected = command(["docker", "inspect", container_id])
    if inspected.returncode != 0:
        return container_id, None
    try:
        return container_id, json.loads(inspected.stdout)[0]
    except (json.JSONDecodeError, IndexError, TypeError):
        return container_id, None


def main() -> int:
    base = config_json(["docker", "compose"])
    scale = config_json(
        ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.scale.yml", "--profile", "scale"]
    )
    if base is None or scale is None:
        return 1

    services = base.get("services", {})
    db = services.get("db", {})
    api = services.get("api", {})
    networks = base.get("networks", {})
    dockerfile_path = ROOT / "Dockerfile"
    dockerfile = dockerfile_path.read_text(encoding="utf-8")
    dockerignore_path = ROOT / ".dockerignore"
    dockerignore = dockerignore_path.read_text(encoding="utf-8") if dockerignore_path.exists() else ""

    from_lines = re.findall(r"^FROM\s+(\S+)", dockerfile, flags=re.MULTILINE | re.IGNORECASE)
    record(
        "Versioned Docker base image",
        bool(from_lines) and all(explicit_versioned_image(image) for image in from_lines),
        ", ".join(from_lines) if from_lines else "no FROM line found",
    )
    user_lines = re.findall(r"^USER\s+(\S+)", dockerfile, flags=re.MULTILINE | re.IGNORECASE)
    non_root_user = bool(user_lines) and all(user not in {"root", "0", "0:0"} for user in user_lines)
    record("Non-root image USER", non_root_user, ", ".join(user_lines) or "USER instruction missing")
    record(
        "Graceful signal handling",
        bool(re.search(r"^STOPSIGNAL\s+SIGTERM\s*$", dockerfile, flags=re.MULTILINE))
        and bool(re.search(r"^CMD\s+\[", dockerfile, flags=re.MULTILINE)),
        "STOPSIGNAL SIGTERM and exec-form CMD are configured",
    )
    docker_env_lines = re.findall(r"^ENV\s+(.+)$", dockerfile, flags=re.MULTILINE)
    baked_secret = any(
        re.search(r"(?i)(DATABASE_URL|POSTGRES_PASSWORD|POSTGRES_APP_PASSWORD|DB_PASSWORD)", line)
        for line in docker_env_lines
    )
    record("Dockerfile does not define secret environment variables", not baked_secret, "no DB passwords/URLs are baked into ENV")
    copy_lines = re.findall(r"^COPY\s+(.+)$", dockerfile, flags=re.MULTILINE)
    unsafe_copy = any(
        line.strip().startswith(". ")
        or line.strip().startswith("./ ")
        or re.search(r"\s\.\s", line) is not None
        or ".env" in line
        for line in copy_lines
    )
    record("No source-root/secret COPY", not unsafe_copy, "Dockerfile copies explicit runtime paths" if not unsafe_copy else str(copy_lines))
    ignore_has_env = any(line.strip() == ".env" for line in dockerignore.splitlines())
    ignore_has_git = any(line.strip() == ".git" for line in dockerignore.splitlines())
    record(".dockerignore excludes secrets and Git metadata", ignore_has_env and ignore_has_git, ".env and .git are excluded from build context")

    record("API image has a fixed tag", explicit_versioned_image(str(api.get("image", ""))), str(api.get("image", "missing")))
    record("Database image has a fixed tag", explicit_versioned_image(str(db.get("image", ""))), str(db.get("image", "missing")))
    record("Database port is not published", not db.get("ports"), "no host port mapping for PostgreSQL" if not db.get("ports") else str(db.get("ports")))
    record("DB healthcheck enabled", healthy_probe(db), "PostgreSQL readiness probe is present and not disabled")
    record("API healthcheck enabled", healthy_probe(api), "application readiness probe is present and not disabled")
    record("API waits for healthy DB", api.get("depends_on", {}).get("db", {}).get("condition") == "service_healthy", "depends_on uses service_healthy")
    record("Named DB volume", has_volume_mount(db, "/var/lib/postgresql/data"), "postgres_data mounted at PGDATA")
    record("Internal backend network", bool(networks.get("backend", {}).get("internal")), "backend network is internal")
    for service_name, service in (("api", api), ("db", db)):
        limits_ok = resource_limits(service)
        record(f"Resource limits ({service_name})", limits_ok, f"cpus={service.get('cpus')}, memory={service.get('mem_limit')}, pids={service.get('pids_limit')}")
    record("API read-only filesystem", bool(api.get("read_only")), "read_only must be true")
    record("Capabilities dropped", "ALL" in api.get("cap_drop", []), "all Linux capabilities are dropped")
    record("No new privileges", any("no-new-privileges:true" in value for value in api.get("security_opt", [])), "no-new-privileges is enabled")
    record("Graceful stop window", bool(api.get("stop_grace_period")), str(api.get("stop_grace_period", "missing")))

    scale_services = scale.get("services", {})
    api1 = scale_services.get("api1", {})
    api2 = scale_services.get("api2", {})
    nginx = scale_services.get("nginx", {})
    record("Scale services exist", bool(api1 and api2 and nginx), "api1, api2 and nginx are declared")
    record("No direct host ports for scaled APIs", not api1.get("ports") and not api2.get("ports"), "only Nginx exposes a host port in scale mode")
    record("Nginx uses a fixed image tag", explicit_versioned_image(str(nginx.get("image", ""))), str(nginx.get("image", "missing")))
    for service_name, service in (("api1", api1), ("api2", api2), ("nginx", nginx)):
        record(f"Healthcheck enabled ({service_name})", healthy_probe(service), "healthcheck exists and is not disabled")
        record(f"Resource limits ({service_name})", resource_limits(service), f"cpus={service.get('cpus')}, memory={service.get('mem_limit')}, pids={service.get('pids_limit')}")

    restore = config_json(["docker", "compose", "-f", "docker-compose.restore.yml"])
    restore_db = (restore or {}).get("services", {}).get("db", {})
    record("Restore DB uses a fixed image", explicit_versioned_image(str(restore_db.get("image", ""))), str(restore_db.get("image", "missing")))
    record("Restore DB healthcheck enabled", healthy_probe(restore_db), "restore database readiness probe is enabled")
    record("Restore DB has named volume", has_volume_mount(restore_db, "/var/lib/postgresql/data"), "restore target has its own volume")
    record("Restore DB resource limits", resource_limits(restore_db), f"cpus={restore_db.get('cpus')}, memory={restore_db.get('mem_limit')}, pids={restore_db.get('pids_limit')}")
    all_image_refs = []
    for config in (base, scale, restore or {}):
        all_image_refs.extend(
            str(service["image"])
            for service in config.get("services", {}).values()
            if service.get("image")
        )
    floating_images = [image for image in all_image_refs if not explicit_versioned_image(image)]
    record(
        "No latest/unpinned image references",
        not floating_images,
        ", ".join(floating_images) if floating_images else "all Compose images have explicit non-latest tags/digests",
    )

    # The gate can run before the first deployment. If a stack already exists,
    # inspect the active single-service or scale-profile deployment as well.
    scale_compose = [
        "docker", "compose", "-f", "docker-compose.yml", "-f",
        "docker-compose.scale.yml", "--profile", "scale",
    ]
    base_db = command(["docker", "compose", "ps", "-a", "-q", "db"]).stdout.strip()
    base_api = command(["docker", "compose", "ps", "-a", "-q", "api"]).stdout.strip()
    scale_db = command(scale_compose + ["ps", "-a", "-q", "db"]).stdout.strip()
    scale_api1 = command(scale_compose + ["ps", "-a", "-q", "api1"]).stdout.strip()
    scale_api2 = command(scale_compose + ["ps", "-a", "-q", "api2"]).stdout.strip()
    scale_nginx = command(scale_compose + ["ps", "-a", "-q", "nginx"]).stdout.strip()

    if base_db and base_api:
        runtime_mode = "single"
    elif scale_db and scale_api1 and scale_api2 and scale_nginx:
        runtime_mode = "scale"
    elif any((base_db, base_api, scale_db, scale_api1, scale_api2, scale_nginx)):
        runtime_mode = "partial"
    else:
        runtime_mode = "none"

    image_name = str(api.get("image", ""))
    image_info = image_inspect(image_name) if runtime_mode in {"single", "scale"} and image_name else None
    if image_info:
        image_user = str(image_info.get("Config", {}).get("User", ""))
        record("Built image is non-root", bool(image_user) and image_user not in {"root", "0", "0:0"}, image_user or "image USER not set")
        image_env = image_info.get("Config", {}).get("Env", [])
        contains_secret_env = any(
            item.split("=", 1)[0] in {"DATABASE_URL", "POSTGRES_PASSWORD", "POSTGRES_APP_PASSWORD"}
            for item in image_env
        )
        record("No database credentials baked into image", not contains_secret_env, "image config has no DB URL/password environment variables")

    port: int | None = None
    if runtime_mode == "scale":
        nginx_ports = nginx.get("ports", [])
        if nginx_ports:
            try:
                port = int(nginx_ports[0].get("published"))
            except (TypeError, ValueError):
                port = None
            record("Nginx binds host loopback only", nginx_ports[0].get("host_ip") == "127.0.0.1", str(nginx_ports[0].get("host_ip", "not set")))
        else:
            record("Nginx host port configured", False, "Nginx has no published host port")
    else:
        published_ports = api.get("ports", [])
        if published_ports:
            first_port = published_ports[0]
            try:
                port = int(first_port.get("published"))
            except (TypeError, ValueError):
                port = None
            record("API binds host loopback only", first_port.get("host_ip") == "127.0.0.1", str(first_port.get("host_ip", "not set")))
        else:
            record("API host port configured", False, "no published API port")

    if runtime_mode == "none":
        print("[INFO] Runtime checks skipped: no Compose containers exist yet. Static policy gate passed; run `make up`, then rerun `make container-check` for runtime validation.")
    elif runtime_mode == "partial":
        record("Runtime Compose stack is complete", False, "found a partial/stopped stack; inspect `docker compose ps -a` before changing the environment")
    else:
        runtime_compose = ["docker", "compose"] if runtime_mode == "single" else scale_compose
        db_id, db_info = wait_healthy("db", compose_args=runtime_compose)
        app_services = ["api"] if runtime_mode == "single" else ["api1", "api2", "nginx"]
        app_infos: dict[str, dict[str, Any] | None] = {}
        for service_name in app_services:
            _, app_infos[service_name] = wait_healthy(service_name, compose_args=runtime_compose)

        if db_info:
            port_bindings = db_info.get("HostConfig", {}).get("PortBindings") or {}
            has_host_bindings = any(bindings for bindings in port_bindings.values())
            record("Runtime DB has no published port", not has_host_bindings, "HostConfig.PortBindings is empty" if not has_host_bindings else str(port_bindings))
            host_config = db_info.get("HostConfig", {})
            runtime_limits = host_config.get("Memory", 0) > 0 and host_config.get("NanoCpus", 0) > 0 and host_config.get("PidsLimit", 0) > 0
            record("Runtime DB limits applied", runtime_limits, f"memory={host_config.get('Memory')}, NanoCpus={host_config.get('NanoCpus')}, pids={host_config.get('PidsLimit')}")

        checked_api_names = ["api"] if runtime_mode == "single" else ["api1", "api2"]
        for service_name in checked_api_names:
            info = app_infos.get(service_name)
            if not info:
                continue
            host_config = info.get("HostConfig", {})
            runtime_limits = host_config.get("Memory", 0) > 0 and host_config.get("NanoCpus", 0) > 0 and host_config.get("PidsLimit", 0) > 0
            record(f"Runtime limits applied ({service_name})", runtime_limits, f"memory={host_config.get('Memory')}, NanoCpus={host_config.get('NanoCpus')}, pids={host_config.get('PidsLimit')}")
            result = command(runtime_compose + ["exec", "-T", service_name, "id", "-u"])
            uid = result.stdout.strip().splitlines()[-1] if result.returncode == 0 and result.stdout.strip() else "unknown"
            record(f"Running {service_name} process is non-root", result.returncode == 0 and uid.isdigit() and int(uid) != 0, f"effective UID={uid}")
            if runtime_mode == "scale":
                container_id = str(info.get("Id", ""))
                inspected = command(["docker", "inspect", container_id]) if container_id else None
                bindings = {}
                if inspected and inspected.returncode == 0:
                    try:
                        bindings = json.loads(inspected.stdout)[0].get("HostConfig", {}).get("PortBindings") or {}
                    except (json.JSONDecodeError, IndexError, TypeError):
                        bindings = {"inspect-error": ["unknown"]}
                record(f"No published host ports ({service_name})", not any(bindings.values()), "no host port bindings" if not any(bindings.values()) else str(bindings))

        nginx_info = app_infos.get("nginx")
        if runtime_mode == "scale" and nginx_info:
            nginx_cfg = nginx_info.get("HostConfig", {})
            nginx_limits = nginx_cfg.get("Memory", 0) > 0 and nginx_cfg.get("NanoCpus", 0) > 0 and nginx_cfg.get("PidsLimit", 0) > 0
            record("Runtime limits applied (nginx)", nginx_limits, f"memory={nginx_cfg.get('Memory')}, NanoCpus={nginx_cfg.get('NanoCpus')}, pids={nginx_cfg.get('PidsLimit')}")

        if port is not None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
                    body = json.loads(response.read().decode("utf-8"))
                    ok = response.status == 200 and body.get("status") == "ok"
                    record("HTTP health endpoint", ok, f"HTTP {response.status}, status={body.get('status')}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                record("HTTP health endpoint", False, str(exc))

    failed = [name for name, ok, _ in checks if not ok]
    print(f"\nContainer policy check: {len(checks) - len(failed)}/{len(checks)} passed.")
    if failed:
        print("Failures: " + ", ".join(failed))
        return 1
    print("Container environment meets the configured policy.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[FAIL] Could not inspect Docker environment: {exc}", file=sys.stderr)
        raise SystemExit(1)
