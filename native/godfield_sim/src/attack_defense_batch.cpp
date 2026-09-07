#include "attack_defense_batch.h"

#include <algorithm>
#include <array>
#include <stdexcept>
#include <string>
#include <unordered_set>

namespace godfield_sim {

namespace {

constexpr std::uint64_t kSplitMixIncrement = 0x9E3779B97F4A7C15ULL;
constexpr std::uint8_t kWeaponCardKind = 1U;
constexpr std::uint8_t kArmorCardKind = 2U;

std::uint64_t mix64(std::uint64_t value) noexcept {
  value = (value ^ (value >> 30U)) * 0xBF58476D1CE4E5B9ULL;
  value = (value ^ (value >> 27U)) * 0x94D049BB133111EBULL;
  return value ^ (value >> 31U);
}

float normalized(std::uint16_t value) noexcept {
  return static_cast<float>(std::min<std::uint16_t>(value, 100U)) / 100.0F;
}

void append_catalog(TokenInput token_ids, ValueInput values,
                    const std::string &catalog_name,
                    std::unordered_set<std::uint32_t> &unique_token_ids,
                    std::vector<std::uint32_t> &output_tokens,
                    std::vector<std::uint16_t> &output_values) {
  if (token_ids.shape(0) == 0 || token_ids.shape(0) != values.shape(0)) {
    throw std::invalid_argument(catalog_name +
                                " token IDs and values must be aligned and "
                                "non-empty");
  }
  output_tokens.reserve(token_ids.shape(0));
  output_values.reserve(values.shape(0));
  for (std::size_t index = 0; index < token_ids.shape(0); ++index) {
    const auto token_id = token_ids(index);
    const auto value = values(index);
    if (token_id < 2U) {
      throw std::invalid_argument(
          "catalog token IDs must exclude PAD and UNKNOWN");
    }
    if (value == 0U || value > 100U) {
      throw std::invalid_argument(catalog_name +
                                  " values must be between 1 and 100");
    }
    if (!unique_token_ids.insert(token_id).second) {
      throw std::invalid_argument(
          "weapon and armor catalog token IDs must be unique");
    }
    output_tokens.push_back(token_id);
    output_values.push_back(value);
  }
}

} // namespace

AttackDefenseBatch::AttackDefenseBatch(
    std::size_t batch_size, TokenInput weapon_token_ids,
    ValueInput attack_values, TokenInput armor_token_ids,
    ValueInput defense_values, std::uint64_t seed, std::uint16_t initial_hp,
    bool mixed_hands)
    : batch_size_(batch_size), base_seed_(seed), initial_hp_(initial_hp),
      mixed_hands_(mixed_hands) {
  if (batch_size_ == 0 || batch_size_ > kMaximumBatchSize) {
    throw std::invalid_argument("batch_size must be between 1 and 1000000");
  }
  if (initial_hp_ == 0 || initial_hp_ > 100) {
    throw std::invalid_argument("initial_hp must be between 1 and 100");
  }

  std::unordered_set<std::uint32_t> unique_token_ids;
  unique_token_ids.reserve(weapon_token_ids.shape(0) +
                           armor_token_ids.shape(0));
  append_catalog(weapon_token_ids, attack_values, "attack", unique_token_ids,
                 weapon_token_ids_, attack_values_);
  append_catalog(armor_token_ids, defense_values, "defense", unique_token_ids,
                 armor_token_ids_, defense_values_);

  terminated_ = std::make_unique<bool[]>(batch_size_);
  player_mask_ = std::make_unique<bool[]>(batch_size_ * kPlayerCount);
  hand_mask_ = std::make_unique<bool[]>(batch_size_ * kHandSlots);
  action_mask_ = std::make_unique<bool[]>(batch_size_ * kActionCount);
  rng_states_.resize(batch_size_);
  episode_ids_.assign(batch_size_, 0U);
  hit_points_.resize(batch_size_ * kPlayerCount);
  hand_values_.resize(batch_size_ * kPlayerCount * kHandSlots);
  hand_token_ids_by_player_.resize(batch_size_ * kPlayerCount * kHandSlots);
  hand_card_kinds_by_player_.resize(batch_size_ * kPlayerCount * kHandSlots);
  active_players_.resize(batch_size_);
  phases_.resize(batch_size_);
  pending_attackers_.resize(batch_size_);
  pending_attacks_.resize(batch_size_);
  turn_numbers_.resize(batch_size_);
  terminal_returns_.resize(batch_size_ * kPlayerCount);
  global_features_.resize(batch_size_ * kGlobalFeatureCount);
  player_features_.resize(batch_size_ * kPlayerCount * kPlayerFeatureCount);
  visible_hand_token_ids_.resize(batch_size_ * kHandSlots);
  visible_hand_card_kinds_.resize(batch_size_ * kHandSlots);

  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    rng_states_[environment] =
        mix64(base_seed_ +
              static_cast<std::uint64_t>(environment) * kSplitMixIncrement);
  }
  reset();
}

