#!/usr/bin/env node
import { chownSync, lstatSync, mkdirSync, readFileSync, readdirSync } from "node:fs";
import { spawn } from "node:child_process";

const OPTIONS_FILE = "/data/options.json";
const SERVER = "/app/node_modules/matter-server/dist/esm/MatterServer.js";
const APP_UID = 1000;
const APP_GID = 1000;

function readOptions() {
  try {
    return JSON.parse(readFileSync(OPTIONS_FILE, "utf8"));
  } catch (error) {
    console.error(`[ERROR] Unable to read ${OPTIONS_FILE}: ${error.message}`);
    process.exit(1);
  }
}

function optionEnabled(value) {
  return value === true;
}

function addFlag(args, enabled, flag) {
  if (optionEnabled(enabled)) {
    args.push(flag);
  }
}

function addValue(args, value, flag) {
  if (value !== undefined && value !== null && String(value).trim() !== "") {
    args.push(flag, String(value));
  }
}

function applyEnvVars(envVars) {
  for (const item of envVars ?? []) {
    const separator = item.indexOf("=");
    if (separator <= 0) {
      continue;
    }
    process.env[item.slice(0, separator)] = item.slice(separator + 1);
  }
}

function chownRecursive(path, uid, gid) {
  try {
    chownSync(path, uid, gid);
    const stat = lstatSync(path);
    if (!stat.isDirectory()) {
      return;
    }

    for (const entry of readdirSync(path, { withFileTypes: true })) {
      chownRecursive(`${path}/${entry.name}`, uid, gid);
    }
  } catch (error) {
    console.warn(`[WARNING] Unable to chown ${path}: ${error.message}`);
  }
}

function prepareStorage(storagePath, runAsRoot) {
  mkdirSync(storagePath, { recursive: true });

  if (!runAsRoot && typeof process.setuid === "function" && process.getuid?.() === 0) {
    chownRecursive(storagePath, APP_UID, APP_GID);

    try {
      process.setgid(APP_GID);
      process.setuid(APP_UID);
    } catch (error) {
      console.warn(`[WARNING] Unable to drop privileges to ${APP_UID}:${APP_GID}: ${error.message}`);
      console.warn("[WARNING] Continuing as root because the storage path or host permissions require it.");
    }
  }
}

function main() {
  const options = readOptions();
  const storagePath = options.storage_path || "/config/matterjs-server";
  const runAsRoot = optionEnabled(options.run_as_root);

  applyEnvVars(options.env_vars);
  prepareStorage(storagePath, runAsRoot);

  process.env.NODE_ENV = "production";
  process.env.DO_NOT_TRACK = "1";
  process.env.NO_UPDATE_NOTIFIER = "1";
  process.env.STORAGE_PATH = storagePath;
  process.env.LOG_LEVEL = options.log_level || "info";
  process.env.PORT = String(options.port || 5580);
  process.env.ENABLE_TEST_NET_DCL = optionEnabled(options.enable_test_net_dcl) ? "true" : "false";
  process.env.DISABLE_OTA = optionEnabled(options.disable_ota) ? "true" : "false";
  process.env.DISABLE_DASHBOARD = optionEnabled(options.disable_dashboard) ? "true" : "false";
  process.env.PRODUCTION_MODE = optionEnabled(options.production_mode) ? "true" : "false";

  const args = ["--enable-source-maps", SERVER];
  addValue(args, storagePath, "--storage-path");
  addValue(args, options.port || 5580, "--port");
  addValue(args, options.log_level || "info", "--log-level");
  addValue(args, options.listen_address, "--listen-address");
  addValue(args, options.primary_interface, "--primary-interface");
  addValue(args, options.bluetooth_adapter, "--bluetooth-adapter");
  addValue(args, options.vendor_id, "--vendorid");
  addValue(args, options.fabric_id, "--fabricid");
  addFlag(args, options.enable_test_net_dcl, "--enable-test-net-dcl");
  addFlag(args, options.disable_ota, "--disable-ota");
  addFlag(args, options.disable_dashboard, "--disable-dashboard");
  addFlag(args, options.production_mode, "--production-mode");

  for (const extraArg of options.extra_args ?? []) {
    if (String(extraArg).trim() !== "") {
      args.push(String(extraArg));
    }
  }

  console.log(`[INFO] Starting Matter.js Server on port ${process.env.PORT}`);
  console.log(`[INFO] Storage path: ${storagePath}`);
  console.log(`[INFO] OTA updates: ${optionEnabled(options.disable_ota) ? "disabled" : "enabled"}`);
  console.log(`[INFO] Test-net DCL: ${optionEnabled(options.enable_test_net_dcl) ? "enabled" : "disabled"}`);

  const child = spawn("node", args, {
    stdio: "inherit",
    env: process.env,
  });

  const forwardSignal = (signal) => {
    child.kill(signal);
  };

  process.on("SIGTERM", () => forwardSignal("SIGTERM"));
  process.on("SIGINT", () => forwardSignal("SIGINT"));

  child.on("exit", (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
    }
    process.exit(code ?? 1);
  });
}

main();
