#include "attack_defense_batch.h"

#include <algorithm>
#include <array>
#include <iterator>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>

namespace godfield_sim {

namespace {

constexpr std::uint64_t kSplitMixIncrement = 0x9E3779B97F4A7C15ULL;
constexpr std::uint8_t kWeaponCardKind = 1U;
constexpr std::uint8_t kArmorCardKind = 2U;
constexpr std::uint8_t kAttackBoosterCardKind = 3U;
constexpr std::uint8_t kHpUtilityCardKind = 4U;
constexpr std::uint8_t kMpUtilityCardKind = 5U;
constexpr std::uint8_t kAttackMiracleCardKind = 6U;
constexpr std::uint8_t kHpMiracleCardKind = 7U;
constexpr std::uint8_t kChanceAttackMiracleCardKind = 8U;
constexpr std::uint8_t kEffectAttackMiracleCardKind = 9U;
constexpr std::uint8_t kAdditiveMiracleCardKind = 10U;
constexpr std::uint8_t kReflectionArmorCardKind = 11U;
constexpr std::uint8_t kReflectionWeaponCardKind = 12U;
constexpr std::uint8_t kDualRoleCardKind = 13U;
constexpr std::uint8_t kChanceWeaponCardKind = 14U;
constexpr std::uint8_t kChanceDualRoleCardKind = 15U;
constexpr std::uint8_t kNoAttackEffect = 0U;
constexpr std::uint8_t kAbsorbHpAttackEffect = 1U;
constexpr std::uint16_t kMaximumResource = 100U;

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
          "weapon and armor catalog token IDs must be unique across all card "
          "catalogs");
    }
    output_tokens.push_back(token_id);
    output_values.push_back(value);
  }
}

void append_token_catalog(TokenInput token_ids, const std::string &catalog_name,
                          std::unordered_set<std::uint32_t> &unique_token_ids,
                          std::vector<std::uint32_t> &output_tokens) {
  if (token_ids.shape(0) == 0) {
    throw std::invalid_argument(catalog_name + " token IDs must be non-empty");
  }
  output_tokens.reserve(token_ids.shape(0));
  for (std::size_t index = 0; index < token_ids.shape(0); ++index) {
    const auto token_id = token_ids(index);
    if (token_id < 2U) {
      throw std::invalid_argument(
          "catalog token IDs must exclude PAD and UNKNOWN");
    }
    if (!unique_token_ids.insert(token_id).second) {
      throw std::invalid_argument(
          "weapon and armor catalog token IDs must be unique across all card "
          "catalogs");
    }
    output_tokens.push_back(token_id);
  }
}

std::vector<std::uint8_t> copy_elements(ElementInput elements,
                                        std::size_t expected_size,
                                        const std::string &catalog_name) {
  if (elements.shape(0) != expected_size) {
    throw std::invalid_argument(catalog_name +
                                " elements must align with its catalog");
  }
  std::vector<std::uint8_t> result;
  result.reserve(expected_size);
  for (std::size_t index = 0; index < expected_size; ++index) {
    const auto element = elements(index);
    if (element >= kElementCount) {
      throw std::invalid_argument(catalog_name +
                                  " contains an unknown element ID");
    }
    result.push_back(element);
  }
  return result;
}

std::vector<std::uint16_t> copy_costs(ValueInput costs,
                                      std::size_t expected_size,
                                      const std::string &catalog_name) {
  if (costs.shape(0) != expected_size) {
    throw std::invalid_argument(catalog_name +
                                " costs must align with its catalog");
  }
  std::vector<std::uint16_t> result;
  result.reserve(expected_size);
  for (std::size_t index = 0; index < expected_size; ++index) {
    const auto cost = costs(index);
    if (cost == 0U || cost > kMaximumResource) {
      throw std::invalid_argument(catalog_name +
                                  " costs must be between 1 and 100");
    }
    result.push_back(cost);
  }
  return result;
}

std::vector<std::uint16_t>
copy_hit_rates(ValueInput hit_rates, std::size_t expected_size,
               const std::string &catalog_name = "chance miracle") {
  if (hit_rates.shape(0) != expected_size) {
    throw std::invalid_argument(catalog_name +
                                " hit rates must align with its catalog");
  }
  std::vector<std::uint16_t> result;
  result.reserve(expected_size);
  for (std::size_t index = 0; index < expected_size; ++index) {
    const auto hit_rate = hit_rates(index);
    if (hit_rate == 0U || hit_rate > 100U) {
      throw std::invalid_argument(catalog_name +
                                  " hit rates must be between 1 and 100");
    }
    result.push_back(hit_rate);
  }
  return result;
}

} // namespace

AttackDefenseBatch::AttackDefenseBatch(
    std::size_t batch_size, TokenInput weapon_token_ids,
    ValueInput attack_values, TokenInput armor_token_ids,
    ValueInput defense_values, std::uint64_t seed, std::uint16_t initial_hp,
    bool mixed_hands)
    : AttackDefenseBatch(batch_size, weapon_token_ids, attack_values, {}, {},
                         {}, {}, armor_token_ids, defense_values, {}, seed,
                         initial_hp, mixed_hands, false, false, false) {}

