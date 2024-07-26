import platform
import sys

from logger import logger


def which_bin() -> tuple[str, str]:
    cpu_arch = get_cpu_architecture()
    if cpu_arch not in ["amd", "arm"]:
        logger.error(f"subconverter does not support current cpu architecture: {cpu_arch}")
        sys.exit(1)

    operating_system = platform.system()
    if operating_system not in ["Windows", "Linux", "Darwin"]:
        logger.error(f"subconverter does not support current operating system: {operating_system}")
        sys.exit(1)

    if operating_system == "Windows" and cpu_arch != "amd":
        logger.error(f"the windows version of subconverter only supports amd64 architecture, current: {cpu_arch}")
        sys.exit(1)

    clashname = f"clash-{operating_system.lower()}-{cpu_arch}"
    subconverter = f"subconverter-{operating_system.lower()}-{cpu_arch}"

    if operating_system == "Windows":
        clashname += ".exe"
        subconverter += ".exe"

    return clashname, subconverter


def get_cpu_architecture() -> str:
    machine = platform.machine()
    if "x86_64" in machine or "AMD64" in machine:
        return "amd"
    elif "x86" in machine or "i386" in machine or "i686" in machine:
        return "x86"
    elif "arm" in machine or "aarch64" in machine:
        return "arm"
    else:
        return "unknown"
