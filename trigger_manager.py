"""
Trigger Manager
Manages and executes trigger sequences with support for parallel execution
"""

import logging
import threading
from action_executor import ActionExecutor

logger = logging.getLogger(__name__)


class TriggerManager:
    """Manages trigger configurations and execution"""
    
    def __init__(self, triggers_config: dict):
        """
        Initialize the trigger manager.
        
        Args:
            triggers_config: Dictionary containing trigger configurations
        """
        self.triggers = triggers_config
        self.executor = ActionExecutor()
    
    def execute_trigger(self, trigger_name: str):
        """
        Execute a named trigger sequence.
        
        Args:
            trigger_name: Name of the trigger to execute (e.g., "on_heater_on")
        """
        if trigger_name not in self.triggers:
            logger.warning(f"Trigger '{trigger_name}' not found in configuration")
            return
        
        actions = self.triggers[trigger_name]
        logger.info(f"→ Executing {trigger_name} triggers")
        self._execute_action_list(actions)
    
    def _execute_action_list(self, actions: list):
        """
        Execute a list of actions, handling parallel execution blocks.
        
        Args:
            actions: List of action dictionaries
        """
        if not actions:
            return
        
        for item in actions:
            # Check if this is a parallel block
            if isinstance(item, dict) and item.get("action_type") == "parallel":
                self._execute_parallel_block(item)
            else:
                # Regular sequential action
                self.executor.execute(item)
    
    def _execute_parallel_block(self, parallel_block: dict):
        """
        Execute a parallel block of actions.
        
        Args:
            parallel_block: Dictionary with action_type="parallel" and "actions" list
        """
        parallel_actions = parallel_block.get("actions", [])
        logger.info(f"Starting parallel execution of {len(parallel_actions)} actions")
        
        # Create threads for each action in the parallel block
        threads = []
        for action in parallel_actions:
            thread = threading.Thread(target=self.executor.execute, args=(action,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        logger.info("Parallel execution completed")