AttackDefenseBatch::AttackDefenseBatch(
    std::size_t batch_size, TokenInput weapon_token_ids,
    ValueInput attack_values, std::vector<std::uint8_t> weapon_elements,
    TokenInput booster_token_ids, ValueInput booster_values,
    std::vector<std::uint8_t> booster_elements, TokenInput armor_token_ids,
    ValueInput defense_values, std::vector<std::uint8_t> armor_elements,
    std::uint64_t seed, std::uint16_t initial_hp, bool mixed_hands,
    bool elemental, bool combo, bool resource_curriculum,
    TokenInput hp_utility_token_ids, ValueInput hp_utility_values,
    TokenInput mp_utility_token_ids, ValueInput mp_utility_values,
    TokenInput attack_miracle_token_ids, ValueInput attack_miracle_values,
    ElementInput attack_miracle_elements, ValueInput attack_miracle_costs,
    TokenInput hp_miracle_token_ids, ValueInput hp_miracle_values,
    ValueInput hp_miracle_costs, std::uint16_t initial_mp,
    bool stochastic_resource_curriculum, TokenInput chance_miracle_token_ids,
    ValueInput chance_miracle_values, ElementInput chance_miracle_elements,
    ValueInput chance_miracle_costs, ValueInput chance_miracle_hit_rates,
    TokenInput effect_miracle_token_ids, ValueInput effect_miracle_values,
    ElementInput effect_miracle_elements, ValueInput effect_miracle_costs,
    bool additive_miracle_curriculum, TokenInput additive_miracle_token_ids,
    ValueInput additive_miracle_values, ElementInput additive_miracle_elements,
    ValueInput additive_miracle_costs, bool reflection_curriculum,
    TokenInput reflection_armor_token_ids, bool reflection_weapon_curriculum,
    TokenInput reflection_weapon_token_ids, ValueInput reflection_weapon_values,
    bool dual_role_curriculum, TokenInput dual_role_token_ids,
    ValueInput dual_role_attack_values, ValueInput dual_role_defense_values,
    ElementInput dual_role_elements, bool chance_weapon_curriculum,
    TokenInput chance_weapon_token_ids, ValueInput chance_weapon_attack_values,
    ElementInput chance_weapon_elements, ValueInput chance_weapon_hit_rates,
    TokenInput chance_dual_role_token_ids,
    ValueInput chance_dual_role_attack_values,
    ValueInput chance_dual_role_defense_values,
    ElementInput chance_dual_role_elements,
    ValueInput chance_dual_role_hit_rates)
    : batch_size_(batch_size), base_seed_(seed), initial_hp_(initial_hp),
      mixed_hands_(mixed_hands), elemental_(elemental), combo_(combo),
      resource_curriculum_(resource_curriculum),
      stochastic_resource_curriculum_(stochastic_resource_curriculum),
      additive_miracle_curriculum_(additive_miracle_curriculum),
      reflection_curriculum_(reflection_curriculum),
      reflection_weapon_curriculum_(reflection_weapon_curriculum),
      dual_role_curriculum_(dual_role_curriculum),
      chance_weapon_curriculum_(chance_weapon_curriculum),
      global_feature_count_(stochastic_resource_curriculum
                                ? kStochasticResourceGlobalFeatureCount
                                : (elemental ? kElementalGlobalFeatureCount
                                             : kGlobalFeatureCount)),
      initial_mp_(initial_mp) {
  if (batch_size_ == 0 || batch_size_ > kMaximumBatchSize) {
    throw std::invalid_argument("batch_size must be between 1 and 1000000");
  }
  if (initial_hp_ == 0 || initial_hp_ > 100) {
    throw std::invalid_argument("initial_hp must be between 1 and 100");
  }
  if (initial_mp_ > kMaximumResource) {
    throw std::invalid_argument("initial_mp must be between 0 and 100");
  }
  if (resource_curriculum_ && (!mixed_hands_ || !elemental_ || !combo_)) {
    throw std::invalid_argument(
        "resource curriculum requires mixed elemental combo semantics");
  }
  if (stochastic_resource_curriculum_ && !resource_curriculum_) {
    throw std::invalid_argument(
        "stochastic resource curriculum requires resource semantics");
  }
  if (additive_miracle_curriculum_ && !stochastic_resource_curriculum_) {
    throw std::invalid_argument(
        "additive miracle curriculum requires stochastic resource semantics");
  }
  if (reflection_curriculum_ && !additive_miracle_curriculum_) {
    throw std::invalid_argument(
        "reflection curriculum requires additive miracle semantics");
  }
  if (reflection_weapon_curriculum_ && !reflection_curriculum_) {
    throw std::invalid_argument(
        "reflection weapon curriculum requires reflection semantics");
  }
  if (dual_role_curriculum_ && !reflection_weapon_curriculum_) {
    throw std::invalid_argument(
        "dual-role curriculum requires reflection weapon semantics");
  }
  if (chance_weapon_curriculum_ && !dual_role_curriculum_) {
    throw std::invalid_argument(
        "chance weapon curriculum requires dual-role semantics");
  }

  std::unordered_set<std::uint32_t> unique_token_ids;
  const auto booster_catalog_size = combo_ ? booster_token_ids.shape(0) : 0U;
  const auto resource_catalog_size =
      resource_curriculum_
          ? hp_utility_token_ids.shape(0) + mp_utility_token_ids.shape(0) +
                attack_miracle_token_ids.shape(0) +
                hp_miracle_token_ids.shape(0)
          : 0U;
  const auto stochastic_catalog_size =
      stochastic_resource_curriculum_ ? chance_miracle_token_ids.shape(0) +
                                            effect_miracle_token_ids.shape(0)
                                      : 0U;
  const auto additive_catalog_size =
      additive_miracle_curriculum_ ? additive_miracle_token_ids.shape(0) : 0U;
  const auto reflection_catalog_size =
      reflection_curriculum_ ? reflection_armor_token_ids.shape(0) : 0U;
  const auto reflection_weapon_catalog_size =
      reflection_weapon_curriculum_ ? reflection_weapon_token_ids.shape(0) : 0U;
  const auto dual_role_catalog_size =
      dual_role_curriculum_ ? dual_role_token_ids.shape(0) : 0U;
  const auto chance_weapon_catalog_size =
      chance_weapon_curriculum_ ? chance_weapon_token_ids.shape(0) +
                                      chance_dual_role_token_ids.shape(0)
                                : 0U;
  unique_token_ids.reserve(weapon_token_ids.shape(0) + booster_catalog_size +
                           armor_token_ids.shape(0) + resource_catalog_size +
                           stochastic_catalog_size + additive_catalog_size +
                           reflection_catalog_size +
                           reflection_weapon_catalog_size +
                           dual_role_catalog_size + chance_weapon_catalog_size);
  append_catalog(weapon_token_ids, attack_values, "attack", unique_token_ids,
                 weapon_token_ids_, attack_values_);
  if (combo_) {
    append_catalog(booster_token_ids, booster_values, "attack booster",
                   unique_token_ids, booster_token_ids_, booster_values_);
  }
  append_catalog(armor_token_ids, defense_values, "defense", unique_token_ids,
                 armor_token_ids_, defense_values_);
  if (resource_curriculum_) {
    append_catalog(hp_utility_token_ids, hp_utility_values, "HP utility",
                   unique_token_ids, hp_utility_token_ids_, hp_utility_values_);
    append_catalog(mp_utility_token_ids, mp_utility_values, "MP utility",
                   unique_token_ids, mp_utility_token_ids_, mp_utility_values_);
    append_catalog(attack_miracle_token_ids, attack_miracle_values,
                   "attack miracle", unique_token_ids,
                   attack_miracle_token_ids_, attack_miracle_values_);
    append_catalog(hp_miracle_token_ids, hp_miracle_values, "HP miracle",
                   unique_token_ids, hp_miracle_token_ids_, hp_miracle_values_);
    attack_miracle_elements_ =
        copy_elements(attack_miracle_elements, attack_miracle_token_ids_.size(),
                      "attack miracle");
    attack_miracle_costs_ =
        copy_costs(attack_miracle_costs, attack_miracle_token_ids_.size(),
                   "attack miracle");
    hp_miracle_costs_ = copy_costs(hp_miracle_costs,
                                   hp_miracle_token_ids_.size(), "HP miracle");
    if (stochastic_resource_curriculum_) {
      append_catalog(chance_miracle_token_ids, chance_miracle_values,
                     "chance attack miracle", unique_token_ids,
                     chance_miracle_token_ids_, chance_miracle_values_);
      chance_miracle_elements_ = copy_elements(chance_miracle_elements,
                                               chance_miracle_token_ids_.size(),
                                               "chance attack miracle");
      chance_miracle_costs_ =
          copy_costs(chance_miracle_costs, chance_miracle_token_ids_.size(),
                     "chance attack miracle");
      chance_miracle_hit_rates_ = copy_hit_rates(
          chance_miracle_hit_rates, chance_miracle_token_ids_.size());
      append_catalog(effect_miracle_token_ids, effect_miracle_values,
                     "effect attack miracle", unique_token_ids,
                     effect_miracle_token_ids_, effect_miracle_values_);
      effect_miracle_elements_ = copy_elements(effect_miracle_elements,
                                               effect_miracle_token_ids_.size(),
                                               "effect attack miracle");
      effect_miracle_costs_ =
          copy_costs(effect_miracle_costs, effect_miracle_token_ids_.size(),
                     "effect attack miracle");
      if (additive_miracle_curriculum_) {
        append_catalog(additive_miracle_token_ids, additive_miracle_values,
                       "additive attack miracle", unique_token_ids,
                       additive_miracle_token_ids_, additive_miracle_values_);
        additive_miracle_elements_ = copy_elements(
            additive_miracle_elements, additive_miracle_token_ids_.size(),
            "additive attack miracle");
        additive_miracle_costs_ = copy_costs(additive_miracle_costs,
                                             additive_miracle_token_ids_.size(),
                                             "additive attack miracle");
        if (reflection_curriculum_) {
          append_token_catalog(reflection_armor_token_ids, "reflection armor",
                               unique_token_ids, reflection_armor_token_ids_);
          if (reflection_weapon_curriculum_) {
            append_catalog(reflection_weapon_token_ids,
                           reflection_weapon_values, "reflection weapon",
                           unique_token_ids, reflection_weapon_token_ids_,
                           reflection_weapon_values_);
            if (dual_role_curriculum_) {
              append_catalog(dual_role_token_ids, dual_role_attack_values,
                             "dual-role attack", unique_token_ids,
                             dual_role_token_ids_, dual_role_attack_values_);
              if (dual_role_defense_values.shape(0) !=
                  dual_role_token_ids_.size()) {
                throw std::invalid_argument(
                    "dual-role defense values must align with its catalog");
              }
              dual_role_defense_values_.reserve(dual_role_token_ids_.size());
              for (std::size_t index = 0; index < dual_role_token_ids_.size();
                   ++index) {
                const auto defense = dual_role_defense_values(index);
                if (defense == 0U || defense > 100U) {
                  throw std::invalid_argument(
                      "dual-role defense values must be between 1 and 100");
                }
                dual_role_defense_values_.push_back(defense);
              }
              dual_role_elements_ =
                  copy_elements(dual_role_elements, dual_role_token_ids_.size(),
                                "dual-role weapon");
              if (chance_weapon_curriculum_) {
                append_catalog(chance_weapon_token_ids,
                               chance_weapon_attack_values, "chance weapon",
                               unique_token_ids, chance_weapon_token_ids_,
                               chance_weapon_attack_values_);
                chance_weapon_elements_ = copy_elements(
                    chance_weapon_elements, chance_weapon_token_ids_.size(),
                    "chance weapon");
                chance_weapon_hit_rates_ = copy_hit_rates(
                    chance_weapon_hit_rates, chance_weapon_token_ids_.size(),
                    "chance weapon");
                append_catalog(chance_dual_role_token_ids,
                               chance_dual_role_attack_values,
                               "chance dual-role attack", unique_token_ids,
                               chance_dual_role_token_ids_,
                               chance_dual_role_attack_values_);
                if (chance_dual_role_defense_values.shape(0) !=
                    chance_dual_role_token_ids_.size()) {
                  throw std::invalid_argument(
                      "chance dual-role defense values must align with its "
                      "catalog");
                }
                chance_dual_role_defense_values_.reserve(
                    chance_dual_role_token_ids_.size());
                for (std::size_t index = 0;
                     index < chance_dual_role_token_ids_.size(); ++index) {
                  const auto defense = chance_dual_role_defense_values(index);
                  if (defense == 0U || defense > 100U) {
                    throw std::invalid_argument(
                        "chance dual-role defense values must be between 1 and "
                        "100");
                  }
                  chance_dual_role_defense_values_.push_back(defense);
                }
                chance_dual_role_elements_ =
                    copy_elements(chance_dual_role_elements,
                                  chance_dual_role_token_ids_.size(),
                                  "chance dual-role weapon");
                chance_dual_role_hit_rates_ =
                    copy_hit_rates(chance_dual_role_hit_rates,
                                   chance_dual_role_token_ids_.size(),
                                   "chance dual-role weapon");
              }
            }
          }
        }
      }
    }
  }
  if (elemental_) {
    if (weapon_elements.size() != weapon_token_ids_.size() ||
        booster_elements.size() != booster_token_ids_.size() ||
        armor_elements.size() != armor_token_ids_.size()) {
      throw std::invalid_argument(
          "element catalogs must align with card catalogs");
    }
    weapon_elements_ = std::move(weapon_elements);
    booster_elements_ = std::move(booster_elements);
    armor_elements_ = std::move(armor_elements);
  } else {
    weapon_elements_.assign(
        weapon_token_ids_.size(),
        static_cast<std::uint8_t>(CombatElement::NonElement));
    booster_elements_.assign(
        booster_token_ids_.size(),
        static_cast<std::uint8_t>(CombatElement::NonElement));
    armor_elements_.assign(
        armor_token_ids_.size(),
        static_cast<std::uint8_t>(CombatElement::NonElement));
  }

  terminated_ = std::make_unique<bool[]>(batch_size_);
  player_mask_ = std::make_unique<bool[]>(batch_size_ * kPlayerCount);
  hand_mask_ = std::make_unique<bool[]>(batch_size_ * kHandSlots);
  action_mask_ = std::make_unique<bool[]>(batch_size_ * kActionCount);
  selected_hand_mask_ = std::make_unique<bool[]>(batch_size_ * kHandSlots);
  pending_reflected_ = std::make_unique<bool[]>(batch_size_);
  rng_states_.resize(batch_size_);
  episode_ids_.assign(batch_size_, 0U);
  hit_points_.resize(batch_size_ * kPlayerCount);
  magic_points_.resize(batch_size_ * kPlayerCount);
  hand_values_.resize(batch_size_ * kPlayerCount * kHandSlots);
  hand_costs_.assign(batch_size_ * kPlayerCount * kHandSlots, 0U);
  hand_hit_rates_.assign(batch_size_ * kPlayerCount * kHandSlots, 100U);
  hand_effects_.assign(batch_size_ * kPlayerCount * kHandSlots,
                       kNoAttackEffect);
  hand_token_ids_by_player_.resize(batch_size_ * kPlayerCount * kHandSlots);
  hand_card_kinds_by_player_.resize(batch_size_ * kPlayerCount * kHandSlots);
  hand_elements_by_player_.resize(batch_size_ * kPlayerCount * kHandSlots);
  active_players_.resize(batch_size_);
  phases_.resize(batch_size_);
  pending_attackers_.resize(batch_size_);
  pending_attacks_.resize(batch_size_);
  pending_elements_.resize(batch_size_);
  pending_effects_.assign(batch_size_, kNoAttackEffect);
  pending_base_kinds_.resize(batch_size_);
  selected_counts_.resize(batch_size_);
  selected_values_.resize(batch_size_);
  selected_elements_.resize(batch_size_);
  selected_costs_.resize(batch_size_);
  selected_base_kinds_.resize(batch_size_);
  selected_hit_rates_.assign(batch_size_, 100U);
  selected_effects_.assign(batch_size_, kNoAttackEffect);
  turn_numbers_.resize(batch_size_);
  terminal_returns_.resize(batch_size_ * kPlayerCount);
  global_features_.resize(batch_size_ * global_feature_count_);
  player_features_.resize(batch_size_ * kPlayerCount * kPlayerFeatureCount);
  visible_hand_token_ids_.resize(batch_size_ * kHandSlots);
  visible_hand_card_kinds_.resize(batch_size_ * kHandSlots);
  visible_hand_elements_.resize(batch_size_ * kHandSlots);

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
  hand_costs_[offset] = 0U;
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kWeaponCardKind;
  hand_elements_by_player_[offset] = weapon_elements_[catalog_index];
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
  hand_costs_[offset] = 0U;
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kArmorCardKind;
  hand_elements_by_player_[offset] = armor_elements_[catalog_index];
}

