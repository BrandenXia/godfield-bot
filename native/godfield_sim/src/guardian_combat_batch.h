#pragma once

#include <array>
#include <unordered_map>
#include <vector>

#include "guardian_lifecycle_batch.h"

namespace godfield_sim {

inline constexpr std::uint32_t kGuardianCombatKernelSchemaVersion = 1;
inline constexpr std::uint32_t kGuardianCombatObservationSchemaVersion = 1;
inline constexpr const char *kGuardianCombatRulesetId =
    "caller-driven-basic-guardian-combat-provisional-v1";

class GuardianCombatBatch {
public:
  GuardianCombatBatch(std::size_t batch_size, std::size_t player_count,
                      std::size_t slots_per_environment,
                      GuardianWeightInput weighted_profiles,
                      GuardianWeightInput basic_attack_profiles,
                      std::uint16_t initial_hp = 40);
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
  [[nodiscard]] std::uint64_t resolved_attack_count() const noexcept {
    return resolved_attack_count_;
  }

private:
  struct BasicAttack {
    std::int64_t value;
    std::int64_t element;
    std::int64_t hit_rate;
  };
  // phase (0 idle, 1 defense), model, owner, target, ATK after hit,
  // element, HP lost at the last completed resolution.
  using Pending = std::array<std::int64_t, 7>;
  [[nodiscard]] std::size_t checked_environment(std::int64_t environment) const;
  void require_idle(ActionInput environments) const;
  static void same_length(std::size_t expected, ActionInput input);
  const std::size_t batch_size_;
  const std::size_t player_count_;
  const std::uint16_t initial_hp_;
  GuardianLifecycleBatch guardians_;
  std::unordered_map<std::int64_t, BasicAttack> attacks_;
  std::vector<std::int64_t> hp_;
  std::vector<Pending> pending_;
  std::uint64_t resolved_attack_count_ = 0;
};

} // namespace godfield_sim
