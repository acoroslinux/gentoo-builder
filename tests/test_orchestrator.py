import tempfile
from pathlib import Path
from core.orchestrator import BuildOrchestrator

def test_mock_build_run():
    with tempfile.TemporaryDirectory() as tmpdir:
        orchestration = BuildOrchestrator(
            arch="x86_64",
            mode="mock",
            clean=True,
            desktop="xfce",
            kernel="gentoo-kernel-bin",
            output_name="test-gentoo-xfce.iso"
        )
        # Override workdir to temporary directory to prevent permission conflicts with real root builds
        orchestration.workdir = Path(tmpdir) / "workdir"
        orchestration.target_root = orchestration.workdir / "chroot"
        
        iso_path = orchestration.build()
        assert iso_path.exists()
        assert (iso_path.parent / f"{iso_path.name}.md5").exists()
        assert (iso_path.parent / f"{iso_path.name}.sha256").exists()

def test_mock_build_stage1():
    with tempfile.TemporaryDirectory() as tmpdir:
        orchestration = BuildOrchestrator(
            arch="x86_64",
            mode="mock",
            clean=True,
            target="livecd-stage1"
        )
        orchestration.workdir = Path(tmpdir) / "workdir"
        orchestration.target_root = orchestration.workdir / "chroot"
        
        tar_path = orchestration.build()
        assert tar_path.name.endswith(".tar.xz")
        assert tar_path.exists()
        assert (tar_path.parent / f"{tar_path.name}.md5").exists()
        assert (tar_path.parent / f"{tar_path.name}.sha256").exists()

def test_mock_build_diskimage_stage2():
    with tempfile.TemporaryDirectory() as tmpdir:
        orchestration = BuildOrchestrator(
            arch="x86_64",
            mode="mock",
            clean=True,
            target="diskimage-stage2"
        )
        orchestration.workdir = Path(tmpdir) / "workdir"
        orchestration.target_root = orchestration.workdir / "chroot"
        
        img_path = orchestration.build()
        assert img_path.name.endswith(".img")
        assert img_path.exists()
        assert (img_path.parent / f"{img_path.name}.md5").exists()
        assert (img_path.parent / f"{img_path.name}.sha256").exists()

def test_mock_build_netboot():
    with tempfile.TemporaryDirectory() as tmpdir:
        orchestration = BuildOrchestrator(
            arch="x86_64",
            mode="mock",
            clean=True,
            target="netboot"
        )
        orchestration.workdir = Path(tmpdir) / "workdir"
        orchestration.target_root = orchestration.workdir / "chroot"
        
        gz_path = orchestration.build()
        assert gz_path.name.endswith(".tar.gz")
        assert gz_path.exists()
        assert (gz_path.parent / f"{gz_path.name}.md5").exists()
        assert (gz_path.parent / f"{gz_path.name}.sha256").exists()
