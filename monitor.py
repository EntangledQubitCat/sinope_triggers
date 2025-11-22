#!/usr/bin/env python3
"""
Neviweb Thermostat Monitor / Trigger Tool
Main entry point - orchestrates the monitoring and triggering system
"""

import argparse
import json
import logging
import time
from pathlib import Path

from neviweb_client import NeviwebClient, Thermostat
from trigger_manager import TriggerManager

# ---------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# =========================================================
#  Load Configuration File
# =========================================================
def load_config(path="config.json"):
    if not Path(path).exists():
        raise FileNotFoundError(f"Configuration file '{path}' not found.")

    with open(path, "r") as f:
        data = json.load(f)

    if "auth" not in data or "settings" not in data:
        raise ValueError("config.json must contain 'auth' and 'settings' sections.")

    return data


# =========================================================
#  Reconnect Helper
# =========================================================
def reconnect(client: NeviwebClient, max_attempts=6, base_delay=5) -> bool:
    """Attempt to gracefully reconnect, with exponential backoff on failures."""
    logger.warning("Reconnecting to Neviweb...")
    client.disconnect()
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        try:
            logger.info(f"Reconnect attempt {attempt}...")
            if not client.login():
                raise RuntimeError("login failed")
            if not client.get_devices():
                raise RuntimeError("get_devices failed")
            logger.info("✓ Reconnected successfully.")
            return True
        except Exception as e:
            delay = base_delay * (2 ** (attempt - 1))
            logger.error(f"Reconnect attempt {attempt} failed: {e}. Sleeping {delay}s before retry.")
            time.sleep(delay)
    logger.error("All reconnect attempts failed.")
    return False


# =========================================================
#  MAIN
# =========================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-mode", choices=["once", "monitor", "trigger"], default="monitor")
    parser.add_argument("-config", default="config.json")
    parser.add_argument("-interval", type=int, help="Override config check_interval (seconds)")
    args = parser.parse_args()

    config = load_config(args.config)
    auth = config["auth"]
    settings = config["settings"]
    triggers_config = config.get("triggers", {})

    # Use check_interval, fall back to interval for backwards compatibility
    interval = args.interval if args.interval is not None else settings.get("check_interval", settings.get("interval", 10))

    print("=" * 60)
    print("Neviweb Thermostat Monitor")
    print("=" * 60)

    # Initialize client
    client = NeviwebClient(
        auth["email"],
        auth["password"],
        location_id=auth.get("locationId")
    )

    # Initial connect
    if not client.login():
        logger.error("Initial login failed. Exiting.")
        return
    if not client.get_devices():
        logger.error("Initial device fetch failed. Exiting.")
        return

    device = next((d for d in client.devices if str(d.get("id")) == str(auth.get("deviceId"))), None)
    if not device:
        logger.error("Device ID not found.")
        return

    thermostat = Thermostat(client, device)

    # One-shot mode
    if args.mode == "once":
        info = thermostat.get_all_info()
        print(json.dumps(info, indent=2))
        client.disconnect()
        return

    # Initialize trigger manager for trigger mode
    trigger_manager = None
    if args.mode == "trigger":
        trigger_manager = TriggerManager(triggers_config)

    # Continuous mode
    last_percent = None

    try:
        while True:
            info = thermostat.get_all_info()

            # If info is None -> network/HTTP error occurred; try reconnect
            if info is None:
                logger.error("No response from API (None). Attempting reconnect.")
                if not reconnect(client):
                    logger.error("Reconnect failed; sleeping then retrying main loop.")
                    time.sleep(interval)
                    continue
                # re-select device in case device list changed during reconnect
                device = next((d for d in client.devices if str(d.get("id")) == str(auth.get("deviceId"))), None)
                if not device:
                    logger.error("Device ID not found after reconnect.")
                    time.sleep(interval)
                    continue
                thermostat = Thermostat(client, device)
                time.sleep(interval)
                continue

            # If API returned an error object, handle it
            if isinstance(info, dict) and "error" in info:
                err_code = info["error"].get("code")
                logger.warning(f"API returned error: {info}")
                # Session expired or user session expired
                if err_code in ("USRSESSEXP", "SESSION_EXPIRED", "SESSIONINVALID"):
                    logger.info(f"Session expired ({err_code}) — attempting reconnect.")
                    if not reconnect(client):
                        logger.error("Reconnect after session expiry failed.")
                        time.sleep(interval)
                        continue
                    # re-fetch device object and thermostat
                    device = next((d for d in client.devices if str(d.get("id")) == str(auth.get("deviceId"))), None)
                    if not device:
                        logger.error("Device ID not found after reconnect.")
                        time.sleep(interval)
                        continue
                    thermostat = Thermostat(client, device)
                    time.sleep(interval)
                    continue
                # Too many sessions returned from API anywhere
                if err_code == "ACCSESSEXC":
                    logger.info("API reports too many sessions (ACCSESSEXC). Forcing reconnect.")
                    if not reconnect(client):
                        time.sleep(interval)
                        continue
                    time.sleep(interval)
                    continue
                # Unknown API error: try reconnect anyway after short sleep
                logger.info("Unknown API error — attempting reconnect.")
                if not reconnect(client):
                    time.sleep(interval)
                    continue
                time.sleep(interval)
                continue

            # At this point info should be a normal dict with attributes or partial attributes
            # Safely extract percent, default to 0 when missing
            percent = 0
            try:
                percent = info.get("outputPercentDisplay", {}).get("percent", 0)
            except Exception:
                percent = 0

            if "outputPercentDisplay" not in info:
                logger.warning("API omitted outputPercentDisplay — assuming 0%")
                logger.debug(json.dumps(info, indent=2))

            print("\n" + "=" * 60)
            print(f"Thermostat: {thermostat.name}")
            print("=" * 60)
            print(json.dumps(info, indent=2))

            # TRIGGER LOGIC (only active in trigger mode)
            if args.mode == "trigger" and trigger_manager:
                try:
                    # Ensure we only trigger when we have a last_percent to compare to
                    if last_percent is not None:
                        # Heat ON (0 -> >0)
                        if last_percent == 0 and percent > 0:
                            logger.info("Heat ON detected")
                            trigger_manager.execute_trigger("on_heater_on")
                        # Heat OFF (>0 -> 0)
                        elif last_percent > 0 and percent == 0:
                            logger.info("Heat OFF detected")
                            trigger_manager.execute_trigger("on_heater_off")
                    # update last_percent
                    last_percent = percent
                except Exception as e:
                    logger.exception(f"Error during trigger handling: {e}")

            # Sleep until next poll
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nCtrl-C received → exiting gracefully...")

    finally:
        client.disconnect()


if __name__ == "__main__":
    main()