std::size_t AttackDefenseBatch::hand_offset(std::size_t environment,
                                            std::size_t player,
                                            std::size_t slot) const noexcept {
  return (environment * kPlayerCount + player) * kHandSlots + slot;
}

std::uint64_t
AttackDefenseBatch::next_random(std::size_t environment) noexcept {
  rng_states_[environment] += kSplitMixIncrement;
  return mix64(rng_states_[environment]);
}

void AttackDefenseBatch::draw_weapon(std::size_t environment,
                                     std::size_t player, std::size_t slot) {
  const auto catalog_index = static_cast<std::size_t>(
      next_random(environment) %
      static_cast<std::uint64_t>(weapon_token_ids_.size()));
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(weapon_token_ids_[catalog_index]);
  hand_values_[offset] = attack_values_[catalog_index];
  hand_card_kinds_by_player_[offset] = kWeaponCardKind;
}

void AttackDefenseBatch::draw_armor(std::size_t environment, std::size_t player,
                                    std::size_t slot) {
  const auto catalog_index = static_cast<std::size_t>(
      next_random(environment) %
      static_cast<std::uint64_t>(armor_token_ids_.size()));
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(armor_token_ids_[catalog_index]);
  hand_values_[offset] = defense_values_[catalog_index];
  hand_card_kinds_by_player_[offset] = kArmorCardKind;
}

void AttackDefenseBatch::draw_mixed(std::size_t environment, std::size_t player,
                                    std::size_t slot) {
  const auto catalog_size = weapon_token_ids_.size() + armor_token_ids_.size();
  const auto catalog_index = static_cast<std::size_t>(
      next_random(environment) % static_cast<std::uint64_t>(catalog_size));
  const auto offset = hand_offset(environment, player, slot);
  if (catalog_index < weapon_token_ids_.size()) {
    hand_token_ids_by_player_[offset] =
        static_cast<std::int64_t>(weapon_token_ids_[catalog_index]);
    hand_values_[offset] = attack_values_[catalog_index];
    hand_card_kinds_by_player_[offset] = kWeaponCardKind;
    return;
  }
  const auto armor_index = catalog_index - weapon_token_ids_.size();
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(armor_token_ids_[armor_index]);
  hand_values_[offset] = defense_values_[armor_index];
  hand_card_kinds_by_player_[offset] = kArmorCardKind;
}

bool AttackDefenseBatch::has_weapon(std::size_t environment,
                                    std::size_t player) const noexcept {
  for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
    if (hand_card_kinds_by_player_[hand_offset(environment, player, slot)] ==
        kWeaponCardKind) {
      return true;
    }
  }
  return false;
}

void AttackDefenseBatch::redraw_consumed(std::size_t environment,
                                         std::size_t player, std::size_t slot,
                                         std::uint8_t consumed_kind) {
  if (!mixed_hands_) {
    if (consumed_kind == kWeaponCardKind) {
      draw_weapon(environment, player, slot);
    } else {
      draw_armor(environment, player, slot);
    }
    return;
  }
  draw_mixed(environment, player, slot);
  if (!has_weapon(environment, player)) {
    draw_weapon(environment, player, slot);
  }
}

