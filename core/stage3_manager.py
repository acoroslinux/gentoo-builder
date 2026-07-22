import urllib.request
import tarfile
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any
from core.logger_setup import setup_logger

logger = setup_logger("stage3_manager")

class Stage3ManagerError(Exception):
    pass

class Stage3Manager:
    def __init__(self, workdir: Path, stage3_config: Dict[str, Any], mode: str = "mock"):
        self.workdir = Path(workdir).resolve()
        self.config = stage3_config
        self.mode = mode.lower()
        self.cache_dir = self.workdir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_and_extract(self, target_root: Path):
        url = self.config.get("url", "https://distfiles.gentoo.org/releases/amd64/autobuilds/current-stage3-amd64-openrc/stage3-amd64-openrc-latest.tar.xz")
        filename = url.split("/")[-1]
        tarball_path = self.cache_dir / filename

        if self.mode == "mock":
            logger.info(f"[MOCK STAGE3] Fetching stage3 from {url}")
            logger.info(f"[MOCK STAGE3] Extracting to {target_root}")
            target_root.mkdir(parents=True, exist_ok=True)
            (target_root / "etc").mkdir(parents=True, exist_ok=True)
            (target_root / "bin").mkdir(parents=True, exist_ok=True)
            return

        if not tarball_path.exists():
            logger.info(f"Downloading Gentoo Stage3 from {url}...")
            try:
                urllib.request.urlretrieve(url, tarball_path)
            except Exception as e:
                raise Stage3ManagerError(f"Failed to download Stage3: {e}")

        logger.info(f"Extracting Gentoo Stage3 into {target_root}...")
        target_root.mkdir(parents=True, exist_ok=True)
        res = subprocess.run(["tar", "xpf", str(tarball_path), "-C", str(target_root), "--numeric-owner"], capture_output=True, text=True)
        if res.returncode != 0:
            raise Stage3ManagerError(f"Failed to extract Stage3 tarball: {res.stderr}")

        logger.info("Stage3 extracted successfully.")
