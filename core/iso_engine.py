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
    def __init__(self, workdir: Path, target_root: Path, output_name: str, config: Dict[str, Any] = None, mode: str = "mock"):
        self.workdir = Path(workdir).resolve()
        self.target_root = Path(target_root).resolve()
        self.output_name = output_name
        self.config = config or {}
        self.mode = mode.lower()
        self.iso_dir = self.workdir / "iso_root"

    def prepare_iso_root(self):
        logger.info(f"Preparing ISO root structure at {self.iso_dir}")
        try:
            self.iso_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            if self.mode == "mock":
                logger.warning(f"[MOCK ISO ENGINE] Permission denied creating {self.iso_dir}. Using existing root.")
            else:
                raise

        for sub in ["live", "boot/grub", "isolinux", "loader/entries"]:
            p = self.iso_dir / sub
            try:
                p.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                if self.mode != "mock":
                    raise

        # Copy kernel and initramfs from chroot if available
        chroot_boot = self.target_root / "boot"
        iso_boot = self.iso_dir / "boot"
        if chroot_boot.exists():
            for kfile in chroot_boot.glob("vmlinuz*"):
                shutil.copy2(kfile, iso_boot / "vmlinuz")
                logger.info(f"Copied kernel {kfile.name} -> {iso_boot / 'vmlinuz'}")
                break
            for ifile in chroot_boot.glob("initramfs*"):
                shutil.copy2(ifile, iso_boot / "initramfs")
                logger.info(f"Copied initramfs {ifile.name} -> {iso_boot / 'initramfs'}")
                break

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

    def generate_grub_config(self):
        grub_cfg = self.iso_dir / "boot" / "grub" / "grub.cfg"
        vol_id = self.config.get("vol_id", "GENTOO_LIVE")
        bootargs = self.config.get("bootargs", f"root=live:CDLABEL={vol_id} rd.live.dir=/ rd.live.squashimg=filesystem.squashfs cdroot")

        lines = [
            "set default=0",
            "set gfxpayload=keep",
            "set timeout=10",
            "insmod all_video",
            "insmod png",
            "insmod gfxterm",
            "terminal_output gfxterm",
            "set gfxmode=auto",
            "",
            "menuentry 'Boot Gentoo LiveCD (Default)' --class gnu-linux --class os {",
            f"    search --no-floppy --set=root -l {vol_id}",
            f"    linux /boot/vmlinuz {bootargs}",
            "    initrd /boot/initramfs",
            "}",
            "",
            "menuentry 'Boot Gentoo LiveCD (Copy to RAM)' --class gnu-linux --class os {",
            f"    search --no-floppy --set=root -l {vol_id}",
            f"    linux /boot/vmlinuz {bootargs} docache rd.live.ram=1",
            "    initrd /boot/initramfs",
            "}",
            "",
            "menuentry 'Boot Gentoo LiveCD (Safe Graphics)' --class gnu-linux --class os {",
            f"    search --no-floppy --set=root -l {vol_id}",
            f"    linux /boot/vmlinuz {bootargs} nomodeset",
            "    initrd /boot/initramfs",
            "}"
        ]

        if self.mode == "mock":
            logger.info(f"[MOCK ISO ENGINE] Writing GRUB config to {grub_cfg}")
        grub_cfg.write_text("\n".join(lines) + "\n")

    def generate_syslinux_config(self):
        syslinux_cfg = self.iso_dir / "isolinux" / "isolinux.cfg"
        bootargs = self.config.get("bootargs", "root=/dev/ram0 looptype=squashfs loop=/live/filesystem.squashfs udev nodevfs")

        lines = [
            "UI vesamenu.c32",
            "DEFAULT gentoo",
            "TIMEOUT 100",
            "PROMPT 0",
            "",
            "LABEL gentoo",
            "  MENU LABEL Boot Gentoo LiveCD (Default)",
            "  KERNEL /boot/vmlinuz",
            f"  APPEND initrd=/boot/initramfs {bootargs}",
            "",
            "LABEL gentoo-ram",
            "  MENU LABEL Boot Gentoo LiveCD (Copy to RAM)",
            "  KERNEL /boot/vmlinuz",
            f"  APPEND initrd=/boot/initramfs {bootargs} docache",
            "",
            "LABEL gentoo-safe",
            "  MENU LABEL Boot Gentoo LiveCD (Safe Graphics)",
            "  KERNEL /boot/vmlinuz",
            f"  APPEND initrd=/boot/initramfs {bootargs} nomodeset"
        ]

        if self.mode == "mock":
            logger.info(f"[MOCK ISO ENGINE] Writing ISOLINUX config to {syslinux_cfg}")
        syslinux_cfg.write_text("\n".join(lines) + "\n")

    def generate_systemd_boot_config(self):
        loader_conf = self.iso_dir / "loader" / "loader.conf"
        entry_conf = self.iso_dir / "loader" / "entries" / "gentoo.conf"
        bootargs = self.config.get("bootargs", "root=/dev/ram0 looptype=squashfs loop=/live/filesystem.squashfs udev nodevfs")

        loader_conf.write_text("default gentoo.conf\ntimeout 10\nconsole-mode max\n")
        entry_conf.write_text(
            "title Gentoo LiveCD\n"
            "linux /boot/vmlinuz\n"
            "initrd /boot/initramfs\n"
            f"options {bootargs}\n"
        )
        if self.mode == "mock":
            logger.info(f"[MOCK ISO ENGINE] Writing Systemd-boot config to {loader_conf}")

    def generate_bootloader_configs(self):
        btype = self.config.get("type", "grub-uefi")
        logger.info(f"Generating bootloader configurations for type: {btype}")

        if "syslinux" in btype or "isolinux" in btype:
            self.generate_syslinux_config()
        elif "systemd-boot" in btype:
            self.generate_systemd_boot_config()
            self.generate_grub_config()
        else:
            self.generate_grub_config()

    def build_iso(self) -> Path:
        self.prepare_iso_root()
        self.create_squashfs()
        self.generate_bootloader_configs()

        output_iso = self.workdir / self.output_name
        logger.info(f"Building ISO file: {output_iso}")

        if self.mode == "mock":
            logger.info(f"[MOCK ISO ENGINE] Creating dummy ISO image: {output_iso}")
            output_iso.write_text("MOCK GENTOO ISO IMAGE CONTENT")
        else:
            vol_id = self.config.get("vol_id", "gentoo_modern")
            btype = self.config.get("type", "grub-uefi")

            if "syslinux" in btype or "isolinux" in btype:
                cmd = [
                    "xorriso", "-as", "mkisofs",
                    "-iso-level", "3",
                    "-full-iso9660-filenames",
                    "-volid", vol_id,
                    "-eltorito-boot", "isolinux/isolinux.bin",
                    "-eltorito-catalog", "isolinux/boot.cat",
                    "-no-emul-boot", "-boot-load-size", "4", "-boot-info-table",
                    "-output", str(output_iso),
                    str(self.iso_dir)
                ]
            else:
                cmd = [
                    "grub-mkrescue",
                    "-volid", vol_id,
                    "-o", str(output_iso),
                    str(self.iso_dir)
                ]

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise ISOEngineError(f"ISO creation failed: {res.stderr}")

        self._generate_checksums(output_iso)
        return output_iso

    def _generate_checksums(self, iso_path: Path):
        logger.info(f"Generating checksums for {iso_path.name}")
        content = iso_path.read_bytes()

        md5 = hashlib.md5(content).hexdigest()
        sha256 = hashlib.sha256(content).hexdigest()

        (iso_path.parent / f"{iso_path.name}.md5").write_text(f"{md5}  {iso_path.name}\n")
        (iso_path.parent / f"{iso_path.name}.sha256").write_text(f"{sha256}  {iso_path.name}\n")