void AttackDefenseBatch::draw_booster(std::size_t environment,
                                      std::size_t player, std::size_t slot) {
  const auto catalog_index = static_cast<std::size_t>(
      next_random(environment) %
      static_cast<std::uint64_t>(booster_token_ids_.size()));
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(booster_token_ids_[catalog_index]);
  hand_values_[offset] = booster_values_[catalog_index];
  hand_costs_[offset] = 0U;
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kAttackBoosterCardKind;
  hand_elements_by_player_[offset] = booster_elements_[catalog_index];
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
    hand_costs_[offset] = 0U;
    hand_hit_rates_[offset] = 100U;
    hand_effects_[offset] = kNoAttackEffect;
    hand_card_kinds_by_player_[offset] = kWeaponCardKind;
    hand_elements_by_player_[offset] = weapon_elements_[catalog_index];
    return;
  }
  const auto armor_index = catalog_index - weapon_token_ids_.size();
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(armor_token_ids_[armor_index]);
  hand_values_[offset] = defense_values_[armor_index];
  hand_costs_[offset] = 0U;
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kArmorCardKind;
  hand_elements_by_player_[offset] = armor_elements_[armor_index];
}

void AttackDefenseBatch::draw_combo(std::size_t environment, std::size_t player,
                                    std::size_t slot) {
  const auto catalog_size = weapon_token_ids_.size() +
                            booster_token_ids_.size() + armor_token_ids_.size();
  const auto catalog_index = static_cast<std::size_t>(
      next_random(environment) % static_cast<std::uint64_t>(catalog_size));
  if (catalog_index < weapon_token_ids_.size()) {
    draw_weapon(environment, player, slot);
    return;
  }
  if (catalog_index < weapon_token_ids_.size() + booster_token_ids_.size()) {
    draw_booster(environment, player, slot);
    return;
  }
  draw_armor(environment, player, slot);
}

void AttackDefenseBatch::draw_hp_utility(std::size_t environment,
                                         std::size_t player, std::size_t slot) {
  const auto index = static_cast<std::size_t>(next_random(environment) %
                                              hp_utility_token_ids_.size());
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(hp_utility_token_ids_[index]);
  hand_values_[offset] = hp_utility_values_[index];
  hand_costs_[offset] = 0U;
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kHpUtilityCardKind;
  hand_elements_by_player_[offset] =
      static_cast<std::uint8_t>(CombatElement::NonElement);
}

void AttackDefenseBatch::draw_mp_utility(std::size_t environment,
                                         std::size_t player, std::size_t slot) {
  const auto index = static_cast<std::size_t>(next_random(environment) %
                                              mp_utility_token_ids_.size());
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(mp_utility_token_ids_[index]);
  hand_values_[offset] = mp_utility_values_[index];
  hand_costs_[offset] = 0U;
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kMpUtilityCardKind;
  hand_elements_by_player_[offset] =
      static_cast<std::uint8_t>(CombatElement::NonElement);
}

void AttackDefenseBatch::draw_attack_miracle(std::size_t environment,
                                             std::size_t player,
                                             std::size_t slot) {
  const auto index = static_cast<std::size_t>(next_random(environment) %
                                              attack_miracle_token_ids_.size());
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(attack_miracle_token_ids_[index]);
  hand_values_[offset] = attack_miracle_values_[index];
  hand_costs_[offset] = attack_miracle_costs_[index];
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kAttackMiracleCardKind;
  hand_elements_by_player_[offset] = attack_miracle_elements_[index];
}

void AttackDefenseBatch::draw_hp_miracle(std::size_t environment,
                                         std::size_t player, std::size_t slot) {
  const auto index = static_cast<std::size_t>(next_random(environment) %
                                              hp_miracle_token_ids_.size());
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(hp_miracle_token_ids_[index]);
  hand_values_[offset] = hp_miracle_values_[index];
  hand_costs_[offset] = hp_miracle_costs_[index];
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kHpMiracleCardKind;
  hand_elements_by_player_[offset] =
      static_cast<std::uint8_t>(CombatElement::NonElement);
}

void AttackDefenseBatch::draw_chance_miracle(std::size_t environment,
                                             std::size_t player,
                                             std::size_t slot) {
  const auto index = static_cast<std::size_t>(next_random(environment) %
                                              chance_miracle_token_ids_.size());
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(chance_miracle_token_ids_[index]);
  hand_values_[offset] = chance_miracle_values_[index];
  hand_costs_[offset] = chance_miracle_costs_[index];
  hand_hit_rates_[offset] = chance_miracle_hit_rates_[index];
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kChanceAttackMiracleCardKind;
  hand_elements_by_player_[offset] = chance_miracle_elements_[index];
}

void AttackDefenseBatch::draw_effect_miracle(std::size_t environment,
                                             std::size_t player,
                                             std::size_t slot) {
  const auto index = static_cast<std::size_t>(next_random(environment) %
                                              effect_miracle_token_ids_.size());
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(effect_miracle_token_ids_[index]);
  hand_values_[offset] = effect_miracle_values_[index];
  hand_costs_[offset] = effect_miracle_costs_[index];
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kAbsorbHpAttackEffect;
  hand_card_kinds_by_player_[offset] = kEffectAttackMiracleCardKind;
  hand_elements_by_player_[offset] = effect_miracle_elements_[index];
}

void AttackDefenseBatch::draw_additive_miracle(std::size_t environment,
                                               std::size_t player,
                                               std::size_t slot) {
  const auto index = static_cast<std::size_t>(
      next_random(environment) % additive_miracle_token_ids_.size());
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(additive_miracle_token_ids_[index]);
  hand_values_[offset] = additive_miracle_values_[index];
  hand_costs_[offset] = additive_miracle_costs_[index];
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kAdditiveMiracleCardKind;
  hand_elements_by_player_[offset] = additive_miracle_elements_[index];
}

void AttackDefenseBatch::draw_reflection_armor(std::size_t environment,
                                               std::size_t player,
                                               std::size_t slot) {
  const auto index = static_cast<std::size_t>(
      next_random(environment) % reflection_armor_token_ids_.size());
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(reflection_armor_token_ids_[index]);
  hand_values_[offset] = 0U;
  hand_costs_[offset] = 0U;
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kReflectionArmorCardKind;
  hand_elements_by_player_[offset] =
      static_cast<std::uint8_t>(CombatElement::NonElement);
}

void AttackDefenseBatch::draw_reflection_weapon(std::size_t environment,
                                                std::size_t player,
                                                std::size_t slot) {
  const auto index = static_cast<std::size_t>(
      next_random(environment) % reflection_weapon_token_ids_.size());
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(reflection_weapon_token_ids_[index]);
  hand_values_[offset] = reflection_weapon_values_[index];
  hand_costs_[offset] = 0U;
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kReflectionWeaponCardKind;
  hand_elements_by_player_[offset] =
      static_cast<std::uint8_t>(CombatElement::NonElement);
}

void AttackDefenseBatch::draw_dual_role(std::size_t environment,
                                        std::size_t player, std::size_t slot) {
  const auto index = static_cast<std::size_t>(next_random(environment) %
                                              dual_role_token_ids_.size());
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(dual_role_token_ids_[index]);
  hand_values_[offset] = dual_role_attack_values_[index];
  hand_costs_[offset] = 0U;
  hand_hit_rates_[offset] = 100U;
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kDualRoleCardKind;
  hand_elements_by_player_[offset] = dual_role_elements_[index];
}

