#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <vector>

#include "batch_types.h"

namespace godfield_sim {

inline constexpr std::uint32_t kAttackDefenseKernelSchemaVersion = 1;
inline constexpr std::uint32_t kAttackDefenseObservationSchemaVersion = 2;
inline constexpr const char *kAttackDefenseRulesetId =
    "plain-attack-defense-redraw-duel-v1";
inline constexpr std::uint32_t kMixedAttackDefenseKernelSchemaVersion = 1;
inline constexpr std::uint32_t kMixedAttackDefenseObservationSchemaVersion = 2;
inline constexpr const char *kMixedAttackDefenseRulesetId =
    "plain-mixed-hand-attack-defense-redraw-duel-v1";
inline constexpr std::uint32_t kElementalAttackDefenseKernelSchemaVersion = 1;
inline constexpr std::uint32_t kElementalAttackDefenseObservationSchemaVersion =
    3;
inline constexpr const char *kElementalAttackDefenseRulesetId =
    "plain-elemental-mixed-hand-attack-defense-redraw-duel-v1";
inline constexpr std::uint32_t kComboAttackDefenseKernelSchemaVersion = 1;
inline constexpr std::uint32_t kComboAttackDefenseObservationSchemaVersion = 4;
inline constexpr const char *kComboAttackDefenseRulesetId =
    "plain-elemental-combo-attack-defense-redraw-duel-v1";
inline constexpr std::uint32_t kResourceAttackDefenseKernelSchemaVersion = 1;
inline constexpr std::uint32_t kResourceAttackDefenseObservationSchemaVersion =
    5;
inline constexpr const char *kResourceAttackDefenseRulesetId =
    "plain-elemental-combo-resource-miracle-attack-defense-redraw-duel-v1";
inline constexpr std::size_t kWeaponSlots = 5;
inline constexpr std::size_t kArmorSlots = kHandSlots - kWeaponSlots;
inline constexpr std::size_t kComboWeaponSlots = 4;
inline constexpr std::size_t kComboBoosterSlots = 2;
inline constexpr std::size_t kComboArmorSlots = 3;
inline constexpr std::size_t kResourceWeaponSlots = 3;
inline constexpr std::size_t kResourceBoosterSlots = 1;
inline constexpr std::size_t kResourceArmorSlots = 2;
inline constexpr std::size_t kResourceUtilitySlots = 2;
inline constexpr std::size_t kResourceAttackMiracleSlots = 1;

enum class TurnPhase : std::uint8_t {
  Attack = 0,
  Defense = 1,
  Terminal = 2,
};

enum class CombatElement : std::uint8_t {
  NonElement = 0,
  Fire = 1,
  Water = 2,
  Wood = 3,
  Stone = 4,
  Light = 5,
  Darkness = 6,
};

class AttackDefenseBatch {
public:
  AttackDefenseBatch(std::size_t batch_size, TokenInput weapon_token_ids,
                     ValueInput attack_values, TokenInput armor_token_ids,
                     ValueInput defense_values, std::uint64_t seed,
                     std::uint16_t initial_hp, bool mixed_hands);

  [[nodiscard]] std::size_t batch_size() const noexcept { return batch_size_; }
  [[nodiscard]] std::uint64_t seed() const noexcept { return base_seed_; }
  [[nodiscard]] std::uint16_t initial_hp() const noexcept {
    return initial_hp_;
  }
  [[nodiscard]] bool mixed_hands() const noexcept { return mixed_hands_; }
  [[nodiscard]] bool elemental() const noexcept { return elemental_; }
  [[nodiscard]] bool combo() const noexcept { return combo_; }
  [[nodiscard]] bool resource_curriculum() const noexcept {
    return resource_curriculum_;
  }
  [[nodiscard]] std::uint16_t initial_mp() const noexcept {
    return initial_mp_;
  }
  [[nodiscard]] std::size_t global_feature_count() const noexcept {
    return global_feature_count_;
  }

  void reset();
  [[nodiscard]] std::size_t reset_done();
  void step(ActionInput actions);

