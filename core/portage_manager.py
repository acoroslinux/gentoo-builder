import os
import platform
import shutil
from pathlib import Path
from typing import Dict, Any, List
from core.chroot_manager import ChrootManager
from core.logger_setup import setup_logger

logger = setup_logger("portage_manager")

# Architectures that require QEMU emulation on x86_64 host (note: i686/i386 run NATIVELY on x86_64!)
_QEMU_ARCHES = {"aarch64", "arm64", "riscv64", "riscv", "armv7", "armhf", "ppc64le", "ppc64"}

def _is_qemu_chroot(config: Dict[str, Any]) -> bool:
    """Return True if the target architecture requires QEMU user-mode emulation."""
    host_machine = platform.machine().lower()  # e.g. 'x86_64'
    target_arch = config.get("arch", "").lower()  # e.g. 'aarch64', 'riscv64', 'i686'
    if not target_arch:
        return False
    
    if host_machine in ("x86_64", "amd64"):
        # i686, i386, x86, x86_64 run NATIVELY on x86_64 Linux kernels
        if target_arch in ("i686", "i386", "x86", "x86_64", "amd64"):
            return False
        return target_arch in _QEMU_ARCHES
    
    if host_machine in ("aarch64", "arm64"):
        if target_arch in ("aarch64", "arm64"):
            return False
        return True

    return False

class PortageManagerError(Exception):
    pass

