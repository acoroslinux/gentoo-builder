# Architecture & Design

This page details the internal structure and design of Gentoo-Builder.

## Directory Structure

```
gentoo-builder/
├── cli.py                    # Main Entrypoint script
├── core/
│   ├── config_loader.py      # Combines, merges, and validates JSON configurations
│   ├── stage3_manager.py     # Dynamically resolves and downloads Gentoo Stage3
│   ├── chroot_setup.py       # Handles resolv.conf and make.profile setups
│   ├── chroot_manager.py     # Mounts/unmounts proc, sys, dev and bind-caches
│   ├── portage_manager.py    # Manages make.conf, overlays, and installs packages
│   ├── customizer.py         # Configures livecd settings and users
│   ├── iso_engine.py         # Builds final bootable SquashFS ISO
│   ├── disk_engine.py        # Generates raw partitioned disk images
│   ├── toolchain_manager.py  # Manages the isolated toolchain environment
│   └── logger_setup.py       # System logging setup
├── configs/
│   ├── architectures/        # Architecture profiles (CFLAGS, make.profile targets)
│   ├── inits/                # Init system profiles (openrc, systemd, etc.)
│   ├── desktops/             # Desktop environment profiles (GNOME, XFCE, etc.)
│   ├── kernels/              # Kernel configs
│   ├── bootloaders/          # Bootloader configs (GRUB, Systemd-boot, Syslinux)
│   ├── packages/             # On-demand software package lists
│   └── services/             # On-demand service profiles
└── tests/                    # Pytest test suite
```

## Compilation Pipeline Flow

The orchestrator executes the build pipeline using the following sequential steps:

```mermaid
graph TD
    A[Start cli.py] --> B[Load Config Loader]
    B --> C[Toolchain Check / Bootstrap]
    C --> D[Fetch & Extract Stage3]
    D --> E[Prepare Chroot Setup]
    E --> F[Mount Virtual FS]
    F --> G[Portage Package Installation]
    G --> H{Check Target}
    H -->|livecd-stage1| I[Archive Rootfs .tar.xz]
    H -->|livecd-stage2| J[Customize + Build ISO]
    H -->|diskimage-stage2| K[Customize + Build Disk Image .img]
    H -->|netboot| L[Archive boot/ .tar.gz]
    I --> M[End / Output Success]
    J --> M
    K --> M
    L --> M
```
