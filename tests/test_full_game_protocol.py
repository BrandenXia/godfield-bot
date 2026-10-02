"""New-engine command contracts do not change or execute existing gameplay."""

import pytest
from pydantic import ValidationError

from godfield_bot.full_game_protocol import (
    FullGameCommand,
    FullGameCommandError,
    FullGameDecisionContext,
    validate_full_game_commands,
)


def context(**changes):
    return FullGameDecisionContext.model_validate(
        {
            "environment": 0,
            "episode": 1,
            "decision": 1,
            "actor": 0,
            "phase": "ready",
            "legal_choice_ids": (0, 4, 512),
            **changes,
        }
    )


def command(**changes):
    return FullGameCommand.model_validate(
        {
            "environment": 0,
            "episode": 1,
            "decision": 1,
            "actor": 0,
            "phase": "ready",
            "choice_id": 4,
            **changes,
        }
    )


def test_matching_commands_return_in_order_without_mutating_contexts():
    contexts = {0: context(), 1: context(environment=1, actor=8, decision=7)}
    before = {env: row.model_dump() for env, row in contexts.items()}
    commands = [command(environment=1, actor=8, decision=7), command(choice_id=0)]
    assert validate_full_game_commands(commands, contexts) == tuple(commands)
    assert {env: row.model_dump() for env, row in contexts.items()} == before
    assert validate_full_game_commands([], {}) == ()


@pytest.mark.parametrize(
    "changes",
    [
        {"episode": 2},
        {"decision": 2},
        {"actor": 1},
        {"phase": "defense-selection"},
        {"choice_id": 3},
        {"environment": 1},
    ],
)
def test_stale_wrong_actor_phase_or_unknown_choice_fail_admission(changes):
    with pytest.raises(FullGameCommandError):
        validate_full_game_commands([command(**changes)], {0: context()})


def test_reset_epoch_invalidates_identical_ids_and_first_decision_after_reset():
    old = command()
    reset_context = context(episode=2)
    with pytest.raises(FullGameCommandError, match="stale"):
        validate_full_game_commands([old], {0: reset_context})
    assert validate_full_game_commands([command(episode=2)], {0: reset_context})


def test_next_decision_invalidates_an_unchanged_reusable_card_choice():
    old = command()
    advanced = context(decision=2)
    with pytest.raises(FullGameCommandError, match="stale"):
        validate_full_game_commands([old], {0: advanced})
    assert validate_full_game_commands([command(decision=2)], {0: advanced})


def test_late_invalid_row_and_duplicate_environments_fail_without_context_changes():
    contexts = {0: context(), 1: context(environment=1)}
    before = {env: row.model_dump() for env, row in contexts.items()}
    with pytest.raises(FullGameCommandError, match="stale"):
        validate_full_game_commands([command(), command(environment=1, decision=2)], contexts)
    with pytest.raises(FullGameCommandError, match="duplicate"):
        validate_full_game_commands([command(), command()], contexts)
    assert {env: row.model_dump() for env, row in contexts.items()} == before


@pytest.mark.parametrize("phase", ["setup", "automatic", "terminal", "truncated"])
def test_noninteractive_phases_have_no_choices_and_reject_policy_commands(phase):
    current = context(phase=phase, legal_choice_ids=())
    with pytest.raises(FullGameCommandError, match="illegal"):
        validate_full_game_commands([command(phase=phase)], {0: current})
    with pytest.raises(ValidationError):
        context(phase=phase)


@pytest.mark.parametrize(
    "changes",
    [
        {"episode": 0},
        {"episode": True},
        {"decision": 2**53},
        {"actor": 9},
        {"environment": -1},
        {"environment": 1_000_000},
        {"choice_id": -1},
        {"phase": "unknown"},
        {"choice_id": "4"},
        {"schema_version": 2},
        {"schema_version": True},
        {"schema_version": 1.0},
        {"actual_model_id": 1},
    ],
)
def test_command_fields_are_strict_bounded_and_do_not_accept_hidden_state(changes):
    with pytest.raises(ValidationError):
        command(**changes)


@pytest.mark.parametrize("choices", [(), (1, 1), tuple(range(16_385))])
def test_interactive_choice_tables_are_nonempty_unique_and_bounded(choices):
    with pytest.raises(ValidationError):
        context(legal_choice_ids=choices)


def test_context_key_mismatch_and_unchecked_model_copies_fail_closed():
    with pytest.raises(FullGameCommandError, match="mismatched"):
        validate_full_game_commands([command()], {0: context(environment=1)})
    with pytest.raises(ValidationError):
        validate_full_game_commands([command().model_copy(update={"actor": 99})], {0: context()})
    with pytest.raises(ValidationError):
        validate_full_game_commands(
            [command()], {0: context().model_copy(update={"legal_choice_ids": (4, 4)})}
        )


def test_serialization_is_deterministic_and_public_commands_do_not_execute_gameplay():
    current, selected = context(), command()
    assert FullGameDecisionContext.model_validate_json(current.model_dump_json()) == current
    assert FullGameCommand.model_validate_json(selected.model_dump_json()) == selected
    assert set(selected.model_dump()) == {
        "schema_version",
        "environment",
        "episode",
        "decision",
        "actor",
        "phase",
        "choice_id",
    }
    # Revalidating is allowed: admission alone is NOT exactly-once execution.
    assert validate_full_game_commands([selected], {0: current})
    assert validate_full_game_commands([selected], {0: current})


def test_maximum_safe_counters_and_choice_handles_are_preserved_exactly():
    selected = command(
        environment=999_999, episode=2**53 - 1, decision=2**53 - 1, actor=8, choice_id=2**53 - 1
    )
    current = context(
        environment=999_999,
        episode=2**53 - 1,
        decision=2**53 - 1,
        actor=8,
        legal_choice_ids=(2**53 - 1,),
    )
    assert validate_full_game_commands([selected], {999_999: current}) == (selected,)
    assert FullGameCommand.model_validate_json(selected.model_dump_json()) == selected


def test_batch_bound_precedes_iteration_or_context_access():
    class TooManyCommands:
        def __len__(self):
            return 1_000_001

        def __iter__(self):
            raise AssertionError("must not iterate oversized commands")

    with pytest.raises(FullGameCommandError, match="row bound"):
        validate_full_game_commands(TooManyCommands(), {})
