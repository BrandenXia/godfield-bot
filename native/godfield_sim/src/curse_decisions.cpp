#include "curse_dynamics_batch.h"
#include "curse_rules.h"

#include <algorithm>
#include <initializer_list>
#include <memory>
#include <stdexcept>
#include <utility>

namespace godfield_sim {
namespace {
constexpr std::size_t kPaddedPlayers = 9;
constexpr std::size_t kStatusWidth = 6;
constexpr std::size_t kMaximumProjectionPlayers = 2000000;
constexpr std::size_t kMaximumDecisionRows = 1000000;

void bounded_decisions(std::size_t count) {
  if (count > kMaximumDecisionRows) {
    throw std::invalid_argument("curse decision rows exceed bounded capacity");
  }
}

template <typename Output>
Output owned_output(std::unique_ptr<std::int64_t[]> buffer,
                    std::initializer_list<std::size_t> shape) {
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return Output(data, shape, owner);
}
} // namespace

CurseStateSnapshot
CurseDynamicsBatch::status_observations(ActionInput environments,
                                        ActionInput actors) const {
  const auto count = environments.shape(0);
  if (count > kMaximumProjectionPlayers / kPaddedPlayers) {
    throw std::invalid_argument(
        "curse status projection exceeds bounded capacity");
  }
  (void)checked_players(environments, actors, false, false);
  auto buffer = std::make_unique<std::int64_t[]>(
      std::max<std::size_t>(1, count * kPaddedPlayers * kStatusWidth));
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = static_cast<std::size_t>(environments(row));
    const auto actor = static_cast<std::size_t>(actors(row));
    const auto actor_mask = static_cast<std::uint8_t>(
        states_[environment * player_count_ + actor][2]);
    for (std::size_t relative = 0; relative < kPaddedPlayers; ++relative) {
      auto *out =
          buffer.get() + (row * kPaddedPlayers + relative) * kStatusWidth;
      if (relative >= player_count_) {
        std::fill_n(out, kStatusWidth, 0);
        out[0] = -1;
        continue;
      }
      const auto player = (actor + relative) % player_count_;
      const auto &state = states_[environment * player_count_ + player];
      const auto visible = !fog_hides_other_player(actor_mask, relative == 0);
      out[0] = static_cast<std::int64_t>(player);
      out[1] = 1; // Present, including eliminated players; not a living flag.
      out[2] = visible ? 1 : 0;
      out[3] = visible ? state[0] : 0;
      out[4] = visible ? state[1] : 0;
      out[5] = visible ? state[2] : 0;
    }
  }
  return owned_output<CurseStateSnapshot>(
      std::move(buffer), {count, kPaddedPlayers, kStatusWidth});
}

CurseDecisionOutput
CurseDynamicsBatch::defense_card_limits(ActionInput environments,
                                        ActionInput players,
                                        ActionInput ordinary_limits) const {
  const auto count = environments.shape(0);
  bounded_decisions(count);
  const auto indices = checked_players(environments, players, false, false);
  same_length(count, ordinary_limits);
  for (std::size_t row = 0; row < count; ++row) {
    if (ordinary_limits(row) < 1 || ordinary_limits(row) > 512) {
      throw std::invalid_argument(
          "ordinary defense card limit is out of range");
    }
  }
  auto buffer =
      std::make_unique<std::int64_t[]>(std::max<std::size_t>(1, count));
  for (std::size_t row = 0; row < count; ++row) {
    const auto &state = states_[indices[row]];
    buffer[row] =
        state[0] == 0
            ? 0
            : ((state[2] & kCurseFlashBit) != 0 ? 1 : ordinary_limits(row));
  }
  return owned_output<CurseDecisionOutput>(std::move(buffer), {count});
}

Int64_2D CurseDynamicsBatch::hit_decisions(ActionInput environments,
                                           ActionInput targets,
                                           ActionInput hit_rates,
                                           ActionInput hit_tickets) const {
  const auto count = environments.shape(0);
  bounded_decisions(count);
  const auto indices = checked_players(environments, targets, true, false);
  same_length(count, hit_rates);
  same_length(count, hit_tickets);
  for (std::size_t row = 0; row < count; ++row) {
    if (hit_rates(row) < 1 || hit_rates(row) > 100 || hit_tickets(row) < 0 ||
        hit_tickets(row) >= 100) {
      throw std::invalid_argument(
          "percentage hit rate or ticket is out of range");
    }
  }
  auto buffer =
      std::make_unique<std::int64_t[]>(std::max<std::size_t>(1, count * 2));
  for (std::size_t row = 0; row < count; ++row) {
    const auto mask = static_cast<std::uint8_t>(states_[indices[row]][2]);
    const auto rate = static_cast<std::uint8_t>(hit_rates(row));
    buffer[row * 2] =
        percentage_attack_hits(mask, rate,
                               static_cast<std::uint8_t>(hit_tickets(row)))
            ? 1
            : 0;
    buffer[row * 2 + 1] = percentage_hit_requires_ticket(mask, rate) ? 1 : 0;
  }
  return owned_output<Int64_2D>(std::move(buffer), {count, 2});
}

CurseDecisionOutput CurseDynamicsBatch::enemy_targets(
    ActionInput environments, ActionInput actors, ActionInput intended_targets,
    CurseCandidateInput eligible_enemies, ActionInput selection_tickets) const {
  const auto count = environments.shape(0);
  bounded_decisions(count);
  (void)checked_players(environments, actors, true, false);
  same_length(count, intended_targets);
  same_length(count, selection_tickets);
  if (eligible_enemies.shape(0) != count) {
    throw std::invalid_argument("curse enemy candidate rows differ");
  }
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = static_cast<std::size_t>(environments(row));
    const auto actor = static_cast<std::size_t>(actors(row));
    const auto intended = intended_targets(row);
    std::int64_t candidates = 0;
    for (std::size_t player = 0; player < kPaddedPlayers; ++player) {
      const auto eligible = eligible_enemies(row, player);
      if (eligible != 0 && eligible != 1) {
        throw std::invalid_argument("curse enemy candidates must be binary");
      }
      if (eligible == 1) {
        if (player >= player_count_ || player == actor ||
            states_[environment * player_count_ + player][0] == 0) {
          throw std::invalid_argument(
              "curse enemy candidate is padded, self, or dead");
        }
        ++candidates;
      }
    }
    if (intended < 0 || static_cast<std::uint64_t>(intended) >= player_count_ ||
        eligible_enemies(row, static_cast<std::size_t>(intended)) != 1 ||
        selection_tickets(row) < 0 || selection_tickets(row) >= candidates) {
      throw std::invalid_argument(
          "curse intended enemy or selection ticket is invalid");
    }
  }
  auto buffer =
      std::make_unique<std::int64_t[]>(std::max<std::size_t>(1, count));
  for (std::size_t row = 0; row < count; ++row) {
    const auto actor_index =
        static_cast<std::size_t>(environments(row)) * player_count_ +
        static_cast<std::size_t>(actors(row));
    buffer[row] = intended_targets(row);
    if ((states_[actor_index][2] & kCurseFogBit) == 0) {
      continue;
    }
    auto rank = selection_tickets(row);
    for (std::size_t player = 0; player < player_count_; ++player) {
      if (eligible_enemies(row, player) == 1 && rank-- == 0) {
        buffer[row] = static_cast<std::int64_t>(player);
        break;
      }
    }
  }
  return owned_output<CurseDecisionOutput>(std::move(buffer), {count});
}

} // namespace godfield_sim
