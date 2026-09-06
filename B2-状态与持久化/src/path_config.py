"""B2 状态与持久化 - 路径配置"""

import sys
from pathlib import Path

B2_ROOT = Path(__file__).resolve().parents[1]
B1_ROOT = B2_ROOT.parent / "B1-能力注册中心"
B0_BASE = (
    B2_ROOT.parent
    / "B0-契约基础"
    / "contracts"
    / "B0_agent_platform_contracts_v0.2.0"
    / "agent-platform-contracts-v0.2.0"
)
B0_ROOT = B0_BASE / "src"
B0_EXAMPLES = B0_BASE / "examples"

def setup_paths():
    if str(B2_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(B2_ROOT / "src"))
    if str(B1_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(B1_ROOT / "src"))
    if str(B0_ROOT) not in sys.path:
        sys.path.insert(0, str(B0_ROOT))

setup_paths()
