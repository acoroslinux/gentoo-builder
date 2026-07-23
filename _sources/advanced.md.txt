# Advanced Customization & Troubleshooting

This page details advanced usage, customization techniques, and troubleshooting steps for Gentoo-Builder.

---

## 1. Custom Portage Overlays & Local Ebuilds

Gentoo-Builder has native support for inject-compiling custom, third-party, or local ebuilds during the Portage package installation step.

### How it works
During the build, `PortageManager` sets up a local repository named `local_repo` inside the chroot under `/var/db/repos/local_repo` and registers it in `/etc/portage/repos.conf/local_repo.conf`.

### Steps to include custom ebuilds
If you have a local directory containing your custom ebuilds (structured like a standard Portage overlay, e.g., `category/package/package-version.ebuild`), you can inject them:
1. Put your custom overlay directory structure in a local path, e.g., `./my_custom_overlay/`.
2. Ensure you have the corresponding package defined in your config JSON file (e.g. under `packages/my-custom-package`).
3. During runtime, `PortageManager` automatically merges files from the specified `custom_ebuilds_dir` and runs `ebuild digest` inside the chroot to generate Manifest files before calling `emerge`.

---

## 2. Portage Cache Persistence & Performance Otimization

Portage compilation is highly resource-intensive. To prevent downloading source tarballs multiple times and to reuse compiled binary packages across clean builds, Gentoo-Builder implements **Portage Cache Binding**.

### Active Caches
* **Distfiles Cache**: Bind-mounted from the host directory `workdir/<arch>/cache/distfiles` to `/var/cache/distfiles` inside the chroot. This preserves downloaded source tarballs.
* **Binpkgs Cache**: Bind-mounted from the host directory `workdir/<arch>/cache/binpkgs` to `/var/cache/binpkgs` inside the chroot. This caches compiled packages, allowing subsequent builds to install them instantly via `getbinpkg` features without compiling them again.

### Hardware Optimization
The builder dynamically detects the CPU core count on the host:
* Sets `MAKEOPTS="-jN"` where `N` is the number of CPU cores.
* Sets `--jobs` and `--load-average` inside `EMERGE_DEFAULT_OPTS` to prevent overloading the host system while maximizing parallel compilation.

---

## 3. Customizing the Kernel Configuration

If you do not want to use the default binary kernel (`sys-kernel/gentoo-kernel-bin`), you can build a custom kernel:
1. Edit the kernel configuration profile in `configs/kernels/`.
2. Point it to a custom package name or provide kernel sources like `sys-kernel/gentoo-sources`.
3. Provide custom kernel config files by copying them via `custom_files` list or placing them inside target chroot paths like `/usr/src/linux/.config` during customizer execution.

---

## 4. Troubleshooting & Recovery

### Issue 1: Emerge or Package Compilation Fails
If `emerge` fails during the real mode execution, virtual filesystems may remain mounted.
* **Solution**: Before attempting to modify files manually or delete the directory, run the cleanup script or manually unmount virtual filesystems:
  ```bash
  sudo umount -l workdir/x86_64/chroot/dev/pts
  sudo umount -l workdir/x86_64/chroot/dev/shm
  sudo umount -l workdir/x86_64/chroot/dev
  sudo umount -l workdir/x86_64/chroot/proc
  sudo umount -l workdir/x86_64/chroot/sys
  sudo umount -l workdir/x86_64/chroot/var/cache/distfiles
  sudo umount -l workdir/x86_64/chroot/var/cache/binpkgs
  ```

### Issue 2: Clean builds do not clean the download cache
Using the `--clean` argument removes compile chroots (`workdir/<arch>/chroot/` and `workdir/<arch>/iso_root/`) to ensure a fresh, unpolluted environment. However, it **preserves** the cache folder (`workdir/<arch>/cache/`) to avoid redownloading the large Stage3 tarball or Portage distfiles.
* **How to force full clean**: If you want to delete everything (including downloads and cache) to start completely from scratch, delete the workdir manually:
  ```bash
  sudo rm -rf workdir/x86_64/
  ```
