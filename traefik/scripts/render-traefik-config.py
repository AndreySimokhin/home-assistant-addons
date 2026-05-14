#!/usr/bin/env python3
import json
import os
from pathlib import Path

import yaml


CONFIG_DIR = Path(os.environ.get("TRAEFIK_CONFIG_DIR", "/config/traefik"))
DYNAMIC_DIR = CONFIG_DIR / "dynamic"
STATIC_CONFIG = CONFIG_DIR / "traefik.yaml"
HOME_ASSISTANT_CONFIG = DYNAMIC_DIR / "00-homeassistant.yaml"
OPTIONS_FILE = Path(os.environ.get("TRAEFIK_OPTIONS_FILE", "/data/options.json"))
LOGROTATE_CONFIG = Path(os.environ.get("TRAEFIK_LOGROTATE_CONFIG", "/etc/logrotate.d/traefik"))

DEFAULT_STATIC_CONFIG = Path("/usr/share/traefik-addon/defaults/traefik.yaml")
DEFAULT_HOME_ASSISTANT_CONFIG = Path("/usr/share/traefik-addon/defaults/00-homeassistant.yaml")


def load_yaml(path):
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(data, file, sort_keys=False, default_flow_style=False)


def load_options():
    with OPTIONS_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def deep_merge(base, override):
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def yaml_block(value):
    if not value:
        return {}
    loaded = yaml.safe_load(value)
    return loaded or {}


def log_format(options):
    return "json" if options["logs"]["json"] else "common"


def acme_enabled(options):
    return options["tls"]["enabled"] and options["tls"].get("acme", {}).get("enabled", False)


def router_tls_config(options):
    if not options["tls"]["enabled"]:
        return None
    if acme_enabled(options):
        return {"certResolver": options["tls"]["acme"]["resolver"]}
    return {}


def build_static_config(options):
    config = load_yaml(DEFAULT_STATIC_CONFIG)
    dynamic_provider_key = "directory" if options["custom"]["enable_dynamic_directory"] else "filename"
    dynamic_provider_value = str(DYNAMIC_DIR if dynamic_provider_key == "directory" else HOME_ASSISTANT_CONFIG)

    config["log"] = {
        "level": options["logs"]["level"],
        "filePath": options["logs"]["error_file"],
        "format": log_format(options),
    }
    config["providers"]["file"] = {
        dynamic_provider_key: dynamic_provider_value,
        "watch": True,
    }
    config["api"]["dashboard"] = options["dashboard"]["enabled"]
    config["entryPoints"] = {}
    config.pop("certificatesResolvers", None)

    if options["http_enabled"]:
        web = {
            "address": f":{options['http_port']}",
            "transport": {
                "respondingTimeouts": {
                    "readTimeout": "300s",
                    "writeTimeout": "300s",
                    "idleTimeout": "300s",
                }
            },
        }
        if options["redirect_http_to_https"] and options["https_enabled"] and options["tls"]["enabled"]:
            web["http"] = {
                "redirections": {
                    "entryPoint": {
                        "to": "websecure",
                        "scheme": "https",
                        "permanent": True,
                    }
                }
            }
        config["entryPoints"]["web"] = web

    if options["https_enabled"]:
        websecure = {
            "address": f":{options['https_port']}",
            "http2": {"maxConcurrentStreams": 250},
            "transport": {
                "respondingTimeouts": {
                    "readTimeout": "300s",
                    "writeTimeout": "300s",
                    "idleTimeout": "300s",
                }
            },
        }
        if options["tls"]["enabled"]:
            websecure["http"] = {"tls": {"options": "default"}}
        config["entryPoints"]["websecure"] = websecure

    config.pop("accessLog", None)
    if options["logs"]["access_enabled"]:
        config["accessLog"] = {
            "filePath": options["logs"]["access_file"],
            "format": log_format(options),
            "bufferingSize": 0,
            "fields": {
                "defaultMode": "keep",
                "headers": {"defaultMode": "keep"},
            },
        }

    modules = {
        module["name"]: {
            "moduleName": module["module_name"],
            "version": module["version"],
        }
        for module in options.get("experimental_modules", [])
        if module.get("enabled")
    }
    config.pop("experimental", None)
    if modules:
        config["experimental"] = {"plugins": modules}

    if acme_enabled(options):
        acme_options = options["tls"]["acme"]
        acme = {
            "email": acme_options["email"],
            "storage": acme_options["storage"],
        }
        if acme_options.get("ca_server"):
            acme["caServer"] = acme_options["ca_server"]
        if acme_options["challenge"] == "http":
            acme["httpChallenge"] = {"entryPoint": acme_options["http_entrypoint"]}
        elif acme_options["challenge"] == "tls":
            acme["tlsChallenge"] = {}

        config["certificatesResolvers"] = {
            acme_options["resolver"]: {
                "acme": acme,
            }
        }

    extra_static = yaml_block(options["custom"].get("extra_static_config"))
    if extra_static:
        deep_merge(config, extra_static)

    return config


