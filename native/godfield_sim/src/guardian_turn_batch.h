#pragma once

#include <optional>

#include "guardian_combat_batch.h"

namespace godfield_sim {

inline constexpr std::uint32_t kGuardianTurnKernelSchemaVersion = 2;
inline constexpr std::uint32_t kGuardianTurnObservationSchemaVersion = 2;
inline constexpr std::uint32_t kGuardianTurnMaxDefenseActions = 64;
inline constexpr std::uint32_t kGuardianActorHandSchemaVersion = 1;
inline constexpr const char *kGuardianTurnRulesetId =
    "round-robin-card-guardian-resource-turns-provisional-v2";
using GuardianInventorySnapshot =
    nb::ndarray<const std::int64_t, nb::numpy, nb::ndim<4>, nb::c_contig>;

// Isolated provisional scheduler: one card attack, caller-selected guardian
// effect, or pass per turn. It does not model official guardian timing.
class GuardianTurnBatch {
public:
  GuardianTurnBatch(
      std::size_t batch_size, std::size_t player_count,
      std::size_t guardian_slots, GuardianWeightInput weighted_profiles,
      GuardianWeightInput effect_profiles, GuardianWeightInput defense_profiles,
      std::size_t hand_slots = 18, std::uint64_t max_turns = 1000,
      std::uint16_t initial_hp = 40, std::uint16_t initial_mp = 10,
      std::uint16_t initial_cp = 0,
      std::optional<GuardianWeightInput> attack_profiles = std::nullopt);
  void summon(ActionInput environments, ActionInput slots,
              ActionInput instances, ActionInput owners, ActionInput groups);
  void remove(ActionInput environments, ActionInput slots,
              ActionInput instances);
  void deal_defenses(ActionInput environments, ActionInput players,
                     ActionInput slots, ActionInput instances,
                     ActionInput models);
  void deal_cards(ActionInput environments, ActionInput players,
                  ActionInput slots, ActionInput instances, ActionInput models);
  void begin_card_attacks(ActionInput environments, ActionInput players,
                          ActionInput slots, ActionInput targets);
  void begin_effects(ActionInput environments, ActionInput slots,
                     ActionInput instances, ActionInput targets,
                     ActionInput selection_tickets, ActionInput hit_tickets);
  void pass_turns(ActionInput environments, ActionInput players);
  void step_defenses(ActionInput environments, ActionInput players,
                     ActionInput actions);
  void resolve_bounces(ActionInput environments, ActionInput players,
                       ActionInput targets);
  void reset_environments(ActionInput environments);
  [[nodiscard]] Bool2D defense_action_masks() const;
  [[nodiscard]] Bool2D attack_action_masks() const;
  [[nodiscard]] Bool2D attack_target_masks() const;
  [[nodiscard]] Bool2D bounce_target_masks() const;
  [[nodiscard]] Int64_2D turn_snapshot() const;
  [[nodiscard]] GuardianInventorySnapshot inventory_snapshot() const;
  [[nodiscard]] GuardianInventorySnapshot hand_feature_snapshot() const;
  [[nodiscard]] GuardianStateSnapshot actor_hand_snapshot() const;
  [[nodiscard]] GuardianStateSnapshot guardian_snapshot() const {
    return combat_.guardian_snapshot();
  }
  [[nodiscard]] GuardianStateSnapshot resource_snapshot() const {
    return combat_.resource_snapshot();
  }
  [[nodiscard]] Int64_2D combat_snapshot() const {
    return combat_.combat_snapshot();
  }
  [[nodiscard]] std::size_t hand_slots() const noexcept { return hand_slots_; }
  [[nodiscard]] std::size_t action_count() const noexcept {
    return hand_slots_ + 2;
  }
  [[nodiscard]] std::uint64_t consumed_card_count() const noexcept {
    return consumed_card_count_;
  }
  [[nodiscard]] std::uint64_t resolved_effect_count() const noexcept {
    return combat_.resolved_effect_count();
  }
  [[nodiscard]] std::uint64_t miracle_cast_count() const noexcept {
    return miracle_cast_count_;
  }
  [[nodiscard]] std::uint64_t mp_spent() const noexcept { return mp_spent_; }

private:
  struct Defense {
    std::int64_t value;
    std::int64_t element;
    std::int64_t kind = 0; // 0 armor, 1 block NE weapon, 2 bounce miracle
    std::int64_t cost = 0;
  };
  struct Attack {
    std::int64_t value;
    std::int64_t element;
    std::int64_t origin; // 0 weapon, 1 reusable miracle
    std::int64_t cost;
  };
  struct Card {
    std::int64_t instance = 0;
    std::int64_t model = 0;
  };
  struct Turn {
    std::int64_t owner = 0;
    std::uint64_t completed = 0;
    std::int64_t winner = -1;
    bool truncated = false;
    std::uint32_t defense_actions = 0;
    std::int64_t origin = -1; // 2 guardian; never guessed to be weapon/miracle
    bool bounced = false;
    bool bounce_pending = false;
  };
  void require_ready(ActionInput environments) const;
  void validate_unique(ActionInput environments) const;
  void finish_turn(std::size_t environment);
  void deal_cards_impl(ActionInput environments, ActionInput players,
                       ActionInput slots, ActionInput instances,
                       ActionInput models, bool defense_only);
  [[nodiscard]] std::size_t card_offset(std::size_t environment,
                                        std::int64_t player,
                                        std::size_t slot) const;
  [[nodiscard]] bool legal_card(std::size_t environment,
                                std::size_t slot) const;
  [[nodiscard]] std::int64_t selected_defense(std::size_t environment) const;
  [[nodiscard]] std::int64_t selected_cost(std::size_t environment) const;
  [[nodiscard]] std::int64_t
  selected_special_slot(std::size_t environment) const;
  [[nodiscard]] bool finished(std::size_t environment) const;
  [[nodiscard]] Bool2D target_masks(bool bounce) const;
  [[nodiscard]] std::array<std::int64_t, 6>
  hand_features(const Card &card) const;
  const std::size_t batch_size_;
  const std::size_t player_count_;
  const std::size_t hand_slots_;
  const std::uint64_t max_turns_;
  GuardianCombatBatch combat_;
  std::unordered_map<std::int64_t, Defense> defenses_;
  std::unordered_map<std::int64_t, Attack> attacks_;
  std::vector<Card> cards_;
  std::vector<std::uint8_t> selected_;
  std::vector<Turn> turns_;
  std::uint64_t consumed_card_count_ = 0;
  std::uint64_t miracle_cast_count_ = 0;
  std::uint64_t mp_spent_ = 0;
};

} // namespace godfield_sim
