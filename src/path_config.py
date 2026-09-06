"""Compatibility asset locations for the staged modules.

New code should import assets from ``agent_platform_contracts.assets_api``.
This module remains temporarily for the existing stage tests while they are
migrated to the installed package API.
"""

from importlib.resources import files

B0_ASSETS = files("agent_platform_contracts").joinpath("assets")
B0_EXAMPLES = B0_ASSETS.joinpath("examples")
