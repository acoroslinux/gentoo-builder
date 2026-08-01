# Portage & Gentoo Modern Troubleshooting Guide 🛠️

This guide documents common dependency patterns in Gentoo Linux and explains how **Gentoo Modern / AçorOS** automatically resolves build conflicts to ensure a seamless experience for all users.

---

## 1. Circular Dependencies

### Symptom
Portage outputs a message similar to:
`* Error: circular dependencies: (package-A depends on package-B -> package-C -> package-A)`

### Real World Case Study & Solution
- `net-print/cups` (with `USE="zeroconf"`) ➔ requires `net-dns/avahi`
- `net-dns/avahi` (with `USE="qt6"`) ➔ requires `dev-qt/qtbase[cups]`
- `dev-qt/qtbase` (with `USE="cups"`) ➔ requires `net-print/cups`

### Resolution
Break the unneeded binding on one of the intermediate nodes in `/etc/portage/package.use/00-builder-overrides`:
```ini
# Disable Qt5/Qt6 bindings on Avahi to break the circular loop with CUPS and QtBase
net-dns/avahi dbus gtk gtk3 python -qt5 -qt6
```

---

## 2. Strict USE Flag Constraints (*REQUIRED_USE unsatisfied*)

### Symptom
Portage outputs the following error:
`The following REQUIRED_USE flag constraints are unsatisfied: featureA? ( featureB )`

### Real World Case Study & Solution
In Samba: `ldap? ( ads )` and `ads? ( ldap )`.
If the `ads` flag is set without the `ldap` flag (or vice versa), the Samba ebuild fails dependency resolution.

### Resolution
In `/etc/portage/package.use/00-builder-overrides`, align both flags together:
```ini
# For clean desktop network client/server sharing without Active Directory Domain Controller features:
net-fs/samba client server winbind -ads -ldap
```

---

## 3. Packages Outside Main Tree (*No ebuilds to satisfy*)

### Symptom
Portage outputs the error:
`emerge: there are no ebuilds to satisfy "category/package"`

### Cause & Resolution
Third-party overlay packages (e.g., Linux Mint X-Apps such as `xed` or `pix`) do not exist in the main `gentoo` repository.
Replace them with official packages maintained in the primary tree:
- `app-editors/xed` ➔ `app-editors/gedit` (or `mousepad`)
- `media-gfx/pix` ➔ `media-gfx/eog` (or `viewnior`)

---

## 4. Automatic Memory Management (*Low Memory Limits*)

To prevent RAM exhaustion during heavy C++/Rust compilation (`nodejs`, `rust`, `webkit-gtk`, `gcc`), the build system dynamically assigns thread constraints in `/etc/portage/package.env/00-builder-ram-limits`:
```ini
net-libs/nodejs low-ram-node.conf
dev-lang/rust low-ram.conf
net-libs/webkit-gtk low-ram.conf
sys-devel/gcc low-ram.conf
```
