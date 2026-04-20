"""Tests for the Progress dataclass and bar renderer."""

from __future__ import annotations

from app.services.progress import (
    Progress,
    STAGE_RANGES,
    render_progress,
    stage_percent,
)


def test_progress_clamp_high():
    assert Progress(150, "Foo").clamp().percent == 100


def test_progress_clamp_low():
    assert Progress(-10, "Foo").clamp().percent == 0


def test_stage_percent_bounds():
    # Start of each stage
    for stage, (start, _end) in STAGE_RANGES.items():
        assert stage_percent(stage, 0.0) == start

    # End of each stage
    for stage, (_start, end) in STAGE_RANGES.items():
        assert stage_percent(stage, 1.0) == end


def test_stage_percent_midpoint():
    # Enriching: 25 .. 90, midpoint ~= 57
    assert 55 <= stage_percent("Enriching", 0.5) <= 60


def test_render_progress_contains_percent():
    out = render_progress(Progress(42, "Enriching"))
    assert "42%" in out
    assert "Enriching" in out


def test_render_progress_with_detail():
    out = render_progress(Progress(50, "Enriching", "12 / 24 websites"))
    assert "12 / 24 websites" in out


def test_render_progress_bar_length():
    # Width 20 at 50% => 10 filled + 10 empty blocks.
    out = render_progress(Progress(50, "X"), width=20)
    first_line = out.splitlines()[0]
    # Count the filled + empty blocks between [ and ]
    inside = first_line[first_line.index("[") + 1 : first_line.index("]")]
    assert len(inside) == 20


def test_render_progress_zero_and_full():
    assert "0%" in render_progress(Progress(0, "Starting"))
    assert "100%" in render_progress(Progress(100, "Done"))


def test_render_progress_clamps_negative():
    # Even with negative input, bar must render sanely.
    out = render_progress(Progress(-5, "Foo"))
    assert "0%" in out
