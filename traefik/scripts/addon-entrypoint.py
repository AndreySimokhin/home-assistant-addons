#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path


CONFIG_DIR = Path("/config/traefik")
STATIC_CONFIG = CONFIG_DIR / "traefik.yaml"
OPTIONS_FILE = Path("/data/options.json")
LOGROTATE_CONFIG = Path("/etc/logrotate.d/traefik")
LOGROTATE_STATUS = Path("/tmp/logrotate.status")
STOP_EVENT = threading.Event()


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
        STOP_EVENT.wait(300)
        log_error(message)


def load_options():
    with OPTIONS_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def log_paths(options):
    return (
        Path(options["logs"]["access_file"]),
        Path(options["logs"]["error_file"]),
    )


def prepare_runtime(options):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    for log_file in log_paths(options):
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.touch(exist_ok=True)
        os.chown(log_file, 0, 0)
        log_file.chmod(0o644)

    if acme_enabled(options):
        storage = Path(options["tls"]["acme"]["storage"])
        storage.parent.mkdir(parents=True, exist_ok=True)
        storage.touch(exist_ok=True)
        os.chown(storage, 0, 0)
        storage.chmod(0o600)

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
    if acme_enabled(options):
        validate_acme_options(options)
        return

    cert_file = Path(options["tls"]["cert_file"])
    key_file = Path(options["tls"]["key_file"])

    if not cert_file.is_file():
        fatal_wait(f"TLS is enabled but certificate file is missing: {cert_file}")
    if not key_file.is_file():
        fatal_wait(f"TLS is enabled but key file is missing: {key_file}")


def acme_enabled(options):
    return options["tls"]["enabled"] and options["tls"].get("acme", {}).get("enabled", False)


def validate_acme_options(options):
    acme = options["tls"]["acme"]
    if not options["https_enabled"]:
        fatal_wait("TLS ACME is enabled but https_enabled is false.")
    if not acme.get("email"):
        fatal_wait("TLS ACME is enabled but tls.acme.email is empty.")
    if acme["challenge"] == "http" and not options["http_enabled"]:
        fatal_wait("TLS ACME HTTP challenge requires http_enabled: true.")


def run_logrotate_loop():
    while not STOP_EVENT.is_set():
        subprocess.run(
            ["/usr/sbin/logrotate", "-s", str(LOGROTATE_STATUS), str(LOGROTATE_CONFIG)],
            check=False,
        )
        STOP_EVENT.wait(3600)


def mirror_log_file(log_file):
    log_file.touch(exist_ok=True)
    with log_file.open("r", encoding="utf-8", errors="replace") as file:
        file.seek(0, os.SEEK_END)
        while not STOP_EVENT.is_set():
            line = file.readline()
            if line:
                print(line.rstrip(), flush=True)
            else:
                STOP_EVENT.wait(0.5)


def start_thread(target, *args):
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()
    return thread


def stop_process(process, timeout=10):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def start_traefik(static_config):
    log_info("Starting Traefik reverse proxy")
    traefik = subprocess.Popen(["traefik", f"--configFile={static_config}"])

    def stop(_signum, _frame):
        STOP_EVENT.set()
        stop_process(traefik)
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    exit_code = traefik.wait()
    STOP_EVENT.set()
    fatal_wait(f"Traefik exited unexpectedly with code {exit_code}. Check the Traefik logs above.")


def main():
    options = load_options()
    prepare_runtime(options)
    render_config()

    static_config = resolve_static_config(options)
    validate_tls_files(options)

    start_thread(run_logrotate_loop)
    if options["logs"].get("mirror_to_stdout", True):
        access_log, error_log = log_paths(options)
        start_thread(mirror_log_file, access_log)
        start_thread(mirror_log_file, error_log)

    start_traefik(static_config)


if __name__ == "__main__":
    main()
