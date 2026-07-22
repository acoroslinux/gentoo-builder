import shutil
import os
import subprocess
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
        force_isolated_toolchain: bool = False
    ):
        self.arch = arch
        self.config_path = resolve_from_project(config_path)
        self.mode = mode
        self.clean = clean
        self.init_system = init_system or "openrc"
        self.desktop = desktop
        self.kernel = kernel
        self.bootloader = bootloader
        self.package_profiles = package_profiles or []
        self.service_profiles = service_profiles or []
        self.live_profile = live_profile
        self.output_name = output_name or f"gentoo-builder-{self.init_system}-{desktop or 'base'}-{arch}.iso"
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

    def build(self) -> Path:
        logger.info(f"Starting Gentoo-Builder pipeline [{self.init_system.upper()}] in [{self.mode.upper()}] mode...")
        
        if self.clean:
            self._safe_clean_build_tree()

        self.workdir.mkdir(parents=True, exist_ok=True)

        # 1. Load merged configurations
        build_config = self.config_loader.assemble_build_config(
            global_config_path=self.config_path,
            init_system=self.init_system,
            desktop=self.desktop,
            kernel=self.kernel,
            bootloader=self.bootloader,
            package_profiles=self.package_profiles,
            service_profiles=self.service_profiles,
            live_profile=self.live_profile
        )

        # 2. Toolchain / Build Host Setup (Isolated Environment)
        toolchain = ToolchainManager(self.workdir, mode=self.mode, force_isolated=self.force_isolated_toolchain)
        if self.force_isolated_toolchain or not toolchain.check_host_tools():
            toolchain.bootstrap_build_host()
            toolchain.mount_virtual_fs()

        try:
            # 3. Target Stage3 Bootstrap
            stage3 = Stage3Manager(self.workdir, build_config.get("stage3", {}), mode=self.mode)
            stage3.fetch_and_extract(self.target_root)

            # 4. Setup Host Network and Profile Symlinks inside Chroot
            chroot_setup = ChrootSetup(self.target_root, mode=self.mode)
            chroot_setup.prepare_resolv_conf()
            chroot_setup.prepare_default_profile_symlink()

            # 5. Setup Target Chroot Environment & Virtual Filesystems
            chroot = ChrootManager(self.target_root, mode=self.mode)
            chroot.mount_virtual_fs()

            try:
                # 6. Configure Portage & Install Packages
                portage = PortageManager(chroot, build_config)
                portage.configure_make_conf()
                portage.sync_portage()
                portage.install_packages(build_config.get("packages", []))

                # 7. LiveCD Customizations (supporting OpenRC, Systemd, Runit, s6)
                customizer = SystemCustomizer(chroot, build_config)
                customizer.configure_system_defaults()
                customizer.setup_live_users()
                customizer.setup_services()

                # 8. Build ISO with GRUB bootloader options
                iso_engine = ISOEngine(self.workdir, self.target_root, self.output_name, config=build_config.get("bootloader", {}), mode=self.mode)
                iso_file = iso_engine.build_iso()
                
                logger.info(f"Build completed successfully! Output: {iso_file}")
                return iso_file
            finally:
                chroot.umount_virtual_fs()
        finally:
            if toolchain.is_mounted:
                toolchain.umount_virtual_fs()
