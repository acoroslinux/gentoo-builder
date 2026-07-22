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
