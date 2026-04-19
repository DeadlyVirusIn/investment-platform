"""Worker package smoke test."""


def test_import_registry() -> None:
    from apps.worker.src.jobs import registry
    assert hasattr(registry, "__dict__")


def test_import_tick_loop() -> None:
    from apps.worker.src.scheduler import tick_loop
    assert hasattr(tick_loop, "__dict__")
