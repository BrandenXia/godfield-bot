"""Compatibility entry point for the versioned all-Earth generated-action probe."""

from pathlib import Path

from godfield_bot.full_game_generated_smoke import (
    FullGameGeneratedSmokeReport as FullGameEarthSmokeReport,
)
from godfield_bot.full_game_generated_smoke import run_full_game_generated_smoke


def run_full_game_earth_smoke(
    *,
    catalog_path: Path,
    bible_path: Path,
    batch_size: int = 4096,
    player_count: int = 3,
    seed: int = 67,
) -> FullGameEarthSmokeReport:
    return run_full_game_generated_smoke(
        catalog_path=catalog_path,
        bible_path=bible_path,
        batch_size=batch_size,
        player_count=player_count,
        seed=seed,
        guardian_kind="earth",
    )