void AttackDefenseBatch::draw_chance_weapon(std::size_t environment,
                                            std::size_t player,
                                            std::size_t slot) {
  const auto index = static_cast<std::size_t>(next_random(environment) %
                                              chance_weapon_token_ids_.size());
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(chance_weapon_token_ids_[index]);
  hand_values_[offset] = chance_weapon_attack_values_[index];
  hand_costs_[offset] = 0U;
  hand_hit_rates_[offset] = chance_weapon_hit_rates_[index];
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kChanceWeaponCardKind;
  hand_elements_by_player_[offset] = chance_weapon_elements_[index];
}

void AttackDefenseBatch::draw_chance_dual_role(std::size_t environment,
                                               std::size_t player,
                                               std::size_t slot) {
  const auto index = static_cast<std::size_t>(
      next_random(environment) % chance_dual_role_token_ids_.size());
  const auto offset = hand_offset(environment, player, slot);
  hand_token_ids_by_player_[offset] =
      static_cast<std::int64_t>(chance_dual_role_token_ids_[index]);
  hand_values_[offset] = chance_dual_role_attack_values_[index];
  hand_costs_[offset] = 0U;
  hand_hit_rates_[offset] = chance_dual_role_hit_rates_[index];
  hand_effects_[offset] = kNoAttackEffect;
  hand_card_kinds_by_player_[offset] = kChanceDualRoleCardKind;
  hand_elements_by_player_[offset] = chance_dual_role_elements_[index];
}

void AttackDefenseBatch::draw_weapon_family(std::size_t environment,
                                            std::size_t player,
                                            std::size_t slot) {
  if (chance_weapon_curriculum_) {
    auto index = static_cast<std::size_t>(
        next_random(environment) %
        (weapon_token_ids_.size() + reflection_weapon_token_ids_.size() +
         dual_role_token_ids_.size() + chance_weapon_token_ids_.size() +
         chance_dual_role_token_ids_.size()));
    if (index < weapon_token_ids_.size()) {
      draw_weapon(environment, player, slot);
      return;
    }
    index -= weapon_token_ids_.size();
    if (index < reflection_weapon_token_ids_.size()) {
      draw_reflection_weapon(environment, player, slot);
      return;
    }
    index -= reflection_weapon_token_ids_.size();
    if (index < dual_role_token_ids_.size()) {
      draw_dual_role(environment, player, slot);
      return;
    }
    index -= dual_role_token_ids_.size();
    if (index < chance_weapon_token_ids_.size()) {
      draw_chance_weapon(environment, player, slot);
      return;
    }
    draw_chance_dual_role(environment, player, slot);
    return;
  }
  if (dual_role_curriculum_) {
    auto index = static_cast<std::size_t>(next_random(environment) %
                                          (weapon_token_ids_.size() +
                                           reflection_weapon_token_ids_.size() +
                                           dual_role_token_ids_.size()));
    if (index < weapon_token_ids_.size()) {
      draw_weapon(environment, player, slot);
      return;
    }
    index -= weapon_token_ids_.size();
    if (index < reflection_weapon_token_ids_.size()) {
      draw_reflection_weapon(environment, player, slot);
      return;
    }
    draw_dual_role(environment, player, slot);
    return;
  }
  if (reflection_weapon_curriculum_ &&
      next_random(environment) % (weapon_token_ids_.size() +
                                  reflection_weapon_token_ids_.size()) >=
          weapon_token_ids_.size()) {
    draw_reflection_weapon(environment, player, slot);
    return;
  }
  draw_weapon(environment, player, slot);
}

void AttackDefenseBatch::draw_armor_family(std::size_t environment,
                                           std::size_t player,
                                           std::size_t slot) {
  if (reflection_curriculum_ &&
      next_random(environment) %
              (armor_token_ids_.size() + reflection_armor_token_ids_.size()) >=
          armor_token_ids_.size()) {
    draw_reflection_armor(environment, player, slot);
    return;
  }
  draw_armor(environment, player, slot);
}

void AttackDefenseBatch::draw_resource(std::size_t environment,
                                       std::size_t player, std::size_t slot) {
  const auto catalog_size =
      weapon_token_ids_.size() + booster_token_ids_.size() +
      armor_token_ids_.size() + hp_utility_token_ids_.size() +
      mp_utility_token_ids_.size() + attack_miracle_token_ids_.size() +
      hp_miracle_token_ids_.size() + chance_miracle_token_ids_.size() +
      effect_miracle_token_ids_.size() + additive_miracle_token_ids_.size() +
      reflection_armor_token_ids_.size() + reflection_weapon_token_ids_.size() +
      dual_role_token_ids_.size() + chance_weapon_token_ids_.size() +
      chance_dual_role_token_ids_.size();
  auto index =
      static_cast<std::size_t>(next_random(environment) % catalog_size);
  if (index < weapon_token_ids_.size()) {
    draw_weapon(environment, player, slot);
    return;
  }
  index -= weapon_token_ids_.size();
  if (index < reflection_weapon_token_ids_.size()) {
    draw_reflection_weapon(environment, player, slot);
    return;
  }
  index -= reflection_weapon_token_ids_.size();
  if (index < dual_role_token_ids_.size()) {
    draw_dual_role(environment, player, slot);
    return;
  }
  index -= dual_role_token_ids_.size();
  if (index < chance_weapon_token_ids_.size()) {
    draw_chance_weapon(environment, player, slot);
    return;
  }
  index -= chance_weapon_token_ids_.size();
  if (index < chance_dual_role_token_ids_.size()) {
    draw_chance_dual_role(environment, player, slot);
    return;
  }
  index -= chance_dual_role_token_ids_.size();
  if (index < booster_token_ids_.size()) {
    draw_booster(environment, player, slot);
    return;
  }
  index -= booster_token_ids_.size();
  if (index < armor_token_ids_.size()) {
    draw_armor(environment, player, slot);
    return;
  }
  index -= armor_token_ids_.size();
  if (index < hp_utility_token_ids_.size()) {
    draw_hp_utility(environment, player, slot);
    return;
  }
  index -= hp_utility_token_ids_.size();
  if (index < mp_utility_token_ids_.size()) {
    draw_mp_utility(environment, player, slot);
    return;
  }
  index -= mp_utility_token_ids_.size();
  if (index < attack_miracle_token_ids_.size()) {
    draw_attack_miracle(environment, player, slot);
    return;
  }
  index -= attack_miracle_token_ids_.size();
  if (index < hp_miracle_token_ids_.size()) {
    draw_hp_miracle(environment, player, slot);
    return;
  }
  index -= hp_miracle_token_ids_.size();
  if (index < chance_miracle_token_ids_.size()) {
    draw_chance_miracle(environment, player, slot);
    return;
  }
  index -= chance_miracle_token_ids_.size();
  if (index < effect_miracle_token_ids_.size()) {
    draw_effect_miracle(environment, player, slot);
    return;
  }
  index -= effect_miracle_token_ids_.size();
  if (index < additive_miracle_token_ids_.size()) {
    draw_additive_miracle(environment, player, slot);
    return;
  }
  draw_reflection_armor(environment, player, slot);
}

bool AttackDefenseBatch::is_weapon_kind(std::uint8_t kind) noexcept {
  return kind == kWeaponCardKind || kind == kReflectionWeaponCardKind ||
         kind == kDualRoleCardKind || kind == kChanceWeaponCardKind ||
         kind == kChanceDualRoleCardKind;
}

std::uint16_t AttackDefenseBatch::defense_value_for_card(
    std::size_t card_offset) const noexcept {
  const auto kind = hand_card_kinds_by_player_[card_offset];
  if (kind == kReflectionArmorCardKind || kind == kReflectionWeaponCardKind) {
    return 0U;
  }
  if (kind != kDualRoleCardKind && kind != kChanceDualRoleCardKind) {
    return hand_values_[card_offset];
  }
  const auto token =
      static_cast<std::uint32_t>(hand_token_ids_by_player_[card_offset]);
  if (kind == kDualRoleCardKind) {
    const auto found = std::find(dual_role_token_ids_.begin(),
                                 dual_role_token_ids_.end(), token);
    if (found == dual_role_token_ids_.end()) {
      return 0U;
    }
    return dual_role_defense_values_[static_cast<std::size_t>(
        std::distance(dual_role_token_ids_.begin(), found))];
  }
  const auto found = std::find(chance_dual_role_token_ids_.begin(),
                               chance_dual_role_token_ids_.end(), token);
  if (found == chance_dual_role_token_ids_.end()) {
    return 0U;
  }
  return chance_dual_role_defense_values_[static_cast<std::size_t>(
      std::distance(chance_dual_role_token_ids_.begin(), found))];
}

