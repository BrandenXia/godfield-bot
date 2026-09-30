#pragma once

#include <array>
#include <unordered_map>
#include <vector>

#include "guardian_lifecycle_batch.h"

namespace godfield_sim {

inline constexpr std::uint32_t kGuardianCombatKernelSchemaVersion = 2;
inline constexpr std::uint32_t kGuardianCombatObservationSchemaVersion = 2;
inline constexpr const char *kGuardianCombatRulesetId =
    "caller-driven-guardian-resource-curse-combat-provisional-v2";

class GuardianCombatBatch {
public:
  GuardianCombatBatch(std::size_t batch_size, std::size_t player_count,
                      std::size_t slots_per_environment,
                      GuardianWeightInput weighted_profiles,
                      GuardianWeightInput basic_attack_profiles,
                      std::uint16_t initial_hp = 40,
                      std::uint16_t initial_mp = 10,
                      std::uint16_t initial_cp = 0);
  void summon(ActionInput environments, ActionInput slots,
              ActionInput instances, ActionInput owners, ActionInput groups);
  void remove(ActionInput environments, ActionInput slots,
              ActionInput instances);
  void reset_environments(ActionInput environments);
  void begin_attacks(ActionInput environments, ActionInput slots,
                     ActionInput instances, ActionInput targets,
                     ActionInput selection_tickets, ActionInput hit_tickets);
  void resolve_defenses(ActionInput environments, ActionInput defense_values,
                        ActionInput defense_elements);
  [[nodiscard]] GuardianStateSnapshot guardian_snapshot() const {
    return guardians_.snapshot();
  }
  [[nodiscard]] Int64_2D hp_snapshot() const;
  [[nodiscard]] Int64_2D combat_snapshot() const;
  [[nodiscard]] GuardianStateSnapshot resource_snapshot() const;
  [[nodiscard]] std::uint64_t resolved_attack_count() const noexcept {
    return resolved_attack_count_;
  }
  [[nodiscard]] std::uint64_t resolved_effect_count() const noexcept {
    return resolved_effect_count_;
  }

private:
  // The scheduler composes this kernel without copying its state or exposing
  // arbitrary defense values to policy callers.
  friend class GuardianTurnBatch;
  friend class GuardianUtilityTurnBatch;
  struct BasicAttack {
    std::int64_t value;
    std::int64_t element;
    std::int64_t hit_rate;
    std::int64_t effect = 0;
    std::int64_t utility = 0;
    std::int64_t curse = 0;
  };
  // phase (0 idle, 1 defense), model, owner, target, ATK after hit,
  // element, HP lost at the last completed resolution.
  using Pending = std::array<std::int64_t, 10>;
  [[nodiscard]] std::size_t checked_environment(std::int64_t environment) const;
  void require_idle(ActionInput environments) const;
  static void same_length(std::size_t expected, ActionInput input);
  static bool compatible(std::int64_t attack, std::int64_t defense);
  const std::size_t batch_size_;
  const std::size_t player_count_;
  const std::uint16_t initial_hp_;
  const std::uint16_t initial_mp_;
  const std::uint16_t initial_cp_;
  GuardianLifecycleBatch guardians_;
  std::unordered_map<std::int64_t, BasicAttack> attacks_;
  std::vector<std::int64_t> hp_;
  std::vector<std::int64_t> mp_;
  std::vector<std::int64_t> cp_;
  std::vector<std::int64_t> curses_;
  std::vector<Pending> pending_;
  std::uint64_t resolved_attack_count_ = 0;
  std::uint64_t resolved_effect_count_ = 0;
};

} // namespace godfield_sim
