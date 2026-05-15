# Matter.js Server

Matter.js WebSocket Server for Home Assistant.

The add-on uses the official `ghcr.io/matter-js/matterjs-server` container as its base and adds a small Home Assistant add-on entrypoint that maps add-on options to Matter.js Server CLI flags.

## Defaults

```yaml
log_level: info
port: 5580
listen_address: ""
primary_interface: ""
bluetooth_adapter: null
vendor_id: 65521
fabric_id: 1
storage_path: /config/matterjs-server
disable_ota: true
disable_dashboard: false
production_mode: true
enable_test_net_dcl: false
run_as_root: false
extra_args: []
env_vars: []
```

OTA is disabled by default and test-net DCL is disabled. The server still needs local network access for Matter/mDNS and may access official Matter vendor/device certificate data when needed.

## Home Assistant Integration

After starting the add-on, add or reconfigure the Matter integration in Home Assistant.

The add-on declares Home Assistant Matter discovery metadata:

```yaml
discovery:
  - matter
```

Use this WebSocket URL when Home Assistant asks for a Matter Server URL:

```text
ws://localhost:5580/ws
```

On Home Assistant OS this is expected: both Home Assistant Core and this add-on run with access to the host network namespace, so Home Assistant can reach the Matter.js Server on the host loopback address.

## Networking

Matter requires local network discovery, IPv6, and mDNS. This add-on uses host networking and host D-Bus so LAN devices can discover and communicate with the Matter controller.

Do not move this add-on to Docker bridge-only networking for production Matter use. Bridge networking can make Home Assistant-to-server traffic work, but it commonly breaks external Matter device discovery and Thread/Wi-Fi communication.

By default the WebSocket API listens on port `5580`. If you need to restrict the listening address, set:

```yaml
listen_address: 127.0.0.1
```

If the host has multiple LAN interfaces, set the interface Matter should prefer for mDNS and device communication:

```yaml
primary_interface: eth0
```

## Version

The add-on currently wraps:

```text
ghcr.io/matter-js/matterjs-server:stable
```

To move to another Matter.js Server image tag, update:

- `MATTERJS_SERVER_VERSION` in `Dockerfile`
