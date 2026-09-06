"""Access packaged B0 contract assets without relying on source paths."""
from importlib.resources import files


def asset_path(relative_name: str):
    """Return a traversable packaged asset by its relative path."""
    if not relative_name or relative_name.startswith("/") or ".." in relative_name.split("/"):
        raise ValueError("relative_name must be a safe package-relative path")
    asset = files("agent_platform_contracts").joinpath("assets", relative_name)
    if not asset.is_file():
        raise FileNotFoundError(relative_name)
    return asset
