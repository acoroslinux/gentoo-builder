import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.path_utils import resolve_from_project
from core.logger_setup import setup_logger

logger = setup_logger("config_loader")

class ConfigLoaderError(Exception):
    pass

class ConfigLoader:
    def __init__(self, config_root: Optional[Path] = None):
        self.config_root = config_root or resolve_from_project("configs")

    def load_json(self, relative_or_abs_path: str | Path) -> Dict[str, Any]:
        path = Path(relative_or_abs_path)
        if not path.is_absolute():
            candidate = resolve_from_project(path)
            if candidate.exists():
                path = candidate
            else:
                path = self.config_root / path

        if not path.exists():
            raise ConfigLoaderError(f"Configuration file not found: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise ConfigLoaderError(f"Error parsing JSON from {path}: {e}")

    def load_profile(self, category: str, profile_name: str) -> Dict[str, Any]:
        if not profile_name.endswith(".json"):
            profile_name = f"{profile_name}.json"
        path = self.config_root / category / profile_name
        return self.load_json(path)

    def assemble_build_config(
        self,
        global_config_path: str | Path,
        architecture: Optional[str] = "x86_64",
        init_system: Optional[str] = "openrc",
        desktop: Optional[str] = None,
        kernel: Optional[str] = None,
        bootloader: Optional[str] = None,
        package_profiles: Optional[List[str]] = None,
        service_profiles: Optional[List[str]] = None,
        live_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        base_cfg = self.load_json(global_config_path)
        merged = {
            "global": base_cfg.get("global", {}),
            "stage3": base_cfg.get("stage3", {}),
            "make_conf": base_cfg.get("make_conf", {}),
            "use_flags": base_cfg.get("use_flags", []),
            "packages": base_cfg.get("packages", []),
            "services": base_cfg.get("services", []),
            "kernel": {},
            "bootloader": {},
            "live_user": base_cfg.get("live_user", {}),
            "custom_files": base_cfg.get("custom_files", []),
            "init_system": "openrc",
            "default_profile": None
        }

        # Apply Init system profile (openrc, systemd, runit, s6)
        if init_system:
            init_cfg = self.load_profile("inits", init_system)
            merged["init_system"] = init_cfg.get("init_system", init_system)
            if "stage3" in init_cfg:
                merged["stage3"].update(init_cfg["stage3"])
            merged["packages"].extend(init_cfg.get("packages", []))
            merged["use_flags"].extend(init_cfg.get("use_flags", []))

        # Apply Architecture profile
        if architecture:
            try:
                arch_cfg = self.load_profile("architectures", architecture)
                if "stage3" in arch_cfg:
                    merged["stage3"].update(arch_cfg["stage3"])
                if "make_conf" in arch_cfg:
                    merged["make_conf"].update(arch_cfg["make_conf"])
                if "packages" in arch_cfg:
                    merged["packages"].extend(arch_cfg["packages"])
                if "use_flags" in arch_cfg:
                    merged["use_flags"].extend(arch_cfg["use_flags"])
                if "default_profile" in arch_cfg:
                    merged["default_profile"] = arch_cfg["default_profile"]
            except ConfigLoaderError:
                pass

        # Apply base customizations if existing
        base_custom_path = self.config_root / "base_customizations.json"
        if base_custom_path.exists():
            base_custom = self.load_json(base_custom_path)
            merged["make_conf"].update(base_custom.get("make_conf", {}))
            merged["use_flags"].extend(base_custom.get("use_flags", []))
            merged["custom_files"].extend(base_custom.get("base_copy_files", []))

        # Always merge base common package & service profiles
        base_pkg_path = self.config_root / "packages" / "base.json"
        if base_pkg_path.exists():
            base_pkg = self.load_json(base_pkg_path)
            merged["packages"].extend(base_pkg.get("packages", []))
            merged["use_flags"].extend(base_pkg.get("use_flags", []))

        base_srv_path = self.config_root / "services" / "base.json"
        if base_srv_path.exists():
            base_srv = self.load_json(base_srv_path)
            merged["services"].extend(base_srv.get("services", []))

                # Desktop profile
        if desktop:
            d_cfg = self.load_profile("desktops", desktop)
            merged["packages"].extend(d_cfg.get("packages", []))
            merged["services"].extend(d_cfg.get("services", []))
            merged["use_flags"].extend(d_cfg.get("use_flags", []))
            merged["make_conf"].update(d_cfg.get("make_conf", {}))
            # Merge desktop_environment block (customizations_path, use_common_config, copy_files)
            if "desktop_environment" in d_cfg:
                merged["desktop_environment"] = d_cfg["desktop_environment"]

        # Kernel profile
        if kernel:
            k_cfg = self.load_profile("kernels", kernel)
            merged["kernel"] = k_cfg
            merged["packages"].extend(k_cfg.get("packages", []))
            merged["use_flags"].extend(k_cfg.get("use_flags", []))

        # Bootloader profile
        if bootloader:
            b_cfg = self.load_profile("bootloaders", bootloader)
            merged["bootloader"] = b_cfg

        # Package profiles
        for pkg_p in (package_profiles or []):
            p_cfg = self.load_profile("packages", pkg_p)
            merged["packages"].extend(p_cfg.get("packages", []))

        # Service profiles
        for srv_p in (service_profiles or []):
            s_cfg = self.load_profile("services", srv_p)
            merged["services"].extend(s_cfg.get("services", []))

        # Live user profile
        if live_profile:
            l_cfg = self.load_profile("live-users", live_profile)
            merged["live_user"].update(l_cfg)

        # Deduplicate packages and use flags
        merged["packages"] = sorted(list(set(merged["packages"])))
        merged["use_flags"] = sorted(list(set(merged["use_flags"])))
        merged["services"] = sorted(list(set(merged["services"])))

        # Interpolate variables in stage3 URL if present
        if "stage3" in merged and "url" in merged["stage3"]:
            url_str = merged["stage3"]["url"]
            merged["stage3"]["url"] = url_str.format(
                init_system=init_system or "openrc",
                arch=architecture or "x86_64"
            )

        return merged
