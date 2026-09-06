"""B3 Context 引擎 - 路径配置"""

import sys
from pathlib import Path

B3_ROOT = Path(__file__).resolve().parents[1]
B0_BASE = (
    B3_ROOT.parent
    / "B0-契约基础"
    / "contracts"
    / "B0_agent_platform_contracts_v0.2.0"
    / "agent-platform-contracts-v0.2.0"
)
B0_ROOT = B0_BASE / "src"
B0_EXAMPLES = B0_BASE / "examples"


def setup_paths():
    if str(B3_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(B3_ROOT / "src"))
    if str(B0_ROOT) not in sys.path:
        sys.path.insert(0, str(B0_ROOT))


setup_paths()
