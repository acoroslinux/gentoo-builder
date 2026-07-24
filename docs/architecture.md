# Architecture & System Design

This page details the internal structure and design principles of **Gentoo Modern ISO & System Builder**.

---

## 🏗️ Directory Structure

```text
gentoo-builder/
├── cli.py                    # CLI entrypoint with flexible argument parser
├── core/
│   ├── config_loader.py      # Combines, merges, and validates JSON configurations
│   ├── stage3_manager.py     # Dynamically resolves and downloads Gentoo Stage3
│   ├── chroot_setup.py       # Handles resolv.conf and make.profile setups
│   ├── chroot_manager.py     # Mounts/unmounts proc, sys, dev and bind-caches
│   ├── portage_manager.py    # Manages make.conf, overlays, USE flags, and emerge
│   ├── customizer.py         # Configures livecd settings, users, os-release, branding
│   ├── iso_engine.py         # Builds final bootable SquashFS ISO or RootFS Tarball
│   ├── disk_engine.py        # Generates raw partitioned disk images
│   ├── toolchain_manager.py  # Manages the isolated toolchain environment
│   └── logger_setup.py       # System logging setup
├── configs/
│   ├── architectures/        # Architecture profiles (x86_64, arm64, riscv64...)
│   ├── base_customizations.json # Base copy entries (Plymouth, GRUB, os-release...)
│   ├── bootloaders/          # Bootloader configs (grub-uefi, syslinux...)
│   ├── custom_files/         # Custom artwork, Calamares, Plymouth, DM configs
│   ├── desktops/             # Desktop environment profiles (XFCE, GNOME, KDE...)
│   ├── inits/                # Init system profiles (openrc, systemd, runit, s6)
│   ├── kernels/              # Kernel configs (gentoo-kernel-bin, gentoo-sources...)
│   ├── packages/             # Categorized software package lists
│   └── services/             # Service activation profiles
└── tests/                    # Pytest test suite
```

---

## 🔄 Compilation Pipeline Flow

The orchestrator executes the build pipeline using the following sequential steps:

```mermaid
graph TD
    A["Start cli.py"] --> B["Load & Merge Profiles (ConfigLoader)"]
    B --> C["Toolchain Check / Bootstrap (ToolchainManager)"]
    C --> D["Fetch & Extract Stage3 (Stage3Manager)"]
    D --> E["Prepare Chroot Setup & Bind Caches"]
    E --> F["Mount Virtual Filesystems (/proc, /sys, /dev)"]
    F --> G["Portage Auto-Unmasking & Emerge (@world & packages)"]
    G --> H["Apply Customizer (Users, Hostname, os-release, Services)"]
    H --> I{"Select Output Format / Target"}
    I -->|ISO| J["Build SquashFS + GRUB/Syslinux ISO"]
    I -->|Disk Image| K["Partition & Write Raw .img"]
    I -->|Tarball| L["Compress RootFS into .tar.xz"]
    J --> M["Generate MD5 / SHA256 Checksums & Finish"]
    K --> M
    L --> M
```

---

## 🔑 Key Architectural Principles

1. **Multi-Init Compatibility**:
   To ensure full compatibility across OpenRC, Systemd, Runit, and S6, `/etc/machine-id` is created as a real text file in the chroot, while `/var/lib/dbus/machine-id` is set as a symlink pointing to `/etc/machine-id`.
2. **Architecture-Agnostic Build Defaults**:
   Global build options in `global_build.json` specify generic options like `COMMON_FLAGS="-O2 -pipe"`, while architecture profiles in `configs/architectures/*.json` supply target `CFLAGS` (`-march=x86-64`, `-march=armv8-a`, `-march=rv64gc`) and `ACCEPT_KEYWORDS`.
3. **Calamares Offline Installation**:
   Calamares extracts the pre-built, customized SquashFS image (`/live/filesystem.squashfs`) directly to the destination drive during installation, avoiding online Stage3 downloads and accelerating installation times.
4. **Portage Auto-Unmasking & Caching**:
   `emerge` commands pass `--autounmask-write=y --autounmask-continue=y` to handle ebuild USE flag dependencies automatically. Package tarballs are saved in `workdir/<arch>/cache` to make subsequent builds fast and incremental.
