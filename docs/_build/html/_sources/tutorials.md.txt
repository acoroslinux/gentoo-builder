# Tutorials & Practical Examples

This page provides practical, step-by-step guides for common Gentoo-Builder tasks.

## Tutorial 1: Creating a Custom XFCE ISO for x86_64

In this tutorial, we will construct a bootable XFCE LiveCD containing office applications and web browsers.

### Step 1: Check available options
First, list the profiles to make sure `xfce` and package profiles like `browsers` and `office` are available:
```bash
python3 cli.py --list-options
```

### Step 2: Test the build configuration in simulation (mock) mode
Always test your build command in simulation mode to ensure configuration loading works perfectly without errors:
```bash
python3 cli.py x86_64 --mode mock --desktop xfce --kernel gentoo-kernel-bin --packages browsers,office
```

### Step 3: Run the real build
Run the pipeline with administrator privileges. Ensure you have the required host tools (`mksquashfs`, `xorriso`, `grub-mkrescue`) installed.
```bash
sudo python3 cli.py x86_64 --mode real --desktop xfce --kernel gentoo-kernel-bin --packages browsers,office
```

The output ISO will be generated in your `workdir/x86_64/` directory with a name like `gentoo-builder-openrc-xfce-x86_64.iso` along with its MD5 and SHA256 checksums.

---

## Tutorial 2: Creating a Minimal Embedded RootFS for ARM64 (Pine64/Raspberry Pi)

In this tutorial, we will build a minimal embedded rootfs tarball for an ARM64 system running OpenRC.

### Step 1: Run the simulation
```bash
python3 cli.py arm64 --target embedded --mode mock --init openrc
```

### Step 2: Run the real rootfs compilation
```bash
sudo python3 cli.py arm64 --target embedded --mode real --init openrc
```

The output will be a compressed tarball file located at:
`workdir/arm64/gentoo-builder-openrc-base-arm64.tar.xz`

This archive can be extracted directly onto the root partition of an SD card or eMMC storage device.

---

## Tutorial 3: Adding a New Package Profile (On-Demand Software)

To add a new software group that users can select using the `--packages` argument:

1. Create a new JSON file inside `configs/packages/`, for example: `configs/packages/devops-tools.json`.
2. Populate the file with package names and USE flags:
   ```json
   {
     "name": "devops-tools",
     "description": "Container and automation tools",
     "packages": [
       "app-containers/docker-compose",
       "app-admin/ansible",
       "net-misc/rsync"
     ],
     "use_flags": [
       "rsync"
     ]
   }
   ```
3. Run the generator using your new profile:
   ```bash
   python3 cli.py x86_64 --packages devops-tools
   ```
