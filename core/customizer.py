import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List
from core.chroot_manager import ChrootManager
from core.logger_setup import setup_logger

logger = setup_logger("customizer")

class SystemCustomizer:
    def __init__(self, chroot: ChrootManager, config: Dict[str, Any]):
        self.chroot = chroot
        self.config = config
        self.target_root = chroot.target_root

    def setup_live_users(self):
        live_user_cfg = self.config.get("live_user", {})
        username = live_user_cfg.get("username", "gentoo")
        groups = live_user_cfg.get("groups", ["wheel", "audio", "video", "input", "plugdev"])
        groups_str = ",".join(groups)

        logger.info(f"Setting up live user '{username}' with groups: {groups_str}")

        if self.chroot.mode == "mock":
            logger.info(f"[MOCK CUSTOMIZER] Adding user {username}")
            return

        # Ensure groups exist and create user
        self.chroot.run_in_chroot(f"groupadd -f {username}")
        user_cmd = f"useradd -m -g {username} -G {groups_str} -s /bin/bash {username}"
        self.chroot.run_in_chroot(user_cmd)

        # Allow passwordless sudo for wheel group
        sudoers_file = self.target_root / "etc" / "sudoers.d" / "live_user"
        sudoers_file.parent.mkdir(parents=True, exist_ok=True)
        sudoers_file.write_text(f"{username} ALL=(ALL) NOPASSWD: ALL\n")
        os.chmod(sudoers_file, 0o440)

    def setup_services(self):
        services = self.config.get("services", [])
        if not services:
            return

        logger.info(f"Enabling OpenRC services: {', '.join(services)}")

        if self.chroot.mode == "mock":
            logger.info(f"[MOCK CUSTOMIZER] Enabling services: {services}")
            return

        for srv in services:
            self.chroot.run_in_chroot(f"rc-update add {srv} default")

    def configure_system_defaults(self):
        logger.info("Applying Gentoo live system defaults (hostname, sshd, fstab, timezone)...")
        if self.chroot.mode == "mock":
            logger.info("[MOCK CUSTOMIZER] Setting up livecd defaults")
            return

        # Hostname
        hostname_path = self.target_root / "etc" / "conf.d" / "hostname"
        hostname_path.parent.mkdir(parents=True, exist_ok=True)
        hostname_path.write_text('hostname="gentoo-live"\n')

        # Fstab
        fstab_path = self.target_root / "etc" / "fstab"
        fstab_path.write_text(
            "# LiveCD fstab\n"
            "tmpfs / tmpfs defaults 0 0\n"
        )

        # SSHD PermitRootLogin if sshd_config exists
        sshd_cfg = self.target_root / "etc" / "ssh" / "sshd_config"
        if sshd_cfg.exists():
            content = sshd_cfg.read_text()
            content = content.replace("#PermitRootLogin prohibit-password", "PermitRootLogin yes")
            sshd_cfg.write_text(content)