void AttackDefenseBatch::reset_environment(std::size_t environment) {
  ++episode_ids_[environment];
  hit_points_[environment * kPlayerCount] = initial_hp_;
  hit_points_[environment * kPlayerCount + 1U] = initial_hp_;
  active_players_[environment] =
      static_cast<std::uint8_t>(next_random(environment) & 1U);
  phases_[environment] = static_cast<std::uint8_t>(TurnPhase::Attack);
  pending_attackers_[environment] = active_players_[environment];
  pending_attacks_[environment] = 0U;
  turn_numbers_[environment] = 0U;
  terminated_[environment] = false;
  terminal_returns_[environment * kPlayerCount] = 0.0F;
  terminal_returns_[environment * kPlayerCount + 1U] = 0.0F;

  for (std::size_t player = 0; player < kPlayerCount; ++player) {
    if (!mixed_hands_) {
      for (std::size_t slot = 0; slot < kWeaponSlots; ++slot) {
        draw_weapon(environment, player, slot);
      }
      for (std::size_t slot = kWeaponSlots; slot < kHandSlots; ++slot) {
        draw_armor(environment, player, slot);
      }
      continue;
    }

    std::array<std::uint8_t, kHandSlots> card_kinds{};
    std::fill_n(card_kinds.begin(), kWeaponSlots, kWeaponCardKind);
    std::fill(card_kinds.begin() + static_cast<std::ptrdiff_t>(kWeaponSlots),
              card_kinds.end(), kArmorCardKind);
    for (std::size_t remaining = kHandSlots; remaining > 1U; --remaining) {
      const auto swap_index = static_cast<std::size_t>(
          next_random(environment) % static_cast<std::uint64_t>(remaining));
      std::swap(card_kinds[remaining - 1U], card_kinds[swap_index]);
    }
    for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
      if (card_kinds[slot] == kWeaponCardKind) {
        draw_weapon(environment, player, slot);
      } else {
        draw_armor(environment, player, slot);
      }
    }
  }
  refresh_environment_views(environment);
}

void AttackDefenseBatch::reset() {
  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    reset_environment(environment);
  }
}

std::size_t AttackDefenseBatch::reset_done() {
  std::size_t reset_count = 0;
  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    if (terminated_[environment]) {
      reset_environment(environment);
      ++reset_count;
    }
  }
  return reset_count;
}

void AttackDefenseBatch::step(ActionInput actions) {
  if (actions.shape(0) != batch_size_) {
    throw std::invalid_argument("actions length must equal batch_size");
  }

  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    if (terminated_[environment]) {
      throw std::runtime_error("environment " + std::to_string(environment) +
                               " is terminal; call reset_done before step");
    }
    const auto action = actions(environment);
    if (action < 0 || action >= static_cast<std::int64_t>(kActionCount)) {
      throw std::invalid_argument(
          "environment " + std::to_string(environment) +
          " selected an action outside the action head");
    }
    if (!action_mask_[environment * kActionCount +
                      static_cast<std::size_t>(action)]) {
      throw std::invalid_argument("environment " + std::to_string(environment) +
                                  " selected a masked action");
    }
  }

  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    const auto action = static_cast<std::size_t>(actions(environment));
    const auto actor = static_cast<std::size_t>(active_players_[environment]);
    const auto phase = static_cast<TurnPhase>(phases_[environment]);
    if (phase == TurnPhase::Attack) {
      const auto slot = action - 1U;
      const auto card_offset = hand_offset(environment, actor, slot);
      const auto consumed_kind = hand_card_kinds_by_player_[card_offset];
      pending_attackers_[environment] = static_cast<std::uint8_t>(actor);
      pending_attacks_[environment] = hand_values_[card_offset];
      redraw_consumed(environment, actor, slot, consumed_kind);
      active_players_[environment] = static_cast<std::uint8_t>(1U - actor);
      phases_[environment] = static_cast<std::uint8_t>(TurnPhase::Defense);
    } else {
      std::uint16_t defense = 0U;
      if (action != kForgiveActionIndex) {
        const auto slot = action - 1U;
        const auto card_offset = hand_offset(environment, actor, slot);
        defense = hand_values_[card_offset];
        const auto consumed_kind = hand_card_kinds_by_player_[card_offset];
        redraw_consumed(environment, actor, slot, consumed_kind);
      }

      const auto attack = pending_attacks_[environment];
      const auto damage =
          attack > defense ? static_cast<std::uint16_t>(attack - defense) : 0U;
      auto &defender_hp = hit_points_[environment * kPlayerCount + actor];
      defender_hp = damage >= defender_hp
                        ? 0U
                        : static_cast<std::uint16_t>(defender_hp - damage);
      ++turn_numbers_[environment];

      if (defender_hp == 0U) {
        const auto attacker =
            static_cast<std::size_t>(pending_attackers_[environment]);
        terminated_[environment] = true;
        phases_[environment] = static_cast<std::uint8_t>(TurnPhase::Terminal);
        terminal_returns_[environment * kPlayerCount + attacker] = 1.0F;
        terminal_returns_[environment * kPlayerCount + actor] = -1.0F;
      } else {
        pending_attacks_[environment] = 0U;
        phases_[environment] = static_cast<std::uint8_t>(TurnPhase::Attack);
      }
    }
    refresh_environment_views(environment);
  }
}