class PortageManager:
    def __init__(self, chroot: ChrootManager, config: Dict[str, Any]):
        self.chroot = chroot
        self.config = config
        self.target_root = chroot.target_root
        self._overlay_setup_done = False

    def configure_make_conf(self):
        make_conf_path = self.target_root / "etc" / "portage" / "make.conf"
        make_conf_path.parent.mkdir(parents=True, exist_ok=True)

        make_conf_data = self.config.get("make_conf", {})
        use_flags = self.config.get("use_flags", [])

        # Detect host CPU cores and RAM dynamically for safe, maximum build performance
        cpu_count = os.cpu_count() or 2
        makeopts = f"-j{cpu_count}"
        load_avg = str(cpu_count)

        mem_total_gb = 32
        if os.path.exists("/proc/meminfo"):
            try:
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            mem_kb = int(line.split()[1])
                            mem_total_gb = max(4, mem_kb // (1024 * 1024))
                            break
            except Exception:
                pass

        # Detect QEMU cross-arch emulation: if so, force single-job to avoid
        # 'qemu_thread_create: Invalid argument' crashes from parallel Portage jobs
        using_qemu = _is_qemu_chroot(self.config)

        if using_qemu:
            # QEMU user-mode emulation: use safe multi-threading
            safe_jobs = max(1, min(cpu_count // 2, 4))
            qemu_threads = max(2, min(cpu_count, 4))
            safe_makeopts = f"-j{qemu_threads}"
            load_avg = str(qemu_threads)
            emerge_opts = f"--jobs={safe_jobs} --load-average={load_avg} --ask=n --autounmask-write=y --autounmask-continue=y --binpkg-respect-use=y --buildpkg --usepkg"
            features_val = "binpkg-logs parallel-fetch buildpkg"
            logger.info(f"[PORTAGE] QEMU emulation detected: using MAKEOPTS={safe_makeopts} --jobs={safe_jobs}")
        else:
            # Native execution (x86_64 and i686/i386 on x86_64 host): MAX PERFORMANCE WITH ALL CPU CORES!
            safe_jobs = max(1, min(cpu_count // 2, mem_total_gb // 3, 12))
            safe_makeopts = f"-j{cpu_count}"
            load_avg = str(cpu_count)
            emerge_opts = f"--jobs={safe_jobs} --load-average={load_avg} --ask=n --autounmask-write=y --autounmask-continue=y --binpkg-respect-use=y --buildpkg --usepkg"
            features_val = "binpkg-logs parallel-install parallel-fetch buildpkg"
            logger.info(f"[PORTAGE] Native execution detected ({self.config.get('arch')}): using FULL CPU power MAKEOPTS={safe_makeopts} --jobs={safe_jobs}")

        # CFLAGS: always comes from arch JSON (e.g. arm64.json has -march=armv8-a).
        # Fall back to a generic safe value if somehow missing.
        cflags = make_conf_data.get("CFLAGS", "-O2 -pipe")
        # ACCEPT_KEYWORDS: comes from arch JSON (e.g. ~arm64, ~amd64, ~riscv).
        # Derive from arch if missing from config.
        target_arch = self.config.get("arch", platform.machine().lower())
        _arch_keyword_map = {
            "x86_64": "~amd64", "amd64": "~amd64",
            "aarch64": "~arm64", "arm64": "~arm64",
            "riscv64": "~riscv",
            "i686": "~x86", "i386": "~x86",
            "ppc64le": "~ppc64", "ppc64": "~ppc64",
        }
        default_keywords = _arch_keyword_map.get(target_arch, f"~{target_arch}")
        accept_keywords = make_conf_data.get("ACCEPT_KEYWORDS", default_keywords)

        makeopts_val = make_conf_data.get("MAKEOPTS") if "MAKEOPTS" in make_conf_data and make_conf_data["MAKEOPTS"] != "-j2" else safe_makeopts
        # Under QEMU always enforce -j1 regardless of config override
        if using_qemu:
            makeopts_val = "-j1"

        lines = [
            '# Generated by gentoo-builder (Hardware & RAM Optimized)',
            'COMMON_FLAGS="' + cflags + '"',
            'CFLAGS="${COMMON_FLAGS}"',
            'CXXFLAGS="${COMMON_FLAGS}"',
            'FCFLAGS="${COMMON_FLAGS}"',
            'FFLAGS="${COMMON_FLAGS}"',
            'MAKEOPTS="' + makeopts_val + '"',
            'ACCEPT_KEYWORDS="' + accept_keywords + '"',
            'ACCEPT_LICENSE="' + make_conf_data.get("ACCEPT_LICENSE", "*") + '"',
            'USE="' + " ".join(use_flags) + '"',
            f'EMERGE_DEFAULT_OPTS="{emerge_opts}"',
            f'FEATURES="{features_val}"',
            'PORTAGE_NICENESS="10"',
            'DISTDIR="/var/cache/distfiles"',
            'PKGDIR="/var/cache/binpkgs"'
        ]

        # Append any custom variables (like VIDEO_CARDS, INPUT_DEVICES, etc.)
        for key, val in make_conf_data.items():
            if key not in ["CFLAGS", "CXXFLAGS", "FCFLAGS", "FFLAGS", "COMMON_FLAGS", "MAKEOPTS", "ACCEPT_KEYWORDS", "ACCEPT_LICENSE", "USE", "EMERGE_DEFAULT_OPTS", "FEATURES", "PORTAGE_NICENESS", "DISTDIR", "PKGDIR"]:
                lines.append(f'{key}="{val}"')

        if self.chroot.mode == "mock":
            logger.info(f"[MOCK PORTAGE] Writing hardware-optimized make.conf to {make_conf_path} (MAKEOPTS={makeopts_val})")
        else:
            logger.info(f"[PORTAGE] Configured make.conf with hardware optimization: MAKEOPTS={makeopts_val}, EMERGE_DEFAULT_OPTS='--jobs={safe_jobs} --load-average={load_avg}'")
            with open(make_conf_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

        # Write package.use overrides to disable broken build-time doc tools & route asciidoc to stable python3.13
        if self.chroot.mode != "mock":
            package_use_dir = self.target_root / "etc" / "portage" / "package.use"
            package_use_dir.mkdir(parents=True, exist_ok=True)
            with open(package_use_dir / "00-builder-overrides", "w", encoding="utf-8") as f:
                f.write(
                    "sys-kernel/dracut -doc -man\n"
                    "# FIXME: Remove Python 3.13 overrides once Python 3.14 asciidoc bug is resolved upstream\n"
                    "app-text/asciidoc -doc -man -test python_single_target_python3_13 -python_single_target_python3_14\n"
                    "dev-python/gpep517 python_targets_python3_13\n"
                    "dev-python/setuptools python_targets_python3_13\n"
                    "dev-python/trove-classifiers python_targets_python3_13\n"
                    "dev-python/calver python_targets_python3_13\n"
                    "dev-python/flit-core python_targets_python3_13\n"
                    "dev-python/jaraco-functools python_targets_python3_13\n"
                    "dev-python/jaraco-context python_targets_python3_13\n"
                    "dev-python/jaraco-text python_targets_python3_13\n"
                    "dev-python/more-itertools python_targets_python3_13\n"
                    "dev-python/platformdirs python_targets_python3_13\n"
                    "dev-python/packaging python_targets_python3_13\n"
                    "dev-python/installer python_targets_python3_13\n"
                    "dev-python/wheel python_targets_python3_13\n"
                    "dev-python/setuptools-scm python_targets_python3_13\n"
                    "dev-python/vcs-versioning python_targets_python3_13\n"
                    "dev-python/mako python_targets_python3_13\n"
                    "dev-python/markupsafe python_targets_python3_13\n"
                    "sys-kernel/gentoo-kernel-bin -doc -man\n"
                    "sys-kernel/installkernel -doc -man\n"
                    "# PulseAudio ALSA plugin required by xfce4-pulseaudio-plugin\n"
                    "media-plugins/alsa-plugins pulseaudio\n"
                    "# GNOME Mutter & Wayland & Samba & libcanberra & ngtcp2 & spice-gtk & networkmanager & freerdp & curl requirements\n"
                    "x11-base/xwayland libei\n"
                    "x11-wm/mutter wayland screencast\n"
                    "net-fs/samba client\n"
                    "media-libs/libcanberra pulseaudio sound\n"
                    "net-libs/ngtcp2 gnutls\n"
                    "net-misc/spice-gtk vala gtk3 introspection\n"
                    "net-misc/networkmanager gnutls -nss\n"
                    "net-misc/freerdp server\n"
                    "net-misc/curl openssl -gnutls ssl curl_ssl_openssl -curl_ssl_gnutls -http3 -quic\n"
                    "app-text/poppler cairo\n"
                    "media-libs/gst-plugins-base ogg pango theora vorbis\n"
                    "media-libs/libmediaart gtk -qt5 -qt6\n"
                    "dev-libs/folks eds\n"
                    "kde-frameworks/* qml\n"
                    "kde-plasma/* qml\n"
                    "dev-qt/* qml vulkan\n"
                    "kde-frameworks/kimageformats heif avif\n"
                    "media-libs/phonon gstreamer\n"
                    "dev-qt/qt5compat qml\n"
                    "kde-plasma/kwin lock\n"
                    "dev-util/ostree -dracut\n"
                    "media-libs/libheif x265 de265\n"
                    "dev-qt/qtbase cups vulkan\n"
                    "dev-qt/qtdeclarative vulkan\n"
                    "sys-libs/zlib minizip\n"
                    "media-gfx/imagemagick svg xml\n"
                    "gnome-base/gvfs samba cifs nfs fuse udisks http zeroconf -google archive\n"
                    "net-fs/samba client server winbind -gpg -ads -ldap\n"
                    "net-dns/bind gssapi\n"
                    "net-dns/avahi dbus python mdnsresponder-compat -gtk -gtk3 -qt5 -qt6\n"
                    "x11-misc/xdg-user-dirs gtk\n"
                    "media-sound/qmmp soxr\n"
                    "media-video/pipewire alsa bluetooth sound-server gstreamer ffmpeg extra\n"
                    "gui-libs/gtk -vulkan\n"
                    "dev-cpp/gtkmm -vulkan\n"
                    "app-text/poppler nss qt6 cairo jpeg tiff\n"
                    "media-libs/opus custom-modes\n"
                    "media-libs/gegl cairo png jpeg svg tiff lcms introspection\n"
                    "dev-libs/libdbusmenu gtk3\n"
                    "app-admin/conky X xft truetype lua-cairo bundled-toluapp -wayland\n"
                    "x11-libs/cairo X glib svg cairo-xlib\n"
                    "media-libs/libglvnd X\n"
                )

                init_sys = self.config.get("init_system", "openrc")
                if init_sys == "systemd":
                    f.write(
                        "sys-auth/polkit systemd -elogind\n"
                        "sys-apps/systemd policykit -elogind\n"
                        "sys-apps/dbus systemd\n"
                        "net-misc/networkmanager systemd -elogind\n"
                        "net-misc/modemmanager systemd -elogind\n"
                    )
                else:
                    f.write(
                        "sys-auth/polkit elogind -systemd\n"
                        "sys-apps/dbus -systemd\n"
                        "net-misc/networkmanager elogind -systemd\n"
                    )

            # Write package.accept_keywords to unmask profile packages, Calamares & printer drivers
            # Note: We use ~x86 ~amd64 ~arm64 keywords (not **) so Portage selects stable/testing release tarballs
            # instead of unstable live VCS git ebuilds (-9999).
            package_keywords_dir = self.target_root / "etc" / "portage" / "package.accept_keywords"
            package_keywords_dir.mkdir(parents=True, exist_ok=True)
            
            all_pkgs = self.config.get("packages", [])
            kw_lines = [
                "# Automatically generated by gentoo-builder to unmask profile-requested packages",
                "app-admin/calamares ** ~x86 ~amd64 ~arm64 ~riscv",
                "sys-libs/kpmcore ** ~x86 ~amd64 ~arm64",
                "net-print/epson-inkjet-printer-escpr ** ~x86 ~amd64 ~arm64",
                "net-print/* ~x86 ~amd64 ~arm64 ~riscv",
            ]
            for pkg in all_pkgs:
                kw_lines.append(f"{pkg} ~x86 ~amd64 ~arm64 ~riscv ~arm ~ppc64")

            with open(package_keywords_dir / "00-builder-keywords", "w", encoding="utf-8") as f_kw:
                f_kw.write("\n".join(kw_lines) + "\n")

            # Write package.mask to block live git ebuilds (-9999) from being pulled into production images
            package_mask_dir = self.target_root / "etc" / "portage" / "package.mask"
            package_mask_dir.mkdir(parents=True, exist_ok=True)
            with open(package_mask_dir / "00-builder-mask", "w", encoding="utf-8") as f_mask:
                f_mask.write(
                    "# Block live VCS git ebuilds (-9999) to ensure reproducible tarball builds\n"
                    "*/*-9999*\n"
                )

            # Create /etc/portage/env/low-ram.conf and /etc/portage/package.env/00-builder-ram-limits
            # to restrict compilation threads for memory-heavy packages (nodejs, rust, webkit-gtk, gcc, spidermonkey)
            env_dir = self.target_root / "etc" / "portage" / "env"
            env_dir.mkdir(parents=True, exist_ok=True)
            with open(env_dir / "low-ram.conf", "w", encoding="utf-8") as f:
                f.write('MAKEOPTS="-j8"\n')
            with open(env_dir / "low-ram-node.conf", "w", encoding="utf-8") as f:
                f.write('MAKEOPTS="-j4"\n')

            package_env_dir = self.target_root / "etc" / "portage" / "package.env"
            package_env_dir.mkdir(parents=True, exist_ok=True)
            with open(package_env_dir / "00-builder-ram-limits", "w", encoding="utf-8") as f:
                f.write(
                    "net-libs/nodejs low-ram-node.conf\n"
                    "net-libs/webkit-gtk low-ram-node.conf\n"
                    "dev-lang/spidermonkey low-ram.conf\n"
                    "dev-lang/rust low-ram.conf\n"
                    "dev-lang/rust-bin low-ram.conf\n"
                    "sys-devel/gcc low-ram.conf\n"
                    "dev-db/sqlite low-ram.conf\n"
                )

            # dracut.conf.d is written here for reference but MUST also be called
            # explicitly via setup_dracut_livecd_conf() BEFORE the kernel is installed.
            self.setup_dracut_livecd_conf()

    def setup_dracut_livecd_conf(self):
        """Writes dracut LiveCD configuration BEFORE the kernel is installed.
        This ensures installkernel/dracut generates the correct initramfs with
        dmsquash-live support during the kernel emerge step itself."""
        if self.chroot.mode == "mock":
            logger.info("[MOCK PORTAGE] Writing dracut LiveCD conf (10-livecd.conf)")
            return

        dracut_conf_dir = self.target_root / "etc" / "dracut.conf.d"
        dracut_conf_dir.mkdir(parents=True, exist_ok=True)
        conf_path = dracut_conf_dir / "10-livecd.conf"
        conf_path.write_text(
            '# Generated by gentoo-builder for LiveCD/LiveUSB boot\n'
            'hostonly="no"\n'
            'hostonly_cmdline="no"\n'
            '# dmsquash-live: mounts SquashFS from CD/USB label\n'
            '# pollcdrom: scans optical/virtual drives for the live medium\n'
            '# dmsquash-live: loads the squashfs/overlayfs live root\n'
            'add_dracutmodules+=" dmsquash-live pollcdrom "\n'
            'add_drivers+=" squashfs loop overlay ext3 ext4 iso9660 vfat "\n'
            'filesystems+=" squashfs ext3 ext4 iso9660 vfat "\n'
            'compress="xz"\n'
        )
        logger.info(f"Written dracut LiveCD conf -> {conf_path}")

    def sync_portage(self):
        logger.info("Syncing Portage ebuild repository (emerge-webrsync)...")
        res = self.chroot.run_in_chroot(["emerge-webrsync"])
        if res.returncode != 0 and self.chroot.mode == "real":
            raise PortageManagerError(f"emerge-webrsync failed to sync Portage repository:\n{res.stderr}")

    def update_world(self):
        """Update Gentoo world set non-interactively (--ask=n)."""
        logger.info("Updating base packages and slot dependencies (emerge --ask=n --update --deep --newuse @world)...")
        self.chroot.run_in_chroot("env-update")

        # Resolve init system package conflicts (sysvinit vs s6-linux-init vs systemd vs elogind)
        init_sys = self.config.get("init_system", "openrc")
        if init_sys == "systemd":
            self.chroot.run_in_chroot("emerge --ask=n --deselect sys-auth/elogind 2>/dev/null || true")
            self.chroot.run_in_chroot("emerge --ask=n --unmerge sys-auth/elogind 2>/dev/null || true")
        else:
            self.chroot.run_in_chroot("emerge --ask=n --deselect sys-apps/systemd sys-apps/systemd-initctl 2>/dev/null || true")
            self.chroot.run_in_chroot("emerge --ask=n --unmerge sys-apps/systemd sys-apps/systemd-initctl 2>/dev/null || true")

        if init_sys == "s6":
            self.chroot.run_in_chroot("emerge --deselect sys-apps/sysvinit 2>/dev/null || true")
            self.chroot.run_in_chroot("emerge -C sys-apps/sysvinit 2>/dev/null || true")
        elif init_sys == "sysvinit":
            self.chroot.run_in_chroot("emerge --deselect sys-apps/s6-linux-init sys-apps/s6-rc sys-apps/s6 2>/dev/null || true")
            self.chroot.run_in_chroot("emerge -C sys-apps/s6-linux-init sys-apps/s6-rc sys-apps/s6 2>/dev/null || true")

        res = self.chroot.run_in_chroot(["emerge", "--ask=n", "--update", "--deep", "--newuse", "--with-bdeps=y", "--backtrack=30", "--autounmask-write=y", "--autounmask-continue=y", "@world"])
        if res.returncode != 0 and self.chroot.mode == "real":
            logger.warning(f"emerge @world returned warnings: {res.stderr}")

    def setup_custom_overlay(self, custom_ebuilds_dir: Path = None):
        """Inject custom overlay and ebuilds into Portage chroot tree."""
        if self._overlay_setup_done:
            return

        local_repo_dir = self.target_root / "var" / "db" / "repos" / "local_repo"
        repos_conf_dir = self.target_root / "etc" / "portage" / "repos.conf"

        if self.chroot.mode == "mock":
            logger.info("[MOCK PORTAGE] Setting up custom overlay repository")
            self._overlay_setup_done = True
            return

        repos_conf_dir.mkdir(parents=True, exist_ok=True)
        local_repo_dir.mkdir(parents=True, exist_ok=True)
        (local_repo_dir / "profiles").mkdir(parents=True, exist_ok=True)
        (local_repo_dir / "metadata").mkdir(parents=True, exist_ok=True)

        repo_name_file = local_repo_dir / "profiles" / "repo_name"
        repo_name_file.write_text("local_repo\n")

        layout_conf = local_repo_dir / "metadata" / "layout.conf"
        layout_conf.write_text(
            "masters = gentoo\n"
            "thin-manifests = true\n"
        )

        local_repo_conf = repos_conf_dir / "local_repo.conf"
        local_repo_conf.write_text(
            "[local_repo]\n"
            "location = /var/db/repos/local_repo\n"
            "masters = gentoo\n"
            "auto-sync = no\n"
        )

        if custom_ebuilds_dir and Path(custom_ebuilds_dir).exists():
            logger.info(f"Copying custom ebuilds from {custom_ebuilds_dir} -> {local_repo_dir}")
            for item in Path(custom_ebuilds_dir).glob("*"):
                if item.is_dir():
                    shutil.copytree(item, local_repo_dir / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, local_repo_dir / item.name)
            self.chroot.run_in_chroot("ebuild $(find /var/db/repos/local_repo -name '*.ebuild') digest", env={"PORTDIR": "/var/db/repos/gentoo"})
        
        self._overlay_setup_done = True

    def install_packages(self, packages: List[str]):
        if not packages:
            return

        self.setup_custom_overlay()
        self.chroot.run_in_chroot("ldconfig")
        self.chroot.run_in_chroot("env-update")
        self.update_world()

        logger.info(f"Installing packages via emerge: {' '.join(packages)}")
        self.chroot.run_in_chroot("ldconfig")
        self.chroot.run_in_chroot("env-update")
        self.chroot.run_in_chroot(["emerge", "--ask=n", "--oneshot", "--nodeps", "dev-util/pkgconf", "virtual/pkgconfig"])
        self.chroot.run_in_chroot("ldconfig")
        self.chroot.run_in_chroot("env-update")
        self.chroot.run_in_chroot(["emerge", "--ask=n", "--autounmask-write=y", "--autounmask-continue=y", "@preserved-rebuild"])
        cmd = ["emerge", "--ask=n", "--noreplace", "--update", "--deep", "--newuse", "--verbose", "--autounmask-write=y", "--autounmask-continue=y"] + packages
        res = self.chroot.run_in_chroot(cmd)
        if res.returncode != 0 and self.chroot.mode == "real":
            raise PortageManagerError(f"Failed to install packages via emerge:\n{res.stderr}")
