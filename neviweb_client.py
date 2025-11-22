"""
Neviweb API Client
Handles authentication and communication with the Neviweb smart thermostat API
"""

import requests
import logging
import atexit
import time
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://neviweb.com"
LOGIN_URL = f"{BASE_URL}/api/login"
LOGOUT_URL = f"{BASE_URL}/api/logout"
DEVICE_LIST_URL = f"{BASE_URL}/api/devices"
DEVICE_DATA_URL = f"{BASE_URL}/api/device"
TIMEOUT = 30


class NeviwebClient:
    """Client for interacting with the Neviweb API"""
    
    def __init__(self, email: str, password: str, network: Optional[str] = None, location_id: Optional[str] = None):
        self.email = email
        self.password = password
        self.network_name = network
        self.session = requests.Session()
        self.session_id = None
        self.network_id = location_id
        self.devices = []

        atexit.register(self.safe_cleanup)

    def safe_cleanup(self):
        """Cleanup on exit"""
        try:
            self.disconnect()
        except Exception:
            pass

    def login(self, stay_connected: int = 1) -> bool:
        """
        Login to Neviweb and establish a session.
        Handles ACCSESSEXC (too many sessions) by forcing logout and retrying.
        
        Returns:
            bool: True if login successful, False otherwise
        """
        logger.info("Logging in to Neviweb...")
        payload = {
            "username": self.email,
            "password": self.password,
            "interface": "neviweb",
            "stayConnected": stay_connected
        }

        try:
            resp = self.session.post(LOGIN_URL, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()
            result = resp.json()
        except Exception as e:
            logger.error(f"Login request failed: {e}")
            return False

        # Success path
        if isinstance(result, dict) and "session" in result:
            self.session_id = result["session"]
            self.session.headers.update({"Session-Id": self.session_id})
            logger.info(f"✓ Login successful. Session ID: {self.session_id[:20]}...")
            return True

        # Too many sessions? try forced logout then retry once
        if isinstance(result, dict) and result.get("error", {}).get("code") == "ACCSESSEXC":
            logger.warning(f"Too many active sessions: {result}. Attempting to clear sessions and retry.")
            try:
                self.session.post(LOGOUT_URL, timeout=10)
                time.sleep(2)
            except Exception:
                pass

            try:
                resp2 = self.session.post(LOGIN_URL, json=payload, timeout=TIMEOUT)
                resp2.raise_for_status()
                result2 = resp2.json()
            except Exception as e:
                logger.error(f"Retry login request failed: {e}")
                return False

            if isinstance(result2, dict) and "session" in result2:
                self.session_id = result2["session"]
                self.session.headers.update({"Session-Id": self.session_id})
                logger.info("✓ Login successful on retry.")
                return True

            logger.error(f"Retry login failed: {result2}")
            return False

        logger.error(f"Login failed: {result}")
        return False

    def get_devices(self) -> bool:
        """
        Fetch the list of devices from Neviweb.
        
        Returns:
            bool: True if devices retrieved successfully, False otherwise
        """
        logger.info("Fetching devices...")
        try:
            url = f"{DEVICE_LIST_URL}?location$id={self.network_id}"
            resp = self.session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Failed to get devices: {e}")
            return False

        if isinstance(data, dict) and "error" in data:
            logger.error(f"API Error while fetching devices: {data}")
            return False

        self.devices = data if isinstance(data, list) else []
        if not self.devices:
            logger.error("No devices found.")
            return False

        logger.info(f"✓ Found {len(self.devices)} device(s)")
        for dev in self.devices:
            logger.info(f"  - {dev.get('name')} (ID: {dev.get('id')}, Type: {dev.get('sku')})")
        return True

    def get_device_attributes(self, device_id: str, attributes: list):
        """
        Get specific attributes for a device.
        
        Args:
            device_id: The device ID to query
            attributes: List of attribute names to retrieve
            
        Returns:
            dict or None: Device attributes or None on error
        """
        try:
            attrs_str = ",".join(attributes)
            url = f"{DEVICE_DATA_URL}/{device_id}/attribute?attributes={attrs_str}"
            resp = self.session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to get device attributes: {e}")
            return None

    def disconnect(self):
        """Logout from Neviweb and clear session"""
        if not self.session_id:
            return
        logger.info("Disconnecting from Neviweb...")
        try:
            # include header if available
            headers = {"Session-Id": self.session_id} if self.session_id else {}
            self.session.post(LOGOUT_URL, headers=headers, timeout=TIMEOUT)
            logger.info("✓ Disconnected")
        except Exception:
            pass
        finally:
            # clear session id to indicate logged out
            self.session_id = None
            self.session.headers.pop("Session-Id", None)


class Thermostat:
    """Represents a Neviweb thermostat device"""
    
    def __init__(self, client: NeviwebClient, device: dict):
        self.client = client
        self.device_id = device.get("id")
        self.name = device.get("name")
        self.device_info = device

    def get_all_info(self):
        """
        Get all relevant information from the thermostat.
        
        Returns:
            dict: Thermostat attributes including temperature, setpoint, output, etc.
        """
        attributes = [
            "roomTemperature",
            "roomSetpoint",
            "outputPercentDisplay",
            "temperatureFormat",
            "timeFormat",
            "occupancy",
            "heatingMode"
        ]
        return self.client.get_device_attributes(self.device_id, attributes)

    def get_output_percent(self, info: dict = None) -> int:
        """
        Extract the heater output percentage from device info.
        
        Args:
            info: Device info dict, or None to fetch fresh data
            
        Returns:
            int: Output percentage (0-100)
        """
        if info is None:
            info = self.get_all_info()
        
        if not info or not isinstance(info, dict):
            return 0
        
        try:
            return info.get("outputPercentDisplay", {}).get("percent", 0)
        except Exception:
            return 0