  [[nodiscard]] Float2D global_features_view() const;
  [[nodiscard]] Float3D player_features_view() const;
  [[nodiscard]] Bool2D player_mask_view() const;
  [[nodiscard]] Int64_2D hand_token_ids_view() const;
  [[nodiscard]] Bool2D hand_mask_view() const;
  [[nodiscard]] UInt8_2D hand_card_kinds_view() const;
  [[nodiscard]] UInt8_2D hand_elements_view() const;
  [[nodiscard]] Bool2D action_mask_view() const;
  [[nodiscard]] UInt8_1D active_players_view() const;
  [[nodiscard]] UInt8_1D phases_view() const;
  [[nodiscard]] UInt16_1D pending_attacks_view() const;
  [[nodiscard]] UInt8_1D pending_elements_view() const;
  [[nodiscard]] Bool2D selected_hand_mask_view() const;
  [[nodiscard]] UInt8_1D selected_counts_view() const;
  [[nodiscard]] UInt16_1D selected_values_view() const;
  [[nodiscard]] UInt8_1D selected_elements_view() const;
  [[nodiscard]] Float2D terminal_returns_view() const;
  [[nodiscard]] Bool1D terminated_view() const;
  [[nodiscard]] UInt64_1D episode_ids_view() const;
  [[nodiscard]] UInt16_1D turn_numbers_view() const;
  [[nodiscard]] UInt16_2D magic_points_view() const;

protected:
  AttackDefenseBatch(
      std::size_t batch_size, TokenInput weapon_token_ids,
      ValueInput attack_values, std::vector<std::uint8_t> weapon_elements,
      TokenInput booster_token_ids, ValueInput booster_values,
      std::vector<std::uint8_t> booster_elements, TokenInput armor_token_ids,
      ValueInput defense_values, std::vector<std::uint8_t> armor_elements,
      std::uint64_t seed, std::uint16_t initial_hp, bool mixed_hands,
      bool elemental, bool combo, bool resource_curriculum,
      TokenInput hp_utility_token_ids = {}, ValueInput hp_utility_values = {},
      TokenInput mp_utility_token_ids = {}, ValueInput mp_utility_values = {},
      TokenInput attack_miracle_token_ids = {},
      ValueInput attack_miracle_values = {},
      ElementInput attack_miracle_elements = {},
      ValueInput attack_miracle_costs = {},
      TokenInput hp_miracle_token_ids = {}, ValueInput hp_miracle_values = {},
      ValueInput hp_miracle_costs = {}, std::uint16_t initial_mp = 0U);

private:
  static constexpr std::size_t kMaximumBatchSize = 1'000'000;

  [[nodiscard]] std::size_t hand_offset(std::size_t environment,
                                        std::size_t player,
                                        std::size_t slot) const noexcept;
  [[nodiscard]] std::uint64_t next_random(std::size_t environment) noexcept;
  void draw_weapon(std::size_t environment, std::size_t player,
                   std::size_t slot);
  void draw_armor(std::size_t environment, std::size_t player,
                  std::size_t slot);
  void draw_booster(std::size_t environment, std::size_t player,
                    std::size_t slot);
  void draw_mixed(std::size_t environment, std::size_t player,
                  std::size_t slot);
  void draw_combo(std::size_t environment, std::size_t player,
                  std::size_t slot);
  void draw_resource(std::size_t environment, std::size_t player,
                     std::size_t slot);
  void draw_hp_utility(std::size_t environment, std::size_t player,
                       std::size_t slot);
  void draw_mp_utility(std::size_t environment, std::size_t player,
                       std::size_t slot);
  void draw_attack_miracle(std::size_t environment, std::size_t player,
                           std::size_t slot);
  void draw_hp_miracle(std::size_t environment, std::size_t player,
                       std::size_t slot);
  [[nodiscard]] bool has_weapon(std::size_t environment,
                                std::size_t player) const noexcept;
  void redraw_consumed(std::size_t environment, std::size_t player,
                       std::size_t slot, std::uint8_t consumed_kind);
  void reset_environment(std::size_t environment);
  void clear_selection(std::size_t environment) noexcept;
  void consume_selection(std::size_t environment, std::size_t player);
  void resolve_defense(std::size_t environment, std::size_t defender,
                       std::uint16_t defense);
  [[nodiscard]] std::uint8_t
  combine_attack_elements(std::uint8_t existing,
                          std::uint8_t added) const noexcept;
  void refresh_environment_views(std::size_t environment);
  [[nodiscard]] bool
  defense_element_is_compatible(std::uint8_t attack_element,
                                std::uint8_t defense_element) const noexcept;

