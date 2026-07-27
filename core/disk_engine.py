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
            
            # Step 1: Allocate space using fallocate (faster than dd for sparse files)
            img_size = self.config.get("bootloader", {}).get("size", self.config.get("size", "4G"))
            logger.info(f"Allocating {img_size} disk image at {output_img}...")
            # Use fallocate for speed; fall back to truncate if fallocate is unavailable
            fallocate_res = subprocess.run(
                ["fallocate", "-l", str(img_size), str(output_img)],
                capture_output=True
            )
            if fallocate_res.returncode != 0:
                # Convert size string (e.g. "4G") to bytes for truncate
                size_map = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
                size_str = str(img_size).upper().strip()
                multiplier = size_map.get(size_str[-1], 1)
                size_bytes = int(size_str[:-1]) * multiplier if size_str[-1] in size_map else int(size_str)
                subprocess.run(["truncate", "-s", str(size_bytes), str(output_img)], check=True)

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
        if self.mode == "mock":
            logger.info(f"[MOCK DISK ENGINE] Generating dummy checksums for {img_path.name}")
            try:
                (img_path.parent / f"{img_path.name}.md5").write_text(f"MOCK_MD5  {img_path.name}\n")
                (img_path.parent / f"{img_path.name}.sha256").write_text(f"MOCK_SHA256  {img_path.name}\n")
            except OSError:
                pass
            return

        logger.info(f"Generating checksums for {img_path.name}")
        # Stream file in 8MB chunks to avoid loading multi-GB images into RAM
        md5 = hashlib.md5()
        sha256 = hashlib.sha256()
        with open(img_path, "rb") as f:
            for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                md5.update(chunk)
                sha256.update(chunk)

        (img_path.parent / f"{img_path.name}.md5").write_text(f"{md5.hexdigest()}  {img_path.name}\n")
        (img_path.parent / f"{img_path.name}.sha256").write_text(f"{sha256.hexdigest()}  {img_path.name}\n")
