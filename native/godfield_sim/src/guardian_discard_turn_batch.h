#pragma once

#include "guardian_utility_turn_batch.h"

namespace godfield_sim {

inline constexpr std::uint32_t kGuardianDiscardTurnKernelSchemaVersion = 1;
inline constexpr std::uint32_t kGuardianDiscardTurnObservationSchemaVersion = 1;
inline constexpr const char *kGuardianDiscardTurnRulesetId =
    "round-robin-inventory-discard-guardian-turns-provisional-v1";

// New opt-in type. Old utility turns cannot discard cards. Removal and turn
// scheduling are provisional; replacements remain caller-supplied.
class GuardianDiscardTurnBatch : public GuardianUtilityTurnBatch {
public:
  GuardianDiscardTurnBatch(
      std::size_t batch_size, std::size_t player_count,
      std::size_t guardian_slots, GuardianWeightInput weighted_profiles,
      GuardianWeightInput effect_profiles, GuardianWeightInput defense_profiles,
      GuardianWeightInput attack_profiles, GuardianWeightInput utility_profiles,
      ActionInput discard_models, std::size_t hand_slots = 18,
      std::uint64_t max_turns = 1000, std::uint16_t initial_hp = 40,
      std::uint16_t initial_mp = 10, std::uint16_t initial_cp = 0);
  void discard_cards(ActionInput environments, ActionInput players,
                     ActionInput slots);
  [[nodiscard]] Bool2D discard_action_masks() const;
  [[nodiscard]] std::uint64_t discarded_card_count() const {
    return discarded_card_count_;
  }

private:
  [[nodiscard]] bool legal_discard(std::size_t environment,
                                    std::size_t slot) const;
  std::unordered_set<std::int64_t> discard_models_;
  std::uint64_t discarded_card_count_ = 0;
};

} // namespace godfield_sim
