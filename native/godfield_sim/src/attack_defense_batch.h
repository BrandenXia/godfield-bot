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
inline constexpr std::size_t kWeaponSlots = 5;
inline constexpr std::size_t kArmorSlots = kHandSlots - kWeaponSlots;

enum class TurnPhase : std::uint8_t {
  Attack = 0,
  Defense = 1,
  Terminal = 2,
};

class AttackDefenseBatch final {
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

  void reset();
  [[nodiscard]] std::size_t reset_done();
  void step(ActionInput actions);

  [[nodiscard]] Float2D global_features_view() const;
  [[nodiscard]] Float3D player_features_view() const;
  [[nodiscard]] Bool2D player_mask_view() const;
  [[nodiscard]] Int64_2D hand_token_ids_view() const;
  [[nodiscard]] Bool2D hand_mask_view() const;
  [[nodiscard]] UInt8_2D hand_card_kinds_view() const;
  [[nodiscard]] Bool2D action_mask_view() const;
  [[nodiscard]] UInt8_1D active_players_view() const;
  [[nodiscard]] UInt8_1D phases_view() const;
  [[nodiscard]] UInt16_1D pending_attacks_view() const;
  [[nodiscard]] Float2D terminal_returns_view() const;
  [[nodiscard]] Bool1D terminated_view() const;
  [[nodiscard]] UInt64_1D episode_ids_view() const;
  [[nodiscard]] UInt16_1D turn_numbers_view() const;

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
  void draw_mixed(std::size_t environment, std::size_t player,
                  std::size_t slot);
  [[nodiscard]] bool has_weapon(std::size_t environment,
                                std::size_t player) const noexcept;
  void redraw_consumed(std::size_t environment, std::size_t player,
                       std::size_t slot, std::uint8_t consumed_kind);
  void reset_environment(std::size_t environment);
  void refresh_environment_views(std::size_t environment);

  std::size_t batch_size_;
  std::uint64_t base_seed_;
  std::uint16_t initial_hp_;
  bool mixed_hands_;
  std::vector<std::uint32_t> weapon_token_ids_;
  std::vector<std::uint16_t> attack_values_;
  std::vector<std::uint32_t> armor_token_ids_;
  std::vector<std::uint16_t> defense_values_;
  std::vector<std::uint64_t> rng_states_;
  std::vector<std::uint64_t> episode_ids_;
  std::vector<std::uint16_t> hit_points_;
  std::vector<std::uint16_t> hand_values_;
  std::vector<std::int64_t> hand_token_ids_by_player_;
  std::vector<std::uint8_t> hand_card_kinds_by_player_;
  std::vector<std::uint8_t> active_players_;
  std::vector<std::uint8_t> phases_;
  std::vector<std::uint8_t> pending_attackers_;
  std::vector<std::uint16_t> pending_attacks_;
  std::vector<std::uint16_t> turn_numbers_;
  std::unique_ptr<bool[]> terminated_;
  std::vector<float> terminal_returns_;

  std::vector<float> global_features_;
  std::vector<float> player_features_;
  std::vector<std::int64_t> visible_hand_token_ids_;
  std::vector<std::uint8_t> visible_hand_card_kinds_;
  std::unique_ptr<bool[]> player_mask_;
  std::unique_ptr<bool[]> hand_mask_;
  std::unique_ptr<bool[]> action_mask_;
};

} // namespace godfield_sim
