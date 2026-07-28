import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List
from core.chroot_manager import ChrootManager
from core.logger_setup import setup_logger
from core.path_utils import resolve_from_project

logger = setup_logger("customizer")

class SystemCustomizer:
    def __init__(self, chroot: ChrootManager, config: Dict[str, Any]):
        self.chroot = chroot
        self.config = config
        self.init_system = config.get("init_system", "openrc")
        self.target_root = chroot.target_root

    def setup_live_users(self):
        live_user_cfg = self.config.get("live_user", {})
        if isinstance(live_user_cfg, dict):
            username = live_user_cfg.get("username", "live")
            password = live_user_cfg.get("password", "live")
            groups = live_user_cfg.get("groups", ["wheel", "audio", "video", "input", "plugdev"])
        else:
            username = str(live_user_cfg) if live_user_cfg else "live"
            password = "live"
            groups = ["wheel", "audio", "video", "input", "plugdev"]

        # Ensure autologin, nopasswdlogin, render, and lightdm groups exist
        for g in ["autologin", "nopasswdlogin", "render", "lightdm"]:
            self.chroot.run_in_chroot(f"groupadd -f {g}")
            if g not in groups and g != "lightdm":
                groups.append(g)

        groups_str = ",".join(groups)

        logger.info(f"Setting up live user '{username}' (password: '{password}') and root (password: 'root')...")

        if self.chroot.mode == "mock":
            logger.info(f"[MOCK CUSTOMIZER] Adding user {username}")
            return

        self.chroot.run_in_chroot(f"groupadd -f {username}")
        self.chroot.run_in_chroot(f"useradd -m -g {username} -G {groups_str} -s /bin/bash {username} 2>/dev/null || usermod -aG {groups_str} {username}")

        # Set live user password
        if password:
            self.chroot.run_in_chroot(f"sh -c \"echo '{username}:{password}' | chpasswd\"")

        # Set root user password to 'root'
        self.chroot.run_in_chroot("sh -c \"echo 'root:root' | chpasswd\"")

        # Fix authentication files permissions and ownership so login/PAM works properly
        self.chroot.run_in_chroot("chown 0:0 /etc/passwd /etc/group")
        self.chroot.run_in_chroot("chown 0:shadow /etc/shadow /etc/gshadow 2>/dev/null || chown 0:0 /etc/shadow /etc/gshadow")
        self.chroot.run_in_chroot("chmod 0644 /etc/passwd /etc/group")
        self.chroot.run_in_chroot("chmod 0640 /etc/shadow /etc/gshadow")

        # Ensure SUID binaries (unix_chkpwd, sudo, su) have correct permissions for PAM authentication
        self.chroot.run_in_chroot("chmod 4755 /sbin/unix_chkpwd /usr/sbin/unix_chkpwd /usr/bin/sudo /bin/su /usr/bin/su 2>/dev/null || true")

        # Ensure user home directory permissions
        self.chroot.run_in_chroot(f"chown -R {username}:{username} /home/{username}")

        # Ensure LightDM system directories belong to lightdm user
        self.chroot.run_in_chroot("mkdir -p /var/lib/lightdm /var/log/lightdm /run/lightdm")
        self.chroot.run_in_chroot("chown -R lightdm:lightdm /var/lib/lightdm /var/log/lightdm /run/lightdm 2>/dev/null || true")

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
                service_aliases = {
                    "cups": ["cupsd", "cups"],
                    "cupsd": ["cupsd", "cups"],
                    "samba": ["samba", "smbd"],
                    "lvm": ["lvm", "device-mapper"],
                    "nfs": ["nfs", "nfsmount"],
                    "cronie": ["cronie", "cron", "vixie-cron"],
                    "lm_sensors": ["lm_sensors", "sensord"]
                }
                candidates = service_aliases.get(srv, [srv])
                target_srv = None
                for cand in candidates:
                    if (self.target_root / "etc" / "init.d" / cand).exists():
                        target_srv = cand
                        break

                if not target_srv:
                    dm_script = self.target_root / "etc" / "init.d" / "display-manager"
                    if dm_script.exists() and srv in ["lightdm", "sddm", "gdm", "xdm", "lxdm"]:
                        target_srv = "display-manager"
                        if self.chroot.mode != "mock":
                            conf_d = self.target_root / "etc" / "conf.d" / "display-manager"
                            conf_d.parent.mkdir(parents=True, exist_ok=True)
                            conf_d.write_text(f'DISPLAYMANAGER="{srv}"\n')
                            
                            # Configure Autologin for the Live User
                            live_user_cfg = self.config.get("live_user", {})
                            if isinstance(live_user_cfg, dict):
                                username = live_user_cfg.get("username", "live")
                            else:
                                username = str(live_user_cfg) if live_user_cfg else "live"

                            session = self.config.get("desktop_environment", {}).get("name", "xfce")
                            if srv == "lightdm":
                                lconf = self.target_root / "etc" / "lightdm" / "lightdm.conf"
                                if lconf.exists():
                                    content = lconf.read_text()
                                    lines = [line for line in content.splitlines() if not line.startswith("autologin-user=")]
                                    clean_content = "\n".join(lines)
                                    autologin_block = (
                                        f"\n\n[Seat:*]\n"
                                        f"autologin-user={username}\n"
                                        f"autologin-user-timeout=0\n"
                                        f"autologin-session={session}\n"
                                        f"user-session={session}\n"
                                        f"pam-service=lightdm-autologin\n"
                                        f"pam-autologin-service=lightdm-autologin\n"
                                    )
                                    lconf.write_text(clean_content + autologin_block)
                            elif srv == "sddm":
                                sddm_dir = self.target_root / "etc" / "sddm.conf.d"
                                sddm_dir.mkdir(parents=True, exist_ok=True)
                                sddm_conf = sddm_dir / "autologin.conf"
                                sddm_conf.write_text(f"[Autologin]\nUser={username}\nSession={session}\n")
                    else:
                        logger.warning(f"Init script for {srv} not found in /etc/init.d/; skipping service enable.")
                        continue
                self.chroot.run_in_chroot(f"rc-update add {target_srv} default")
            elif self.init_system == "runit":
                self.chroot.run_in_chroot(f"ln -s /etc/runit/runsvdir/all/{srv} /etc/runit/runsvdir/default/")
            elif self.init_system == "s6":
                self.chroot.run_in_chroot(f"s6-rc-bundle add default {srv}")

    def copy_custom_files(self):
        """Copies structured files from configs/custom_files/ into the chroot as specified in configs."""
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

            # Ensure all custom files copied to system paths (/etc, /usr, /var) belong to root:root
            if dest_rel.startswith(("/etc/", "/usr/", "/var/", "/boot/")):
                self.chroot.run_in_chroot(f"chown -R 0:0 '{dest_rel}'")

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
                            self.chroot.run_in_chroot(f"chown -R {user_dir.name}:{user_dir.name} '/home/{user_dir.name}/{rel_skel.split('/')[0]}'")

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
            hostname_path.write_text('hostname="gentoo-modern-live"\n')
        else:
            hostname_path = self.target_root / "etc" / "hostname"
            hostname_path.write_text('gentoo-modern-live\n')

        # Stage3 Seed Info Manifest
        stage3_info = self.target_root / "etc" / "gentoo_modern-stage3-info"
        stage3_info.write_text(
            f"DISTRO=Gentoo Modern\n"
            f"INIT={self.init_system}\n"
            f"DESKTOP={self.config.get('desktop', 'base')}\n"
        )

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

        # Setup /usr/src/linux symlink if kernel sources directory exists
        usr_src = self.target_root / "usr" / "src"
        if usr_src.exists():
            kernel_dirs = [d for d in usr_src.iterdir() if d.is_dir() and d.name.startswith("linux-")]
            if kernel_dirs:
                latest_kernel_dir = sorted(kernel_dirs, key=lambda d: d.name)[-1]
                linux_symlink = usr_src / "linux"
                if not linux_symlink.exists() and not linux_symlink.is_symlink():
                    logger.info(f"Creating /usr/src/linux symlink -> {latest_kernel_dir.name}")
                    linux_symlink.symlink_to(latest_kernel_dir.name)
