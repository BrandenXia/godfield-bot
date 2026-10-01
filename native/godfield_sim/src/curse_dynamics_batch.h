#pragma once

#include <array>
#include <vector>

#include "batch_types.h"

namespace godfield_sim {

inline constexpr std::uint32_t kCurseDynamicsSchemaVersion = 1;
inline constexpr const char *kCurseDynamicsRulesetId =
    "caller-driven-documented-curse-dynamics-provisional-v1";
using CurseStateSnapshot =
    nb::ndarray<const std::int64_t, nb::numpy, nb::ndim<3>, nb::c_contig>;
using CurseCandidateInput =
    nb::ndarray<const std::int64_t, nb::numpy, nb::shape<-1, 9>, nb::c_contig,
                nb::device::cpu>;
using CurseDecisionOutput =
    nb::ndarray<const std::int64_t, nb::numpy, nb::ndim<1>, nb::c_contig>;
inline constexpr std::uint32_t kCurseDecisionSchemaVersion = 1;
inline constexpr const char *kCurseDecisionRulesetId =
    "caller-driven-fog-flash-darkcloud-decisions-provisional-v1";

// Trusted caller interface, not a policy-facing environment: no item legality,
// action masks, MP costs, automatic turns, randomness, or winner selection.
class CurseDynamicsBatch {
public:
  CurseDynamicsBatch(std::size_t batch_size, std::size_t player_count,
                     std::uint16_t initial_hp = 40);
  void load_players(ActionInput environments, ActionInput players,
                    ActionInput hp, ActionInput illness,
                    ActionInput curse_masks);
  void apply_illnesses(ActionInput environments, ActionInput players,
                       ActionInput stages);
  void apply_curses(ActionInput environments, ActionInput players,
                    ActionInput curse_bits);
  void cure_players(ActionInput environments, ActionInput players,
                    ActionInput scopes);
  void finish_turns(ActionInput environments, ActionInput players,
                    ActionInput expected_ticks,
                    ActionInput progression_tickets);
  void reset_environments(ActionInput environments);
  [[nodiscard]] CurseStateSnapshot snapshot() const;
  [[nodiscard]] CurseStateSnapshot transition_snapshot() const;
  // Separately versioned, read-only status view and trusted-caller
  // calculations. These do not constitute a complete policy observation or
  // action interface.
  // Defense/hit/target calculations are scheduler-only, not policy features.
  [[nodiscard]] CurseStateSnapshot
  status_observations(ActionInput environments, ActionInput actors) const;
  [[nodiscard]] CurseDecisionOutput
  defense_card_limits(ActionInput environments, ActionInput players,
                      ActionInput ordinary_limits) const;
  [[nodiscard]] Int64_2D hit_decisions(ActionInput environments,
                                       ActionInput targets,
                                       ActionInput hit_rates,
                                       ActionInput hit_tickets) const;
  [[nodiscard]] CurseDecisionOutput
  enemy_targets(ActionInput environments, ActionInput actors,
                ActionInput intended_targets,
                CurseCandidateInput eligible_enemies,
                ActionInput selection_tickets) const;
  [[nodiscard]] std::uint64_t illness_count() const noexcept {
    return illness_count_;
  }
  [[nodiscard]] std::uint64_t curse_count() const noexcept {
    return curse_count_;
  }
  [[nodiscard]] std::uint64_t cure_count() const noexcept {
    return cure_count_;
  }
  [[nodiscard]] std::uint64_t tick_count() const noexcept {
    return tick_count_;
  }
  [[nodiscard]] std::uint64_t death_count() const noexcept {
    return death_count_;
  }

private:
  // HP, exclusive illness stage, non-disease curse mask, completed turn ticks.
  using State = std::array<std::int64_t, 4>;
  // Operation: reset=0, load=1, illness=2, curse=3, cure=4, tick=5;
  // previous HP, previous illness, previous mask, HP delta, newly died.
  using Transition = std::array<std::int64_t, 6>;
  [[nodiscard]] std::vector<std::size_t>
  checked_players(ActionInput environments, ActionInput players,
                  bool living_only, bool require_unique = true) const;
  static void same_length(std::size_t expected, ActionInput input);
  void record(std::size_t index, std::int64_t operation,
              const State &before) noexcept;
  const std::size_t batch_size_;
  const std::size_t player_count_;
  const std::uint16_t initial_hp_;
  std::vector<State> states_;
  std::vector<Transition> transitions_;
  std::uint64_t illness_count_ = 0;
  std::uint64_t curse_count_ = 0;
  std::uint64_t cure_count_ = 0;
  std::uint64_t tick_count_ = 0;
  std::uint64_t death_count_ = 0;
};

} // namespace godfield_sim