void AttackDefenseBatch::refresh_environment_views(std::size_t environment) {
  const auto perspective =
      static_cast<std::size_t>(active_players_[environment]);
  const auto opponent = 1U - perspective;
  const auto global_offset = environment * kGlobalFeatureCount;
  global_features_[global_offset] = normalized(turn_numbers_[environment]);
  global_features_[global_offset + 1U] =
      normalized(hit_points_[environment * kPlayerCount + perspective]);
  global_features_[global_offset + 2U] = 0.0F;
  global_features_[global_offset + 3U] = 0.0F;
  const auto phase = static_cast<TurnPhase>(phases_[environment]);
  global_features_[global_offset + 4U] =
      phase == TurnPhase::Defense ? 1.0F : 0.0F;
  global_features_[global_offset + 5U] =
      normalized(pending_attacks_[environment]);

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
    visible_hand_card_kinds_[visible_hand_offset + slot] =
        hand_card_kinds_by_player_[hand_offset(environment, perspective, slot)];
  }

  const auto action_offset = environment * kActionCount;
  std::fill_n(action_mask_.get() + action_offset, kActionCount, false);
  if (terminated_[environment]) {
    return;
  }
  if (static_cast<TurnPhase>(phases_[environment]) == TurnPhase::Attack) {
    for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
      action_mask_[action_offset + slot + 1U] =
          hand_card_kinds_by_player_[hand_offset(environment, perspective,
                                                 slot)] == kWeaponCardKind;
    }
    return;
  }
  action_mask_[action_offset + kForgiveActionIndex] = true;
  for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
    action_mask_[action_offset + slot + 1U] =
        hand_card_kinds_by_player_[hand_offset(environment, perspective,
                                               slot)] == kArmorCardKind;
  }
}

Float2D AttackDefenseBatch::global_features_view() const {
  return Float2D(global_features_.data(), {batch_size_, kGlobalFeatureCount});
}

Float3D AttackDefenseBatch::player_features_view() const {
  return Float3D(player_features_.data(),
                 {batch_size_, kPlayerCount, kPlayerFeatureCount});
}

Bool2D AttackDefenseBatch::player_mask_view() const {
  return Bool2D(player_mask_.get(), {batch_size_, kPlayerCount});
}

Int64_2D AttackDefenseBatch::hand_token_ids_view() const {
  return Int64_2D(visible_hand_token_ids_.data(), {batch_size_, kHandSlots});
}

Bool2D AttackDefenseBatch::hand_mask_view() const {
  return Bool2D(hand_mask_.get(), {batch_size_, kHandSlots});
}

UInt8_2D AttackDefenseBatch::hand_card_kinds_view() const {
  return UInt8_2D(visible_hand_card_kinds_.data(), {batch_size_, kHandSlots});
}

Bool2D AttackDefenseBatch::action_mask_view() const {
  return Bool2D(action_mask_.get(), {batch_size_, kActionCount});
}

UInt8_1D AttackDefenseBatch::active_players_view() const {
  return UInt8_1D(active_players_.data(), {batch_size_});
}

UInt8_1D AttackDefenseBatch::phases_view() const {
  return UInt8_1D(phases_.data(), {batch_size_});
}

UInt16_1D AttackDefenseBatch::pending_attacks_view() const {
  return UInt16_1D(pending_attacks_.data(), {batch_size_});
}

Float2D AttackDefenseBatch::terminal_returns_view() const {
  return Float2D(terminal_returns_.data(), {batch_size_, kPlayerCount});
}

Bool1D AttackDefenseBatch::terminated_view() const {
  return Bool1D(terminated_.get(), {batch_size_});
}

UInt64_1D AttackDefenseBatch::episode_ids_view() const {
  return UInt64_1D(episode_ids_.data(), {batch_size_});
}

UInt16_1D AttackDefenseBatch::turn_numbers_view() const {
  return UInt16_1D(turn_numbers_.data(), {batch_size_});
}

} // namespace godfield_sim
