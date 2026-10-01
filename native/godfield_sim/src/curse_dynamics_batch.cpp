#include "curse_dynamics_batch.h"
#include "curse_rules.h"

#include <algorithm>
#include <memory>
#include <set>
#include <stdexcept>

namespace godfield_sim {
namespace {
constexpr std::size_t kMaximumPlayers = 9;
constexpr std::size_t kMaximumTotalPlayers = 2000000;
constexpr std::int64_t kMaximumTicks = 1000000000;

template <std::size_t Width>
CurseStateSnapshot
copy_snapshot(const std::vector<std::array<std::int64_t, Width>> &states,
              std::size_t batch_size, std::size_t player_count) {
  auto buffer = std::make_unique<std::int64_t[]>(states.size() * Width);
  for (std::size_t index = 0; index < states.size(); ++index) {
    std::copy(states[index].begin(), states[index].end(),
              buffer.get() + index * Width);
  }
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return CurseStateSnapshot(data, {batch_size, player_count, Width}, owner);
}
} // namespace

CurseDynamicsBatch::CurseDynamicsBatch(std::size_t batch_size,
                                       std::size_t player_count,
                                       std::uint16_t initial_hp)
    : batch_size_(batch_size), player_count_(player_count),
      initial_hp_(initial_hp) {
  if (batch_size == 0 || player_count < 2 || player_count > kMaximumPlayers ||
      batch_size > kMaximumTotalPlayers / player_count || initial_hp == 0 ||
      initial_hp > 100) {
    throw std::invalid_argument(
        "curse dynamics dimensions or initial HP are invalid");
  }
  states_.resize(batch_size * player_count, State{initial_hp, 0, 0, 0});
  transitions_.resize(batch_size * player_count, Transition{});
}

void CurseDynamicsBatch::same_length(std::size_t expected, ActionInput input) {
  if (input.shape(0) != expected) {
    throw std::invalid_argument("curse dynamics input lengths differ");
  }
}

std::vector<std::size_t>
CurseDynamicsBatch::checked_players(ActionInput environments,
                                    ActionInput players, bool living_only,
                                    bool require_unique) const {
  same_length(environments.shape(0), players);
  std::vector<std::size_t> indices;
  indices.reserve(environments.shape(0));
  std::set<std::size_t> unique;
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    const auto environment = environments(row);
    const auto player = players(row);
    if (environment < 0 ||
        static_cast<std::uint64_t>(environment) >= batch_size_ || player < 0 ||
        static_cast<std::uint64_t>(player) >= player_count_) {
      throw std::invalid_argument(
          "curse dynamics environment or player is out of range");
    }
    const auto index = static_cast<std::size_t>(environment) * player_count_ +
                       static_cast<std::size_t>(player);
    if ((require_unique && !unique.insert(index).second) ||
        (living_only && states_[index][0] == 0)) {
      throw std::invalid_argument("curse dynamics player is duplicate or dead");
    }
    indices.push_back(index);
  }
  return indices;
}

void CurseDynamicsBatch::record(std::size_t index, std::int64_t operation,
                                const State &before) noexcept {
  const auto &after = states_[index];
  const auto newly_died = before[0] > 0 && after[0] == 0;
  transitions_[index] = {
      operation,         before[0], before[1], before[2], after[0] - before[0],
      newly_died ? 1 : 0};
  // Loading external combat results is not an illness-caused death.
  if (newly_died && operation != 1) {
    ++death_count_;
  }
}

void CurseDynamicsBatch::load_players(ActionInput environments,
                                      ActionInput players, ActionInput hp,
                                      ActionInput illness,
                                      ActionInput curse_masks) {
  const auto indices = checked_players(environments, players, false);
  same_length(indices.size(), hp);
  same_length(indices.size(), illness);
  same_length(indices.size(), curse_masks);
  for (std::size_t row = 0; row < indices.size(); ++row) {
    if (hp(row) < 0 || hp(row) > 100 || illness(row) < 0 || illness(row) > 4 ||
        curse_masks(row) < 0 || curse_masks(row) > kCurseMask) {
      throw std::invalid_argument(
          "loaded curse dynamics state is out of range");
    }
  }
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto index = indices[row];
    const auto before = states_[index];
    // External resource synchronization must not make stale ticks valid again.
    states_[index] = {hp(row), illness(row), curse_masks(row), before[3]};
    record(index, 1, before);
  }
}

