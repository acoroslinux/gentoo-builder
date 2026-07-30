import shutil
import os
import subprocess
import hashlib
from pathlib import Path
from typing import List, Optional
from core.config_loader import ConfigLoader
from core.chroot_manager import ChrootManager
from core.chroot_setup import ChrootSetup
from core.toolchain_manager import ToolchainManager
from core.stage3_manager import Stage3Manager
from core.portage_manager import PortageManager
from core.customizer import SystemCustomizer
from core.iso_engine import ISOEngine
from core.disk_engine import DiskEngine
from core.path_utils import resolve_from_project
from core.logger_setup import setup_logger

logger = setup_logger("orchestrator")

class BuildOrchestratorError(Exception):
    pass

class BuildOrchestrator:
    def __init__(
        self,
        arch: str = "x86_64",
        config_path: str = "configs/global_build.json",
        mode: str = "mock",
        clean: bool = True,
        init_system: Optional[str] = "openrc",
        desktop: Optional[str] = None,
        kernel: Optional[str] = None,
        bootloader: Optional[str] = None,
        package_profiles: Optional[List[str]] = None,
        service_profiles: Optional[List[str]] = None,
        live_profile: Optional[str] = None,
        output_name: Optional[str] = None,
        force_isolated_toolchain: bool = False,
        target: str = "livecd-stage2",
        output_format: str = "iso",
        stage3_url: str = None
    ):
        self.arch = arch
        self.config_path = resolve_from_project(config_path)
        self.mode = mode
        self.clean = clean
        self.init_system = init_system or "openrc"
        self.desktop = desktop
        self.kernel = kernel
        self.bootloader = bootloader
        self.package_profiles = list(package_profiles) if package_profiles else []
        self.service_profiles = list(service_profiles) if service_profiles else []
        self.live_profile = live_profile
        self.target = target or "livecd-stage2"
        self.output_format = output_format
        self.stage3_url = stage3_url

        # Automatically include calamares installer profile ONLY for LiveCD target ISO builds
        if self.target.startswith("livecd") and self.output_format == "iso" and "calamares" not in self.package_profiles:
            self.package_profiles.append("calamares")

        # Determine extension based on format or target
        if self.output_format in ["tarball", "stage3"] or self.target in ["livecd-stage1", "diskimage-stage1", "embedded"]:
            ext = "tar.xz"
        elif self.output_format == "img" or self.target == "diskimage-stage2":
            ext = "img"
        elif self.target == "netboot":
            ext = "tar.gz"
        else:
            ext = "iso"

        if output_name:
            self.output_name = output_name
        elif self.output_format == "stage3":
            self.output_name = f"gentoo-modern-stage3-{self.init_system}-{desktop or 'base'}-{arch}.tar.xz"
        else:
            self.output_name = f"gentoo-builder-{self.init_system}-{desktop or 'base'}-{arch}.{ext}"
        self.force_isolated_toolchain = force_isolated_toolchain

        self.workdir = resolve_from_project("workdir") / self.arch
        self.target_root = self.workdir / "chroot"
        self.config_loader = ConfigLoader()

    def _safe_clean_build_tree(self):
        """
        Limpa APENAS as pastas de build (chroot e iso_root),
        PRESERVANDO a pasta 'cache' com o Stage3 e os pacotes baixados.
        """
        if not self.workdir.exists():
            return

        logger.info(f"Limpar pastas de compilação (preservando cache de downloads) em: {self.workdir}")
        if self.mode != "mock":
            chroot_tmp = ChrootManager(self.target_root, self.mode)
            chroot_tmp.umount_virtual_fs()
            toolchain_tmp = ToolchainManager(self.workdir, self.mode)
            toolchain_tmp.umount_virtual_fs()

            for mount_point in [self.target_root / "dev" / "pts", self.target_root / "dev" / "shm", self.target_root / "dev", self.target_root / "sys", self.target_root / "proc"]:
                if mount_point.exists():
                    subprocess.run(["umount", "-l", str(mount_point)], capture_output=True)

        # Apagar apenas chroot e iso_root, preservando a pasta cache/
        targets_to_clean = [self.workdir / "chroot", self.workdir / "iso_root"]
        for target in targets_to_clean:
            if target.exists():
                try:
                    shutil.rmtree(target)
                except Exception as e:
                    logger.warning(f"Não foi possível remover {target} diretamente: {e}. A tentar remoção recursiva...")
                    shutil.rmtree(target, ignore_errors=True)

    def _create_tarball(self, source_dir: Path, output_file: Path):
        logger.info(f"Creating archive at {output_file} from {source_dir}...")
        if self.mode == "mock":
            logger.info(f"[MOCK ARCHIVER] Creating dummy tarball: {output_file}")
            output_file.write_text("MOCK GENTOO ARCHIVE CONTENT")
        else:
            if output_file.name.endswith(".gz"):
                cmd = ["tar", "czf", str(output_file), "-C", str(source_dir), "."]
            else:
                cmd = ["tar", "cJf", str(output_file), "-C", str(source_dir), "."]
            subprocess.run(cmd, check=True)

        # Generate checksums
        content = output_file.read_bytes()
        md5 = hashlib.md5(content).hexdigest()
        sha256 = hashlib.sha256(content).hexdigest()
        (output_file.parent / f"{output_file.name}.md5").write_text(f"{md5}  {output_file.name}\n")
        (output_file.parent / f"{output_file.name}.sha256").write_text(f"{sha256}  {output_file.name}\n")

    def build(self) -> Path:
        logger.info(f"Starting Gentoo-Builder pipeline [{self.target.upper()}] [{self.init_system.upper()}] in [{self.mode.upper()}] mode...")
        
        if self.clean:
            self._safe_clean_build_tree()

        self.workdir.mkdir(parents=True, exist_ok=True)

        # 1. Load merged configurations
        build_config = self.config_loader.assemble_build_config(
            global_config_path=self.config_path,
            architecture=self.arch,
            init_system=self.init_system,
            desktop=self.desktop,
            kernel=self.kernel,
            bootloader=self.bootloader,
            package_profiles=self.package_profiles,
            service_profiles=self.service_profiles,
            live_profile=self.live_profile
        )

        if self.output_format == "stage3":
            logger.info("Stripping kernel and bootloader packages for pristine Stage3 build...")
            build_config["packages"] = [
                pkg for pkg in build_config.get("packages", [])
                if not pkg.startswith("sys-kernel/") and not pkg.startswith("sys-boot/")
            ]

        if self.stage3_url:
            if "stage3" not in build_config:
                build_config["stage3"] = {}
            build_config["stage3"]["url"] = self.stage3_url

        # 2. Toolchain / Build Host Setup (Isolated Environment)
        toolchain = ToolchainManager(self.workdir, mode=self.mode, force_isolated=self.force_isolated_toolchain)
        if self.force_isolated_toolchain or not toolchain.check_host_tools():
            toolchain.bootstrap_build_host()
            toolchain.mount_virtual_fs()
            toolchain.ensure_build_tools()

        try:
            # 3. Target Stage3 Bootstrap
            stage3 = Stage3Manager(self.workdir, build_config.get("stage3", {}), mode=self.mode)
            stage3.fetch_and_extract(self.target_root, clean=self.clean)

            # 4. Setup Host Network and Profile Symlinks inside Chroot
            chroot_setup = ChrootSetup(self.target_root, mode=self.mode, default_profile=build_config.get("default_profile"))
            chroot_setup.prepare_resolv_conf()
            chroot_setup.prepare_default_profile_symlink()

            # 5. Setup Target Chroot Environment & Virtual Filesystems
            cache_dir = self.workdir / "cache"
            chroot = ChrootManager(self.target_root, mode=self.mode, cache_dir=cache_dir)
            chroot.mount_virtual_fs()

            try:
                # 6. Configure Portage & Install Packages
                portage = PortageManager(chroot, build_config)
                portage.configure_make_conf()
                portage.sync_portage()

                # 6.1 Write dracut LiveCD conf and install dracut BEFORE the kernel,
                # so installkernel picks up the LiveCD dmsquash-live config at build time.
                if self.output_format != "stage3":
                    portage.setup_dracut_livecd_conf()
                    logger.info("Installing sys-kernel/dracut, lvm2, and cryptsetup explicitly before kernel package...")
                    portage.chroot.run_in_chroot(
                        ["emerge", "--ask=n", "--noreplace", "--verbose", "sys-kernel/dracut", "sys-fs/lvm2", "sys-fs/cryptsetup"],
                        check=False
                    )

                # 6.2 Prioritize Kernel & Firmware installation so /usr/src/linux exists for driver modules (skipped for Stage3 seeds)
                kernel_pkgs = build_config.get("kernel_packages", [])
                if kernel_pkgs and self.output_format != "stage3":
                    logger.info(f"Prioritizing kernel package installation FIRST: {' '.join(kernel_pkgs)}")
                    portage.install_packages(kernel_pkgs)

                # 6.2 Install remaining target system packages
                portage.install_packages(build_config.get("packages", []))

                # Handle Stage 1 and minimal embedded tarball targets
                if self.target in ["livecd-stage1", "diskimage-stage1", "embedded"]:
                    chroot.umount_virtual_fs()
                    output_file = self.workdir / self.output_name
                    self._create_tarball(self.target_root, output_file)
                    logger.info(f"Target build completed successfully! Output: {output_file}")
                    return output_file

                # Handle netboot target (kernel + initramfs pack)
                if self.target == "netboot":
                    # Build kernel packages if needed
                    customizer = SystemCustomizer(chroot, build_config)
                    customizer.configure_system_defaults()
                    
                    # Package boot files (kernel + initramfs)
                    boot_dir = self.target_root / "boot"
                    if self.mode == "mock":
                        boot_dir.mkdir(parents=True, exist_ok=True)
                        (boot_dir / "vmlinuz-mock").touch()
                        (boot_dir / "initramfs-mock.img").touch()

                    output_file = self.workdir / self.output_name
                    self._create_tarball(boot_dir, output_file)
                    logger.info(f"Netboot target completed successfully! Output: {output_file}")
                    return output_file

                bootloader_cfg = build_config.get("bootloader", {})
                bootloader_cfg["desktop"] = self.desktop or build_config.get("desktop", "GNOME")
                iso_engine = ISOEngine(self.workdir, self.target_root, self.output_name, config=bootloader_cfg, mode=self.mode, toolchain=toolchain)

                if self.output_format == "stage3":
                    chroot.umount_virtual_fs()
                    stage3_file = iso_engine.build_stage3()
                    logger.info(f"Pristine Stage3 seed tarball build completed successfully! Output: {stage3_file}")
                    return stage3_file

                # 7. Customize target system defaults (only for LiveCD / DiskImage targets)
                customizer = SystemCustomizer(chroot, build_config)
                customizer.setup_live_users()
                customizer.configure_system_defaults()
                customizer.setup_services()

                # Ensure Dracut initramfs is freshly regenerated with LiveCD support before unmounting & packaging
                if self.output_format != "stage3" and self.mode != "mock":
                    logger.info("Regenerating Dracut initramfs with LiveCD dmsquash-live support...")
                    # Find the installed kernel version to target the correct initramfs
                    # Sort to always pick the newest if multiple kernels exist
                    boot_dir = self.target_root / "boot"
                    kver = None
                    if boot_dir.exists():
                        kfiles = [
                            f for f in boot_dir.glob("vmlinuz-*")
                            if not f.name.endswith(('.old', '.bak', '.tmp'))
                        ]
                        if not kfiles:
                            kfiles = [
                                f for f in boot_dir.glob("kernel-*")
                                if not f.name.endswith(('.old', '.bak', '.tmp'))
                            ]
                        if kfiles:
                            newest_kfile = sorted(kfiles, key=lambda f: f.stat().st_mtime, reverse=True)[0]
                            kver = newest_kfile.name.replace("vmlinuz-", "").replace("kernel-", "")

                    if kver:
                        logger.info(f"Regenerating initramfs for kernel version: {kver}")
                        try:
                            chroot.run_in_chroot(
                                f'dracut --force --no-hostonly --xz '
                                f'--add "dmsquash-live pollcdrom" '
                                f'--add-drivers "squashfs loop overlay ext3 ext4 iso9660 vfat" '
                                f'/boot/initramfs-{kver}.img {kver}',
                                check=False
                            )
                            # Create RELATIVE symlinks so Python on the HOST can resolve them
                            # correctly without chroot-absolute path confusion.
                            chroot.run_in_chroot(
                                f'ln -sf initramfs-{kver}.img /boot/initramfs',
                                check=False
                            )
                            chroot.run_in_chroot(
                                f'ln -sf vmlinuz-{kver} /boot/vmlinuz',
                                check=False
                            )
                        except Exception as e:
                            logger.warning(
                                f"Dracut regeneration failed ({e}). "
                                f"The kernel-generated initramfs will be used instead. "
                                f"The ISO may still boot if installkernel produced a valid initramfs."
                            )
                    else:
                        logger.warning("Could not detect kernel version — skipping dracut regeneration.")

                # Unmount chroot virtual filesystems before creating ISO / tarball / disk image
                chroot.umount_virtual_fs()

                if self.output_format == "tarball":
                    tarball_file = iso_engine.build_tarball()
                    logger.info(f"Tarball build completed successfully! Output: {tarball_file}")
                    return tarball_file

                if self.output_format == "img" or self.target == "diskimage-stage2":
                    # 8. Build disk image via DiskEngine
                    disk_engine = DiskEngine(self.workdir, self.target_root, self.output_name, config=build_config, mode=self.mode)
                    img_file = disk_engine.build_disk_image()
                    logger.info(f"Disk image build completed successfully! Output: {img_file}")
                    return img_file

                # Default target: livecd-stage2 ISO
                # 8. Build ISO with GRUB bootloader options
                iso_file = iso_engine.build_iso()
                
                # Copy final ISO to output/ directory for easy user access
                project_output_dir = resolve_from_project("output")
                project_output_dir.mkdir(parents=True, exist_ok=True)
                final_output_file = project_output_dir / iso_file.name
                if iso_file != final_output_file:
                    try:
                        shutil.copy2(iso_file, final_output_file)
                        if iso_file.with_suffix(iso_file.suffix + ".md5").exists():
                            shutil.copy2(iso_file.with_suffix(iso_file.suffix + ".md5"), final_output_file.with_suffix(final_output_file.suffix + ".md5"))
                        if iso_file.with_suffix(iso_file.suffix + ".sha256").exists():
                            shutil.copy2(iso_file.with_suffix(iso_file.suffix + ".sha256"), final_output_file.with_suffix(final_output_file.suffix + ".sha256"))
                        logger.info(f"Copied final ISO to: {final_output_file}")
                    except OSError as e:
                        logger.warning(f"Could not copy ISO to output directory: {e}")

                logger.info(f"Build completed successfully! Output: {iso_file}")
                return iso_file
            finally:
                chroot.umount_virtual_fs()
        finally:
            if toolchain.is_mounted:
                toolchain.umount_virtual_fs()
