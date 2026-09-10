import os
import sys

# Suite stays offline even when the operator .env enables the live sink;
# live tests opt in per-test via monkeypatched LANGFUSE_LIVE=1.
os.environ["LANGFUSE_LIVE"] = "0"

# Suite pins the default time budget: main.py load_dotenv() must not let
# the operator .env override it (load_dotenv never overrides existing vars).
os.environ["PORTFOLIO_TIME_BUDGET_S"] = "60.0"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