  std::size_t batch_size_;
  std::uint64_t base_seed_;
  std::uint16_t initial_hp_;
  bool mixed_hands_;
  bool elemental_;
  bool combo_;
  bool resource_curriculum_;
  std::size_t global_feature_count_;
  std::uint16_t initial_mp_;
  std::vector<std::uint32_t> weapon_token_ids_;
  std::vector<std::uint16_t> attack_values_;
  std::vector<std::uint8_t> weapon_elements_;
  std::vector<std::uint32_t> booster_token_ids_;
  std::vector<std::uint16_t> booster_values_;
  std::vector<std::uint8_t> booster_elements_;
  std::vector<std::uint32_t> armor_token_ids_;
  std::vector<std::uint16_t> defense_values_;
  std::vector<std::uint8_t> armor_elements_;
  std::vector<std::uint32_t> hp_utility_token_ids_;
  std::vector<std::uint16_t> hp_utility_values_;
  std::vector<std::uint32_t> mp_utility_token_ids_;
  std::vector<std::uint16_t> mp_utility_values_;
  std::vector<std::uint32_t> attack_miracle_token_ids_;
  std::vector<std::uint16_t> attack_miracle_values_;
  std::vector<std::uint8_t> attack_miracle_elements_;
  std::vector<std::uint16_t> attack_miracle_costs_;
  std::vector<std::uint32_t> hp_miracle_token_ids_;
  std::vector<std::uint16_t> hp_miracle_values_;
  std::vector<std::uint16_t> hp_miracle_costs_;
  std::vector<std::uint64_t> rng_states_;
  std::vector<std::uint64_t> episode_ids_;
  std::vector<std::uint16_t> hit_points_;
  std::vector<std::uint16_t> magic_points_;
  std::vector<std::uint16_t> hand_values_;
  std::vector<std::uint16_t> hand_costs_;
  std::vector<std::int64_t> hand_token_ids_by_player_;
  std::vector<std::uint8_t> hand_card_kinds_by_player_;
  std::vector<std::uint8_t> hand_elements_by_player_;
  std::vector<std::uint8_t> active_players_;
  std::vector<std::uint8_t> phases_;
  std::vector<std::uint8_t> pending_attackers_;
  std::vector<std::uint16_t> pending_attacks_;
  std::vector<std::uint8_t> pending_elements_;
  std::unique_ptr<bool[]> selected_hand_mask_;
  std::vector<std::uint8_t> selected_counts_;
  std::vector<std::uint16_t> selected_values_;
  std::vector<std::uint8_t> selected_elements_;
  std::vector<std::uint16_t> selected_costs_;
  std::vector<std::uint8_t> selected_base_kinds_;
  std::vector<std::uint16_t> turn_numbers_;
  std::unique_ptr<bool[]> terminated_;
  std::vector<float> terminal_returns_;

  std::vector<float> global_features_;
  std::vector<float> player_features_;
  std::vector<std::int64_t> visible_hand_token_ids_;
  std::vector<std::uint8_t> visible_hand_card_kinds_;
  std::vector<std::uint8_t> visible_hand_elements_;
  std::unique_ptr<bool[]> player_mask_;
  std::unique_ptr<bool[]> hand_mask_;
  std::unique_ptr<bool[]> action_mask_;
};

class ElementalAttackDefenseBatch final : public AttackDefenseBatch {
public:
  ElementalAttackDefenseBatch(std::size_t batch_size,
                              TokenInput weapon_token_ids,
                              ValueInput attack_values,
                              ElementInput weapon_elements,
                              TokenInput armor_token_ids,
                              ValueInput defense_values,
                              ElementInput armor_elements, std::uint64_t seed,
                              std::uint16_t initial_hp);
};

class ComboAttackDefenseBatch final : public AttackDefenseBatch {
public:
  ComboAttackDefenseBatch(std::size_t batch_size, TokenInput weapon_token_ids,
                          ValueInput attack_values,
                          ElementInput weapon_elements,
                          TokenInput booster_token_ids,
                          ValueInput booster_values,
                          ElementInput booster_elements,
                          TokenInput armor_token_ids, ValueInput defense_values,
                          ElementInput armor_elements, std::uint64_t seed,
                          std::uint16_t initial_hp);
};

class ResourceAttackDefenseBatch final : public AttackDefenseBatch {
public:
  ResourceAttackDefenseBatch(
      std::size_t batch_size, TokenInput weapon_token_ids,
      ValueInput attack_values, ElementInput weapon_elements,
      TokenInput booster_token_ids, ValueInput booster_values,
      ElementInput booster_elements, TokenInput armor_token_ids,
      ValueInput defense_values, ElementInput armor_elements,
      TokenInput hp_utility_token_ids, ValueInput hp_utility_values,
      TokenInput mp_utility_token_ids, ValueInput mp_utility_values,
      TokenInput attack_miracle_token_ids, ValueInput attack_miracle_values,
      ElementInput attack_miracle_elements, ValueInput attack_miracle_costs,
      TokenInput hp_miracle_token_ids, ValueInput hp_miracle_values,
      ValueInput hp_miracle_costs, std::uint64_t seed, std::uint16_t initial_hp,
      std::uint16_t initial_mp);
};

} // namespace godfield_sim
