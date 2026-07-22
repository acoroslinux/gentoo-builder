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
        self.init_system = config.get("init_system", "openrc")
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

        self.chroot.run_in_chroot(f"groupadd -f {username}")
        user_cmd = f"useradd -m -g {username} -G {groups_str} -s /bin/bash {username}"
        self.chroot.run_in_chroot(user_cmd)

        sudoers_file = self.target_root / "etc" / "sudoers.d" / "live_user"
        sudoers_file.parent.mkdir(parents=True, exist_ok=True)
        sudoers_file.write_text(f"{username} ALL=(ALL) NOPASSWD: ALL\n")
        os.chmod(sudoers_file, 0o440)

    def setup_services(self):
        services = self.config.get("services", [])
        if not services:
            return

        logger.info(f"Enabling [{self.init_system.upper()}] services: {', '.join(services)}")

        if self.chroot.mode == "mock":
            logger.info(f"[MOCK CUSTOMIZER] Enabling {self.init_system} services: {services}")
            return

        for srv in services:
            if self.init_system == "systemd":
                self.chroot.run_in_chroot(f"systemctl enable {srv}")
            elif self.init_system == "openrc":
                self.chroot.run_in_chroot(f"rc-update add {srv} default")
            elif self.init_system == "runit":
                self.chroot.run_in_chroot(f"ln -s /etc/runit/runsvdir/all/{srv} /etc/runit/runsvdir/default/")
            elif self.init_system == "s6":
                self.chroot.run_in_chroot(f"s6-rc-bundle add default {srv}")

    def copy_custom_files(self):
        """Copia ficheiros estruturados de configs/custom_files/ para o chroot conforme especificado nas configs."""
        custom_files_list = self.config.get("custom_files", [])
        desktop_env = self.config.get("desktop_environment", {})
        
        if desktop_env and isinstance(desktop_env, dict):
            desktop_copy_files = desktop_env.get("copy_files", [])
            for item in desktop_copy_files:
                if item not in custom_files_list:
                    custom_files_list.append(item)

        if not custom_files_list:
            return

        logger.info(f"Copying {len(custom_files_list)} custom file entries from configs/custom_files/ into chroot...")
        
        if self.chroot.mode == "mock":
            for entry in custom_files_list:
                logger.info(f"[MOCK CUSTOMIZER] Copy file entry: {entry.get('source')} -> {entry.get('destination')}")
            return

        project_root = resolve_from_project("")
        custom_files_root = project_root / "configs" / "custom_files"

        # Resolve python version in chroot if {python_version} is present in destinations
        py_ver = "3.12"
        if self.chroot.mode == "real":
            python_dirs = list(self.target_root.glob("usr/lib/python3.*"))
            if python_dirs:
                py_ver = python_dirs[0].name.replace("python", "")

        for entry in custom_files_list:
            src_rel = entry.get("source")
            dest_rel = entry.get("destination")
            if not src_rel or not dest_rel:
                continue

            dest_rel = dest_rel.format(python_version=py_ver)
            src_path = custom_files_root / src_rel
            dest_path = self.target_root / dest_rel.lstrip("/")

            if not src_path.exists():
                logger.warning(f"Custom source path does not exist, skipping: {src_path}")
                continue

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if src_path.is_dir():
                shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
            else:
                shutil.copy2(src_path, dest_path)
            logger.info(f"Copied custom file: {src_rel} -> {dest_rel}")

            # Propagate files destination under /etc/skel/ to existing home directories
            if dest_rel.startswith("/etc/skel/"):
                rel_skel = dest_rel[len("/etc/skel/"):]
                home_dir = self.target_root / "home"
                if home_dir.exists():
                    for user_dir in home_dir.iterdir():
                        if user_dir.is_dir() and user_dir.name not in ["lost+found"]:
                            user_dest = user_dir / rel_skel
                            user_dest.parent.mkdir(parents=True, exist_ok=True)
                            if src_path.is_dir():
                                shutil.copytree(src_path, user_dest, dirs_exist_ok=True)
                            else:
                                shutil.copy2(src_path, user_dest)
                            self.chroot.run_in_chroot(f"chown -R {user_dir.name}:{user_dir.name} /home/{user_dir.name}/{rel_skel.split('/')[0]}")

    def configure_system_defaults(self):
        logger.info("Applying Gentoo live system defaults (hostname, sshd, fstab, timezone)...")
        self.copy_custom_files()

        if self.chroot.mode == "mock":
            logger.info("[MOCK CUSTOMIZER] Setting up livecd defaults")
            return

        # Hostname
        if self.init_system == "openrc":
            hostname_path = self.target_root / "etc" / "conf.d" / "hostname"
            hostname_path.parent.mkdir(parents=True, exist_ok=True)
            hostname_path.write_text('hostname="gentoo-live"\n')
        else:
            hostname_path = self.target_root / "etc" / "hostname"
            hostname_path.write_text('gentoo-live\n')

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