def configured_middlewares(options, router_name):
    return options.get("middlewares", {}).get(router_name, [])


def build_dynamic_config(options):
    config = load_yaml(DEFAULT_HOME_ASSISTANT_CONFIG)
    http = {}
    http["serversTransports"] = {
        "ha-transport": {
            "forwardingTimeouts": {
                "dialTimeout": "30s",
                "responseHeaderTimeout": "0s",
                "idleConnTimeout": "300s",
            }
        }
    }

    domain = options["domain"]
    home_assistant_middlewares = configured_middlewares(options, "home_assistant")
    dashboard_middlewares = configured_middlewares(options, "dashboard")
    routers = {}

    if options["http_enabled"]:
        router = {
            "rule": f"Host(`{domain}`)",
            "entryPoints": ["web"],
            "service": "homeassistant",
        }
        if home_assistant_middlewares:
            router["middlewares"] = home_assistant_middlewares
        routers["homeassistant-http"] = router

    if options["https_enabled"]:
        tls_config = router_tls_config(options)
        router = {
            "rule": f"Host(`{domain}`)",
            "entryPoints": ["websecure"],
            "service": "homeassistant",
        }
        if home_assistant_middlewares:
            router["middlewares"] = home_assistant_middlewares
        if tls_config is not None:
            router["tls"] = tls_config
        routers["homeassistant-https"] = router

    if options["dashboard"]["enabled"] and options["dashboard"]["external"] and options["tls"]["enabled"]:
        tls_config = router_tls_config(options)
        router = {
            "rule": f"Host(`traefik.{domain}`)",
            "entryPoints": ["websecure"],
            "service": "api@internal",
            "tls": tls_config if tls_config is not None else {},
        }
        if dashboard_middlewares:
            router["middlewares"] = dashboard_middlewares
        routers["traefik-dashboard"] = router

    http["routers"] = routers
    http["services"] = {
        "homeassistant": {
            "loadBalancer": {
                "passHostHeader": options["home_assistant"]["pass_host_header"],
                "serversTransport": "ha-transport",
                "servers": [{"url": options["home_assistant"]["url"]}],
            }
        }
    }
    config["http"] = http

    config["tls"] = {
        "options": {
            "default": {
                "minVersion": options["tls"]["min_version"],
                "sniStrict": True,
            }
        }
    }
    if options["tls"]["enabled"]:
        if not acme_enabled(options):
            config["tls"]["certificates"] = [
                {
                    "certFile": options["tls"]["cert_file"],
                    "keyFile": options["tls"]["key_file"],
                }
            ]

    extra_dynamic = yaml_block(options["custom"].get("extra_dynamic_config"))
    if extra_dynamic:
        deep_merge(config, extra_dynamic)

    return config


def render_logrotate_config(options):
    LOGROTATE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    LOGROTATE_CONFIG.write_text(
        "\n".join(
            [
                f"{options['logs']['access_file']} {options['logs']['error_file']} {{",
                f"  size {options['logs']['rotate_size']}",
                f"  rotate {options['logs']['rotate_count']}",
                "  missingok",
                "  notifempty",
                "  copytruncate",
                "  compress",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main():
    options = load_options()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DYNAMIC_DIR.mkdir(parents=True, exist_ok=True)

    write_yaml(STATIC_CONFIG, build_static_config(options))
    write_yaml(HOME_ASSISTANT_CONFIG, build_dynamic_config(options))
    render_logrotate_config(options)

    print(f"Rendered Traefik static config in {STATIC_CONFIG}")
    print(f"Rendered Traefik dynamic config in {DYNAMIC_DIR}")


if __name__ == "__main__":
    main()
