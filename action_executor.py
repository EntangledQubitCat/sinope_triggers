"""
Action Executor
Handles execution of various action types including keyboard, command, and sleep actions
"""

import logging
import time
import subprocess
import keyboard
import os

logger = logging.getLogger(__name__)

REPEAT_DELAY_IN_SECONDS = 0.35


class ConditionChecker:
    """Checks conditions before executing actions"""
    
    @staticmethod
    def check(condition: dict) -> bool:
        """
        Check if a condition is met.
        
        Args:
            condition: Dictionary describing the condition to check
            
        Returns:
            bool: True if condition passes, False otherwise
        """
        if not condition:
            return True  # No condition means always execute
        
        condition_type = condition.get("type")
        
        try:
            if condition_type == "ping":
                return ConditionChecker._check_ping(condition)
            else:
                logger.warning(f"Unknown condition type: {condition_type}")
                return True  # Unknown condition type, default to execute
        
        except Exception as e:
            logger.exception(f"Error checking condition {condition}: {e}")
            return False  # Error checking condition, default to not execute
    
    @staticmethod
    def _check_ping(condition: dict) -> bool:
        """Check if a host responds to ping"""
        host = condition.get("host")
        count = condition.get("count", 1)
        timeout_ms = condition.get("timeout", 100)
        
        logger.info(f"Checking ping condition: {host} (count={count}, timeout={timeout_ms}ms)")
        
        # Build ping command based on OS
        if os.name == 'nt':  # Windows
            ping_cmd = f"ping -n {count} -w {timeout_ms} {host}"
        else:  # Linux/Mac
            timeout_sec = timeout_ms / 1000.0
            ping_cmd = f"ping -c {count} -W {timeout_sec} {host}"
        
        result = subprocess.run(ping_cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✓ Ping condition met: {host} is reachable")
            return True
        else:
            logger.info(f"✗ Ping condition not met: {host} is not reachable")
            return False


class ActionExecutor:
    """Executes individual actions"""
    
    def __init__(self):
        self.condition_checker = ConditionChecker()
    
    def execute(self, action: dict):
        """
        Execute a single action.
        
        Args:
            action: Dictionary describing the action to execute
        """
        # Skip disabled actions
        if not action.get("enabled", True):
            logger.debug(f"Skipping disabled action: {action}")
            return
        
        # Check condition if present
        condition = action.get("condition")
        if condition and not self.condition_checker.check(condition):
            logger.info(f"Skipping action due to condition not met: {action.get('action_type')}")
            return
        
        action_type = action.get("action_type")
        
        try:
            if action_type == "keyboard":
                self._execute_keyboard(action)
            elif action_type == "command":
                self._execute_command(action)
            elif action_type == "sleep":
                self._execute_sleep(action)
            else:
                logger.warning(f"Unknown action_type: {action_type}")
        
        except Exception as e:
            logger.exception(f"Error executing action {action}: {e}")
    
    def _execute_keyboard(self, action: dict):
        """Execute a keyboard action"""
        key = action.get("key")
        repeat = action.get("repeat", 1)
        logger.info(f"Executing keyboard action: '{key}' x{repeat}")
        
        for i in range(repeat):
            keyboard.press_and_release(key)
            if i < repeat - 1:  # Don't delay after last repeat
                time.sleep(REPEAT_DELAY_IN_SECONDS)
    
    def _execute_command(self, action: dict):
        """Execute a shell command"""
        command = action.get("command")
        repeat = action.get("repeat", 1)
        logger.info(f"Executing command: '{command}' x{repeat}")
        
        for i in range(repeat):
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            logger.info(f"Command exit code: {result.returncode}")
            if result.stdout:
                logger.info(f"stdout:\n{result.stdout}")
            if result.stderr:
                logger.info(f"stderr:\n{result.stderr}")
            if i < repeat - 1:  # Don't delay after last repeat
                time.sleep(REPEAT_DELAY_IN_SECONDS)
    
    def _execute_sleep(self, action: dict):
        """Execute a sleep/delay action"""
        seconds = action.get("seconds", 0)
        logger.info(f"Sleeping for {seconds} seconds")
        time.sleep(seconds)