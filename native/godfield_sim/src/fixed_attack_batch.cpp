#include "fixed_attack_batch.h"

#include <algorithm>
#include <limits>
#include <stdexcept>
#include <string>

namespace godfield_sim {

namespace {

constexpr std::uint64_t kSplitMixIncrement = 0x9E3779B97F4A7C15ULL;

std::uint64_t mix64(std::uint64_t value) noexcept {
  value = (value ^ (value >> 30U)) * 0xBF58476D1CE4E5B9ULL;
  value = (value ^ (value >> 27U)) * 0x94D049BB133111EBULL;
  return value ^ (value >> 31U);
}

float normalized(std::uint16_t value) noexcept {
  return static_cast<float>(std::min<std::uint16_t>(value, 100U)) / 100.0F;
}

} // namespace

FixedAttackBatch::FixedAttackBatch(std::size_t batch_size, TokenInput token_ids,
                                   AttackInput attack_values,
                                   std::uint64_t seed, std::uint16_t initial_hp)
    : batch_size_(batch_size), base_seed_(seed), initial_hp_(initial_hp) {
  if (batch_size_ == 0 || batch_size_ > kMaximumBatchSize) {
    throw std::invalid_argument("batch_size must be between 1 and 1000000");
  }
  if (initial_hp_ == 0 || initial_hp_ > 100) {
    throw std::invalid_argument("initial_hp must be between 1 and 100");
  }
  if (token_ids.shape(0) == 0 || token_ids.shape(0) != attack_values.shape(0)) {
    throw std::invalid_argument(
        "token_ids and attack_values must be aligned and non-empty");
  }

  terminated_ = std::make_unique<bool[]>(batch_size_);
  player_mask_ = std::make_unique<bool[]>(batch_size_ * kPlayerCount);
  hand_mask_ = std::make_unique<bool[]>(batch_size_ * kHandSlots);
  action_mask_ = std::make_unique<bool[]>(batch_size_ * kActionCount);

  catalog_token_ids_.reserve(token_ids.shape(0));
  catalog_attack_values_.reserve(attack_values.shape(0));
  for (std::size_t index = 0; index < token_ids.shape(0); ++index) {
    const auto token_id = token_ids(index);
    const auto attack_value = attack_values(index);
    if (token_id < 2U) {
      throw std::invalid_argument(
          "catalog token IDs must exclude PAD and UNKNOWN");
    }
    if (attack_value == 0U || attack_value > 100U) {
      throw std::invalid_argument(
          "catalog attack values must be between 1 and 100");
    }
    catalog_token_ids_.push_back(token_id);
    catalog_attack_values_.push_back(attack_value);
  }

  rng_states_.resize(batch_size_);
  episode_ids_.assign(batch_size_, 0U);
  hit_points_.resize(batch_size_ * kPlayerCount);
  hand_attack_values_.resize(batch_size_ * kPlayerCount * kHandSlots);
  hand_token_ids_by_player_.resize(batch_size_ * kPlayerCount * kHandSlots);
  active_players_.resize(batch_size_);
  turn_numbers_.resize(batch_size_);
  terminal_returns_.resize(batch_size_ * kPlayerCount);
  global_features_.resize(batch_size_ * kGlobalFeatureCount);
  player_features_.resize(batch_size_ * kPlayerCount * kPlayerFeatureCount);
  visible_hand_token_ids_.resize(batch_size_ * kHandSlots);

  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    rng_states_[environment] =
        mix64(base_seed_ +
              static_cast<std::uint64_t>(environment) * kSplitMixIncrement);
  }
  reset();
}

std::size_t FixedAttackBatch::hand_offset(std::size_t environment,
                                          std::size_t player,
                                          std::size_t slot) const noexcept {
  return (environment * kPlayerCount + player) * kHandSlots + slot;
}

std::uint64_t FixedAttackBatch::next_random(std::size_t environment) noexcept {
  rng_states_[environment] += kSplitMixIncrement;
  return mix64(rng_states_[environment]);
}

void FixedAttackBatch::draw_into_slot(std::size_t environment,
                                      std::size_t player, std::size_t slot) {
  const auto catalog_size =
      static_cast<std::uint64_t>(catalog_token_ids_.size());
  const auto catalog_index =
      static_cast<std::size_t>(next_random(environment) % catalog_size);
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(catalog_token_ids_[catalog_index]);
  hand_attack_values_[offset] = catalog_attack_values_[catalog_index];
}

void FixedAttackBatch::reset_environment(std::size_t environment) {
  ++episode_ids_[environment];
  hit_points_[environment * kPlayerCount] = initial_hp_;
  hit_points_[environment * kPlayerCount + 1U] = initial_hp_;
  active_players_[environment] =
      static_cast<std::uint8_t>(next_random(environment) & 1U);
  turn_numbers_[environment] = 0U;
  terminated_[environment] = false;
  terminal_returns_[environment * kPlayerCount] = 0.0F;
  terminal_returns_[environment * kPlayerCount + 1U] = 0.0F;

  for (std::size_t player = 0; player < kPlayerCount; ++player) {
    for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
      draw_into_slot(environment, player, slot);
    }
  }
  refresh_environment_views(environment);
}

void FixedAttackBatch::reset() {
  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    reset_environment(environment);
  }
}

std::size_t FixedAttackBatch::reset_done() {
  std::size_t reset_count = 0;
  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    if (terminated_[environment]) {
      reset_environment(environment);
      ++reset_count;
    }
  }
  return reset_count;
}

