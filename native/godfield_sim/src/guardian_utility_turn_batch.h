#pragma once

#include "guardian_turn_batch.h"

namespace godfield_sim {

inline constexpr std::uint32_t kGuardianUtilityTurnKernelSchemaVersion = 1;
inline constexpr std::uint32_t kGuardianUtilityTurnObservationSchemaVersion = 1;
inline constexpr std::uint32_t kGuardianUtilityActorHandSchemaVersion = 1;
inline constexpr const char *kGuardianUtilityTurnRulesetId =
    "round-robin-inventory-utility-guardian-turns-provisional-v1";

// Distinct public type and hand projection: old GuardianTurnBatch contracts and
// checkpoints cannot accidentally acquire utility cards or wider features.
class GuardianUtilityTurnBatch {
public:
  GuardianUtilityTurnBatch(
      std::size_t batch_size, std::size_t player_count,
      std::size_t guardian_slots, GuardianWeightInput weighted_profiles,
      GuardianWeightInput effect_profiles, GuardianWeightInput defense_profiles,
      GuardianWeightInput attack_profiles, GuardianWeightInput utility_profiles,
      std::size_t hand_slots = 18, std::uint64_t max_turns = 1000,
      std::uint16_t initial_hp = 40, std::uint16_t initial_mp = 10,
      std::uint16_t initial_cp = 0);
  void deal_cards(ActionInput environments, ActionInput players,
                  ActionInput slots, ActionInput instances, ActionInput models);
  void use_utility_cards(ActionInput environments, ActionInput players,
                         ActionInput slots);
  [[nodiscard]] Bool2D utility_action_masks() const;
  [[nodiscard]] Bool2D ready_action_masks() const;
  [[nodiscard]] GuardianStateSnapshot actor_hand_snapshot() const;
  [[nodiscard]] GuardianInventorySnapshot hand_feature_snapshot() const;
  void summon(ActionInput envs, ActionInput slots, ActionInput instances,
              ActionInput owners, ActionInput groups) {
    turns_.summon(envs, slots, instances, owners, groups);
  }
  void remove(ActionInput envs, ActionInput slots, ActionInput instances) {
    turns_.remove(envs, slots, instances);
  }
  void deal_defenses(ActionInput envs, ActionInput players, ActionInput slots,
                     ActionInput instances, ActionInput models) {
    turns_.deal_defenses(envs, players, slots, instances, models);
  }
  void begin_card_attacks(ActionInput envs, ActionInput players,
                          ActionInput slots, ActionInput targets) {
    turns_.begin_card_attacks(envs, players, slots, targets);
  }
  void begin_effects(ActionInput envs, ActionInput slots, ActionInput instances,
                     ActionInput targets, ActionInput selection_tickets,
                     ActionInput hit_tickets) {
    turns_.begin_effects(envs, slots, instances, targets, selection_tickets,
                         hit_tickets);
  }
  void pass_turns(ActionInput envs, ActionInput players) {
    turns_.pass_turns(envs, players);
  }
  void step_defenses(ActionInput envs, ActionInput players,
                     ActionInput actions) {
    turns_.step_defenses(envs, players, actions);
  }
  void resolve_bounces(ActionInput envs, ActionInput players,
                       ActionInput targets) {
    turns_.resolve_bounces(envs, players, targets);
  }
  void reset_environments(ActionInput envs) { turns_.reset_environments(envs); }
  [[nodiscard]] Bool2D defense_action_masks() const {
    return turns_.defense_action_masks();
  }
  [[nodiscard]] Bool2D attack_action_masks() const {
    return turns_.attack_action_masks();
  }
  [[nodiscard]] Bool2D attack_target_masks() const {
    return turns_.attack_target_masks();
  }
  [[nodiscard]] Bool2D bounce_target_masks() const {
    return turns_.bounce_target_masks();
  }
  [[nodiscard]] Int64_2D turn_snapshot() const {
    return turns_.turn_snapshot();
  }
  [[nodiscard]] GuardianInventorySnapshot inventory_snapshot() const {
    return turns_.inventory_snapshot();
  }
  [[nodiscard]] GuardianStateSnapshot guardian_snapshot() const {
    return turns_.guardian_snapshot();
  }
  [[nodiscard]] GuardianStateSnapshot resource_snapshot() const {
    return turns_.resource_snapshot();
  }
  [[nodiscard]] Int64_2D combat_snapshot() const {
    return turns_.combat_snapshot();
  }
  [[nodiscard]] std::size_t hand_slots() const { return turns_.hand_slots(); }
  [[nodiscard]] std::size_t action_count() const {
    return turns_.action_count();
  }
  [[nodiscard]] std::uint64_t consumed_card_count() const {
    return turns_.consumed_card_count();
  }
  [[nodiscard]] std::uint64_t miracle_cast_count() const {
    return turns_.miracle_cast_count();
  }
  [[nodiscard]] std::uint64_t mp_spent() const { return turns_.mp_spent(); }
  [[nodiscard]] std::uint64_t resolved_effect_count() const {
    return turns_.resolved_effect_count();
  }
  [[nodiscard]] std::uint64_t utility_use_count() const {
    return utility_use_count_;
  }
  [[nodiscard]] std::uint64_t hp_gained() const { return hp_gained_; }
  [[nodiscard]] std::uint64_t mp_gained() const { return mp_gained_; }

private:
  struct Utility {
    std::int64_t resource; // 0 HP, 1 MP
    std::int64_t value;
    std::int64_t reusable;
    std::int64_t cost;
  };
  [[nodiscard]] bool legal_utility(std::size_t environment,
                                   std::size_t slot) const;
  [[nodiscard]] std::array<std::int64_t, 8>
  hand_features(const GuardianTurnBatch::Card &card) const;
  GuardianTurnBatch turns_;
  std::unordered_map<std::int64_t, Utility> utilities_;
  std::unordered_set<std::int64_t> utility_models_;
  std::uint64_t utility_use_count_ = 0;
  std::uint64_t hp_gained_ = 0;
  std::uint64_t mp_gained_ = 0;
};

} // namespace godfield_sim
