from opencode_loop.orchestrator import clamp_effective_checks


def test_clamp_effective_checks_defaults_to_five():
    effective = clamp_effective_checks(
        ["r1", "r2", "r3"],
        ["c1", "c2", "c3", "c4"],
        recovered=False,
        max_effective_checks=5,
    )

    assert effective == ["r1", "r2", "r3", "c1", "c2"]


def test_clamp_effective_checks_resets_to_base_checks_after_recovery():
    effective = clamp_effective_checks(
        ["r1", "r2"],
        ["c1", "c2", "c3"],
        recovered=True,
        max_effective_checks=5,
    )

    assert effective == ["c1", "c2", "c3"]