bool AttackDefenseBatch::has_weapon(std::size_t environment,
                                    std::size_t player) const noexcept {
  for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
    if (is_weapon_kind(hand_card_kinds_by_player_[hand_offset(environment,
                                                              player, slot)])) {
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
  if (combo_) {
    if (resource_curriculum_) {
      draw_resource(environment, player, slot);
    } else {
      draw_combo(environment, player, slot);
    }
    if (!has_weapon(environment, player)) {
      draw_weapon_family(environment, player, slot);
    }
    return;
  }
  draw_mixed(environment, player, slot);
  if (!has_weapon(environment, player)) {
    draw_weapon_family(environment, player, slot);
  }
}

void AttackDefenseBatch::reset_environment(std::size_t environment) {
  ++episode_ids_[environment];
  hit_points_[environment * kPlayerCount] = initial_hp_;
  hit_points_[environment * kPlayerCount + 1U] = initial_hp_;
  magic_points_[environment * kPlayerCount] = initial_mp_;
  magic_points_[environment * kPlayerCount + 1U] = initial_mp_;
  active_players_[environment] =
      static_cast<std::uint8_t>(next_random(environment) & 1U);
  phases_[environment] = static_cast<std::uint8_t>(TurnPhase::Attack);
  pending_attackers_[environment] = active_players_[environment];
  pending_attacks_[environment] = 0U;
  pending_elements_[environment] =
      static_cast<std::uint8_t>(CombatElement::NonElement);
  pending_effects_[environment] = kNoAttackEffect;
  pending_base_kinds_[environment] = 0U;
  pending_reflected_[environment] = false;
  turn_numbers_[environment] = 0U;
  terminated_[environment] = false;
  terminal_returns_[environment * kPlayerCount] = 0.0F;
  terminal_returns_[environment * kPlayerCount + 1U] = 0.0F;
  clear_selection(environment);

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
    if (stochastic_resource_curriculum_) {
      auto output = card_kinds.begin();
      output =
          std::fill_n(output, kStochasticResourceWeaponSlots, kWeaponCardKind);
      output = std::fill_n(output, kStochasticResourceBoosterSlots,
                           kAttackBoosterCardKind);
      output =
          std::fill_n(output, kStochasticResourceArmorSlots, kArmorCardKind);
      output = std::fill_n(output, kStochasticResourceUtilitySlots,
                           kHpUtilityCardKind);
      output = std::fill_n(output, kStochasticResourceAttackMiracleSlots,
                           kAttackMiracleCardKind);
      output = std::fill_n(output, kStochasticResourceChanceMiracleSlots,
                           kChanceAttackMiracleCardKind);
      std::fill_n(output, kStochasticResourceEffectMiracleSlots,
                  kEffectAttackMiracleCardKind);
    } else if (resource_curriculum_) {
      auto output = card_kinds.begin();
      output = std::fill_n(output, kResourceWeaponSlots, kWeaponCardKind);
      output =
          std::fill_n(output, kResourceBoosterSlots, kAttackBoosterCardKind);
      output = std::fill_n(output, kResourceArmorSlots, kArmorCardKind);
      output = std::fill_n(output, kResourceUtilitySlots, kHpUtilityCardKind);
      std::fill_n(output, kResourceAttackMiracleSlots, kAttackMiracleCardKind);
    } else if (combo_) {
      std::fill_n(card_kinds.begin(), kComboWeaponSlots, kWeaponCardKind);
      std::fill_n(card_kinds.begin() +
                      static_cast<std::ptrdiff_t>(kComboWeaponSlots),
                  kComboBoosterSlots, kAttackBoosterCardKind);
      std::fill(card_kinds.begin() +
                    static_cast<std::ptrdiff_t>(kComboWeaponSlots +
                                                kComboBoosterSlots),
                card_kinds.end(), kArmorCardKind);
    } else {
      std::fill_n(card_kinds.begin(), kWeaponSlots, kWeaponCardKind);
      std::fill(card_kinds.begin() + static_cast<std::ptrdiff_t>(kWeaponSlots),
                card_kinds.end(), kArmorCardKind);
    }
    for (std::size_t remaining = kHandSlots; remaining > 1U; --remaining) {
      const auto swap_index = static_cast<std::size_t>(
          next_random(environment) % static_cast<std::uint64_t>(remaining));
      std::swap(card_kinds[remaining - 1U], card_kinds[swap_index]);
    }
    for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
      if (card_kinds[slot] == kWeaponCardKind) {
        draw_weapon_family(environment, player, slot);
      } else if (card_kinds[slot] == kAttackBoosterCardKind) {
        if (additive_miracle_curriculum_ &&
            next_random(environment) % (booster_token_ids_.size() +
                                        additive_miracle_token_ids_.size()) >=
                booster_token_ids_.size()) {
          draw_additive_miracle(environment, player, slot);
        } else {
          draw_booster(environment, player, slot);
        }
      } else if (card_kinds[slot] == kAttackMiracleCardKind) {
        draw_attack_miracle(environment, player, slot);
      } else if (card_kinds[slot] == kChanceAttackMiracleCardKind) {
        draw_chance_miracle(environment, player, slot);
      } else if (card_kinds[slot] == kEffectAttackMiracleCardKind) {
        draw_effect_miracle(environment, player, slot);
      } else if (card_kinds[slot] == kHpUtilityCardKind) {
        const auto hp_count = hp_utility_token_ids_.size();
        const auto mp_count = mp_utility_token_ids_.size();
        const auto utility_index = static_cast<std::size_t>(
            next_random(environment) %
            (hp_count + mp_count + hp_miracle_token_ids_.size()));
        if (utility_index < hp_count) {
          draw_hp_utility(environment, player, slot);
        } else if (utility_index < hp_count + mp_count) {
          draw_mp_utility(environment, player, slot);
        } else {
          draw_hp_miracle(environment, player, slot);
        }
      } else {
        draw_armor_family(environment, player, slot);
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

void AttackDefenseBatch::clear_selection(std::size_t environment) noexcept {
  std::fill_n(selected_hand_mask_.get() + environment * kHandSlots, kHandSlots,
              false);
  selected_counts_[environment] = 0U;
  selected_values_[environment] = 0U;
  selected_elements_[environment] =
      static_cast<std::uint8_t>(CombatElement::NonElement);
  selected_costs_[environment] = 0U;
  selected_base_kinds_[environment] = 0U;
  selected_hit_rates_[environment] = 100U;
  selected_effects_[environment] = kNoAttackEffect;
}

void AttackDefenseBatch::consume_selection(std::size_t environment,
                                           std::size_t player) {
  for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
    if (!selected_hand_mask_[environment * kHandSlots + slot]) {
      continue;
    }
    const auto card_offset = hand_offset(environment, player, slot);
    const auto kind = hand_card_kinds_by_player_[card_offset];
    if (kind == kAttackMiracleCardKind || kind == kHpMiracleCardKind ||
        kind == kChanceAttackMiracleCardKind ||
        kind == kEffectAttackMiracleCardKind ||
        kind == kAdditiveMiracleCardKind) {
      continue;
    }
    redraw_consumed(environment, player, slot, kind);
  }
}

std::uint8_t
AttackDefenseBatch::combine_attack_elements(std::uint8_t existing,
                                            std::uint8_t added) const noexcept {
  if (existing == added) {
    return existing;
  }
  const auto light = static_cast<std::uint8_t>(CombatElement::Light);
  const auto ordinary_element = [](std::uint8_t element) {
    return element >= static_cast<std::uint8_t>(CombatElement::Fire) &&
           element <= static_cast<std::uint8_t>(CombatElement::Stone);
  };
  if (existing == light && ordinary_element(added)) {
    return added;
  }
  if (added == light && ordinary_element(existing)) {
    return existing;
  }
  return static_cast<std::uint8_t>(CombatElement::NonElement);
}

void AttackDefenseBatch::resolve_defense(std::size_t environment,
                                         std::size_t defender,
                                         std::uint16_t defense) {
  const auto attack = pending_attacks_[environment];
  auto damage =
      attack > defense ? static_cast<std::uint16_t>(attack - defense) : 0U;
  auto &defender_hp = hit_points_[environment * kPlayerCount + defender];
  const auto defender_hp_before = defender_hp;
  if (pending_elements_[environment] ==
          static_cast<std::uint8_t>(CombatElement::Darkness) &&
      damage > 0U) {
    damage = defender_hp;
  }
  defender_hp = damage >= defender_hp
                    ? 0U
                    : static_cast<std::uint16_t>(defender_hp - damage);
  if (pending_effects_[environment] == kAbsorbHpAttackEffect) {
    const auto attacker =
        static_cast<std::size_t>(pending_attackers_[environment]);
    auto &attacker_hp = hit_points_[environment * kPlayerCount + attacker];
    const auto hp_lost =
        static_cast<unsigned int>(defender_hp_before - defender_hp);
    attacker_hp = static_cast<std::uint16_t>(std::min<unsigned int>(
        kMaximumResource, static_cast<unsigned int>(attacker_hp) + hp_lost));
  }
  ++turn_numbers_[environment];

  if (defender_hp == 0U) {
    const auto attacker =
        static_cast<std::size_t>(pending_attackers_[environment]);
    terminated_[environment] = true;
    phases_[environment] = static_cast<std::uint8_t>(TurnPhase::Terminal);
    terminal_returns_[environment * kPlayerCount + attacker] = 1.0F;
    terminal_returns_[environment * kPlayerCount + defender] = -1.0F;
    pending_effects_[environment] = kNoAttackEffect;
    pending_base_kinds_[environment] = 0U;
    pending_reflected_[environment] = false;
    return;
  }
  pending_attacks_[environment] = 0U;
  pending_elements_[environment] =
      static_cast<std::uint8_t>(CombatElement::NonElement);
  pending_effects_[environment] = kNoAttackEffect;
  pending_base_kinds_[environment] = 0U;
  pending_reflected_[environment] = false;
  phases_[environment] = static_cast<std::uint8_t>(TurnPhase::Attack);
}

void AttackDefenseBatch::resolve_reflection(std::size_t environment,
                                            std::size_t reflector) {
  active_players_[environment] = static_cast<std::uint8_t>(1U - reflector);
  pending_attackers_[environment] = static_cast<std::uint8_t>(reflector);
  pending_reflected_[environment] = true;
  phases_[environment] = static_cast<std::uint8_t>(TurnPhase::Defense);
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
    if (combo_) {
      if (phase == TurnPhase::Attack) {
        if (action == kConfirmActionIndex) {
          if (resource_curriculum_) {
            auto &actor_mp = magic_points_[environment * kPlayerCount + actor];
            actor_mp = static_cast<std::uint16_t>(actor_mp -
                                                  selected_costs_[environment]);
          }
          const auto selected_value = selected_values_[environment];
          const auto selected_element = selected_elements_[environment];
          const auto selected_hit_rate = selected_hit_rates_[environment];
          const auto selected_effect = selected_effects_[environment];
          const auto selected_base_kind = selected_base_kinds_[environment];
          consume_selection(environment, actor);
          clear_selection(environment);
          active_players_[environment] = static_cast<std::uint8_t>(1U - actor);
          if (selected_hit_rate < 100U &&
              next_random(environment) % 100U >= selected_hit_rate) {
            pending_attacks_[environment] = 0U;
            pending_elements_[environment] =
                static_cast<std::uint8_t>(CombatElement::NonElement);
            pending_effects_[environment] = kNoAttackEffect;
            pending_base_kinds_[environment] = 0U;
            pending_reflected_[environment] = false;
            ++turn_numbers_[environment];
            phases_[environment] = static_cast<std::uint8_t>(TurnPhase::Attack);
            refresh_environment_views(environment);
            continue;
          }
          pending_attackers_[environment] = static_cast<std::uint8_t>(actor);
          pending_attacks_[environment] = selected_value;
          pending_elements_[environment] = selected_element;
          pending_effects_[environment] = selected_effect;
          pending_base_kinds_[environment] = selected_base_kind;
          pending_reflected_[environment] = false;
          phases_[environment] = static_cast<std::uint8_t>(TurnPhase::Defense);
        } else {
          const auto slot = action - 1U;
          const auto card_offset = hand_offset(environment, actor, slot);
          const auto kind = hand_card_kinds_by_player_[card_offset];
          if (resource_curriculum_ && selected_counts_[environment] == 0U &&
              (kind == kHpUtilityCardKind || kind == kMpUtilityCardKind ||
               kind == kHpMiracleCardKind)) {
            auto &resource =
                kind == kMpUtilityCardKind
                    ? magic_points_[environment * kPlayerCount + actor]
                    : hit_points_[environment * kPlayerCount + actor];
            resource = static_cast<std::uint16_t>(std::min<unsigned int>(
                kMaximumResource, static_cast<unsigned int>(resource) +
                                      hand_values_[card_offset]));
            if (kind == kHpMiracleCardKind) {
              auto &actor_mp =
                  magic_points_[environment * kPlayerCount + actor];
              actor_mp = static_cast<std::uint16_t>(actor_mp -
                                                    hand_costs_[card_offset]);
            } else {
              redraw_consumed(environment, actor, slot, kind);
            }
            ++turn_numbers_[environment];
            active_players_[environment] =
                static_cast<std::uint8_t>(1U - actor);
            refresh_environment_views(environment);
            continue;
          }
          selected_hand_mask_[environment * kHandSlots + slot] = true;
          if (selected_counts_[environment] == 0U) {
            selected_values_[environment] = hand_values_[card_offset];
            selected_elements_[environment] =
                hand_elements_by_player_[card_offset];
            selected_costs_[environment] = hand_costs_[card_offset];
            selected_base_kinds_[environment] = kind;
            selected_hit_rates_[environment] = hand_hit_rates_[card_offset];
            selected_effects_[environment] = hand_effects_[card_offset];
          } else {
            selected_values_[environment] = static_cast<std::uint16_t>(
                selected_values_[environment] + hand_values_[card_offset]);
            selected_costs_[environment] = static_cast<std::uint16_t>(
                selected_costs_[environment] + hand_costs_[card_offset]);
            selected_elements_[environment] =
                combine_attack_elements(selected_elements_[environment],
                                        hand_elements_by_player_[card_offset]);
          }
          ++selected_counts_[environment];
        }
      } else if (action == kForgiveActionIndex) {
        resolve_defense(environment, actor, 0U);
      } else if (action == kConfirmActionIndex) {
        const auto defense = selected_values_[environment];
        const auto selected_kind = selected_base_kinds_[environment];
        consume_selection(environment, actor);
        clear_selection(environment);
        if (selected_kind == kReflectionArmorCardKind ||
            selected_kind == kReflectionWeaponCardKind) {
          resolve_reflection(environment, actor);
        } else {
          resolve_defense(environment, actor, defense);
        }
      } else {
        const auto slot = action - 1U;
        const auto card_offset = hand_offset(environment, actor, slot);
        const auto kind = hand_card_kinds_by_player_[card_offset];
        selected_hand_mask_[environment * kHandSlots + slot] = true;
        selected_values_[environment] =
            static_cast<std::uint16_t>(selected_values_[environment] +
                                       defense_value_for_card(card_offset));
        selected_elements_[environment] = hand_elements_by_player_[card_offset];
        if (selected_counts_[environment] == 0U) {
          selected_base_kinds_[environment] = kind;
        }
        ++selected_counts_[environment];
      }
      refresh_environment_views(environment);
      continue;
    }
    if (phase == TurnPhase::Attack) {
      const auto slot = action - 1U;
      const auto card_offset = hand_offset(environment, actor, slot);
      const auto consumed_kind = hand_card_kinds_by_player_[card_offset];
      pending_attackers_[environment] = static_cast<std::uint8_t>(actor);
      pending_attacks_[environment] = hand_values_[card_offset];
      pending_elements_[environment] = hand_elements_by_player_[card_offset];
      pending_effects_[environment] = kNoAttackEffect;
      pending_base_kinds_[environment] = consumed_kind;
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

      resolve_defense(environment, actor, defense);
    }
    refresh_environment_views(environment);
  }
}

void AttackDefenseBatch::refresh_environment_views(std::size_t environment) {
  const auto perspective =
      static_cast<std::size_t>(active_players_[environment]);
  const auto opponent = 1U - perspective;
  const auto global_offset = environment * global_feature_count_;
  global_features_[global_offset] = normalized(turn_numbers_[environment]);
  global_features_[global_offset + 1U] =
      normalized(hit_points_[environment * kPlayerCount + perspective]);
  global_features_[global_offset + 2U] =
      normalized(magic_points_[environment * kPlayerCount + perspective]);
  global_features_[global_offset + 3U] = 0.0F;
  const auto phase = static_cast<TurnPhase>(phases_[environment]);
  global_features_[global_offset + 4U] =
      phase == TurnPhase::Defense ? 1.0F : 0.0F;
  global_features_[global_offset + 5U] = normalized(
      combo_ && phase == TurnPhase::Attack ? selected_values_[environment]
                                           : pending_attacks_[environment]);
  if (elemental_) {
    std::fill_n(global_features_.data() + global_offset + kGlobalFeatureCount,
                kElementCount, 0.0F);
    if (phase == TurnPhase::Defense ||
        (combo_ && selected_counts_[environment] > 0U)) {
      const auto visible_element = phase == TurnPhase::Defense
                                       ? pending_elements_[environment]
                                       : selected_elements_[environment];
      global_features_[global_offset + kGlobalFeatureCount + visible_element] =
          1.0F;
    }
  }
  if (stochastic_resource_curriculum_) {
    global_features_[global_offset + kElementalGlobalFeatureCount] =
        phase == TurnPhase::Defense &&
                pending_effects_[environment] == kAbsorbHpAttackEffect
            ? 1.0F
            : 0.0F;
  }

  const auto player_offset = environment * kPlayerCount * kPlayerFeatureCount;
  const std::size_t ordered_players[kPlayerCount] = {perspective, opponent};
  for (std::size_t row = 0; row < kPlayerCount; ++row) {
    const auto output = player_offset + row * kPlayerFeatureCount;
    player_features_[output] = normalized(
        hit_points_[environment * kPlayerCount + ordered_players[row]]);
    player_features_[output + 1U] = normalized(
        magic_points_[environment * kPlayerCount + ordered_players[row]]);
    player_features_[output + 2U] = 0.0F;
    player_features_[output + 3U] = row == 0U ? 1.0F : 0.0F;
    player_mask_[environment * kPlayerCount + row] = true;
  }

  const auto visible_hand_offset = environment * kHandSlots;
  for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
    const auto selected =
        combo_ && selected_hand_mask_[environment * kHandSlots + slot];
    const auto source = hand_offset(environment, perspective, slot);
    const auto token = selected ? 0 : hand_token_ids_by_player_[source];
    visible_hand_token_ids_[visible_hand_offset + slot] = token;
    hand_mask_[visible_hand_offset + slot] = token != 0;
    visible_hand_card_kinds_[visible_hand_offset + slot] =
        selected ? 0U : hand_card_kinds_by_player_[source];
    visible_hand_elements_[visible_hand_offset + slot] =
        selected ? 0U : hand_elements_by_player_[source];
  }

  const auto action_offset = environment * kActionCount;
  std::fill_n(action_mask_.get() + action_offset, kActionCount, false);
  if (terminated_[environment]) {
    return;
  }
  if (combo_) {
    if (phase == TurnPhase::Attack) {
      const auto has_base = selected_counts_[environment] > 0U;
      for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
        if (selected_hand_mask_[environment * kHandSlots + slot]) {
          continue;
        }
        const auto kind = hand_card_kinds_by_player_[hand_offset(
            environment, perspective, slot)];
        if (has_base) {
          const auto card_offset = hand_offset(environment, perspective, slot);
          const auto mp =
              magic_points_[environment * kPlayerCount + perspective];
          action_mask_[action_offset + slot + 1U] =
              is_weapon_kind(selected_base_kinds_[environment]) &&
              (kind == kAttackBoosterCardKind ||
               (kind == kAdditiveMiracleCardKind &&
                selected_costs_[environment] + hand_costs_[card_offset] <= mp));
          continue;
        }
        if (!resource_curriculum_) {
          action_mask_[action_offset + slot + 1U] = is_weapon_kind(kind);
          continue;
        }
        const auto card_offset = hand_offset(environment, perspective, slot);
        const auto mp = magic_points_[environment * kPlayerCount + perspective];
        const auto hp = hit_points_[environment * kPlayerCount + perspective];
        action_mask_[action_offset + slot + 1U] =
            is_weapon_kind(kind) ||
            ((kind == kAttackMiracleCardKind ||
              kind == kChanceAttackMiracleCardKind ||
              kind == kEffectAttackMiracleCardKind) &&
             hand_costs_[card_offset] <= mp) ||
            (kind == kHpUtilityCardKind && hp < kMaximumResource) ||
            (kind == kMpUtilityCardKind && mp < kMaximumResource) ||
            (kind == kHpMiracleCardKind && hp < kMaximumResource &&
             hand_costs_[card_offset] <= mp);
      }
      action_mask_[action_offset + kConfirmActionIndex] = has_base;
      return;
    }
    const auto has_defense = selected_counts_[environment] > 0U;
    const auto selected_reflection =
        selected_base_kinds_[environment] == kReflectionArmorCardKind ||
        selected_base_kinds_[environment] == kReflectionWeaponCardKind;
    action_mask_[action_offset + kForgiveActionIndex] = !has_defense;
    action_mask_[action_offset + kConfirmActionIndex] = has_defense;
    for (std::size_t slot = 0; slot < kHandSlots; ++slot) {
      if (selected_hand_mask_[environment * kHandSlots + slot]) {
        continue;
      }
      const auto card_offset = hand_offset(environment, perspective, slot);
      const auto kind = hand_card_kinds_by_player_[card_offset];
      action_mask_[action_offset + slot + 1U] =
          (!selected_reflection &&
           (kind == kArmorCardKind || kind == kDualRoleCardKind ||
            kind == kChanceDualRoleCardKind) &&
           defense_element_is_compatible(
               pending_elements_[environment],
               hand_elements_by_player_[card_offset])) ||
          (!has_defense && !pending_reflected_[environment] &&
           (kind == kReflectionArmorCardKind ||
            (kind == kReflectionWeaponCardKind &&
             is_weapon_kind(pending_base_kinds_[environment]) &&
             pending_elements_[environment] ==
                 static_cast<std::uint8_t>(CombatElement::NonElement))));
    }
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
    const auto card_offset = hand_offset(environment, perspective, slot);
    action_mask_[action_offset + slot + 1U] =
        hand_card_kinds_by_player_[card_offset] == kArmorCardKind &&
        defense_element_is_compatible(pending_elements_[environment],
                                      hand_elements_by_player_[card_offset]);
  }
}

