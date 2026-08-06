import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional
from core.command_runner import CommandRunner
from core.logger_setup import setup_logger

logger = setup_logger("chroot_manager")

# Map target arch -> qemu-static binary name
_QEMU_STATIC_MAP = {
    "aarch64": "qemu-aarch64-static",
    "arm64":   "qemu-aarch64-static",
    "riscv64": "qemu-riscv64-static",
    "armv7":   "qemu-arm-static",
    "armhf":   "qemu-arm-static",
    "i686":    "qemu-i386-static",
    "i386":    "qemu-i386-static",
}

def _host_arch() -> str:
    return platform.machine().lower()

class ChrootManagerError(Exception):
    pass

class ChrootManager:
    def __init__(self, target_root: Path, mode: str = "mock", cache_dir: Optional[Path] = None, arch: Optional[str] = None):
        self.target_root = Path(target_root).resolve()
        self.mode = mode.lower()
        self.cache_dir = Path(cache_dir).resolve() if cache_dir else None
        self.is_mounted = False
        # Detect architecture: use explicit arg, else infer from workdir name
        if arch:
            self.arch = arch.lower()
        else:
            # workdir is typically .../workdir/aarch64/chroot  -> parent.name = 'aarch64'
            self.arch = self.target_root.parent.name.lower()

    def _setup_qemu_static(self):
        """Copy qemu-*-static into the chroot /usr/bin/ for cross-arch binfmt_misc support."""
        host = _host_arch()
        target = self.arch

        # No QEMU needed when building natively
        if host in ("x86_64", "amd64") and target in ("x86_64", "amd64"):
            return
        if host == target:
            return

        qemu_bin_name = _QEMU_STATIC_MAP.get(target)
        if not qemu_bin_name:
            logger.debug(f"No QEMU static binary mapping for target arch '{target}' — skipping QEMU setup.")
            return

        # Locate qemu-*-static on the host
        host_qemu = shutil.which(qemu_bin_name)
        if not host_qemu:
            # Try common install paths
            for candidate in [
                f"/usr/bin/{qemu_bin_name}",
                f"/usr/local/bin/{qemu_bin_name}",
                f"/usr/libexec/{qemu_bin_name}",
            ]:
                if Path(candidate).exists():
                    host_qemu = candidate
                    break

        if not host_qemu:
            logger.warning(
                f"[QEMU] '{qemu_bin_name}' not found on host! "
                f"Cross-arch chroot for '{target}' will fail without it. "
                f"Install it with: sudo emerge app-emulation/qemu (USE=static-user)"
            )
            return

        chroot_qemu_dir = self.target_root / "usr" / "bin"
        chroot_qemu_dir.mkdir(parents=True, exist_ok=True)
        chroot_qemu_path = chroot_qemu_dir / qemu_bin_name

        if not chroot_qemu_path.exists():
            try:
                shutil.copy2(host_qemu, chroot_qemu_path)
                # Must be world-executable (static binary)
                chroot_qemu_path.chmod(0o755)
                logger.info(f"[QEMU] Installed {host_qemu} -> {chroot_qemu_path} for {target} chroot binfmt_misc")
            except Exception as e:
                logger.warning(f"[QEMU] Failed to copy {qemu_bin_name} into chroot: {e}")
        else:
            logger.debug(f"[QEMU] {chroot_qemu_path} already present in chroot.")

    def mount_virtual_fs(self):
        if self.mode == "mock":
            logger.info(f"[MOCK] Mounting virtual filesystems into {self.target_root}")
            self.is_mounted = True
            return

        if os.geteuid() != 0:
            raise ChrootManagerError("Real mode requires root privileges to mount virtual filesystems.")

        # Setup QEMU static binary for cross-arch chroots BEFORE mounting
        self._setup_qemu_static()

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

    def run_in_chroot(self, command: List[str] | str, env: Optional[dict] = None, check: bool = True) -> subprocess.CompletedProcess:
        """Executes commands inside chroot with real-time log streaming to console."""
        return CommandRunner.run_chroot_stream(
            chroot_path=str(self.target_root),
            command=command,
            env=env,
            mode=self.mode
        )
