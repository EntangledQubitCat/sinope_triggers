# sinope_triggers
Trigger implementation for sinope thermostats. Useful for volume control when the heater is running.

# Set up
Update config.json with your username, password, location, device id. You can obtain these from https://neviweb.com/locations/{location}/devices/{device} if you login.

# Default configuration
The default configuration adjusts your computer's volume using the keyboard library.

# LGTVCompanion
Has been tested with the following tool for LGTVs: https://github.com/JPersson77/LGTVCompanion. Replace the config.json with config_lgtvcompanion.json.

We restart the LGTVsvc service when waking from sleep due to occasional crash issues with the service. This may require administrator privileges, but you can remove these actions if you don't want to do this.

# Invocation
```
python monitor.py -mode trigger
```
