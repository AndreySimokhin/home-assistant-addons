#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import time
from pathlib import Path


CONFIG_DIR = Path("/config/traefik")
STATIC_CONFIG = CONFIG_DIR / "traefik.yaml"
OPTIONS_FILE = Path("/data/options.json")
LOGROTATE_CONFIG = Path("/etc/logrotate.d/traefik")
LOGROTATE_STATUS = Path("/tmp/logrotate.status")


def log_info(message):
    print(f"[INFO] {message}", flush=True)


def log_warning(message):
    print(f"[WARNING] {message}", flush=True)


def log_error(message):
    print(f"[ERROR] {message}", flush=True)


def fatal_wait(message):
    log_error(message)
    log_error("Traefik is not started. Fix the add-on options or mounted files, then restart the add-on.")
    while True:
        time.sleep(300)
        log_error(message)


def load_options():
    with OPTIONS_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def prepare_runtime():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    Path("/share").mkdir(parents=True, exist_ok=True)

    for log_file in (Path("/share/traefik-access.log"), Path("/share/traefik-error.log")):
        log_file.touch(exist_ok=True)
        os.chown(log_file, 0, 0)
        log_file.chmod(0o644)

    os.chown(CONFIG_DIR, 0, 0)


def render_config():
    result = subprocess.run(["/usr/local/bin/render-traefik-config.py"], check=False)
    if result.returncode != 0:
        fatal_wait("Failed to render Traefik configuration.")


def resolve_static_config(options):
    override = options["custom"].get("static_config_override_file") or ""
    if not override:
        return STATIC_CONFIG

    override_path = Path(override)
    if not override_path.is_file():
        fatal_wait(f"Static config override file is missing: {override}")

    log_warning(f"Using custom static Traefik config override: {override_path}")
    return override_path


def validate_tls_files(options):
    if not options["tls"]["enabled"]:
        return

    cert_file = Path(options["tls"]["cert_file"])
    key_file = Path(options["tls"]["key_file"])

    if not cert_file.is_file():
        fatal_wait(f"TLS is enabled but certificate file is missing: {cert_file}")
    if not key_file.is_file():
        fatal_wait(f"TLS is enabled but key file is missing: {key_file}")


def validate_traefik_config(static_config):
    result = subprocess.run(["traefik", "check", f"--configFile={static_config}"], check=False)
    if result.returncode != 0:
        fatal_wait("Traefik configuration validation failed.")


def start_logrotate_background():
    return subprocess.Popen(
        [
            "python3",
            "-c",
            (
                "import subprocess, time; "
                "cmd = ['/usr/sbin/logrotate', '-s', '/tmp/logrotate.status', '/etc/logrotate.d/traefik']; "
                "\nwhile True:\n"
                "    subprocess.run(cmd, check=False)\n"
                "    time.sleep(3600)\n"
            ),
        ],
        start_new_session=True,
    )


def start_traefik(static_config):
    log_info("Starting Traefik reverse proxy")
    os.execvp("traefik", ["traefik", f"--configFile={static_config}"])


def main():
    prepare_runtime()
    render_config()

    options = load_options()
    static_config = resolve_static_config(options)
    validate_tls_files(options)
    validate_traefik_config(static_config)

    logrotate = start_logrotate_background()
    signal.signal(signal.SIGTERM, lambda *_: logrotate.terminate())

    start_traefik(static_config)


if __name__ == "__main__":
    main()
