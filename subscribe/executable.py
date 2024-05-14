import platform
import sys

from logger import logger


def which_bin() -> tuple[str, str]:
    operating_system = str(platform.platform())
    if operating_system.startswith("macOS"):
        if "arm64" in operating_system:
            clashname = "clash-darwin-arm"
        else:
            clashname = "clash-darwin-amd"

        subconverter = "subconverter-darwin"
    elif operating_system.startswith("Linux"):
        clashname = "clash-linux"
        subconverter = "subconverter-linux"
    elif operating_system.startswith("Windows"):
        clashname = "clash-windows.exe"
        subconverter = "subconverter-windows.exe"
    else:
        logger.error("Unsupported Platform")
        sys.exit(1)

    return clashname, subconverter
