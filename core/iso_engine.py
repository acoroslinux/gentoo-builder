import os
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
    def __init__(self, workdir: Path, target_root: Path, output_name: str, config: Dict[str, Any] = None, mode: str = "mock", toolchain: Any = None):
        self.workdir = Path(workdir).resolve()
        self.target_root = Path(target_root).resolve()
        self.output_name = output_name
        self.config = config or {}
        self.mode = mode.lower()
        self.toolchain = toolchain
        self.iso_dir = self.workdir / "iso_root"

    def prepare_iso_root(self):
        logger.info(f"Preparing ISO root structure at {self.iso_dir}")
        # Wipe old iso_dir to prevent stale files (like old squashfs) from bloating the ISO on --no-clean rebuilds
        if self.iso_dir.exists() and self.mode != "mock":
            try:
                shutil.rmtree(self.iso_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Could not cleanly remove old iso_dir: {e}")

        try:
            self.iso_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            if self.mode == "mock":
                logger.warning(f"[MOCK ISO ENGINE] Permission denied creating {self.iso_dir}. Using existing root.")
            else:
                raise

        for sub in ["LiveOS", "boot/grub", "isolinux"]:
            p = self.iso_dir / sub
            try:
                p.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                if self.mode != "mock":
                    raise

        # Copy kernel and initramfs from chroot if available
        chroot_boot = self.target_root / "boot"
        iso_boot = self.iso_dir / "boot"
        iso_boot.mkdir(parents=True, exist_ok=True)
        if chroot_boot.exists():
            kfiles = [
                f for f in chroot_boot.glob("vmlinuz*")
                if not f.name.endswith(('.old', '.bak', '.tmp'))
            ]
            if not kfiles:
                kfiles = [
                    f for f in chroot_boot.glob("kernel*")
                    if not f.name.endswith(('.old', '.bak', '.tmp'))
                ]

            canonical_vmlinuz = chroot_boot / "vmlinuz"
            kernel_src = None

            if canonical_vmlinuz.is_symlink():
                link_target = Path(os.readlink(canonical_vmlinuz))
                if link_target.is_absolute():
                    real_path = self.target_root / str(link_target).lstrip("/")
                else:
                    real_path = (canonical_vmlinuz.parent / link_target).resolve()
                if real_path.exists():
                    kernel_src = real_path
                else:
                    logger.warning(f"Symlink /boot/vmlinuz -> {link_target} is broken. Falling back to newest vmlinuz file.")
            elif canonical_vmlinuz.is_file():
                kernel_src = canonical_vmlinuz

            if kernel_src is None and kfiles:
                real_kfiles = [f for f in kfiles if f.is_file() and not f.is_symlink()]
                if real_kfiles:
                    kernel_src = max(real_kfiles, key=lambda f: f.stat().st_mtime)
                else:
                    kernel_src = max(kfiles, key=lambda f: f.stat().st_mtime)

            if kernel_src and kernel_src.exists():
                shutil.copyfile(kernel_src, iso_boot / "vmlinuz")
                shutil.copymode(kernel_src, iso_boot / "vmlinuz")
                logger.info(f"Copied kernel {kernel_src.name} -> {iso_boot / 'vmlinuz'} ({os.path.getsize(iso_boot / 'vmlinuz')} bytes)")
            else:
                logger.error("CRITICAL: No kernel file (vmlinuz) found in chroot /boot — bootloader will fail!")

            ifiles = [
                f for f in chroot_boot.glob("initramfs*")
                if not f.name.endswith(('.old', '.bak', '.tmp')) and f.is_file()
            ]
            # Prefer the canonical symlink/file named exactly "initramfs".
            # IMPORTANT: symlinks inside chroot use chroot-absolute paths like
            # /boot/initramfs-kver.img. Python's Path.resolve() on the HOST would
            # follow the symlink to /boot/initramfs-kver.img on the HOST (wrong!).
            # We must resolve relative to target_root ourselves.
            canonical = chroot_boot / "initramfs"
            initramfs_src = None

            if canonical.is_symlink():
                link_target = Path(os.readlink(canonical))
                if link_target.is_absolute():
                    # Chroot-absolute path: prepend target_root to locate on host
                    real_path = self.target_root / str(link_target).lstrip("/")
                else:
                    # Relative symlink: resolve from the symlink's directory
                    real_path = (canonical.parent / link_target).resolve()
                if real_path.exists():
                    initramfs_src = real_path
                else:
                    logger.warning(f"Symlink /boot/initramfs -> {link_target} is broken (dracut may have failed). Falling back to newest initramfs file.")
            elif canonical.is_file():
                initramfs_src = canonical

            if initramfs_src is None and ifiles:
                initramfs_src = max(ifiles, key=lambda f: f.stat().st_mtime)
                logger.info(f"Using fallback initramfs: {initramfs_src.name}")

            if initramfs_src:
                shutil.copy2(initramfs_src, iso_boot / "initramfs")
                logger.info(f"Copied initramfs {initramfs_src.name} -> {iso_boot / 'initramfs'}")
            else:
                logger.warning("No initramfs found in chroot /boot — bootloader will not have an initramfs!")


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

        # Copy GRUB unicode font into iso_root/boot/grub/fonts/unicode.pf2
        font_paths = [
            self.target_root / "usr" / "share" / "grub" / "unicode.pf2",
            self.workdir / "build_host" / "usr" / "share" / "grub" / "unicode.pf2",
            Path("/usr/share/grub/unicode.pf2")
        ]
        iso_fonts_dir = self.iso_dir / "boot" / "grub" / "fonts"
        iso_fonts_dir.mkdir(parents=True, exist_ok=True)
        for font_path in font_paths:
            if font_path.exists():
                shutil.copy2(font_path, iso_fonts_dir / "unicode.pf2")
                logger.info(f"Copied GRUB font {font_path} -> {iso_fonts_dir / 'unicode.pf2'}")
                break

        splash_src = resolve_from_project("configs/custom_files/grub/modern/background.png")
        if splash_src.exists():
            isolinux_target = self.iso_dir / "isolinux"
            try:
                isolinux_target.mkdir(parents=True, exist_ok=True)
                from PIL import Image
                img = Image.open(splash_src)
                img_scaled = img.resize((640, 480), Image.Resampling.LANCZOS)
                img_scaled.save(isolinux_target / "splash.png", "PNG")
                logger.info(f"Scaled and copied ISOLINUX splash image (640x480) -> {isolinux_target / 'splash.png'}")
            except Exception as e:
                logger.warning(f"Could not scale ISOLINUX splash image: {e}")
                shutil.copy2(splash_src, isolinux_target / "splash.png")

        # For syslinux/isolinux targets, copy syslinux boot binaries
        btype = self.config.get("type", "grub-uefi")
        if "syslinux" in btype or "isolinux" in btype or "hybrid" in btype or "dual" in btype:
            syslinux_paths = [
                self.target_root / "usr" / "share" / "syslinux",
                self.target_root / "usr" / "lib" / "syslinux" / "bios",
                self.workdir / "build_host" / "usr" / "share" / "syslinux",
                self.workdir / "build_host" / "usr" / "lib" / "syslinux" / "bios",
                Path("/usr/share/syslinux"),
                Path("/usr/lib/syslinux/bios")
            ]
            
            isolinux_target = self.iso_dir / "isolinux"
            isolinux_target.mkdir(parents=True, exist_ok=True)
            
            copied = False
            sys_files = ["isolinux.bin", "vesamenu.c32", "ldlinux.c32", "libcom32.c32", "libcom.c32", "libutil.c32", "chain.c32", "reboot.c32", "poweroff.c32"]
            for path in syslinux_paths:
                if path.exists():
                    for sys_file in sys_files:
                        src_file = path / sys_file
                        if src_file.exists():
                            shutil.copy2(src_file, isolinux_target / sys_file)
                            copied = True
                    if copied:
                        logger.info(f"Copied syslinux boot binaries from {path} into isolinux target")
                        break
            if not copied and self.mode != "mock":
                logger.warning("Could not find syslinux boot files inside chroot or host distribution!")

    def clean_chroot_for_livecd(self):
        """Cleans temporary build files, logs, caches, and history before creating SquashFS, matching Gentoo Catalyst behavior."""
        if self.mode == "mock":
            logger.info("[MOCK ISO ENGINE] Cleaning chroot before SquashFS creation...")
            return

        logger.info("Cleaning chroot temporary build files, logs, and caches for LiveCD SquashFS...")
        # Force unmount any lingering proc, sys, dev mounts
        for vfs in ["dev/pts", "dev/shm", "dev", "sys", "proc"]:
            vfs_path = self.target_root / vfs
            if vfs_path.exists():
                subprocess.run(["umount", "-l", str(vfs_path)], capture_output=True)

        cleanup_commands = [
            f"rm -rf {self.target_root}/var/tmp/portage/*",
            f"rm -rf {self.target_root}/tmp/*",
            f"rm -rf {self.target_root}/var/tmp/*",
            f"rm -rf {self.target_root}/var/log/portage/*",
            f"rm -rf {self.target_root}/var/log/emerge.log*",
            f"rm -rf {self.target_root}/root/.cache/*",
            f"rm -rf {self.target_root}/root/.bash_history",
            f"rm -rf {self.target_root}/home/*/.cache/*",
            f"rm -rf {self.target_root}/home/*/.bash_history",
            f"rm -rf {self.target_root}/proc/*",
            f"rm -rf {self.target_root}/sys/*",
            f"rm -rf {self.target_root}/run/*",
            f"rm -rf {self.target_root}/dev/*",
        ]
        for cmd in cleanup_commands:
            subprocess.run(cmd, shell=True, capture_output=True)

    def create_squashfs(self):
        squash_path = self.iso_dir / "LiveOS" / "squashfs.img"
        squash_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Creating direct rootfs SquashFS image at {squash_path}")
        if self.mode == "mock":
            logger.info("[MOCK ISO ENGINE] Creating dummy squashfs.img")
            try:
                squash_path.touch()
            except OSError as e:
                logger.warning(f"[MOCK ISO ENGINE] Skipped creating dummy squashfs due to: {e}")
            return

        self.clean_chroot_for_livecd()
        logger.info("Chroot cleanup completed successfully. Starting SquashFS compression (mksquashfs)...")

        cpu_cores = os.cpu_count() or 4
        comp_alg = self.config.get("squashfs_compression", "xz")
        logger.info(f"Using {comp_alg.upper()} compression with {cpu_cores} parallel CPU threads for mksquashfs...")

        cmd = [
            "mksquashfs", str(self.target_root), str(squash_path),
            "-noappend",
            "-comp", comp_alg,
            "-processors", str(cpu_cores),
            "-progress",
            "-wildcards",
            "-e", "proc/*", "sys/*", "dev/*", "run/*", "var/tmp/portage/*", "tmp/*", "var/tmp/*", "var/log/portage/*", "root/.cache/*"
        ]
        res = subprocess.run(cmd)
        if res.returncode != 0:
            raise ISOEngineError("mksquashfs failed during SquashFS compression")

    def _get_template_placeholders(self) -> dict:
        vol_id = self.config.get("vol_id", "gentoo_modern")
        boot_title = self.config.get("title", "Gentoo Modern")
        arch = self.workdir.name if self.workdir else "x86_64"
        desktop_raw = self.config.get("desktop") or getattr(self, "desktop", None) or "GNOME"
        desktop = desktop_raw.upper() if isinstance(desktop_raw, str) else "GNOME"

        # @@BOOT_CMDLINE@@ is for EXTRA args appended AFTER the standard
        # root=live:... rd.live.image ... params already in the template itself.
        # Do NOT include root= or rd.live.* here to avoid duplication.
        extra_bootargs = self.config.get("extra_bootargs", "")

        # Find kernel version string from /boot inside target_root
        kver = "7.1.5-gentoo-dist-bin"
        boot_dir = self.target_root / "boot"
        if boot_dir.exists():
            vmlinuz_files = [f.name.replace("vmlinuz-", "") for f in boot_dir.glob("vmlinuz-*") if not f.name.endswith(('.old', '.bak', '.tmp'))]
            if vmlinuz_files:
                kver = vmlinuz_files[0]

        return {
            "@@BOOT_TITLE@@": boot_title,
            "@@KERNVER@@": kver,
            "@@ARCH@@": arch,
            "@@DESKTOP@@": desktop,
            "@@VOL_ID@@": vol_id,
            "@@BOOT_CMDLINE@@": extra_bootargs,
            "@@KEYMAP@@": self.config.get("keymap", "us"),
            "@@LOCALE@@": self.config.get("locale", "en_US.UTF-8")
        }


    def generate_grub_config(self):
        grub_cfg = self.iso_dir / "boot" / "grub" / "grub.cfg"
        template_file = resolve_from_project("configs/bootloaders/templates/grub.cfg.in")
        
        placeholders = self._get_template_placeholders()

        if template_file.exists():
            content = template_file.read_text()
            for k, v in placeholders.items():
                content = content.replace(k, str(v))
        else:
            vol_id = placeholders["@@VOL_ID@@"]
            bootargs = placeholders["@@BOOT_CMDLINE@@"]
            content = (
                "set default=0\nset timeout=10\nset gfxmode=auto\ninsmod all_video\ninsmod gfxterm\ninsmod png\n"
                "set theme=/boot/grub/themes/modern/theme.txt\nterminal_output gfxterm\n\n"
                f"menuentry 'Boot Gentoo Modern (Default)' --class gnu-linux --class os {{\n"
                f"    search --no-floppy --set=root -l {vol_id}\n"
                f"    linux /boot/vmlinuz {bootargs} quiet splash plymouth.theme=gentoo-modern\n"
                f"    initrd /boot/initramfs\n}}\n"
            )

        if self.mode == "mock":
            logger.info(f"[MOCK ISO ENGINE] Writing GRUB config to {grub_cfg}")
            try:
                grub_cfg.parent.mkdir(parents=True, exist_ok=True)
                grub_cfg.write_text(content)
            except OSError as e:
                logger.warning(f"[MOCK ISO ENGINE] Skipped writing GRUB config due to: {e}")
        else:
            grub_cfg.parent.mkdir(parents=True, exist_ok=True)
            grub_cfg.write_text(content)

    def generate_syslinux_config(self):
        syslinux_cfg = self.iso_dir / "isolinux" / "isolinux.cfg"
        template_file = resolve_from_project("configs/bootloaders/templates/isolinux.cfg.in")
        
        placeholders = self._get_template_placeholders()

        if template_file.exists():
            content = template_file.read_text()
            for k, v in placeholders.items():
                content = content.replace(k, str(v))
        else:
            vol_id = placeholders["@@VOL_ID@@"]
            bootargs = placeholders["@@BOOT_CMDLINE@@"]
            content = (
                "UI vesamenu.c32\nMENU TITLE Gentoo Modern Live ISO\nMENU RESOLUTION 640 480\nMENU BACKGROUND /isolinux/splash.png\n"
                "DEFAULT gentoo\nTIMEOUT 100\nPROMPT 0\n\n"
                "LABEL gentoo\n  MENU LABEL Boot Gentoo Modern (Default)\n  KERNEL /boot/vmlinuz\n"
                f"  APPEND initrd=/boot/initramfs {bootargs} quiet splash plymouth.theme=gentoo-modern\n"
            )

        syslinux_cfg.parent.mkdir(parents=True, exist_ok=True)
        syslinux_cfg.write_text(content)

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

    def generate_grub_efi_image(self):
        """Generates EFI bootable efiboot.img and standalone BOOTX64.EFI image."""
        efiboot_img = self.iso_dir / "boot" / "grub" / "efiboot.img"
        efiboot_img.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Generating EFI standalone image at {efiboot_img}")
        if self.mode == "mock":
            efiboot_img.touch()
            return

        efi_tmp = self.workdir / "tmp_efi"
        efi_tmp.mkdir(parents=True, exist_ok=True)
        bootx64 = efi_tmp / "BOOTX64.EFI"

        if self.toolchain and getattr(self.toolchain, "is_mounted", False):
            self.toolchain.run_in_build_host(
                "grub-mkstandalone --format=x86_64-efi --output=/workdir/tmp_efi/BOOTX64.EFI boot/grub/grub.cfg=/workdir/iso_root/boot/grub/grub.cfg"
            )
        elif shutil.which("grub-mkstandalone"):
            grub_cfg = self.iso_dir / "boot" / "grub" / "grub.cfg"
            subprocess.run([
                "grub-mkstandalone", "--format=x86_64-efi",
                f"-o={bootx64}", f"boot/grub/grub.cfg={grub_cfg}"
            ], capture_output=True)

        if bootx64.exists():
            # 1. Copy BOOTX64.EFI and grub.cfg directly to /EFI/BOOT/ in iso_root
            # This allows direct UEFI filesystem booting on VirtualBox/QEMU/hardware
            iso_efi_dir = self.iso_dir / "EFI" / "BOOT"
            iso_efi_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bootx64, iso_efi_dir / "BOOTX64.EFI")

            grub_cfg = self.iso_dir / "boot" / "grub" / "grub.cfg"
            if grub_cfg.exists():
                shutil.copy2(grub_cfg, iso_efi_dir / "grub.cfg")

            # 2. Package BOOTX64.EFI into El Torito FAT image (efiboot.img)
            subprocess.run(["truncate", "-s", "32M", str(efiboot_img)], check=True)

            packed = False
            if self.toolchain and getattr(self.toolchain, "is_mounted", False):
                res = self.toolchain.run_in_build_host(
                    "mformat -i /workdir/iso_root/boot/grub/efiboot.img -h 32 -t 32 -n 64 -c 1 :: && "
                    "mmd -i /workdir/iso_root/boot/grub/efiboot.img ::/EFI && "
                    "mmd -i /workdir/iso_root/boot/grub/efiboot.img ::/EFI/BOOT && "
                    "mcopy -i /workdir/iso_root/boot/grub/efiboot.img /workdir/tmp_efi/BOOTX64.EFI ::/EFI/BOOT/BOOTX64.EFI"
                )
                if res.returncode == 0:
                    packed = True
                    logger.info(f"Successfully packaged BOOTX64.EFI into {efiboot_img} via isolated toolchain mtools")

            if not packed and shutil.which("mformat") and shutil.which("mcopy"):
                subprocess.run(["mformat", "-i", str(efiboot_img), "-h", "32", "-t", "32", "-n", "64", "-c", "1", "::"], check=True, capture_output=True)
                subprocess.run(["mmd", "-i", str(efiboot_img), "::/EFI"], capture_output=True)
                subprocess.run(["mmd", "-i", str(efiboot_img), "::/EFI/BOOT"], capture_output=True)
                subprocess.run(["mcopy", "-i", str(efiboot_img), str(bootx64), "::/EFI/BOOT/BOOTX64.EFI"], check=True, capture_output=True)
                packed = True
                logger.info(f"Successfully packaged BOOTX64.EFI into {efiboot_img} via host mtools")

            if not packed:
                mkfs_fat = shutil.which("mkfs.vfat") or shutil.which("mkfs.fat")
                if mkfs_fat:
                    subprocess.run([mkfs_fat, str(efiboot_img)], capture_output=True)
                    logger.info(f"Formatted FAT image {efiboot_img} with {mkfs_fat}")

        shutil.rmtree(efi_tmp, ignore_errors=True)

    def generate_bootloader_configs(self):
        btype = self.config.get("type", "grub-uefi")
        logger.info(f"Generating bootloader configurations for type: {btype}")

        if "hybrid" in btype or "dual" in btype:
            self.generate_syslinux_config()
            self.generate_grub_config()
            self.generate_grub_efi_image()
        elif "syslinux" in btype or "isolinux" in btype:
            self.generate_syslinux_config()
        elif "systemd-boot" in btype:
            self.generate_systemd_boot_config()
            self.generate_grub_config()
            self.generate_grub_efi_image()
        else:
            self.generate_grub_config()
            self.generate_grub_efi_image()

        # Clean up empty loader dir if not using systemd-boot
        if "systemd-boot" not in btype:
            loader_dir = self.iso_dir / "loader"
            if loader_dir.exists():
                shutil.rmtree(loader_dir, ignore_errors=True)

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

            success = False
            is_hybrid_isolinux = "isolinux" in btype or "hybrid-isolinux" in btype

            if not is_hybrid_isolinux:
                # Pure GRUB modes: try grub-mkrescue first (embeds GRUB in MBR + EFI)
                if self.toolchain and getattr(self.toolchain, "is_mounted", False):
                    logger.info("Executing grub-mkrescue INSIDE isolated build_host toolchain...")
                    res = self.toolchain.run_in_build_host(
                        f"grub-mkrescue -volid {vol_id} -o /workdir/{output_iso.name} /workdir/iso_root"
                    )
                    if res.returncode == 0:
                        success = True
                    else:
                        logger.warning(f"grub-mkrescue inside build_host failed, trying host fallback...")

                if not success and shutil.which("grub-mkrescue") and shutil.which("mformat"):
                    logger.info("Executing grub-mkrescue on host to build hybrid UEFI/BIOS bootable ISO image...")
                    cmd = [
                        "grub-mkrescue",
                        "-volid", vol_id,
                        "-o", str(output_iso),
                        str(self.iso_dir)
                    ]
                    res = subprocess.run(cmd, capture_output=True, text=True)
                    if res.returncode == 0:
                        success = True
                    else:
                        logger.warning(f"grub-mkrescue on host failed ({res.stderr.strip()}), falling back to xorriso...")
            else:
                logger.info(
                    "Hybrid ISOLINUX+GRUB mode: using xorriso with El Torito (BIOS via ISOLINUX) "
                    "+ EFI (via efiboot.img). This is the most compatible method for all hardware."
                )

            if not success:
                logger.info(f"Using xorriso to build ISO image: {output_iso}")
                cmd = [
                    "xorriso", "-as", "mkisofs",
                    "-pad",
                    "-iso-level", "3",
                    "-rock", "-joliet", "-joliet-long",
                    "-max-iso9660-filenames", "-omit-period",
                    "-omit-version-number", "-relaxed-filenames", "-allow-lowercase",
                    "-volid", vol_id,
                    "-output", str(output_iso)
                ]

                isohdpfx_paths = [
                    self.target_root / "usr" / "share" / "syslinux" / "isohdpfx.bin",
                    self.target_root / "usr" / "lib" / "syslinux" / "bios" / "isohdpfx.bin",
                    self.workdir / "build_host" / "usr" / "share" / "syslinux" / "isohdpfx.bin",
                    self.workdir / "build_host" / "usr" / "lib" / "syslinux" / "bios" / "isohdpfx.bin",
                    Path("/usr/share/syslinux/isohdpfx.bin"),
                    Path("/usr/lib/syslinux/bios/isohdpfx.bin")
                ]
                for isohdpfx in isohdpfx_paths:
                    if isohdpfx.exists():
                        cmd.extend(["-isohybrid-mbr", str(isohdpfx)])
                        logger.info(f"Using isohybrid MBR from: {isohdpfx}")
                        break

                isolinux_bin = self.iso_dir / "isolinux" / "isolinux.bin"
                if isolinux_bin.exists():
                    logger.info("Adding El Torito BIOS boot entry (ISOLINUX)...")
                    cmd.extend([
                        "-eltorito-boot", "isolinux/isolinux.bin",
                        "-eltorito-catalog", "isolinux/boot.cat",
                        "-no-emul-boot", "-boot-load-size", "4", "-boot-info-table"
                    ])
                elif is_hybrid_isolinux:
                    logger.warning(
                        "isolinux/isolinux.bin not found in iso_root — "
                        "BIOS boot will NOT work! Ensure syslinux is installed in the chroot."
                    )

                efiboot_img = self.iso_dir / "boot" / "grub" / "efiboot.img"
                if efiboot_img.exists():
                    logger.info("Adding El Torito EFI boot entry (GRUB EFI)...")
                    cmd.extend([
                        "-eltorito-alt-boot",
                        "-e", "boot/grub/efiboot.img",
                        "-no-emul-boot", "-isohybrid-gpt-basdat"
                    ])

                cmd.append(str(self.iso_dir))

                res = subprocess.run(cmd)
                if res.returncode != 0:
                    raise ISOEngineError(f"ISO creation failed with exit code: {res.returncode}")


        self._generate_checksums(output_iso)
        return output_iso

    def clean_chroot_for_stage3(self):
        """Cleans temporary build caches, logs, and user histories before packaging tarballs or Stage3 seeds."""
        if self.mode == "mock":
            logger.info("[MOCK ISO ENGINE] Cleaning chroot for tarball packaging...")
            return

        logger.info("Cleaning chroot temporary files, build logs, and caches for tarball packaging...")
        cleanup_commands = [
            f"rm -rf {self.target_root}/var/tmp/portage/*",
            f"rm -rf {self.target_root}/tmp/*",
            f"rm -rf {self.target_root}/var/tmp/*",
            f"rm -rf {self.target_root}/var/log/portage/*",
            f"rm -rf {self.target_root}/var/log/emerge.log*",
            f"rm -rf {self.target_root}/root/.cache/*",
            f"rm -rf {self.target_root}/root/.bash_history",
            f"rm -rf {self.target_root}/home/*/.cache/*",
            f"rm -rf {self.target_root}/home/*/.bash_history",
        ]
        for cmd in cleanup_commands:
            subprocess.run(cmd, shell=True, capture_output=True)

    def build_stage3(self) -> Path:
        return self.build_tarball()

    def build_tarball(self) -> Path:
        if self.mode != "mock":
            self.clean_chroot_for_stage3()

        output_tarball = self.workdir / self.output_name
        if not output_tarball.name.endswith((".tar.xz", ".tar.gz", ".tar.bz2", ".tar")):
            output_tarball = self.workdir / f"{Path(self.output_name).stem}.tar.xz"

        logger.info(f"Building compressed rootfs tarball: {output_tarball}")

        if self.mode == "mock":
            logger.info(f"[MOCK ISO ENGINE] Creating dummy tarball: {output_tarball}")
            try:
                output_tarball.write_text("MOCK GENTOO ROOTFS TARBALL CONTENT")
            except OSError as e:
                logger.warning(f"[MOCK ISO ENGINE] Skipped creating dummy tarball due to: {e}")
        else:
            cmd = ["tar", "-cJf", str(output_tarball), "-C", str(self.target_root), "."]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise ISOEngineError(f"Tarball creation failed: {res.stderr}")

        self._generate_checksums(output_tarball)
        return output_tarball

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
