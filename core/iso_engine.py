import subprocess
import shutil
import hashlib
from pathlib import Path
from typing import Dict, Any
from core.logger_setup import setup_logger

logger = setup_logger("iso_engine")

class ISOEngineError(Exception):
    pass

class ISOEngine:
    def __init__(self, workdir: Path, target_root: Path, output_name: str, mode: str = "mock"):
        self.workdir = Path(workdir).resolve()
        self.target_root = Path(target_root).resolve()
        self.output_name = output_name
        self.mode = mode.lower()
        self.iso_dir = self.workdir / "iso_root"

    def prepare_iso_root(self):
        logger.info(f"Preparing ISO root structure at {self.iso_dir}")
        self.iso_dir.mkdir(parents=True, exist_ok=True)
        (self.iso_dir / "live").mkdir(parents=True, exist_ok=True)
        (self.iso_dir / "boot" / "grub").mkdir(parents=True, exist_ok=True)

    def create_squashfs(self):
        squash_path = self.iso_dir / "live" / "filesystem.squashfs"
        logger.info(f"Creating SquashFS image at {squash_path}")
        if self.mode == "mock":
            logger.info("[MOCK ISO ENGINE] Creating dummy filesystem.squashfs")
            squash_path.touch()
            return

        cmd = ["mksquashfs", str(self.target_root), str(squash_path), "-comp", "xz", "-wildcards", "-e", "boot/*"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise ISOEngineError(f"mksquashfs failed: {res.stderr}")

    def build_iso(self) -> Path:
        self.prepare_iso_root()
        self.create_squashfs()

        output_iso = self.workdir / self.output_name
        logger.info(f"Building ISO file: {output_iso}")

        if self.mode == "mock":
            logger.info(f"[MOCK ISO ENGINE] Creating dummy ISO image: {output_iso}")
            output_iso.write_text("MOCK GENTOO ISO IMAGE CONTENT")
        else:
            grub_cfg = self.iso_dir / "boot" / "grub" / "grub.cfg"
            grub_cfg.write_text(
                'set default=0\n'
                'set timeout=10\n'
                'menuentry "Gentoo Linux Live ISO" {\n'
                '    linux /boot/vmlinuz root=/dev/ram0 looptype=squashfs loop=/live/filesystem.squashfs udev nodevfs initrd=/boot/initramfs\n'
                '    initrd /boot/initramfs\n'
                '}\n'
            )
            cmd = [
                "grub-mkrescue",
                "-o", str(output_iso),
                str(self.iso_dir)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise ISOEngineError(f"grub-mkrescue failed: {res.stderr}")

        self._generate_checksums(output_iso)
        return output_iso

    def _generate_checksums(self, iso_path: Path):
        logger.info(f"Generating checksums for {iso_path.name}")
        content = iso_path.read_bytes()

        md5 = hashlib.md5(content).hexdigest()
        sha256 = hashlib.sha256(content).hexdigest()

        (iso_path.parent / f"{iso_path.name}.md5").write_text(f"{md5}  {iso_path.name}\n")
        (iso_path.parent / f"{iso_path.name}.sha256").write_text(f"{sha256}  {iso_path.name}\n")