bool AttackDefenseBatch::defense_element_is_compatible(
    std::uint8_t attack_element, std::uint8_t defense_element) const noexcept {
  if (!elemental_) {
    return true;
  }
  const auto attack = static_cast<CombatElement>(attack_element);
  const auto defense = static_cast<CombatElement>(defense_element);
  if (attack == CombatElement::Light) {
    return false;
  }
  if (attack == CombatElement::Fire) {
    return defense == CombatElement::Water || defense == CombatElement::Light;
  }
  if (attack == CombatElement::Water) {
    return defense == CombatElement::Fire || defense == CombatElement::Light;
  }
  if (attack == CombatElement::Wood) {
    return defense == CombatElement::Stone || defense == CombatElement::Light;
  }
  if (attack == CombatElement::Stone) {
    return defense == CombatElement::Wood || defense == CombatElement::Light;
  }
  return true;
}

Float2D AttackDefenseBatch::global_features_view() const {
  return Float2D(global_features_.data(), {batch_size_, global_feature_count_});
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

UInt8_2D AttackDefenseBatch::hand_elements_view() const {
  return UInt8_2D(visible_hand_elements_.data(), {batch_size_, kHandSlots});
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

UInt8_1D AttackDefenseBatch::pending_elements_view() const {
  return UInt8_1D(pending_elements_.data(), {batch_size_});
}

Bool1D AttackDefenseBatch::pending_reflected_view() const {
  return Bool1D(pending_reflected_.get(), {batch_size_});
}

Bool2D AttackDefenseBatch::selected_hand_mask_view() const {
  return Bool2D(selected_hand_mask_.get(), {batch_size_, kHandSlots});
}

UInt8_1D AttackDefenseBatch::selected_counts_view() const {
  return UInt8_1D(selected_counts_.data(), {batch_size_});
}

UInt16_1D AttackDefenseBatch::selected_values_view() const {
  return UInt16_1D(selected_values_.data(), {batch_size_});
}

UInt8_1D AttackDefenseBatch::selected_elements_view() const {
  return UInt8_1D(selected_elements_.data(), {batch_size_});
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

UInt16_2D AttackDefenseBatch::magic_points_view() const {
  return UInt16_2D(magic_points_.data(), {batch_size_, kPlayerCount});
}

ElementalAttackDefenseBatch::ElementalAttackDefenseBatch(
    std::size_t batch_size, TokenInput weapon_token_ids,
    ValueInput attack_values, ElementInput weapon_elements,
    TokenInput armor_token_ids, ValueInput defense_values,
    ElementInput armor_elements, std::uint64_t seed, std::uint16_t initial_hp)
    : AttackDefenseBatch(
          batch_size, weapon_token_ids, attack_values,
          copy_elements(weapon_elements, weapon_token_ids.shape(0), "weapon"),
          {}, {}, {}, armor_token_ids, defense_values,
          copy_elements(armor_elements, armor_token_ids.shape(0), "armor"),
          seed, initial_hp, true, true, false, false) {}

ComboAttackDefenseBatch::ComboAttackDefenseBatch(
    std::size_t batch_size, TokenInput weapon_token_ids,
    ValueInput attack_values, ElementInput weapon_elements,
    TokenInput booster_token_ids, ValueInput booster_values,
    ElementInput booster_elements, TokenInput armor_token_ids,
    ValueInput defense_values, ElementInput armor_elements, std::uint64_t seed,
    std::uint16_t initial_hp)
    : AttackDefenseBatch(
          batch_size, weapon_token_ids, attack_values,
          copy_elements(weapon_elements, weapon_token_ids.shape(0), "weapon"),
          booster_token_ids, booster_values,
          copy_elements(booster_elements, booster_token_ids.shape(0),
                        "attack booster"),
          armor_token_ids, defense_values,
          copy_elements(armor_elements, armor_token_ids.shape(0), "armor"),
          seed, initial_hp, true, true, true, false) {}

ResourceAttackDefenseBatch::ResourceAttackDefenseBatch(
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
    std::uint16_t initial_mp)
    : AttackDefenseBatch(
          batch_size, weapon_token_ids, attack_values,
          copy_elements(weapon_elements, weapon_token_ids.shape(0), "weapon"),
          booster_token_ids, booster_values,
          copy_elements(booster_elements, booster_token_ids.shape(0),
                        "attack booster"),
          armor_token_ids, defense_values,
          copy_elements(armor_elements, armor_token_ids.shape(0), "armor"),
          seed, initial_hp, true, true, true, true, hp_utility_token_ids,
          hp_utility_values, mp_utility_token_ids, mp_utility_values,
          attack_miracle_token_ids, attack_miracle_values,
          attack_miracle_elements, attack_miracle_costs, hp_miracle_token_ids,
          hp_miracle_values, hp_miracle_costs, initial_mp) {}

StochasticResourceAttackDefenseBatch::StochasticResourceAttackDefenseBatch(
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
    ValueInput hp_miracle_costs, TokenInput chance_miracle_token_ids,
    ValueInput chance_miracle_values, ElementInput chance_miracle_elements,
    ValueInput chance_miracle_costs, ValueInput chance_miracle_hit_rates,
    TokenInput effect_miracle_token_ids, ValueInput effect_miracle_values,
    ElementInput effect_miracle_elements, ValueInput effect_miracle_costs,
    std::uint64_t seed, std::uint16_t initial_hp, std::uint16_t initial_mp)
    : AttackDefenseBatch(
          batch_size, weapon_token_ids, attack_values,
          copy_elements(weapon_elements, weapon_token_ids.shape(0), "weapon"),
          booster_token_ids, booster_values,
          copy_elements(booster_elements, booster_token_ids.shape(0),
                        "attack booster"),
          armor_token_ids, defense_values,
          copy_elements(armor_elements, armor_token_ids.shape(0), "armor"),
          seed, initial_hp, true, true, true, true, hp_utility_token_ids,
          hp_utility_values, mp_utility_token_ids, mp_utility_values,
          attack_miracle_token_ids, attack_miracle_values,
          attack_miracle_elements, attack_miracle_costs, hp_miracle_token_ids,
          hp_miracle_values, hp_miracle_costs, initial_mp, true,
          chance_miracle_token_ids, chance_miracle_values,
          chance_miracle_elements, chance_miracle_costs,
          chance_miracle_hit_rates, effect_miracle_token_ids,
          effect_miracle_values, effect_miracle_elements,
          effect_miracle_costs) {}

ExpandedResourceAttackDefenseBatch::ExpandedResourceAttackDefenseBatch(
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
    ValueInput hp_miracle_costs, TokenInput chance_miracle_token_ids,
    ValueInput chance_miracle_values, ElementInput chance_miracle_elements,
    ValueInput chance_miracle_costs, ValueInput chance_miracle_hit_rates,
    TokenInput effect_miracle_token_ids, ValueInput effect_miracle_values,
    ElementInput effect_miracle_elements, ValueInput effect_miracle_costs,
    TokenInput additive_miracle_token_ids, ValueInput additive_miracle_values,
    ElementInput additive_miracle_elements, ValueInput additive_miracle_costs,
    std::uint64_t seed, std::uint16_t initial_hp, std::uint16_t initial_mp)
    : AttackDefenseBatch(
          batch_size, weapon_token_ids, attack_values,
          copy_elements(weapon_elements, weapon_token_ids.shape(0), "weapon"),
          booster_token_ids, booster_values,
          copy_elements(booster_elements, booster_token_ids.shape(0),
                        "attack booster"),
          armor_token_ids, defense_values,
          copy_elements(armor_elements, armor_token_ids.shape(0), "armor"),
          seed, initial_hp, true, true, true, true, hp_utility_token_ids,
          hp_utility_values, mp_utility_token_ids, mp_utility_values,
          attack_miracle_token_ids, attack_miracle_values,
          attack_miracle_elements, attack_miracle_costs, hp_miracle_token_ids,
          hp_miracle_values, hp_miracle_costs, initial_mp, true,
          chance_miracle_token_ids, chance_miracle_values,
          chance_miracle_elements, chance_miracle_costs,
          chance_miracle_hit_rates, effect_miracle_token_ids,
          effect_miracle_values, effect_miracle_elements, effect_miracle_costs,
          true, additive_miracle_token_ids, additive_miracle_values,
          additive_miracle_elements, additive_miracle_costs) {}

ReflectionResourceAttackDefenseBatch::ReflectionResourceAttackDefenseBatch(
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
    ValueInput hp_miracle_costs, TokenInput chance_miracle_token_ids,
    ValueInput chance_miracle_values, ElementInput chance_miracle_elements,
    ValueInput chance_miracle_costs, ValueInput chance_miracle_hit_rates,
    TokenInput effect_miracle_token_ids, ValueInput effect_miracle_values,
    ElementInput effect_miracle_elements, ValueInput effect_miracle_costs,
    TokenInput additive_miracle_token_ids, ValueInput additive_miracle_values,
    ElementInput additive_miracle_elements, ValueInput additive_miracle_costs,
    TokenInput reflection_armor_token_ids, std::uint64_t seed,
    std::uint16_t initial_hp, std::uint16_t initial_mp)
    : AttackDefenseBatch(
          batch_size, weapon_token_ids, attack_values,
          copy_elements(weapon_elements, weapon_token_ids.shape(0), "weapon"),
          booster_token_ids, booster_values,
          copy_elements(booster_elements, booster_token_ids.shape(0),
                        "attack booster"),
          armor_token_ids, defense_values,
          copy_elements(armor_elements, armor_token_ids.shape(0), "armor"),
          seed, initial_hp, true, true, true, true, hp_utility_token_ids,
          hp_utility_values, mp_utility_token_ids, mp_utility_values,
          attack_miracle_token_ids, attack_miracle_values,
          attack_miracle_elements, attack_miracle_costs, hp_miracle_token_ids,
          hp_miracle_values, hp_miracle_costs, initial_mp, true,
          chance_miracle_token_ids, chance_miracle_values,
          chance_miracle_elements, chance_miracle_costs,
          chance_miracle_hit_rates, effect_miracle_token_ids,
          effect_miracle_values, effect_miracle_elements, effect_miracle_costs,
          true, additive_miracle_token_ids, additive_miracle_values,
          additive_miracle_elements, additive_miracle_costs, true,
          reflection_armor_token_ids) {}

ReflectionWeaponResourceAttackDefenseBatch::
    ReflectionWeaponResourceAttackDefenseBatch(
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
        ValueInput hp_miracle_costs, TokenInput chance_miracle_token_ids,
        ValueInput chance_miracle_values, ElementInput chance_miracle_elements,
        ValueInput chance_miracle_costs, ValueInput chance_miracle_hit_rates,
        TokenInput effect_miracle_token_ids, ValueInput effect_miracle_values,
        ElementInput effect_miracle_elements, ValueInput effect_miracle_costs,
        TokenInput additive_miracle_token_ids,
        ValueInput additive_miracle_values,
        ElementInput additive_miracle_elements,
        ValueInput additive_miracle_costs,
        TokenInput reflection_armor_token_ids,
        TokenInput reflection_weapon_token_ids,
        ValueInput reflection_weapon_values, std::uint64_t seed,
        std::uint16_t initial_hp, std::uint16_t initial_mp)
    : AttackDefenseBatch(
          batch_size, weapon_token_ids, attack_values,
          copy_elements(weapon_elements, weapon_token_ids.shape(0), "weapon"),
          booster_token_ids, booster_values,
          copy_elements(booster_elements, booster_token_ids.shape(0),
                        "attack booster"),
          armor_token_ids, defense_values,
          copy_elements(armor_elements, armor_token_ids.shape(0), "armor"),
          seed, initial_hp, true, true, true, true, hp_utility_token_ids,
          hp_utility_values, mp_utility_token_ids, mp_utility_values,
          attack_miracle_token_ids, attack_miracle_values,
          attack_miracle_elements, attack_miracle_costs, hp_miracle_token_ids,
          hp_miracle_values, hp_miracle_costs, initial_mp, true,
          chance_miracle_token_ids, chance_miracle_values,
          chance_miracle_elements, chance_miracle_costs,
          chance_miracle_hit_rates, effect_miracle_token_ids,
          effect_miracle_values, effect_miracle_elements, effect_miracle_costs,
          true, additive_miracle_token_ids, additive_miracle_values,
          additive_miracle_elements, additive_miracle_costs, true,
          reflection_armor_token_ids, true, reflection_weapon_token_ids,
          reflection_weapon_values) {}

DualRoleResourceAttackDefenseBatch::DualRoleResourceAttackDefenseBatch(
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
    ValueInput hp_miracle_costs, TokenInput chance_miracle_token_ids,
    ValueInput chance_miracle_values, ElementInput chance_miracle_elements,
    ValueInput chance_miracle_costs, ValueInput chance_miracle_hit_rates,
    TokenInput effect_miracle_token_ids, ValueInput effect_miracle_values,
    ElementInput effect_miracle_elements, ValueInput effect_miracle_costs,
    TokenInput additive_miracle_token_ids, ValueInput additive_miracle_values,
    ElementInput additive_miracle_elements, ValueInput additive_miracle_costs,
    TokenInput reflection_armor_token_ids,
    TokenInput reflection_weapon_token_ids, ValueInput reflection_weapon_values,
    TokenInput dual_role_token_ids, ValueInput dual_role_attack_values,
    ValueInput dual_role_defense_values, ElementInput dual_role_elements,
    std::uint64_t seed, std::uint16_t initial_hp, std::uint16_t initial_mp)
    : AttackDefenseBatch(
          batch_size, weapon_token_ids, attack_values,
          copy_elements(weapon_elements, weapon_token_ids.shape(0), "weapon"),
          booster_token_ids, booster_values,
          copy_elements(booster_elements, booster_token_ids.shape(0),
                        "attack booster"),
          armor_token_ids, defense_values,
          copy_elements(armor_elements, armor_token_ids.shape(0), "armor"),
          seed, initial_hp, true, true, true, true, hp_utility_token_ids,
          hp_utility_values, mp_utility_token_ids, mp_utility_values,
          attack_miracle_token_ids, attack_miracle_values,
          attack_miracle_elements, attack_miracle_costs, hp_miracle_token_ids,
          hp_miracle_values, hp_miracle_costs, initial_mp, true,
          chance_miracle_token_ids, chance_miracle_values,
          chance_miracle_elements, chance_miracle_costs,
          chance_miracle_hit_rates, effect_miracle_token_ids,
          effect_miracle_values, effect_miracle_elements, effect_miracle_costs,
          true, additive_miracle_token_ids, additive_miracle_values,
          additive_miracle_elements, additive_miracle_costs, true,
          reflection_armor_token_ids, true, reflection_weapon_token_ids,
          reflection_weapon_values, true, dual_role_token_ids,
          dual_role_attack_values, dual_role_defense_values,
          dual_role_elements) {}

ChanceWeaponResourceAttackDefenseBatch::ChanceWeaponResourceAttackDefenseBatch(
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
    ValueInput hp_miracle_costs, TokenInput chance_miracle_token_ids,
    ValueInput chance_miracle_values, ElementInput chance_miracle_elements,
    ValueInput chance_miracle_costs, ValueInput chance_miracle_hit_rates,
    TokenInput effect_miracle_token_ids, ValueInput effect_miracle_values,
    ElementInput effect_miracle_elements, ValueInput effect_miracle_costs,
    TokenInput additive_miracle_token_ids, ValueInput additive_miracle_values,
    ElementInput additive_miracle_elements, ValueInput additive_miracle_costs,
    TokenInput reflection_armor_token_ids,
    TokenInput reflection_weapon_token_ids, ValueInput reflection_weapon_values,
    TokenInput dual_role_token_ids, ValueInput dual_role_attack_values,
    ValueInput dual_role_defense_values, ElementInput dual_role_elements,
    TokenInput chance_weapon_token_ids, ValueInput chance_weapon_attack_values,
    ElementInput chance_weapon_elements, ValueInput chance_weapon_hit_rates,
    TokenInput chance_dual_role_token_ids,
    ValueInput chance_dual_role_attack_values,
    ValueInput chance_dual_role_defense_values,
    ElementInput chance_dual_role_elements,
    ValueInput chance_dual_role_hit_rates, std::uint64_t seed,
    std::uint16_t initial_hp, std::uint16_t initial_mp)
    : AttackDefenseBatch(
          batch_size, weapon_token_ids, attack_values,
          copy_elements(weapon_elements, weapon_token_ids.shape(0), "weapon"),
          booster_token_ids, booster_values,
          copy_elements(booster_elements, booster_token_ids.shape(0),
                        "attack booster"),
          armor_token_ids, defense_values,
          copy_elements(armor_elements, armor_token_ids.shape(0), "armor"),
          seed, initial_hp, true, true, true, true, hp_utility_token_ids,
          hp_utility_values, mp_utility_token_ids, mp_utility_values,
          attack_miracle_token_ids, attack_miracle_values,
          attack_miracle_elements, attack_miracle_costs, hp_miracle_token_ids,
          hp_miracle_values, hp_miracle_costs, initial_mp, true,
          chance_miracle_token_ids, chance_miracle_values,
          chance_miracle_elements, chance_miracle_costs,
          chance_miracle_hit_rates, effect_miracle_token_ids,
          effect_miracle_values, effect_miracle_elements, effect_miracle_costs,
          true, additive_miracle_token_ids, additive_miracle_values,
          additive_miracle_elements, additive_miracle_costs, true,
          reflection_armor_token_ids, true, reflection_weapon_token_ids,
          reflection_weapon_values, true, dual_role_token_ids,
          dual_role_attack_values, dual_role_defense_values, dual_role_elements,
          true, chance_weapon_token_ids, chance_weapon_attack_values,
          chance_weapon_elements, chance_weapon_hit_rates,
          chance_dual_role_token_ids, chance_dual_role_attack_values,
          chance_dual_role_defense_values, chance_dual_role_elements,
          chance_dual_role_hit_rates) {}

} // namespace godfield_sim
