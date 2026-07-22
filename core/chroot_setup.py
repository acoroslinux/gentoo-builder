import os
import shutil
from pathlib import Path
from core.logger_setup import setup_logger

logger = setup_logger("chroot_setup")

class ChrootSetup:
    def __init__(self, target_root: Path, mode: str = "mock"):
        self.target_root = Path(target_root).resolve()
        self.mode = mode.lower()

    def prepare_resolv_conf(self):
        """Copy host's /etc/resolv.conf into chroot for network connectivity."""
        if self.mode == "mock":
            logger.info("[MOCK CHROOT SETUP] Copying /etc/resolv.conf")
            return

        host_resolv = Path("/etc/resolv.conf")
        target_resolv = self.target_root / "etc" / "resolv.conf"

        if host_resolv.exists():
            logger.info("Copying host /etc/resolv.conf into chroot...")
            target_resolv.parent.mkdir(parents=True, exist_ok=True)
            if target_resolv.is_symlink() or target_resolv.exists():
                target_resolv.unlink(missing_ok=True)
            shutil.copy2(host_resolv, target_resolv)

    def prepare_default_profile_symlink(self):
        """Ensure /etc/portage/make.profile points to a valid profile if missing."""
        if self.mode == "mock":
            logger.info("[MOCK CHROOT SETUP] Ensuring make.profile symlink")
            return

        profile_link = self.target_root / "etc" / "portage" / "make.profile"
        default_profile_target = "../var/db/repos/gentoo/profiles/default/linux/amd64/23.0/split-usr"

        if not profile_link.exists() and not profile_link.is_symlink():
            logger.info("Creating default profile symlink for Gentoo Portage...")
            profile_link.parent.mkdir(parents=True, exist_ok=True)
            try:
                profile_link.symlink_to(default_profile_target)
            except Exception as e:
                logger.warning(f"Could not create make.profile symlink: {e}")
