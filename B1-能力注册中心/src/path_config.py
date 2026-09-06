"""B1 能力注册中心 - 路径配置

统一管理 B0 模块的路径引用。
所有需要导入 B0 模块的文件都应使用此配置。
"""

import sys
from pathlib import Path

# 项目根目录
B1_ROOT = Path(__file__).resolve().parents[1]

# B0 权威契约包（运行时和资源文件统一从 contracts 来源读取）
B0_BASE = (
    B1_ROOT.parent
    / "B0-契约基础"
    / "contracts"
    / "B0_agent_platform_contracts_v0.2.0"
    / "agent-platform-contracts-v0.2.0"
)

# B0 模块路径（用于 Python import）
B0_ROOT = B0_BASE / "src"

# B0 示例目录
B0_EXAMPLES = B0_BASE / "examples"

# 添加到 Python 路径
def setup_paths():
    """设置所有必要的 Python 路径"""
    if str(B1_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(B1_ROOT / "src"))
    if str(B0_ROOT) not in sys.path:
        sys.path.insert(0, str(B0_ROOT))

# 自动设置
setup_paths()
