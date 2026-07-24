# Gentoo Modern ISO & System Builder

Modular, dynamic, and fully automated Gentoo Linux LiveCD, Disk Image, and Tarball builder (**Gentoo Modern**). Designed with isolated toolchain bootstrap capabilities and driven by modular JSON configuration profiles.

---

## 🚀 Key Features

* **Multi-Init System Support**: Native support for `OpenRC`, `Systemd`, `Runit`, and `S6` init systems with automatic service initialization and multi-init `/etc/machine-id` compatibility.
* **Multi-Architecture Support**: 20 supported target architectures including `x86_64`, `x86`, `arm64`, `arm`, `riscv64`, `riscv`, `ppc64`, `ppc64le`, `loong`, `s390x`, `sparc64`, and more with architecture-agnostic global build configs.
* **Calamares Installer Integration**: Pre-configured Calamares graphical installer with `Gentoo Modern` branding, offline SquashFS extraction, and automated `grub-install` / `/boot` kernel search logic.
* **Multiple Output Formats**: Supports building bootable LiveCD ISOs (`--format iso`), disk images (`--format img`), and rootfs tarballs for WSL2 / LXC / Docker / Cloud snapshots (`--format tarball`).
* **Flexible CLI Argument Syntax**: Package and service profiles can be passed via comma-separated strings, space-separated lists, or repeated arguments (`--packages filesystems,network-tools` or `--package audio`).
* **Portage Auto-Unmasking & Caching**: Automatic handling of package USE flag dependency resolution via `--autounmask-write=y --autounmask-continue=y` and incremental build caching.
* **Gentoo Modern Visual Design**: Unified dark-mode theme across Desktop (XFCE / GNOME / KDE), GRUB bootloader (`modern`), Plymouth bootsplash (`gentoo-modern`), LightDM, and SDDM greeters.

---

## 📁 Repository Layout

```text
gentoo-builder/
├── cli.py                        # Command line interface launcher
├── configs/
│   ├── architectures/           # Architecture profiles (x86_64, arm64, riscv64...)
│   ├── base_customizations.json # Base copy entries and customizations
│   ├── bootloaders/             # Bootloader profiles (grub-uefi, syslinux...)
│   ├── custom_files/            # Custom files copied into chroot (calamares, plymouth...)
│   ├── desktops/                # Desktop environment profiles (xfce, gnome...)
│   ├── global_build.json        # Global distro build settings and USE flags
│   ├── inits/                   # Init system profiles (openrc, systemd, runit, s6)
│   ├── kernels/                 # Kernel profiles (gentoo-kernel-bin, gentoo-sources...)
│   ├── live-users/              # Live user profiles
│   ├── packages/                # Categorized package profiles (filesystems, audio...)
│   └── services/                # Service profiles
├── core/
│   ├── chroot_manager.py        # Real chroot mount/umount execution
│   ├── config_loader.py         # Profile merger & config assembly
│   ├── customizer.py            # System customization, users, and branding
│   ├── disk_engine.py           # Disk image builder (.img)
│   ├── iso_engine.py            # LiveCD ISO and Tarball builder (.iso, .tar.xz)
│   ├── logger_setup.py          # Structured logging
│   ├── orchestrator.py          # Pipeline build orchestrator
│   ├── portage_manager.py       # Portage/emerge package installation
│   ├── stage3_manager.py        # Automatic Stage3 fetching and extraction
│   └── toolchain_manager.py     # Isolated build_host bootstrap manager
├── docs/                        # Project documentation (Sphinx / Markdown)
├── pytest.ini
├── tests/                       # Unit tests suite
└── workdir/                     # Build tree, chroot, and download cache
```

---

## ⚙️ Quick Start

### 1. List Available Profiles & Options
```bash
python3 cli.py --list-options
```

### 2. Mock Build Simulation (No Root Required)
```bash
python3 cli.py x86_64 --init openrc --desktop xfce --kernel gentoo-kernel-bin --mode mock
```

### 3. Real Build (Requires Root / Sudo)
```bash
sudo python3 cli.py x86_64 --init openrc --desktop xfce --kernel gentoo-kernel-bin --force-isolated-toolchain --mode real
```

### 4. Build RootFS Tarball (For WSL2 / LXC / Cloud Container Base)
```bash
python3 cli.py x86_64 --init openrc --desktop xfce --format tarball --mode mock
```

### 5. Flexible Package Selection Examples
```bash
# Comma-separated package profiles
python3 cli.py x86_64 --packages filesystems,network-tools,system-utils

# Space-separated or repeated flags
python3 cli.py x86_64 --packages filesystems network-tools --package audio -s dbus,NetworkManager
```

### 6. Run Unit Tests
```bash
pytest
```

---

## 🛠️ Supported Architectures & Init Systems

| Category | Options |
| --- | --- |
| **Architectures** | `x86_64`, `x86`, `arm64`, `arm`, `riscv64`, `riscv`, `ppc64`, `ppc64le`, `ppc`, `loong`, `s390x`, `s390`, `sparc64`, `sparc`, `alpha`, `hppa`, `ia64`, `m68k`, `mips`, `sh` |
| **Init Systems** | `openrc`, `systemd`, `runit`, `s6` |
| **Output Formats** | `iso` (Bootable ISO), `img` (Disk Image), `tarball` (`.tar.xz` rootfs tarball) |
| **Kernel Profiles** | `gentoo-kernel-bin`, `gentoo-sources`, `vanilla-kernel-bin` |