void CurseDynamicsBatch::apply_illnesses(ActionInput environments,
                                         ActionInput players,
                                         ActionInput stages) {
  const auto indices = checked_players(environments, players, true);
  same_length(indices.size(), stages);
  for (std::size_t row = 0; row < indices.size(); ++row) {
    if (stages(row) < 1 || stages(row) > 4) {
      throw std::invalid_argument("incoming illness stage is out of range");
    }
  }
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto index = indices[row];
    auto &state = states_[index];
    const auto before = state;
    const auto result = inflict_illness({static_cast<std::uint16_t>(state[0]),
                                         static_cast<std::uint8_t>(state[1])},
                                        static_cast<std::uint8_t>(stages(row)));
    state[0] = result.hp;
    state[1] = result.stage;
    record(index, 2, before);
  }
  illness_count_ += indices.size();
}

void CurseDynamicsBatch::apply_curses(ActionInput environments,
                                      ActionInput players,
                                      ActionInput curse_bits) {
  const auto indices = checked_players(environments, players, true);
  same_length(indices.size(), curse_bits);
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto bit = curse_bits(row);
    if (bit != kCurseFogBit && bit != kCurseDreamBit && bit != kCurseFlashBit &&
        bit != kCurseDarkCloudBit) {
      throw std::invalid_argument("incoming non-disease curse bit is invalid");
    }
  }
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto index = indices[row];
    const auto before = states_[index];
    states_[index][2] |= curse_bits(row);
    record(index, 3, before);
  }
  curse_count_ += indices.size();
}

void CurseDynamicsBatch::cure_players(ActionInput environments,
                                      ActionInput players, ActionInput scopes) {
  const auto indices = checked_players(environments, players, true);
  same_length(indices.size(), scopes);
  for (std::size_t row = 0; row < indices.size(); ++row) {
    if (scopes(row) != 1 && scopes(row) != 2) {
      throw std::invalid_argument("curse cure scope must be mild=1 or all=2");
    }
    const auto &state = states_[indices[row]];
    const auto stage = static_cast<std::uint8_t>(state[1]);
    const auto mask = static_cast<std::uint8_t>(state[2]);
    const auto all = scopes(row) == 2;
    if (cured_illness_stage(stage, all) == stage &&
        cured_documented_mask(mask, all) == mask) {
      throw std::invalid_argument("curse cure does not affect this player");
    }
  }
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto index = indices[row];
    auto &state = states_[index];
    const auto before = state;
    state[1] = cured_illness_stage(static_cast<std::uint8_t>(state[1]),
                                   scopes(row) == 2);
    state[2] = cured_documented_mask(static_cast<std::uint8_t>(state[2]),
                                     scopes(row) == 2);
    record(index, 4, before);
  }
  cure_count_ += indices.size();
}

void CurseDynamicsBatch::finish_turns(ActionInput environments,
                                      ActionInput players,
                                      ActionInput expected_ticks,
                                      ActionInput progression_tickets) {
  const auto indices = checked_players(environments, players, true);
  same_length(indices.size(), expected_ticks);
  same_length(indices.size(), progression_tickets);
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto ticks = states_[indices[row]][3];
    if (ticks == kMaximumTicks || expected_ticks(row) != ticks ||
        progression_tickets(row) < 0 || progression_tickets(row) >= 100) {
      throw std::invalid_argument(
          "curse turn tick is stale or progression ticket is invalid");
    }
  }
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto index = indices[row];
    auto &state = states_[index];
    const auto before = state;
    auto result =
        periodic_illness_effect({static_cast<std::uint16_t>(state[0]),
                                 static_cast<std::uint8_t>(state[1])});
    // Effect-before-progression ordering is explicitly provisional. A lethal
    // periodic effect cannot be followed by progression or Heaven healing.
    if (result.hp > 0 && progression_tickets(row) < 5) {
      result = worsen_illness(result);
    }
    state[0] = result.hp;
    state[1] = result.stage;
    ++state[3];
    record(index, 5, before);
  }
  tick_count_ += indices.size();
}

void CurseDynamicsBatch::reset_environments(ActionInput environments) {
  std::set<std::size_t> unique;
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    const auto environment = environments(row);
    if (environment < 0 ||
        static_cast<std::uint64_t>(environment) >= batch_size_ ||
        !unique.insert(static_cast<std::size_t>(environment)).second) {
      throw std::invalid_argument(
          "curse dynamics reset environment is invalid or duplicate");
    }
  }
  for (const auto environment : unique) {
    for (std::size_t player = 0; player < player_count_; ++player) {
      const auto index = environment * player_count_ + player;
      states_[index] = {initial_hp_, 0, 0, 0};
      transitions_[index] = {};
    }
  }
}

CurseStateSnapshot CurseDynamicsBatch::snapshot() const {
  return copy_snapshot(states_, batch_size_, player_count_);
}

CurseStateSnapshot CurseDynamicsBatch::transition_snapshot() const {
  return copy_snapshot(transitions_, batch_size_, player_count_);
}

} // namespace godfield_sim
