#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <vector>

#include "batch_types.h"

namespace godfield_sim {

inline constexpr std::uint32_t kKernelSchemaVersion = 2;
inline constexpr std::uint32_t kObservationSchemaVersion = 2;
inline constexpr const char *kRulesetId = "plain-attack-redraw-duel-v1";

class FixedAttackBatch final {
public:
  FixedAttackBatch(std::size_t batch_size, TokenInput token_ids,
                   AttackInput attack_values, std::uint64_t seed,
                   std::uint16_t initial_hp);

  [[nodiscard]] std::size_t batch_size() const noexcept { return batch_size_; }
  [[nodiscard]] std::uint64_t seed() const noexcept { return base_seed_; }
  [[nodiscard]] std::uint16_t initial_hp() const noexcept {
    return initial_hp_;
  }

  void reset();
  [[nodiscard]] std::size_t reset_done();
  void step(ActionInput actions);

  [[nodiscard]] Float2D global_features_view() const;
  [[nodiscard]] Float3D player_features_view() const;
  [[nodiscard]] Bool2D player_mask_view() const;
  [[nodiscard]] Int64_2D hand_token_ids_view() const;
  [[nodiscard]] Bool2D hand_mask_view() const;
  [[nodiscard]] Bool2D action_mask_view() const;
  [[nodiscard]] UInt8_1D active_players_view() const;
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
  void draw_into_slot(std::size_t environment, std::size_t player,
                      std::size_t slot);
  void reset_environment(std::size_t environment);
  void refresh_environment_views(std::size_t environment);

  std::size_t batch_size_;
  std::uint64_t base_seed_;
  std::uint16_t initial_hp_;
  std::vector<std::uint32_t> catalog_token_ids_;
  std::vector<std::uint16_t> catalog_attack_values_;
  std::vector<std::uint64_t> rng_states_;
  std::vector<std::uint64_t> episode_ids_;
  std::vector<std::uint16_t> hit_points_;
  std::vector<std::uint16_t> hand_attack_values_;
  std::vector<std::int64_t> hand_token_ids_by_player_;
  std::vector<std::uint8_t> active_players_;
  std::vector<std::uint16_t> turn_numbers_;
  std::unique_ptr<bool[]> terminated_;
  std::vector<float> terminal_returns_;

  std::vector<float> global_features_;
  std::vector<float> player_features_;
  std::vector<std::int64_t> visible_hand_token_ids_;
  std::unique_ptr<bool[]> player_mask_;
  std::unique_ptr<bool[]> hand_mask_;
  std::unique_ptr<bool[]> action_mask_;
};

} // namespace godfield_sim
