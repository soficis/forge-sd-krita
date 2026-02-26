from forge.domain.progress_state import parse_progress_state


def test_parse_progress_state_for_active_job():
    state = parse_progress_state(
        {
            "progress": 0.42,
            "state": {"skipped": False, "interrupted": False},
            "current_image": "BASE64",
        }
    )

    assert state.is_active is True
    assert state.is_interrupted is False
    assert state.percent == 42
    assert state.current_image == "BASE64"


def test_parse_progress_state_for_interrupted_job():
    state = parse_progress_state(
        {
            "progress": 0.75,
            "state": {"skipped": False, "interrupted": True},
            "current_image": "BASE64",
        }
    )

    assert state.is_active is False
    assert state.is_interrupted is True


def test_parse_progress_state_handles_empty_payload():
    state = parse_progress_state(None)

    assert state.is_active is False
    assert state.percent == 0
    assert state.current_image is None
