import os
import subprocess
from pathlib import Path
from typing import List, Optional
from core.command_runner import CommandRunner
from core.logger_setup import setup_logger

logger = setup_logger("chroot_manager")

class ChrootManagerError(Exception):
    pass

class ChrootManager:
    def __init__(self, target_root: Path, mode: str = "mock", cache_dir: Optional[Path] = None):
        self.target_root = Path(target_root).resolve()
        self.mode = mode.lower()
        self.cache_dir = Path(cache_dir).resolve() if cache_dir else None
        self.is_mounted = False

    def mount_virtual_fs(self):
        if self.mode == "mock":
            logger.info(f"[MOCK] Mounting virtual filesystems into {self.target_root}")
            self.is_mounted = True
            return

        if os.geteuid() != 0:
            raise ChrootManagerError("Real mode requires root privileges to mount virtual filesystems.")

        logger.info(f"Mounting proc, sys, dev into {self.target_root}")
        mounts = [
            ("proc", self.target_root / "proc", "proc", None),
            ("sysfs", self.target_root / "sys", "sysfs", None),
            ("udev", self.target_root / "dev", "devtmpfs", None),
            ("devpts", self.target_root / "dev" / "pts", "devpts", None),
            ("tmpfs", self.target_root / "dev" / "shm", "tmpfs", None),
        ]

        for src, target, fstype, opts in mounts:
            target.mkdir(parents=True, exist_ok=True)
            cmd = ["mount", "-t", fstype]
            if opts:
                cmd.extend(["-o", opts])
            cmd.extend([src, str(target)])
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 and "already mounted" not in res.stderr:
                logger.warning(f"Failed to mount {target}: {res.stderr.strip()}")

        # Bind-mount persistent cache for Portage packages (distfiles & binpkgs)
        if self.cache_dir:
            distfiles_host = self.cache_dir / "distfiles"
            binpkgs_host = self.cache_dir / "binpkgs"
            distfiles_host.mkdir(parents=True, exist_ok=True)
            binpkgs_host.mkdir(parents=True, exist_ok=True)

            distfiles_target = self.target_root / "var" / "cache" / "distfiles"
            binpkgs_target = self.target_root / "var" / "cache" / "binpkgs"
            distfiles_target.mkdir(parents=True, exist_ok=True)
            binpkgs_target.mkdir(parents=True, exist_ok=True)

            logger.info(f"Bind-mounting Portage package cache from {self.cache_dir} into chroot...")
            for host_path, target_path in [(distfiles_host, distfiles_target), (binpkgs_host, binpkgs_target)]:
                cmd = ["mount", "--bind", str(host_path), str(target_path)]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode != 0 and "already mounted" not in res.stderr:
                    logger.warning(f"Failed to bind mount {host_path} -> {target_path}: {res.stderr.strip()}")

        self.is_mounted = True

    def umount_virtual_fs(self):
        if self.mode == "mock":
            logger.info(f"[MOCK] Unmounting virtual filesystems from {self.target_root}")
            self.is_mounted = False
            return

        if not self.is_mounted and os.geteuid() != 0:
            return

        logger.info(f"Unmounting virtual filesystems from {self.target_root}")
        targets = [
            self.target_root / "var" / "cache" / "binpkgs",
            self.target_root / "var" / "cache" / "distfiles",
            self.target_root / "dev" / "shm",
            self.target_root / "dev" / "pts",
            self.target_root / "dev",
            self.target_root / "sys",
            self.target_root / "proc",
        ]

        for target in targets:
            if target.exists():
                subprocess.run(["umount", "-l", str(target)], capture_output=True)

        self.is_mounted = False

    def run_in_chroot(self, command: List[str] | str, env: Optional[dict] = None) -> subprocess.CompletedProcess:
        """Executa comandos dentro do chroot com streaming em tempo real dos logs na tela."""
        return CommandRunner.run_chroot_stream(
            chroot_path=str(self.target_root),
            command=command,
            env=env,
            mode=self.mode
        )
