import subprocess
import shutil
import hashlib
from pathlib import Path
from typing import Dict, Any
from core.logger_setup import setup_logger
from core.path_utils import resolve_from_project

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

        # Copy GRUB theme and ISOLINUX splash image into iso_root
        grub_theme_src = resolve_from_project("configs/custom_files/grub/modern")
        if grub_theme_src.exists():
            iso_grub_theme = self.iso_dir / "boot" / "grub" / "themes" / "modern"
            try:
                iso_grub_theme.mkdir(parents=True, exist_ok=True)
                shutil.copytree(grub_theme_src, iso_grub_theme, dirs_exist_ok=True)
                logger.info(f"Copied GRUB theme -> {iso_grub_theme}")
            except OSError as e:
                logger.warning(f"Could not copy GRUB theme to ISO root: {e}")

        splash_src = resolve_from_project("configs/custom_files/grub/modern/background.png")
        if splash_src.exists():
            isolinux_target = self.iso_dir / "isolinux"
            try:
                isolinux_target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(splash_src, isolinux_target / "splash.png")
                logger.info(f"Copied ISOLINUX splash image -> {isolinux_target / 'splash.png'}")
            except OSError as e:
                logger.warning(f"Could not copy ISOLINUX splash image: {e}")

        # For syslinux/isolinux targets, we must copy syslinux boot files if they exist in the chroot or host
        btype = self.config.get("type", "grub-uefi")
        if "syslinux" in btype or "isolinux" in btype:
            syslinux_paths = [
                self.target_root / "usr" / "share" / "syslinux",
                self.target_root / "usr" / "lib" / "syslinux" / "bios",
                Path("/usr/share/syslinux"),
                Path("/usr/lib/syslinux/bios")
            ]
            
            isolinux_target = self.iso_dir / "isolinux"
            isolinux_target.mkdir(parents=True, exist_ok=True)
            
            copied = False
            for path in syslinux_paths:
                if path.exists():
                    for filename in ["isolinux.bin", "vesamenu.c32", "menu.c32", "ldlinux.c32", "libcom32.c32", "libutil.c32"]:
                        src_file = path / filename
                        if src_file.exists():
                            try:
                                shutil.copy2(src_file, isolinux_target / filename)
                                copied = True
                            except Exception as e:
                                logger.warning(f"Could not copy {filename} from {path}: {e}")
                    if copied:
                        logger.info(f"Copied syslinux boot binaries from {path} into isolinux target")
                        break
            if not copied and self.mode != "mock":
                logger.warning("Could not find syslinux boot files inside chroot or host distribution!")

    def create_squashfs(self):
        squash_path = self.iso_dir / "live" / "filesystem.squashfs"
        logger.info(f"Creating SquashFS image at {squash_path}")
        if self.mode == "mock":
            logger.info("[MOCK ISO ENGINE] Creating dummy filesystem.squashfs")
            try:
                squash_path.parent.mkdir(parents=True, exist_ok=True)
                squash_path.touch()
            except OSError as e:
                logger.warning(f"[MOCK ISO ENGINE] Skipped creating dummy squashfs due to: {e}")
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
            "set timeout=10",
            "set gfxmode=auto",
            "insmod all_video",
            "insmod gfxterm",
            "insmod png",
            "set theme=/boot/grub/themes/modern/theme.txt",
            "terminal_output gfxterm",
            "",
            "menuentry 'Boot Gentoo Modern (Default)' --class gnu-linux --class os {",
            f"    search --no-floppy --set=root -l {vol_id}",
            f"    linux /boot/vmlinuz {bootargs} quiet splash plymouth.theme=gentoo-modern",
            "    initrd /boot/initramfs",
            "}",
            "",
            "menuentry 'Boot Gentoo Modern (Copy to RAM)' --class gnu-linux --class os {",
            f"    search --no-floppy --set=root -l {vol_id}",
            f"    linux /boot/vmlinuz {bootargs} docache rd.live.ram=1 quiet splash plymouth.theme=gentoo-modern",
            "    initrd /boot/initramfs",
            "}",
            "",
            "menuentry 'Boot Gentoo Modern (Safe Graphics)' --class gnu-linux --class os {",
            f"    search --no-floppy --set=root -l {vol_id}",
            f"    linux /boot/vmlinuz {bootargs} nomodeset",
            "    initrd /boot/initramfs",
            "}"
        ]

        if self.mode == "mock":
            logger.info(f"[MOCK ISO ENGINE] Writing GRUB config to {grub_cfg}")
            try:
                grub_cfg.parent.mkdir(parents=True, exist_ok=True)
                grub_cfg.write_text("\n".join(lines) + "\n")
            except OSError as e:
                logger.warning(f"[MOCK ISO ENGINE] Skipped writing GRUB config due to: {e}")
        else:
            grub_cfg.write_text("\n".join(lines) + "\n")

    def generate_syslinux_config(self):
        syslinux_cfg = self.iso_dir / "isolinux" / "isolinux.cfg"
        bootargs = self.config.get("bootargs", "root=/dev/ram0 looptype=squashfs loop=/live/filesystem.squashfs udev nodevfs")

        lines = [
            "UI vesamenu.c32",
            "MENU TITLE Gentoo Modern Live ISO",
            "MENU BACKGROUND /isolinux/splash.png",
            "DEFAULT gentoo",
            "TIMEOUT 100",
            "PROMPT 0",
            "",
            "LABEL gentoo",
            "  MENU LABEL Boot Gentoo Modern (Default)",
            "  KERNEL /boot/vmlinuz",
            f"  APPEND initrd=/boot/initramfs {bootargs} quiet splash plymouth.theme=gentoo-modern",
            "",
            "LABEL gentoo-ram",
            "  MENU LABEL Boot Gentoo Modern (Copy to RAM)",
            "  KERNEL /boot/vmlinuz",
            f"  APPEND initrd=/boot/initramfs {bootargs} docache quiet splash plymouth.theme=gentoo-modern",
            "",
            "LABEL gentoo-safe",
            "  MENU LABEL Boot Gentoo Modern (Safe Graphics)",
            "  KERNEL /boot/vmlinuz",
            f"  APPEND initrd=/boot/initramfs {bootargs} nomodeset"
        ]

        if self.mode == "mock":
            logger.info(f"[MOCK ISO ENGINE] Writing ISOLINUX config to {syslinux_cfg}")
            try:
                syslinux_cfg.parent.mkdir(parents=True, exist_ok=True)
                syslinux_cfg.write_text("\n".join(lines) + "\n")
            except OSError as e:
                logger.warning(f"[MOCK ISO ENGINE] Skipped writing ISOLINUX config due to: {e}")
        else:
            syslinux_cfg.write_text("\n".join(lines) + "\n")

    def generate_systemd_boot_config(self):
        loader_conf = self.iso_dir / "loader" / "loader.conf"
        entry_conf = self.iso_dir / "loader" / "entries" / "gentoo.conf"
        bootargs = self.config.get("bootargs", "root=/dev/ram0 looptype=squashfs loop=/live/filesystem.squashfs udev nodevfs")

        if self.mode == "mock":
            logger.info(f"[MOCK ISO ENGINE] Writing Systemd-boot config to {loader_conf}")
            try:
                loader_conf.parent.mkdir(parents=True, exist_ok=True)
                loader_conf.write_text("default gentoo.conf\ntimeout 10\nconsole-mode max\n")
                entry_conf.parent.mkdir(parents=True, exist_ok=True)
                entry_conf.write_text(
                    "title Gentoo Modern\n"
                    "linux /boot/vmlinuz\n"
                    "initrd /boot/initramfs\n"
                    f"options {bootargs} quiet splash plymouth.theme=gentoo-modern\n"
                )
            except OSError as e:
                logger.warning(f"[MOCK ISO ENGINE] Skipped writing Systemd-boot config due to: {e}")
        else:
            loader_conf.parent.mkdir(parents=True, exist_ok=True)
            loader_conf.write_text("default gentoo.conf\ntimeout 10\nconsole-mode max\n")
            entry_conf.parent.mkdir(parents=True, exist_ok=True)
            entry_conf.write_text(
                "title Gentoo Modern\n"
                "linux /boot/vmlinuz\n"
                "initrd /boot/initramfs\n"
                f"options {bootargs} quiet splash plymouth.theme=gentoo-modern\n"
            )

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
            try:
                output_iso.write_text("MOCK GENTOO ISO IMAGE CONTENT")
            except OSError as e:
                logger.warning(f"[MOCK ISO ENGINE] Skipped creating dummy ISO due to: {e}")
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
        if self.mode == "mock":
            try:
                (iso_path.parent / f"{iso_path.name}.md5").write_text("MOCK_MD5")
                (iso_path.parent / f"{iso_path.name}.sha256").write_text("MOCK_SHA256")
            except OSError as e:
                logger.warning(f"[MOCK ISO ENGINE] Skipped generating checksums due to: {e}")
            return

        try:
            content = iso_path.read_bytes()
            md5 = hashlib.md5(content).hexdigest()
            sha256 = hashlib.sha256(content).hexdigest()

            (iso_path.parent / f"{iso_path.name}.md5").write_text(f"{md5}  {iso_path.name}\n")
            (iso_path.parent / f"{iso_path.name}.sha256").write_text(f"{sha256}  {iso_path.name}\n")
        except OSError as e:
            raise ISOEngineError(f"Checksum generation failed: {e}")
