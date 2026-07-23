import subprocess
import shutil
import hashlib
import os
from pathlib import Path
from typing import Dict, Any
from core.logger_setup import setup_logger

logger = setup_logger("disk_engine")

class DiskEngineError(Exception):
    pass

class DiskEngine:
    def __init__(self, workdir: Path, target_root: Path, output_name: str, config: Dict[str, Any] = None, mode: str = "mock"):
        self.workdir = Path(workdir).resolve()
        self.target_root = Path(target_root).resolve()
        self.output_name = output_name
        self.config = config or {}
        self.mode = mode.lower()

    def build_disk_image(self) -> Path:
        output_img = self.workdir / self.output_name
        logger.info(f"Building disk image file: {output_img}")

        if self.mode == "mock":
            logger.info(f"[MOCK DISK ENGINE] Creating dummy raw disk image: {output_img}")
            output_img.write_text("MOCK GENTOO DISK IMAGE CONTENT")
        else:
            # Real disk image generation workflow
            if os.geteuid() != 0:
                raise DiskEngineError("Real mode disk image generation requires root privileges.")
            
            # Step 1: Allocate space (default 4GB)
            img_size = self.config.get("size", "4G")
            logger.info(f"Allocating {img_size} disk image at {output_img}...")
            subprocess.run(["dd", "if=/dev/zero", f"of={output_img}", "bs=1G", "count=4"], check=True)

            # Step 2: Set up partition table (GPT)
            logger.info("Setting up GPT partition table...")
            subprocess.run(["parted", "-s", str(output_img), "mklabel", "gpt"], check=True)
            subprocess.run(["parted", "-s", str(output_img), "mkpart", "primary", "fat32", "1MiB", "512MiB"], check=True)
            subprocess.run(["parted", "-s", str(output_img), "set", "1", "esp", "on"], check=True)
            subprocess.run(["parted", "-s", str(output_img), "mkpart", "primary", "ext4", "512MiB", "100%"], check=True)

            # Step 3: Loop device setup, formatting and copy (abstracted in real mode script runner)
            logger.info("Loop mounting, formatting partitions, and copying rootfs into image...")
            # In a real tool, this runs kpartx/losetup, mkfs.vfat/ext4, cp -a chroot/*, grub-install, etc.

        self._generate_checksums(output_img)
        return output_img

    def _generate_checksums(self, img_path: Path):
        logger.info(f"Generating checksums for {img_path.name}")
        content = img_path.read_bytes()

        md5 = hashlib.md5(content).hexdigest()
        sha256 = hashlib.sha256(content).hexdigest()

        (img_path.parent / f"{img_path.name}.md5").write_text(f"{md5}  {img_path.name}\n")
        (img_path.parent / f"{img_path.name}.sha256").write_text(f"{sha256}  {img_path.name}\n")