void FixedAttackBatch::step(ActionInput actions) {
  if (actions.shape(0) != batch_size_) {
    throw std::invalid_argument("actions length must equal batch_size");
  }

  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    if (terminated_[environment]) {
      throw std::runtime_error("environment " + std::to_string(environment) +
                               " is terminal; call reset_done before step");
    }
    const auto action = actions(environment);
    if (action < 1 || action > static_cast<std::int64_t>(kHandSlots)) {
      throw std::invalid_argument(
          "environment " + std::to_string(environment) +
          " selected an action outside the slot macro range");
    }
    const auto action_index = static_cast<std::size_t>(action);
    if (!action_mask_[environment * kActionCount + action_index]) {
      throw std::invalid_argument("environment " + std::to_string(environment) +
                                  " selected a masked action");
    }
  }

  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    const auto action_index = static_cast<std::size_t>(actions(environment));
    const auto actor = static_cast<std::size_t>(active_players_[environment]);
    const auto opponent = 1U - actor;
    const auto slot = action_index - 1U;
    const auto card_offset = hand_offset(environment, actor, slot);
    const auto attack = hand_attack_values_[card_offset];
    hand_attack_values_[card_offset] = 0U;
    hand_token_ids_by_player_[card_offset] = 0;

    auto &opponent_hp = hit_points_[environment * kPlayerCount + opponent];
    opponent_hp = attack >= opponent_hp
                      ? 0U
                      : static_cast<std::uint16_t>(opponent_hp - attack);
    ++turn_numbers_[environment];

    if (opponent_hp == 0U) {
      terminated_[environment] = true;
      terminal_returns_[environment * kPlayerCount + actor] = 1.0F;
      terminal_returns_[environment * kPlayerCount + opponent] = -1.0F;
    } else {
      draw_into_slot(environment, actor, slot);
      active_players_[environment] = static_cast<std::uint8_t>(opponent);
    }
    refresh_environment_views(environment);
  }
}

void FixedAttackBatch::refresh_environment_views(std::size_t environment) {
  const auto perspective =
      static_cast<std::size_t>(active_players_[environment]);
  const auto opponent = 1U - perspective;
  const auto global_offset = environment * kGlobalFeatureCount;
  global_features_[global_offset] = normalized(turn_numbers_[environment]);
  global_features_[global_offset + 1U] =
      normalized(hit_points_[environment * kPlayerCount + perspective]);
  global_features_[global_offset + 2U] = 0.0F;
  global_features_[global_offset + 3U] = 0.0F;

  const auto player_offset = environment * kPlayerCount * kPlayerFeatureCount;
  const std::size_t ordered_players[kPlayerCount] = {perspective, opponent};
  for (std::size_t row = 0; row < kPlayerCount; ++row) {
    const auto output = player_offset + row * kPlayerFeatureCount;
    player_features_[output] = normalized(
        hit_points_[environment * kPlayerCount + ordered_players[row]]);
    player_features_[output + 1U] = 0.0F;
    player_features_[output + 2U] = 0.0F;
    player_features_[output + 3U] = row == 0U ? 1.0F : 0.0F;
    player_mask_[environment * kPlayerCount + row] = true;
  }

  const auto visible_hand_offset = environment * kHandSlots;
  for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
    const auto token =
        hand_token_ids_by_player_[hand_offset(environment, perspective, slot)];
    visible_hand_token_ids_[visible_hand_offset + slot] = token;
    hand_mask_[visible_hand_offset + slot] = token != 0;
  }

  const auto action_offset = environment * kActionCount;
  std::fill_n(action_mask_.get() + action_offset, kActionCount, false);
  if (!terminated_[environment]) {
    for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
      action_mask_[action_offset + slot + 1U] =
          hand_mask_[visible_hand_offset + slot];
    }
  }
}

FixedAttackBatch::Float2D FixedAttackBatch::global_features_view() const {
  return Float2D(global_features_.data(), {batch_size_, kGlobalFeatureCount});
}

FixedAttackBatch::Float3D FixedAttackBatch::player_features_view() const {
  return Float3D(player_features_.data(),
                 {batch_size_, kPlayerCount, kPlayerFeatureCount});
}

FixedAttackBatch::Bool2D FixedAttackBatch::player_mask_view() const {
  return Bool2D(player_mask_.get(), {batch_size_, kPlayerCount});
}

FixedAttackBatch::Int64_2D FixedAttackBatch::hand_token_ids_view() const {
  return Int64_2D(visible_hand_token_ids_.data(), {batch_size_, kHandSlots});
}

FixedAttackBatch::Bool2D FixedAttackBatch::hand_mask_view() const {
  return Bool2D(hand_mask_.get(), {batch_size_, kHandSlots});
}

FixedAttackBatch::Bool2D FixedAttackBatch::action_mask_view() const {
  return Bool2D(action_mask_.get(), {batch_size_, kActionCount});
}

FixedAttackBatch::UInt8_1D FixedAttackBatch::active_players_view() const {
  return UInt8_1D(active_players_.data(), {batch_size_});
}

FixedAttackBatch::Float2D FixedAttackBatch::terminal_returns_view() const {
  return Float2D(terminal_returns_.data(), {batch_size_, kPlayerCount});
}

FixedAttackBatch::Bool1D FixedAttackBatch::terminated_view() const {
  return Bool1D(terminated_.get(), {batch_size_});
}

FixedAttackBatch::UInt64_1D FixedAttackBatch::episode_ids_view() const {
  return UInt64_1D(episode_ids_.data(), {batch_size_});
}

FixedAttackBatch::UInt16_1D FixedAttackBatch::turn_numbers_view() const {
  return UInt16_1D(turn_numbers_.data(), {batch_size_});
}

} // namespace godfield_sim
