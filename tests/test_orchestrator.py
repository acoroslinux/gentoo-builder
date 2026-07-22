from core.orchestrator import BuildOrchestrator

def test_mock_build_run():
    orchestration = BuildOrchestrator(
        arch="x86_64",
        mode="mock",
        clean=True,
        desktop="xfce",
        kernel="gentoo-kernel-bin",
        output_name="test-gentoo-xfce.iso"
    )
    iso_path = orchestration.build()
    assert iso_path.exists()
    assert (iso_path.parent / f"{iso_path.name}.md5").exists()
    assert (iso_path.parent / f"{iso_path.name}.sha256").exists()
