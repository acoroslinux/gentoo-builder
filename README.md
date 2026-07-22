# Gentoo-Builder

Modular and dynamic Gentoo Linux ISO & image builder. Designed with complete host isolation and fully driven by JSON configuration profiles.

## Layout

```text
gentoo-builder/
├── cli.py
├── configs/
│   ├── architectures/
│   ├── bootloaders/
│   ├── desktops/
│   ├── kernels/
│   ├── live-users/
│   ├── packages/
│   └── services/
├── core/
│   ├── chroot_manager.py
│   ├── config_loader.py
│   ├── iso_engine.py
│   ├── logger_setup.py
│   ├── orchestrator.py
│   ├── path_utils.py
│   ├── portage_manager.py
│   └── stage3_manager.py
├── pytest.ini
├── tests/
└── workdir/
```

## Quick Start

### List available profiles
```bash
python3 cli.py --list-options
```

### Mock build simulation
```bash
python3 cli.py x86_64 --desktop xfce --kernel gentoo-kernel-bin --bootloader grub-uefi --mode mock
```

### Real build (Requires root)
```bash
sudo python3 cli.py x86_64 --desktop xfce --kernel gentoo-kernel-bin --bootloader grub-uefi --mode real
```

### Run tests
```bash
pytest
```
