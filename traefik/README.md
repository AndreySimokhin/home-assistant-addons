# Traefik Reverse Proxy Add-on

Production-oriented Traefik v3 reverse proxy for Home Assistant OS.

## Current capabilities

- Reverse proxy to `homeassistant:8123`
- HTTP and HTTPS entrypoints with configurable ports
- Existing certificate support via `/ssl/fullchain.pem` and `/ssl/privkey.pem`
- File provider with dynamic reload
- WebSocket and SSE friendly timeouts
- HTTP/2 on the HTTPS entrypoint
- Persistent access and error logs under `/share/traefik`
- User-selected Traefik middlewares through dynamic configuration
- Optional Traefik dashboard, disabled externally by default
- User-managed dynamic config files in `/config/traefik/dynamic/*.yaml`
- Raw advanced escape hatches via `custom.extra_static_config` and `custom.extra_dynamic_config`
- No Docker socket, privileged mode, host networking, host firewall control, or iptables dependency

## Default ports

The add-on listens inside the container on:

- `80/tcp` for HTTP
- `443/tcp` for HTTPS

Traefik listens on `http_port` and `https_port` from the add-on options. If you change those internal ports, update the `ports` keys in `config.yaml` to the same container ports. Home Assistant Supervisor can only publish ports declared by the add-on.

## TLS

By default TLS is enabled with existing certificate files and expects:

- `/ssl/fullchain.pem`
- `/ssl/privkey.pem`

If those files are missing, the add-on logs a clear error and waits instead of repeatedly crashing.

For automatic certificates, enable ACME:

```yaml
tls:
  enabled: true
  acme:
    enabled: true
    email: you@example.com
    resolver: letsencrypt
    storage: /config/traefik/acme/acme.json
    challenge: http
    http_entrypoint: web
    ca_server: ""
```

With `challenge: http`, Let's Encrypt must reach this add-on on public port `80`. With `challenge: tls`, Let's Encrypt must reach this add-on on public port `443`. Non-standard external ports like `8443` do not work for these ACME challenges. Use the Let's Encrypt staging CA in `ca_server` while testing to avoid rate limits:

```yaml
ca_server: https://acme-staging-v02.api.letsencrypt.org/directory
```

## Dashboard

The dashboard is disabled by default. Keep `dashboard.external` disabled unless you attach your own authentication middleware through `middlewares.dashboard`.

## Operational notes

Generated Traefik config is written to `/config/traefik`, which is persistent through add-on restarts and Home Assistant OS updates. Logs are written to `/share/traefik` and rotated hourly via logrotate.

By default, access and error logs are also mirrored to the add-on stdout with `logs.mirror_to_stdout: true`, so they appear in the Home Assistant add-on journal.

## File layout

The repository keeps source files in plain project directories and copies them into the image explicitly:

- `Dockerfile` builds a Home Assistant add-on image and copies the Traefik binary from the official Traefik image.
- `scripts/addon-entrypoint.py` prepares runtime directories, validates configuration, starts log rotation, and runs Traefik.
- `scripts/render-traefik-config.py` is a Python renderer that reads add-on options and writes final config to `/config/traefik`.
- `defaults/*.yaml` contains real base Traefik config files copied into the image as renderer input.

The final Traefik config is rendered at container start, not during Docker build, because Home Assistant add-on options are only available at runtime in `/data/options.json`.

## Traefik version

The Traefik binary version is configured at build time in:

```dockerfile
ARG TRAEFIK_VERSION=3.3.3
```

Change it in `Dockerfile`, or override it in CI/manual builds with `--build-arg TRAEFIK_VERSION=...`, then rebuild the add-on image.

## Dynamic configuration

The add-on writes the standard Home Assistant dynamic configuration to:

```text
/config/traefik/dynamic/00-homeassistant.yaml
```

Additional Traefik dynamic configuration can be added as separate YAML files in:

```text
/config/traefik/dynamic/
```

Traefik watches this directory and reloads file changes automatically. Files added directly to `/config/traefik/dynamic/` do not require an add-on restart.

Advanced static Traefik settings can be merged with `custom.extra_static_config`. Advanced dynamic settings from the add-on options can be merged with `custom.extra_dynamic_config`; changing add-on options requires restarting the add-on so the renderer can write the generated files again.

To attach custom middleware to the managed Home Assistant routers, define the middleware in dynamic config and reference it by name:

```yaml
middlewares:
  home_assistant:
    - my-security-headers
  dashboard:
    - dashboard-auth

custom:
  extra_dynamic_config: |
    http:
      middlewares:
        my-security-headers:
          headers:
            contentTypeNosniff: true
            referrerPolicy: strict-origin-when-cross-origin
        dashboard-auth:
          basicAuth:
            users:
              - "user:hashed-password"
```

For complete control over static Traefik configuration, set:

```yaml
custom:
  static_config_override_file: /config/traefik/custom-static.yaml
```

Static configuration cannot be hot-reloaded by Traefik. Changes to static config, static modules, ACME resolvers, entrypoints, or providers require restarting the add-on.
