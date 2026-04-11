import importlib.util
import os
import sys

# Get the absolute path to the speedtest module
module_path = os.path.join(os.path.dirname(__file__), "src", "cloudmesh", "ai", "command", "speedtest.py")
module_name = "cloudmesh.ai.command.speedtest"

# Load the module directly from the file path
spec = importlib.util.spec_from_file_location(module_name, module_path)
speedtest_module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = speedtest_module
spec.loader.exec_module(speedtest_module)

# Export the entry_point for the registry
entry_point = speedtest_module.entry_point