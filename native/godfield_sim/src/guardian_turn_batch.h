#pragma once

#include "guardian_combat_batch.h"

namespace godfield_sim {

inline constexpr std::uint32_t kGuardianTurnKernelSchemaVersion = 1;
inline constexpr std::uint32_t kGuardianTurnObservationSchemaVersion = 1;
inline constexpr std::uint32_t kGuardianTurnMaxDefenseActions = 64;
inline constexpr const char *kGuardianTurnRulesetId =
    "round-robin-guardian-armor-turns-provisional-v1";
using GuardianInventorySnapshot =
    nb::ndarray<const std::int64_t, nb::numpy, nb::ndim<4>, nb::c_contig>;

// Isolated provisional scheduler: one caller-selected guardian effect or pass
// per turn. It does not model the official guardian activation timing.
class GuardianTurnBatch {
public:
  GuardianTurnBatch(std::size_t batch_size, std::size_t player_count,
                    std::size_t guardian_slots,
                    GuardianWeightInput weighted_profiles,
                    GuardianWeightInput effect_profiles,
                    GuardianWeightInput defense_profiles,
                    std::size_t hand_slots = 18, std::uint64_t max_turns = 1000,
                    std::uint16_t initial_hp = 40,
                    std::uint16_t initial_mp = 10,
                    std::uint16_t initial_cp = 0);
  void summon(ActionInput environments, ActionInput slots,
              ActionInput instances, ActionInput owners, ActionInput groups);
  void remove(ActionInput environments, ActionInput slots,
              ActionInput instances);
  void deal_defenses(ActionInput environments, ActionInput players,
                     ActionInput slots, ActionInput instances,
                     ActionInput models);
  void begin_effects(ActionInput environments, ActionInput slots,
                     ActionInput instances, ActionInput targets,
                     ActionInput selection_tickets, ActionInput hit_tickets);
  void pass_turns(ActionInput environments, ActionInput players);
  void step_defenses(ActionInput environments, ActionInput players,
                     ActionInput actions);
  void reset_environments(ActionInput environments);
  [[nodiscard]] Bool2D defense_action_masks() const;
  [[nodiscard]] Int64_2D turn_snapshot() const;
  [[nodiscard]] GuardianInventorySnapshot inventory_snapshot() const;
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

private:
  struct Defense {
    std::int64_t value;
    std::int64_t element;
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
  };
  void require_ready(ActionInput environments) const;
  void validate_unique(ActionInput environments) const;
  void finish_turn(std::size_t environment);
  [[nodiscard]] std::size_t card_offset(std::size_t environment,
                                        std::int64_t player,
                                        std::size_t slot) const;
  [[nodiscard]] bool legal_card(std::size_t environment,
                                std::size_t slot) const;
  [[nodiscard]] std::int64_t selected_defense(std::size_t environment) const;
  const std::size_t batch_size_;
  const std::size_t player_count_;
  const std::size_t hand_slots_;
  const std::uint64_t max_turns_;
  GuardianCombatBatch combat_;
  std::unordered_map<std::int64_t, Defense> defenses_;
  std::vector<Card> cards_;
  std::vector<std::uint8_t> selected_;
  std::vector<Turn> turns_;
  std::uint64_t consumed_card_count_ = 0;
};

} // namespace godfield_sim
