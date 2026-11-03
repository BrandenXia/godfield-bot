#include "full_game_batch.h"
#include "combat_rules.h"
#include "curse_rules.h"
#include "full_game_random.h"
#include "payment_rules.h"

#include <algorithm>
#include <memory>
#include <set>
#include <stdexcept>

namespace godfield_sim {
namespace {
using full_game_random::kMaximumCounter;
using full_game_random::random_rank;
template <typename Output, typename T>
Output owned_array(std::unique_ptr<T[]> buffer,
                   std::initializer_list<std::size_t> shape) {
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<T *>(pointer);
  });
  const auto *data = buffer.release();
  return Output(data, shape, owner);
}
} // namespace

std::size_t FullGameBatch::validate_dimensions(
    std::size_t batch_size, std::size_t players, std::size_t capacity,
    std::uint64_t turns, std::uint64_t decisions, std::uint16_t hp,
    std::uint16_t mp, std::uint16_t cp, std::uint16_t resource_cap) {
  if (batch_size == 0 || players < 2 || players > 9 || capacity == 0 ||
      capacity > 512 || batch_size > 2000000 / players / capacity ||
      turns < 1 || turns > 1000000000 || decisions < 1 ||
      decisions > 1000000000 || (resource_cap != 99 && resource_cap != 100) ||
      hp < 1 || hp > resource_cap || mp > resource_cap || cp > resource_cap) {
    throw std::invalid_argument(
        "full-game dimensions or resource bounds are invalid");
  }
  return batch_size;
}

FullGameBatch::FullGameBatch(
    std::size_t batch_size, std::size_t player_count,
    InventoryProfileInput inventory_profiles, InventoryInput utility_profiles,
    std::size_t capacity, std::uint64_t seed, std::uint64_t max_turns,
    std::uint64_t max_decisions, std::uint16_t initial_hp,
    std::uint16_t initial_mp, std::uint16_t initial_cp,
    std::optional<GuardianWeightInput> attack_profiles,
    std::optional<GuardianWeightInput> armor_profiles,
    std::optional<InventoryProfileInput> gift_profiles,
    std::size_t initial_cards, bool refill_on_use, bool prayer_gifts,
    std::size_t hand_limit, bool oldest_overflow,
    std::optional<FullGameBoostInput> boost_profiles,
    std::optional<GuardianWeightInput> special_profiles,
    std::optional<InventoryProfileInput> chance_profiles,
    std::optional<FullGameAttackEffectInput> attack_effect_profiles,
    std::optional<GuardianWeightInput> defense_effect_profiles,
    std::optional<InventoryProfileInput> passive_profiles,
    std::optional<FullGameAttackEffectInput> removal_profiles,
    std::optional<InventoryInput> cost_reducer_profiles,
    std::optional<InventoryInput> complex_weapon_profiles,
    std::optional<InventoryInput> danger_profiles,
    std::optional<InventoryInput> dream_defense_profiles,
    std::optional<FullGameBoostInput> ascension_profiles,
    std::optional<InventoryProfileInput> area_profiles,
    std::optional<ActionInput> discard_model_ids,
    std::optional<FullGameGuardianInput> guardian_profiles,
    std::optional<InventoryProfileInput> summon_profiles,
    std::optional<InventoryInput> devil_profiles,
    std::uint64_t apocalypse_after_turns,
    std::optional<FullGamePhenomenonInput> phenomenon_profiles,
    std::optional<ActionInput> fate_model_ids,
    std::optional<ActionInput> exchange_model_ids,
    std::optional<FullGameAttackEffectInput> market_profiles,
    std::optional<InventoryInput> guardian_generated_profiles,
    std::optional<InventoryProfileInput> guardian_action_profiles,
    bool sacrifice_enabled, std::uint16_t resource_cap,
    bool resolve_hidden_targeting, bool resolve_hidden_trades,
    bool resolve_hidden_components,
    std::optional<InventoryProfileInput> role_profiles,
    bool resolve_hidden_removals, bool teams_enabled)
    : batch_size_(validate_dimensions(batch_size, player_count, capacity,
                                      max_turns, max_decisions, initial_hp,
                                      initial_mp, initial_cp, resource_cap)),
      player_count_(player_count), capacity_(capacity), seed_(seed),
      max_turns_(max_turns), max_decisions_(max_decisions),
      initial_mp_(initial_mp), initial_cp_(initial_cp),
      statuses_(batch_size_, player_count, initial_hp),
      inventory_(batch_size_, player_count, inventory_profiles, capacity),
      families_(batch_size_), selected_(batch_size_ * capacity, 0),
      resources_(batch_size_ * player_count, Resources{initial_mp, initial_cp}),
      episodes_(batch_size_) {
  resource_cap_ = resource_cap;
  resolve_hidden_targeting_ = resolve_hidden_targeting;
  resolve_hidden_trades_ = resolve_hidden_trades;
  resolve_hidden_components_ = resolve_hidden_components;
  resolve_hidden_removals_ = resolve_hidden_removals;
  teams_enabled_ = teams_enabled;
  if (utility_profiles.shape(0) == 0 || utility_profiles.shape(0) > 237) {
    throw std::invalid_argument("full-game utility profile count is invalid");
  }
  for (std::size_t row = 0; row < utility_profiles.shape(0); ++row) {
    const auto model = utility_profiles(row, 0);
    const Effect effect{utility_profiles(row, 1), utility_profiles(row, 2),
                        utility_profiles(row, 3)};
    const auto category = inventory_.category(model);
    if ((category != 3 && category != 4) || effect.kind < 1 ||
        effect.kind > 7 ||
        ((effect.kind <= 2 || effect.kind >= 5) &&
         (effect.value < 1 || effect.value > 100)) ||
        ((effect.kind == 3 || effect.kind == 4) && effect.value != 0) ||
        (effect.kind == 5 && (category != 4 || effect.cost == 0)) ||
        (effect.kind >= 6 && category != 3) || effect.cost < 0 ||
        effect.cost > 100 || (category == 3 && effect.cost != 0) ||
        !effects_.emplace(model, effect).second) {
      throw std::invalid_argument(
          "full-game utility profile is invalid or duplicate");
    }
  }
  for (std::size_t env = 0; env < batch_size_; ++env) {
    episodes_[env] = fresh_episode(env, 1);
  }
  if (attack_profiles.has_value() != armor_profiles.has_value())
    throw std::invalid_argument(
        "full-game combat profiles must be supplied together");
  if (attack_profiles) {
    const auto &attacks = *attack_profiles;
    const auto &armor = *armor_profiles;
    if (attacks.shape(1) != 5 || armor.shape(1) != 5 || attacks.shape(0) == 0 ||
        attacks.shape(0) > 237 || armor.shape(0) == 0 || armor.shape(0) > 237)
      throw std::invalid_argument(
          "full-game combat profile dimensions are invalid");
    for (std::size_t row = 0; row < attacks.shape(0); ++row) {
      const auto model = attacks(row, 0);
      const Attack effect{attacks(row, 1), attacks(row, 2), attacks(row, 3),
                          attacks(row, 4)};
      if (effect.value < 0 || effect.value > 65535 || effect.element < 0 ||
          effect.element > 6 || effect.origin < 0 || effect.origin > 1 ||
          inventory_.category(model) != (effect.origin == 0 ? 1 : 4) ||
          effect.cost < 0 || effect.cost > 100 ||
          (effect.origin == 0 ? effect.cost != 0 : effect.cost == 0) ||
          effects_.contains(model) || !attacks_.emplace(model, effect).second)
        throw std::invalid_argument(
            "full-game attack profile is invalid or duplicate");
    }
    for (std::size_t row = 0; row < armor.shape(0); ++row) {
      const auto model = armor(row, 0);
      const Armor effect{armor(row, 1), armor(row, 2)};
      const auto category = inventory_.category(model);
      if ((category != 2 && !(category == 1 && attacks_.contains(model))) ||
          effect.value < 0 || effect.value > 65535 || effect.element < 0 ||
          effect.element > 6 || armor(row, 3) != 0 || armor(row, 4) != 0 ||
          !armor_.emplace(model, effect).second)
        throw std::invalid_argument(
            "full-game armor profile is invalid or duplicate");
    }
  }
  initial_cards_ = initial_cards;
  refill_on_use_ = refill_on_use;
  prayer_gifts_ = prayer_gifts;
  hand_limit_ = hand_limit == 0 ? capacity_ : hand_limit;
  oldest_overflow_ = oldest_overflow;
  if (hand_limit_ > capacity_ || initial_cards_ > hand_limit_ ||
      ((initial_cards_ > 0 || refill_on_use_ || prayer_gifts_ ||
        oldest_overflow_) &&
       !gift_profiles))
    throw std::invalid_argument(
        "full-game acquisition configuration is invalid");
  if (gift_profiles) {
    const auto &profiles = *gift_profiles;
    if (profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument("full-game gift profile count is invalid");
    std::set<std::int64_t> seen;
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0), weight = profiles(row, 1);
      static_cast<void>(inventory_.category(model));
      if (weight < 1 || weight > 500 || !seen.insert(model).second)
        throw std::invalid_argument(
            "full-game gift profile is invalid or duplicate");
      gift_weights_.emplace_back(model, static_cast<std::uint64_t>(weight));
    }
    std::sort(gift_weights_.begin(), gift_weights_.end());
    for (auto &profile : gift_weights_) {
      gift_total_ += profile.second;
      profile.second = gift_total_;
    }
  }
  if (boost_profiles) {
    const auto &profiles = *boost_profiles;
    if (!attack_profiles || profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument(
          "full-game attack composition profile count is invalid");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0),
                 category = inventory_.category(model);
      const Boost boost{profiles(row, 1), profiles(row, 2), profiles(row, 3),
                        profiles(row, 4), profiles(row, 5) == 1};
      if (category < 1 || category > 4 || boost.kind < 0 || boost.kind > 2 ||
          boost.value < (boost.kind == 2 ? 0 : 1) || boost.value > 65535 ||
          (boost.kind == 2 &&
           (boost.value != 0 || boost.can_lead || category != 4)) ||
          boost.element < 0 || boost.element > 6 ||
          (boost.kind == 1 &&
           (boost.element < 1 || boost.element > 4 || category != 1)) ||
          boost.cost < 0 || boost.cost > 100 ||
          (category == 4 ? boost.cost == 0 : boost.cost != 0) ||
          profiles(row, 5) < 0 || profiles(row, 5) > 1 ||
          (boost.can_lead && category != 1 && category != 4) ||
          attacks_.contains(model) || effects_.contains(model) ||
          !boosts_.emplace(model, boost).second)
        throw std::invalid_argument(
            "full-game attack composition profile is invalid or duplicate");
    }
  }
  if (special_profiles) {
    const auto &profiles = *special_profiles;
    if (!attack_profiles || profiles.shape(1) != 5 || profiles.shape(0) == 0 ||
        profiles.shape(0) > 237)
      throw std::invalid_argument(
          "full-game special defense profile dimensions are invalid");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0),
                 category = inventory_.category(model);
      const Special effect{profiles(row, 1), profiles(row, 2), profiles(row, 4),
                           profiles(row, 3) == 1};
      if (category < 1 || category > 4 || category == 3 || effect.kind < 1 ||
          effect.kind > 3 || effect.origin < -1 || effect.origin > 1 ||
          profiles(row, 3) < 0 || profiles(row, 3) > 1 ||
          (effect.neutral_only && effect.origin != 0) ||
          (effect.origin == -1 && (effect.kind != 2 || category != 2)) ||
          effect.cost < 0 || effect.cost > 100 ||
          (category == 4 ? effect.cost == 0 : effect.cost != 0) ||
          (category == 1 && !attacks_.contains(model) &&
           !boosts_.contains(model)) ||
          (category == 2 && effect.origin != -1 && !armor_.contains(model)) ||
          effects_.contains(model) || !specials_.emplace(model, effect).second)
        throw std::invalid_argument(
            "full-game special defense profile is invalid or duplicate");
    }
  }
  if (chance_profiles) {
    const auto &profiles = *chance_profiles;
    if (!attack_profiles || profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument("full-game chance profile count is invalid");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0), rate = profiles(row, 1);
      if (rate < 1 || rate > 99 || !attacks_.contains(model) ||
          attacks_.at(model).value == 0 ||
          !chances_.emplace(model, rate).second)
        throw std::invalid_argument(
            "full-game chance profile is invalid or duplicate");
    }
  }
  if (attack_effect_profiles) {
    const auto &profiles = *attack_effect_profiles;
    if (!attack_profiles || profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument(
          "full-game attack effect profile count is invalid");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0);
      const AttackEffect effect{profiles(row, 1), profiles(row, 2)};
      const bool direct = effect.kind >= 4;
      if (!attacks_.contains(model) || effect.kind < 1 || effect.kind > 5 ||
          (effect.kind == 1 ? effect.value != 0
           : (effect.kind == 2 || effect.kind == 4)
               ? (effect.value != 1 && effect.value != 2 && effect.value != 4 &&
                  effect.value != 8)
               : (effect.value < 1 || effect.value > 4)) ||
          (attacks_.at(model).value == 0) != direct ||
          (direct && attacks_.at(model).origin != 1) ||
          !attack_effects_.emplace(model, effect).second)
        throw std::invalid_argument(
            "full-game attack effect profile is invalid or duplicate");
    }
  }
  for (const auto &[model, attack] : attacks_)
    if (attack.value == 0 && !attack_effects_.contains(model))
      throw std::invalid_argument(
          "full-game zero attack requires a direct curse effect profile");
  if (defense_effect_profiles) {
    const auto &profiles = *defense_effect_profiles;
    if (!armor_profiles || profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument(
          "full-game defense effect profile count is invalid");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0);
      const DefenseEffect effect{profiles(row, 1), profiles(row, 2),
                                 profiles(row, 3), profiles(row, 4)};
      if (!armor_.contains(model) || inventory_.category(model) != 2 ||
          effect.kind < 1 || effect.kind > 6 ||
          effect.element != armor_.at(model).element || effect.rate < 1 ||
          effect.rate > 100 || (effect.kind != 1 && effect.rate != 100) ||
          (effect.kind == 1 && effect.value != 1 && effect.value != 2) ||
          (effect.kind == 2 && effect.value != 1 && effect.value != 2 &&
           effect.value != 4 && effect.value != 8) ||
          (effect.kind == 3 && (effect.value != 2 || effect.element != 0)) ||
          (effect.kind == 4 && (effect.value != 1 || effect.element != 0)) ||
          (effect.kind == 5 && (effect.value != 0 || effect.element != 0)) ||
          (effect.kind == 6 && (effect.value < 1 || effect.value > 4)) ||
          (armor_.at(model).value == 0) != (effect.kind <= 5) ||
          specials_.contains(model) ||
          !defense_effects_.emplace(model, effect).second)
        throw std::invalid_argument(
            "full-game defense effect profile is invalid or duplicate");
    }
  }
  for (const auto &[model, armor] : armor_)
    if (armor.value == 0 && !defense_effects_.contains(model))
      throw std::invalid_argument(
          "full-game zero defense requires a counter or filter profile");
  if (!boosts_.empty() || !chances_.empty() || !defense_effects_.empty())
    attack_order_.resize(batch_size_ * capacity_, 0);
  if (passive_profiles) {
    const auto &profiles = *passive_profiles;
    if (profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument("full-game passive profile count is invalid");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0), hp = profiles(row, 1);
      if (inventory_.category(model) != 3 || hp < 1 || hp > 100 ||
          effects_.contains(model) || attacks_.contains(model) ||
          armor_.contains(model) || boosts_.contains(model) ||
          specials_.contains(model) || !passives_.emplace(model, hp).second)
        throw std::invalid_argument(
            "full-game passive profile is invalid or duplicate");
    }
  }
  if (removal_profiles) {
    const auto &profiles = *removal_profiles;
    if (profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument("full-game removal profile count is invalid");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0), kind = profiles(row, 1),
                 maximum = profiles(row, 2);
      if (inventory_.category(model) != 3 || kind < 1 || kind > 2 ||
          maximum != (kind == 1 ? 3 : 2) || effects_.contains(model) ||
          attacks_.contains(model) || armor_.contains(model) ||
          boosts_.contains(model) || specials_.contains(model) ||
          passives_.contains(model) ||
          !removals_.emplace(model, AttackEffect{kind, maximum}).second)
        throw std::invalid_argument(
            "full-game removal profile is invalid or duplicate");
      // A sundry leader is neither a weapon nor a miracle: Super Mirror only.
      attacks_.emplace(model, Attack{0, 0, 3, 0});
    }
  }
  if (cost_reducer_profiles) {
    const auto &profiles = *cost_reducer_profiles;
    if (profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument(
          "full-game cost reducer profile count is invalid");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0), category = profiles(row, 1);
      const auto attack = profiles(row, 2), defense = profiles(row, 3);
      if (category < 1 || category > 3 ||
          inventory_.category(model) != category || attack < 0 ||
          attack > 65535 || defense < 0 || defense > 65535 ||
          (category == 1 ? attack == 0 || defense != 0 : attack != 0) ||
          (category == 2 ? defense == 0 : defense != 0) ||
          effects_.contains(model) || attacks_.contains(model) ||
          armor_.contains(model) || boosts_.contains(model) ||
          specials_.contains(model) || passives_.contains(model) ||
          removals_.contains(model) || !cost_reducers_.insert(model).second)
        throw std::invalid_argument(
            "full-game cost reducer profile is invalid or duplicate");
      if (category == 1)
        attacks_.emplace(model, Attack{attack, 0, 0, 0});
      if (category == 2)
        armor_.emplace(model, Armor{defense, 0});
    }
    if (attack_order_.empty())
      attack_order_.resize(batch_size_ * capacity_, 0);
  }
  if (complex_weapon_profiles) {
    const auto &profiles = *complex_weapon_profiles;
    if (profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument(
          "full-game complex weapon profile count is invalid");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0);
      const ComplexWeapon weapon{profiles(row, 1), profiles(row, 2),
                                 profiles(row, 3)};
      if (inventory_.category(model) != 1 || weapon.kind < 1 ||
          weapon.kind > 3 || weapon.value < 1 || weapon.value > 65535 ||
          weapon.element < 0 || weapon.element > 6 ||
          effects_.contains(model) || attacks_.contains(model) ||
          armor_.contains(model) || boosts_.contains(model) ||
          specials_.contains(model) || passives_.contains(model) ||
          removals_.contains(model) || cost_reducers_.contains(model) ||
          !complex_weapons_.emplace(model, weapon).second)
        throw std::invalid_argument(
            "full-game complex weapon profile is invalid or duplicate");
      attacks_.emplace(model, Attack{weapon.kind == 1 ? 0 : weapon.value,
                                     weapon.element, 0, 0});
    }
    if (attack_order_.empty())
      attack_order_.resize(batch_size_ * capacity_, 0);
  }
  if (danger_profiles) {
    const auto &profiles = *danger_profiles;
    if (profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument("full-game danger profile count is invalid");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0);
      const Danger danger{profiles(row, 1), profiles(row, 2), profiles(row, 3)};
      if (danger.kind < 1 || danger.kind > 2 ||
          inventory_.category(model) != (danger.kind == 1 ? 1 : 3) ||
          danger.value < 1 || danger.value > (danger.kind == 1 ? 65535 : 100) ||
          danger.element < 0 || danger.element > 6 ||
          (danger.kind == 2 && danger.element != 0) ||
          effects_.contains(model) || attacks_.contains(model) ||
          armor_.contains(model) || boosts_.contains(model) ||
          specials_.contains(model) || passives_.contains(model) ||
          removals_.contains(model) || cost_reducers_.contains(model) ||
          complex_weapons_.contains(model) ||
          !dangers_.emplace(model, danger).second)
        throw std::invalid_argument(
            "full-game danger profile is invalid or duplicate");
      if (danger.kind == 1)
        attacks_.emplace(model, Attack{danger.value, danger.element, 0, 0});
    }
    if (attack_order_.empty())
      attack_order_.resize(batch_size_ * capacity_, 0);
  }
  if (dream_defense_profiles) {
    const auto &profiles = *dream_defense_profiles;
    if (gift_total_ == 0 || profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument(
          "full-game Dream defense requires profiles and gift weights");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0), value = profiles(row, 1);
      const auto element = profiles(row, 2), mask = profiles(row, 3);
      if (inventory_.category(model) != 2 || value < 1 || value > 65535 ||
          element < 0 || element > 6 || mask != kCurseDreamBit ||
          effects_.contains(model) || attacks_.contains(model) ||
          armor_.contains(model) || boosts_.contains(model) ||
          specials_.contains(model) || passives_.contains(model) ||
          removals_.contains(model) || cost_reducers_.contains(model) ||
          complex_weapons_.contains(model) || dangers_.contains(model))
        throw std::invalid_argument(
            "full-game Dream defense profile is invalid or duplicate");
      armor_.emplace(model, Armor{value, element});
      defense_effects_.emplace(model, DefenseEffect{7, mask, element, 100});
    }
    if (attack_order_.empty())
      attack_order_.resize(batch_size_ * capacity_, 0);
  }
  if (ascension_profiles) {
    const auto &profiles = *ascension_profiles;
    if (profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument(
          "full-game Ascension profile count is invalid");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0);
      const Ascension bow{profiles(row, 1), profiles(row, 2), profiles(row, 3),
                          profiles(row, 4), profiles(row, 5)};
      if (inventory_.category(model) != 1 || bow.attack < 1 ||
          bow.attack > 65535 || bow.dying_attack < 1 ||
          bow.dying_attack > 65535 || bow.rate < 1 || bow.rate >= 100 ||
          bow.dying_rate < 1 || bow.dying_rate >= 100 || bow.element < 0 ||
          bow.element > 6 || effects_.contains(model) ||
          attacks_.contains(model) || armor_.contains(model) ||
          boosts_.contains(model) || specials_.contains(model) ||
          passives_.contains(model) || removals_.contains(model) ||
          cost_reducers_.contains(model) || complex_weapons_.contains(model) ||
          dangers_.contains(model) || chances_.contains(model) ||
          !ascensions_by_model_.emplace(model, bow).second)
        throw std::invalid_argument(
            "full-game Ascension profile is invalid or duplicate");
      attacks_.emplace(model, Attack{bow.attack, bow.element, 0, 0});
      chances_.emplace(model, bow.rate);
    }
    if (attack_order_.empty())
      attack_order_.resize(batch_size_ * capacity_, 0);
  }
  if (area_profiles) {
    const auto &profiles = *area_profiles;
    if (!attack_profiles || profiles.shape(0) == 0 || profiles.shape(0) > 237)
      throw std::invalid_argument(
          "full-game area profile count or combat dependency is invalid");
    for (std::size_t row = 0; row < profiles.shape(0); ++row) {
      const auto model = profiles(row, 0), cost = profiles(row, 1);
      if (inventory_.category(model) != 4 || cost < 1 || cost > 100 ||
          effects_.contains(model) || attacks_.contains(model) ||
          armor_.contains(model) || boosts_.contains(model) ||
          specials_.contains(model) || passives_.contains(model) ||
          removals_.contains(model) || cost_reducers_.contains(model) ||
          complex_weapons_.contains(model) || dangers_.contains(model) ||
          ascensions_by_model_.contains(model) ||
          !area_costs_.emplace(model, cost).second)
        throw std::invalid_argument(
            "full-game area profile is invalid or duplicate");
      boosts_.emplace(model, Boost{0, 0, cost, 3, false});
    }
    if (attack_order_.empty())
      attack_order_.resize(batch_size_ * capacity_, 0);
  }
  if (guardian_profiles) {
    const auto &rows = *guardian_profiles;
    if (!attack_profiles || rows.shape(0) == 0 || rows.shape(0) > 40)
      throw std::invalid_argument(
          "full-game guardian profile count or combat dependency is invalid");
    for (std::size_t i = 0; i < rows.shape(0); ++i) {
      const auto model = rows(i, 0);
      const GuardianEffect e{rows(i, 1), rows(i, 2), rows(i, 3),
                             rows(i, 4), rows(i, 5), rows(i, 6),
                             rows(i, 7), rows(i, 8), rows(i, 9)};
      if (model < 245 || model > 284 || e.group < 0 || e.group > 7 ||
          e.weight < 1 || e.weight > 20 || e.attack < 0 || e.attack > 65535 ||
          e.element < 0 || e.element > 6 || e.rate < 1 || e.rate > 100 ||
          e.kind < 0 || e.kind > 10 || e.value < 0 || e.value > 100 ||
          (e.origin != 0 && e.origin != 4) ||
          (e.kind == 2 || e.kind == 3
               ? e.curse != 1 && e.curse != 2 && e.curse != 4 && e.curse != 8
               : e.curse != 0) ||
          (e.kind <= 2 ? e.attack == 0 : e.attack != 0) ||
          (e.kind >= 5 ? e.value == 0 : e.value != 0) ||
          (e.kind >= 4 && e.rate != 100) ||
          !guardian_effects_.emplace(model, e).second)
        throw std::invalid_argument(
            "full-game guardian profile is invalid or duplicate");
      auto &weights = guardian_weights_[static_cast<std::size_t>(e.group)];
      weights.emplace_back(
          model, e.weight + (weights.empty() ? 0 : weights.back().second));
    }
  }
  if (summon_profiles) {
    const auto &rows = *summon_profiles;
    if (!guardian_profiles || rows.shape(0) == 0 || rows.shape(0) > 237 ||
        std::any_of(guardian_weights_.begin(), guardian_weights_.end(),
                    [](const auto &w) { return w.empty(); }))
      throw std::invalid_argument(
          "full-game summon profiles require all standard guardian groups");
    for (std::size_t i = 0; i < rows.shape(0); ++i) {
      const auto model = rows(i, 0), cost = rows(i, 1),
                 category = inventory_.category(model);
      if ((category != 3 && category != 4) || cost < 0 || cost > 100 ||
          (category == 3 && cost != 0) || effects_.contains(model) ||
          attacks_.contains(model) || armor_.contains(model) ||
          boosts_.contains(model) || specials_.contains(model) ||
          passives_.contains(model) || removals_.contains(model) ||
          dangers_.contains(model) || cost_reducers_.contains(model) ||
          !summon_models_.insert(model).second)
        throw std::invalid_argument(
            "full-game summon profile is invalid or duplicate");
      effects_.emplace(model, Effect{8, 0, cost});
    }
    if (attack_order_.empty())
      attack_order_.resize(batch_size_ * capacity_, 0);
  }
  if (discard_model_ids) {
    const auto &models = *discard_model_ids;
    if (models.shape(0) == 0 || models.shape(0) > 237)
      throw std::invalid_argument("full-game discard model count is invalid");
    for (std::size_t i = 0; i < models.shape(0); ++i) {
      const auto model = models(i), category = inventory_.category(model);
      if (category < 2 || category > 5 || model == 208 || model == 209 ||
          !discard_models_.insert(model).second)
        throw std::invalid_argument(
            "full-game discard model is forbidden or duplicate");
    }
    if (attack_order_.empty())
      attack_order_.resize(batch_size_ * capacity_, 0);
  }
  if (apocalypse_after_turns > 1000000000 ||
      (apocalypse_after_turns != 0 && (!devil_profiles || !gift_profiles)))
    throw std::invalid_argument(
        "full-game Apocalypse threshold requires devil and gift profiles");
  apocalypse_after_turns_ = apocalypse_after_turns;
  if (sacrifice_enabled && (!discard_model_ids || !gift_profiles))
    throw std::invalid_argument(
        "full-game Sacrifice requires discard and gift profiles");
  sacrifice_enabled_ = sacrifice_enabled;
  if (devil_profiles) {
    const auto &rows = *devil_profiles;
    if (rows.shape(0) == 0 || rows.shape(0) > 5)
      throw std::invalid_argument("full-game devil profile count is invalid");
    std::uint64_t total = 0;
    for (std::size_t row = 0; row < rows.shape(0); ++row) {
      const auto model = rows(row, 0);
      const Devil effect{rows(row, 1), rows(row, 2), rows(row, 3)};
      if (model < 240 || model > 244 || effect.weight < 1 ||
          effect.weight > 100 ||
          effect.kind != (model < 243    ? 1
                          : model == 243 ? 2
                                         : 3) ||
          effect.value != (model < 243    ? (model - 239) * 10
                           : model == 243 ? 2
                                          : 10) ||
          !devils_by_model_.emplace(model, effect).second)
        throw std::invalid_argument(
            "full-game devil profile is invalid or duplicate");
      total += static_cast<std::uint64_t>(effect.weight);
      if (total > 100)
        throw std::invalid_argument(
            "full-game devil appearance total exceeds 100 percent");
      devil_weights_.emplace_back(model, total);
    }
  }
  if (phenomenon_profiles) {
    const auto &rows = *phenomenon_profiles;
    if (rows.shape(0) == 0 || rows.shape(0) > 10)
      throw std::invalid_argument(
          "full-game phenomenon profile count is invalid");
    constexpr std::array<std::int64_t, 10> values{2,  1,  3, 1, 50,
                                                  30, 50, 0, 0, 0};
    for (std::size_t i = 0; i < rows.shape(0); ++i) {
      const auto model = rows(i, 0);
      const Phenomenon effect{rows(i, 1), rows(i, 2), rows(i, 3), rows(i, 4)};
      if (model < 287 || model > 296 || effect.kind != model - 286 ||
          effect.value != values[static_cast<std::size_t>(model - 287)] ||
          effect.element != (effect.kind == 5   ? 5
                             : effect.kind == 6 ? 6
                                                : 0) ||
          effect.rate < 1 || effect.rate > 100 ||
          (effect.kind != 6 && effect.rate != 100) ||
          (effect.kind == 10 &&
           (!guardian_profiles ||
            std::any_of(guardian_weights_.begin(), guardian_weights_.end(),
                        [](const auto &w) { return w.empty(); }))) ||
          ((effect.kind == 5 || effect.kind == 6) && !attack_profiles) ||
          !phenomena_.emplace(model, effect).second)
        throw std::invalid_argument(
            "full-game phenomenon profile is invalid or lacks dependencies");
    }
  }
  if (fate_model_ids) {
    const auto &models = *fate_model_ids;
    if (!phenomenon_profiles || models.shape(0) != 1 || models(0) != 207 ||
        inventory_.category(207) != 3 || effects_.contains(207) ||
        attacks_.contains(207) || boosts_.contains(207) ||
        specials_.contains(207) || removals_.contains(207))
      throw std::invalid_argument("full-game Fate requires phenomenon profiles "
                                  "and its unique source role");
    effects_.emplace(207, Effect{9, 0, 0});
    if (attack_order_.empty())
      attack_order_.resize(batch_size_ * capacity_, 0);
  }
  if (exchange_model_ids) {
    const auto &models = *exchange_model_ids;
    if (models.shape(0) != 1 || models(0) != 3 || inventory_.category(3) != 5 ||
        effects_.contains(3) || attacks_.contains(3) || boosts_.contains(3) ||
        specials_.contains(3) || removals_.contains(3))
      throw std::invalid_argument(
          "full-game Exchange requires its unique source trade role");
    exchange_models_.insert(3);
  }
  if (market_profiles) {
    const auto &rows = *market_profiles;
    if (rows.shape(0) != inventory_.categories_.size())
      throw std::invalid_argument(
          "full-game market prices must cover every held model");
    for (std::size_t row = 0; row < rows.shape(0); ++row) {
      const auto model = rows(row, 0), kind = rows(row, 1),
                 price = rows(row, 2);
      static_cast<void>(inventory_.category(model));
      if (kind != (model >= 3 && model <= 5 ? model - 2 : 0) || price < 0 ||
          price > 100 || !market_prices_.emplace(model, price).second)
        throw std::invalid_argument(
            "full-game market price is invalid or duplicate");
    }
    for (const auto model : {4, 5})
      if (!market_prices_.contains(model) || inventory_.category(model) != 5 ||
          effects_.contains(model) || attacks_.contains(model) ||
          boosts_.contains(model) || specials_.contains(model))
        throw std::invalid_argument(
            "full-game Sell/Buy requires unique trade roles");
    if (attack_order_.empty())
      attack_order_.resize(batch_size_ * capacity_, 0);
  }
  if (guardian_generated_profiles) {
    const auto &rows = *guardian_generated_profiles;
    if (rows.shape(0) == 0 || rows.shape(0) > 237 || guardian_effects_.empty())
      throw std::invalid_argument("full-game guardian generated profile count "
                                  "or dependency is invalid");
    std::set<std::int64_t> seen;
    for (std::size_t row = 0; row < rows.shape(0); ++row) {
      const auto group = rows(row, 0), model = rows(row, 1),
                 category = rows(row, 2), weight = rows(row, 3);
      if (model < 3 || model > 239 || (group != 9 && group != 10) ||
          category != inventory_.category(model) ||
          (category == 4 ? group != 10 : group != 9) || weight < 1 ||
          weight > 500 || !seen.insert(model).second)
        throw std::invalid_argument(
            "full-game guardian generated profile is invalid or duplicate");
      guardian_generated_weights_[static_cast<std::size_t>(group - 9)]
          .emplace_back(model, static_cast<std::uint64_t>(weight));
    }
    for (auto &pool : guardian_generated_weights_) {
      std::sort(pool.begin(), pool.end());
      std::uint64_t total = 0;
      for (auto &entry : pool) {
        total += entry.second;
        if (total > 500)
          throw std::invalid_argument(
              "full-game guardian generated pool weight exceeds500");
        entry.second = total;
      }
    }
  }
  if (guardian_action_profiles) {
    const auto &rows = *guardian_action_profiles;
    if (!guardian_generated_profiles || rows.shape(0) == 0 ||
        rows.shape(0) > 237)
      throw std::invalid_argument(
          "full-game guardian action profile count or dependency is invalid");
    for (std::size_t row = 0; row < rows.shape(0); ++row) {
      const auto model = rows(row, 0), route = rows(row, 1);
      const auto category = inventory_.category(model);
      const bool drop = category == 2 || model == 203 || model == 204 ||
                        model == 208 || model == 209;
      const bool moon = model >= 231 && model <= 234;
      if (model < 3 || model > 239 || route < 1 || route > 7 ||
          ((route == 6) != drop) || ((route == 7) != moon) ||
          (route == 3 && model != 3) || (route == 4 && model != 4) ||
          (route == 5 && model != 5) || (category == 5 && route != model) ||
          (route == 2 && category != 3 && category != 4) ||
          !guardian_action_routes_.emplace(model, route).second)
        throw std::invalid_argument(
            "full-game guardian action profile is invalid or duplicate");
    }
    for (const auto &pool : guardian_generated_weights_)
      for (const auto &entry : pool)
        if (!guardian_action_routes_.contains(entry.first))
          throw std::invalid_argument("full-game guardian action profiles do "
                                      "not cover the generated pool");
  }
  if (resolve_hidden_removals_ && discard_models_.empty())
    throw std::invalid_argument(
        "full-game hidden removal retention requires discard profiles");
  if (resolve_hidden_components_ && !role_profiles)
    throw std::invalid_argument(
        "full-game hidden components require a complete role manifest");
  if (role_profiles) {
    const auto &rows = *role_profiles;
    if (rows.shape(0) != 237)
      throw std::invalid_argument(
          "full-game role manifest must cover all 237 held models");
    for (std::size_t row = 0; row < rows.shape(0); ++row) {
      const auto model = rows(row, 0), bits = rows(row, 1);
      if (model != static_cast<std::int64_t>(row + 3) || bits < 1 ||
          bits > 511 || registered_roles(model) != bits)
        throw std::invalid_argument("full-game role manifest differs from "
                                    "registered native capabilities");
      role_profiles_.emplace(model, bits);
    }
  }
}

FullGameBatch::Episode
FullGameBatch::fresh_episode(std::size_t env,
                             std::int64_t epoch) const noexcept {
  Episode episode;
  episode.epoch = epoch;
  episode.illness_rng =
      seed_ ^ (static_cast<std::uint64_t>(env) + 1) * 0x9e3779b97f4a7c15ULL ^
      static_cast<std::uint64_t>(epoch) * 0xbf58476d1ce4e5b9ULL;
  episode.gift_rng = episode.illness_rng ^ 0x94d049bb133111ebULL;
  episode.combat_rng = episode.illness_rng ^ 0xd2b74407b1ce6e93ULL;
  episode.model_rng = episode.illness_rng ^ 0xca5a826395121157ULL;
  episode.bounce_rng = episode.illness_rng ^ 0x8cb92baa3f3d8dd7ULL;
  episode.chance_rng = episode.illness_rng ^ 0xe19b01aa9d42c633ULL;
  episode.chance_target_rng = episode.illness_rng ^ 0xc6bc279692b5c323ULL;
  episode.counter_rng = episode.illness_rng ^ 0x8f43c615b2ea970dULL;
  episode.removal_rng = episode.illness_rng ^ 0x243f6a8885a308d3ULL;
  episode.utility_rng = episode.illness_rng ^ 0x13198a2e03707344ULL;
  episode.danger_rng = episode.illness_rng ^ 0xa4093822299f31d0ULL;
  episode.redraw_model_rng = episode.illness_rng ^ 0x452821e638d01377ULL;
  episode.redraw_disguise_rng = episode.illness_rng ^ 0xbe5466cf34e90c6cULL;
  episode.attractor_rng = episode.illness_rng ^ 0x082efa98ec4e6c89ULL;
  episode.ascension_rng = episode.illness_rng ^ 0xc0ac29b7c97c50ddULL;
  episode.guardian_summon_rng = episode.illness_rng ^ 0x3f84d5b5b5470917ULL;
  episode.guardian_trigger_rng = episode.illness_rng ^ 0x9216d5d98979fb1bULL;
  episode.guardian_model_rng = episode.illness_rng ^ 0xd1310ba698dfb5acULL;
  episode.guardian_target_rng = episode.illness_rng ^ 0x2ffd72dbd01adfb7ULL;
  episode.guardian_hit_rng = episode.illness_rng ^ 0xb8e1afed6a267e96ULL;
  episode.guardian_departure_rng = episode.illness_rng ^ 0xba7c9045f12c7f99ULL;
  episode.guardian_generated_rng = episode.illness_rng ^ 0x2ba9c55d741831f6ULL;
  episode.guardian_receipt_rng = episode.illness_rng ^ 0xce5c3e169b87931eULL;
  episode.guardian_allocation_rng = episode.illness_rng ^ 0xd7a34e5f18b9026cULL;
  episode.devil_rng = episode.illness_rng ^ 0x24a19947b3916cf7ULL;
  episode.devil_removal_rng = episode.illness_rng ^ 0x0801f2e2858efc16ULL;
  episode.devil_charity_rng = episode.illness_rng ^ 0x636920d871574e69ULL;
  episode.phenomenon_rng = episode.illness_rng ^ 0xa458fea3f4933d7eULL;
  episode.phenomenon_target_rng = episode.illness_rng ^ 0x0d95748f728eb658ULL;
  episode.phenomenon_hit_rng = episode.illness_rng ^ 0x718bcd5882154aeeULL;
  episode.phenomenon_shuffle_rng = episode.illness_rng ^ 0x7b54a41dc25a59b5ULL;
  episode.phenomenon_disguise_rng = episode.illness_rng ^ 0x9c30d5392af26013ULL;
  episode.confusion_rng = episode.illness_rng ^ 0xc5d1b023286085f0ULL;
  episode.confusion_target_rng = episode.illness_rng ^ 0xca417918b8db38efULL;
  episode.exchange_rng = episode.illness_rng ^ 0xb8e1afed6a267e96ULL;
  episode.hidden_targeting_rng = episode.illness_rng ^ 0x6c9e0e8bb01e8a3eULL;
  episode.hidden_exchange_rng = episode.illness_rng ^ 0x7c4a7f8c93c4d7a1ULL;
  episode.hidden_sale_rng = episode.illness_rng ^ 0xb31f2c8e57a04d69ULL;
  episode.hidden_market_target_rng =
      episode.illness_rng ^ 0x9e87c4d1b62a503fULL;
  episode.market_target_rng = episode.illness_rng ^ 0xba7c9045f12c7f99ULL;
  episode.market_offer_rng = episode.illness_rng ^ 0x24a19947b3916cf7ULL;
  episode.market_disguise_rng = episode.illness_rng ^ 0x0801f2e2858efc16ULL;
  episode.market_purchase_rng = episode.illness_rng ^ 0x636920d871574e69ULL;
  episode.market_sale_rng = episode.illness_rng ^ 0xa1f1651d92b39463ULL;
  return episode;
}

std::vector<std::size_t>
FullGameBatch::checked_environments(ActionInput environments) const {
  if (environments.shape(0) > batch_size_) {
    throw std::invalid_argument("full-game environment row limit exceeded");
  }
  std::vector<std::size_t> result;
  result.reserve(environments.shape(0));
  std::set<std::size_t> seen;
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    const auto env = environments(row);
    if (env < 0 || static_cast<std::uint64_t>(env) >= batch_size_ ||
        !seen.insert(static_cast<std::size_t>(env)).second) {
      throw std::invalid_argument(
          "full-game environment is invalid or duplicate");
    }
    result.push_back(static_cast<std::size_t>(env));
  }
  return result;
}

void FullGameBatch::require_setup(std::size_t environment) const {
  if (episodes_[environment].phase != 0) {
    throw std::invalid_argument("full-game setup is sealed after starting");
  }
}

void FullGameBatch::seed_players(ActionInput environments, ActionInput owners,
                                 InventoryInput state, ActionInput masks) {
  if (environments.shape(0) > statuses_.states_.size()) {
    throw std::invalid_argument("full-game setup owner row limit exceeded");
  }
  const auto indices = statuses_.checked_players(environments, owners, false);
  CurseDynamicsBatch::same_length(indices.size(), masks);
  if (state.shape(0) != indices.size()) {
    throw std::invalid_argument("full-game setup input lengths differ");
  }
  for (std::size_t row = 0; row < indices.size(); ++row) {
    require_setup(indices[row] / player_count_);
    if (state(row, 0) < 0 || state(row, 0) > resource_cap_ ||
        state(row, 1) < 0 || state(row, 1) > resource_cap_ ||
        state(row, 2) < 0 || state(row, 2) > resource_cap_ ||
        state(row, 3) < 0 || state(row, 3) > 4 || masks(row) < 0 ||
        masks(row) > 15) {
      throw std::invalid_argument(
          "full-game setup resource or status is out of range");
    }
  }
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto index = indices[row];
    const auto before = statuses_.states_[index];
    statuses_.states_[index] = {state(row, 0), state(row, 3), masks(row), 0};
    resources_[index] = {state(row, 1), state(row, 2)};
    statuses_.record(index, 1, before);
  }
}

void FullGameBatch::seed_hand(std::size_t env, std::size_t owner,
                              InventoryInput items) {
  if (env >= batch_size_)
    throw std::invalid_argument("full-game environment is out of range");
  require_setup(env);
  inventory_.seed_hand(env, owner, items);
  for (std::size_t row = 0; row < items.shape(0); ++row)
    episodes_[env].next_instance =
        std::max(episodes_[env].next_instance, items(row, 0) + 1);
}

void FullGameBatch::seed_guardians(ActionInput environments, ActionInput owners,
                                   ActionInput groups) {
  const auto indices = inventory_.checked_owners(environments, owners);
  DreamInventoryBatch::same_length(indices.size(), groups);
  std::set<std::size_t> seen;
  std::map<std::size_t, Episode> staged;
  for (std::size_t i = 0; i < indices.size(); ++i) {
    const auto env = indices[i] / player_count_,
               seat = indices[i] % player_count_;
    require_setup(env);
    const auto group = groups(i);
    if (group < 0 || group > 10 || !seen.insert(indices[i]).second ||
        (group != 0 && (guardian_effects_.empty() ||
                        (group <= 8 && guardian_weights_[group - 1].empty()))))
      throw std::invalid_argument(
          "full-game guardian setup group or duplicate owner is invalid");
    auto &episode = staged.try_emplace(env, episodes_[env]).first->second;
    if (episode.next_guardian_instance > kMaximumCounter)
      throw std::invalid_argument("full-game guardian identities exhausted");
    episode.guardians[seat] = {
        group, group == 0 ? 0 : episode.next_guardian_instance++};
  }
  for (const auto &[env, episode] : staged)
    episodes_[env] = episode;
}

void FullGameBatch::summon_guardian(Mutation &mutation,
                                    std::size_t owner) const {
  auto &e = mutation.episode;
  if (e.next_guardian_instance > kMaximumCounter)
    throw std::invalid_argument("full-game guardian identities exhausted");
  ++e.guardian_stats[0];
  e.guardian_stats[1] += e.guardians[owner][0] != 0 ? 1 : 0;
  e.guardians[owner] = {
      static_cast<std::int64_t>(random_rank(e.guardian_summon_rng, 10)) + 1,
      e.next_guardian_instance++};
}

void FullGameBatch::guardian_damage(Mutation &mutation, std::size_t owner,
                                    std::int64_t loss) const {
  auto &e = mutation.episode;
  if (loss <= 0 || e.guardians[owner][0] == 0)
    return;
  if (mutation.statuses[owner][0] == 0) {
    e.guardians[owner] = {0, 0};
    ++e.guardian_stats[12];
    return;
  }
  ++e.guardian_stats[10];
  if (random_rank(e.guardian_departure_rng, 100) < 10) {
    e.guardians[owner] = {0, 0};
    ++e.guardian_stats[11];
  }
}

void FullGameBatch::schedule_guardians(Mutation &mutation,
                                       std::size_t turn_owner) const {
  auto &e = mutation.episode;
  std::vector<QueuedAttack> shots;
  for (std::size_t owner = 0; owner < player_count_; ++owner) {
    const auto group = e.guardians[owner][0];
    if (!are_enemies(e, owner, turn_owner) ||
        mutation.statuses[owner][0] <= 0 || group == 0)
      continue;
    ++e.guardian_stats[2];
    if (random_rank(e.guardian_trigger_rng, 100) >= 25)
      continue;
    ++e.guardian_stats[3];
    if (group > 8) {
      const auto &pool =
          guardian_generated_weights_[static_cast<std::size_t>(group - 9)];
      if (pool.empty() || guardian_action_routes_.empty())
        throw std::invalid_argument("full-game Earth/Moon guardian producer "
                                    "requires generated action profiles");
      const auto model = draw_generated_model(mutation, group);
      ++e.guardian_stats[4];
      ++e.guardian_generated_stats[group == 9 ? 0 : 7];
      ++e.guardian_generated_stats[1];
      ++e.guardian_generated_model_counts[static_cast<std::size_t>(model - 3)];
      QueuedAttack producer{8,
                            static_cast<std::int64_t>(owner),
                            static_cast<std::int64_t>(owner),
                            0,
                            0,
                            4,
                            100};
      producer.guardian_model = group == 9 ? 285 : 286;
      producer.guardian_instance = e.guardians[owner][1];
      producer.generated_model = model;
      shots.push_back(producer);
      continue;
    }
    const auto &weights = guardian_weights_[group - 1];
    const auto ticket =
        random_rank(e.guardian_model_rng, weights.back().second);
    const auto model = std::upper_bound(weights.begin(), weights.end(), ticket,
                                        [](auto rank, const auto &row) {
                                          return rank < row.second;
                                        })
                           ->first;
    ++e.guardian_stats[4];
    ++e.guardian_model_counts[static_cast<std::size_t>(model - 245)];
    const auto &effect = guardian_effects_.at(model);
    const bool automatic = effect.kind >= 4 && effect.kind <= 8;
    auto target = static_cast<std::int64_t>(owner);
    if (!automatic) {
      std::array<std::int64_t, 8> enemies{};
      std::size_t count = 0;
      for (std::size_t seat = 0; seat < player_count_; ++seat)
        if (are_enemies(e, owner, seat) && mutation.statuses[seat][0] > 0)
          enemies[count++] = static_cast<std::int64_t>(seat);
      target = static_cast<std::int64_t>(turn_owner);
      if (count != 0) {
        target = enemies[random_rank(e.guardian_target_rng, count)];
        ++e.guardian_stats[5];
      }
    }
    const auto kind = effect.kind == 3    ? 4
                      : effect.kind == 9  ? 11
                      : effect.kind == 10 ? 7
                                          : effect.kind;
    QueuedAttack shot{4,
                      static_cast<std::int64_t>(owner),
                      target,
                      effect.attack,
                      effect.element,
                      effect.origin,
                      effect.rate,
                      kind,
                      effect.kind == 2 || effect.kind == 3 ? effect.curse
                                                           : effect.value};
    shot.guardian_model = model;
    shot.guardian_instance = e.guardians[owner][1];
    shot.guardian_automatic = automatic;
    shots.push_back(shot);
  }
  for (auto it = shots.rbegin(); it != shots.rend(); ++it) {
    enqueue_attack(mutation, *it);
    ++e.guardian_stats[6];
  }
}

void FullGameBatch::apply_guardian_automatic(Mutation &mutation,
                                             const QueuedAttack &shot) const {
  const auto owner = static_cast<std::size_t>(shot.source);
  const auto &effect = guardian_effects_.at(shot.guardian_model);
  auto &e = mutation.episode;
  if (effect.kind == 4) {
    auto &status = mutation.statuses[owner];
    const auto before = status[2];
    status[1] = cured_illness_stage(static_cast<std::uint8_t>(status[1]), true);
    status[2] =
        cured_documented_mask(static_cast<std::uint8_t>(status[2]), true);
    if ((before & kCurseDreamBit) != 0) {
      auto &hand = stage_hand(mutation, owner);
      for (auto &item : hand) {
        mutation.restored += item[2] != 0 ? 1 : 0;
        item[2] = 0;
      }
    }
    ++e.guardian_stats[18];
  } else if (effect.kind == 5) {
    const auto gain = std::min<std::int64_t>(
        effect.value, resource_cap_ - mutation.statuses[owner][0]);
    mutation.statuses[owner][0] += gain;
    e.guardian_stats[14] += gain;
  } else if (effect.kind == 6) {
    const auto gain = std::min<std::int64_t>(
        effect.value, resource_cap_ - mutation.resources[owner][0]);
    mutation.resources[owner][0] += gain;
    e.guardian_stats[15] += gain;
  } else {
    for (std::size_t seat = 0; seat < player_count_; ++seat) {
      if ((effect.kind != 8 && seat != owner) ||
          mutation.statuses[seat][0] <= 0)
        continue;
      const auto credit = credit_cp_capped({mutation.statuses[seat][0],
                                            mutation.resources[seat][0],
                                            mutation.resources[seat][1]},
                                           effect.value, resource_cap_);
      mutation.resources[seat][1] = credit.wallet.cp;
      e.guardian_stats[16] += credit.credited;
    }
  }
}

void FullGameBatch::deal_cards(ActionInput envs, ActionInput owners,
                               ActionInput instances, ActionInput models) {
  const auto indices = inventory_.checked_owners(envs, owners);
  DreamInventoryBatch::same_length(indices.size(), instances);
  DreamInventoryBatch::same_length(indices.size(), models);
  if (indices.empty())
    return;
  std::vector<std::int64_t> masks(indices.size()), disguise(indices.size(), 99),
      fake(indices.size(), 0);
  std::map<std::size_t, Episode> staged;
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto env = indices[row] / player_count_;
    require_setup(env);
    const auto category = inventory_.category(models(row));
    if (instances(row) < 1 || instances(row) > kMaximumCounter)
      throw std::invalid_argument(
          "full-game setup gift instance is out of range");
    auto [found, inserted] = staged.try_emplace(env, episodes_[env]);
    static_cast<void>(inserted);
    found->second.next_instance =
        std::max(found->second.next_instance, instances(row) + 1);
    masks[row] = statuses_.states_[indices[row]][2];
    if ((masks[row] & kCurseDreamBit) != 0) {
      disguise[row] =
          static_cast<std::int64_t>(random_rank(found->second.gift_rng, 100));
      if (disguise[row] < 50) {
        fake[row] = static_cast<std::int64_t>(random_rank(
            found->second.gift_rng,
            inventory_.fake_pools_[static_cast<std::size_t>(category - 1)]
                .size()));
      }
    }
  }
  const ActionInput mask_input(masks.data(), {masks.size()});
  const ActionInput disguise_input(disguise.data(), {disguise.size()});
  const ActionInput fake_input(fake.data(), {fake.size()});
  inventory_.add_cards(envs, owners, instances, models, mask_input,
                       disguise_input, fake_input);
  // Gift mutation succeeded: committing its RNG cannot throw.
  for (const auto &[env, episode] : staged)
    episodes_[env] = episode;
}

void FullGameBatch::start_environments(ActionInput environments) {
  const auto indices = checked_environments(environments);
  std::vector<Mutation> staged;
  staged.reserve(indices.size());
  for (const auto env : indices) {
    require_setup(env);
    for (std::size_t seat = 0; seat < player_count_; ++seat) {
      const auto owner = env * player_count_ + seat;
      if (inventory_.sizes_[owner] > hand_limit_ ||
          (initial_cards_ > 0 && statuses_.states_[owner][0] > 0 &&
           inventory_.sizes_[owner] != 0))
        throw std::invalid_argument("full-game automatic deal requires empty "
                                    "living hands within the hand limit");
    }
    auto mutation = staged_episode(env);
    auto &episode = mutation.episode;
    episode.phase = 1;
    decide_outcome(mutation);
    if (episode.phase == 1) {
      for (std::size_t player = 0; player < player_count_; ++player) {
        if (mutation.statuses[player][0] > 0) {
          episode.actor = static_cast<std::int64_t>(player);
          break;
        }
      }
      for (std::size_t player = 0; player < player_count_; ++player)
        if (mutation.statuses[player][0] > 0)
          for (std::size_t card = 0; card < initial_cards_; ++card)
            grant_gift(mutation, player);
    }
    staged.push_back(std::move(mutation));
  }
  for (auto &mutation : staged)
    commit(mutation);
}

bool FullGameBatch::visible_utility_eligible(
    std::size_t owner, const Effect &effect) const noexcept {
  const auto &status = statuses_.states_[owner];
  if (status[0] == 0 ||
      (cost_reducers_.empty() && resources_[owner][0] < effect.cost))
    return false;
  if (effect.kind == 1)
    return status[0] < resource_cap_;
  if (effect.kind == 2)
    return resources_[owner][0] < resource_cap_;
  if (effect.kind == 5)
    return resources_[owner][1] < resource_cap_;
  if (effect.kind >= 6)
    return true; // Status/risk component remains meaningful at full resources.
  const auto stage = static_cast<std::uint8_t>(status[1]);
  const auto mask = static_cast<std::uint8_t>(status[2]);
  return cured_illness_stage(stage, effect.kind == 4) != stage ||
         cured_documented_mask(mask, effect.kind == 4) != mask;
}

bool FullGameBatch::compatible(std::int64_t attack,
                               std::int64_t defense) noexcept {
  return armor_element_compatible(attack, defense);
}

FullGameBatch::Mutation FullGameBatch::staged_episode(std::size_t env) const {
  Mutation mutation{};
  mutation.environment = env;
  mutation.episode = episodes_[env];
  mutation.family = families_[env];
  for (std::size_t seat = 0; seat < player_count_; ++seat) {
    mutation.statuses[seat] = statuses_.states_[env * player_count_ + seat];
    mutation.resources[seat] = resources_[env * player_count_ + seat];
  }
  std::copy_n(selected_.begin() + static_cast<std::ptrdiff_t>(env * capacity_),
              capacity_, mutation.selected.begin());
  if (!attack_order_.empty())
    std::copy_n(attack_order_.begin() +
                    static_cast<std::ptrdiff_t>(env * capacity_),
                capacity_, mutation.order.begin());
  return mutation;
}

std::vector<DreamInventoryBatch::Item> &
FullGameBatch::stage_hand(Mutation &mutation, std::size_t seat) const {
  auto [found, inserted] = mutation.hands.try_emplace(seat);
  if (inserted) {
    const auto owner = mutation.environment * player_count_ + seat;
    const auto first = inventory_.items_.begin() +
                       static_cast<std::ptrdiff_t>(owner * capacity_);
    found->second.assign(
        first, first + static_cast<std::ptrdiff_t>(inventory_.sizes_[owner]));
  }
  return found->second;
}

std::int64_t FullGameBatch::grant_gift(Mutation &mutation,
                                       std::size_t seat) const {
  const auto ticket = random_rank(mutation.episode.model_rng, gift_total_);
  const auto profile = std::upper_bound(
      gift_weights_.begin(), gift_weights_.end(), ticket,
      [](auto rank, const auto &row) { return rank < row.second; });
  const auto model =
      profile->first; // Positive bounded cumulative weights guarantee a match.
  static_cast<void>(
      receive_artifact(mutation, seat, model, mutation.episode.gift_rng));
  ++mutation.gifts;
  ++mutation.episode.gifts_given[seat];
  return model;
}

std::uint8_t FullGameBatch::receive_artifact(Mutation &mutation,
                                             std::size_t seat,
                                             std::int64_t model,
                                             std::uint64_t &rng) const {
  const auto category =
      static_cast<std::size_t>(inventory_.category(model) - 1);
  if (mutation.episode.next_instance > kMaximumCounter)
    throw std::invalid_argument("full-game native instance IDs are exhausted");
  std::uint8_t flags = 0;
  auto &hand = stage_hand(mutation, seat);
  if (hand.size() >= hand_limit_) {
    if (!oldest_overflow_)
      throw std::invalid_argument(
          "full-game provisional hand limit would overflow");
    hand.erase(hand.begin()); // Approved provisional oldest-held eviction, not
                              // official proof.
    ++mutation.overflow;
    ++mutation.episode.evicted[seat];
    flags |= 2;
  }
  DreamInventoryBatch::Item item{mutation.episode.next_instance++, model, 0, 0};
  if ((mutation.statuses[seat][2] & kCurseDreamBit) != 0 &&
      random_rank(rng, 100) < 50) {
    const auto &pool = inventory_.fake_pools_[category];
    item[2] = pool[random_rank(rng, pool.size())];
    flags |= 1;
  }
  hand.push_back(item);
  return flags;
}

void FullGameBatch::grant_pending_gifts(Mutation &mutation) const {
  for (std::size_t seat = 0; seat < player_count_; ++seat) {
    const auto count = mutation.episode.gifts_due[seat];
    const auto sacrifice_count = mutation.episode.sacrifice_gifts_due[seat];
    if (mutation.episode.phase != 1 || mutation.statuses[seat][0] == 0) {
      mutation.suppressed_gifts += count;
      mutation.episode.sacrifice_stats[8] += sacrifice_count;
    } else {
      for (std::size_t item = 0; item < count; ++item) {
        const auto model = grant_gift(mutation, seat);
        if (item < static_cast<std::size_t>(sacrifice_count)) {
          ++mutation.episode.sacrifice_stats[7];
          ++mutation.episode
                .sacrifice_model_counts[static_cast<std::size_t>(model - 3)];
        }
      }
    }
    mutation.episode.gifts_due[seat] = 0;
    mutation.episode.sacrifice_gifts_due[seat] = 0;
  }
}

bool FullGameBatch::schedule_receipts(Mutation &mutation) const {
  auto &e = mutation.episode;
  if (!e.apocalypse &&
      static_cast<std::uint64_t>(e.turns) >= apocalypse_after_turns_) {
    e.apocalypse = true;
    ++e.devil_stats[0];
  }
  const bool ended =
      living_factions(mutation) < 2 ||
      static_cast<std::uint64_t>(e.turns) >= max_turns_ ||
      static_cast<std::uint64_t>(e.commands + 1) >= max_decisions_;
  if (ended) {
    for (std::size_t seat = 0; seat < player_count_; ++seat) {
      mutation.suppressed_gifts += e.gifts_due[seat];
      e.sacrifice_stats[8] += e.sacrifice_gifts_due[seat];
      e.gifts_due[seat] = e.sacrifice_gifts_due[seat] = 0;
    }
    return false;
  }
  // Keep the original turn and its tick alive until receipt-generated Sun/Bow
  // work finishes. No hidden future gift/model is a learner decision.
  for (std::size_t seat = player_count_; seat-- > 0;) {
    const auto count = e.gifts_due[seat];
    const auto sacrifice_count = e.sacrifice_gifts_due[seat];
    e.gifts_due[seat] = 0;
    e.sacrifice_gifts_due[seat] = 0;
    for (std::int64_t i = 0; i < count; ++i) {
      QueuedAttack receipt{5,
                           static_cast<std::int64_t>(seat),
                           static_cast<std::int64_t>(seat),
                           0,
                           0,
                           0,
                           100};
      // LIFO insertion: Sacrifice replacements run first for each owner;
      // ordinary use/revival receipts retain their separate attribution.
      receipt.sacrifice_receipt = i >= count - sacrifice_count;
      enqueue_attack(mutation, receipt);
      ++e.devil_stats[14];
    }
  }
  if (mutation.family.empty())
    return false;
  ++e.devil_stats[17];
  return true;
}

void FullGameBatch::apply_devil(Mutation &mutation, std::size_t owner) const {
  auto &e = mutation.episode;
  if (!e.apocalypse)
    return;
  ++e.devil_stats[1];
  const auto ticket = random_rank(e.devil_rng, 100);
  const auto row = std::upper_bound(
      devil_weights_.begin(), devil_weights_.end(), ticket,
      [](auto rank, const auto &w) { return rank < w.second; });
  if (row == devil_weights_.end())
    return;
  const auto model = row->first;
  const auto &effect = devils_by_model_.at(model);
  ++e.devil_stats[2];
  ++e.devil_model_counts[static_cast<std::size_t>(model - 240)];
  if (effect.kind == 1) {
    auto &hp = mutation.statuses[owner][0];
    const auto loss = std::min(hp, effect.value);
    hp -= loss;
    ++e.devil_stats[3];
    e.devil_stats[4] += loss;
    if (loss > 0 && hp == 0)
      resolve_hp_zero(mutation, owner, 7);
    guardian_damage(mutation, owner, loss);
  } else if (effect.kind == 2) {
    auto &hand = stage_hand(mutation, owner);
    std::vector<std::size_t> eligible;
    for (std::size_t slot = 0; slot < hand.size(); ++slot)
      if (inventory_.category(hand[slot][1]) != 4 || hand[slot][3] != 0)
        eligible.push_back(slot);
    ++e.devil_stats[5];
    e.devil_stats[6] += static_cast<std::int64_t>(eligible.size());
    const auto count = std::min<std::size_t>(2, eligible.size());
    for (std::size_t i = 0; i < count; ++i) {
      const auto pick =
          i + random_rank(e.devil_removal_rng, eligible.size() - i);
      std::swap(eligible[i], eligible[pick]);
      ++e.devil_stats[12];
    }
    std::set<std::size_t> removed(eligible.begin(),
                                  eligible.begin() +
                                      static_cast<std::ptrdiff_t>(count));
    std::vector<DreamInventoryBatch::Item> survivors;
    survivors.reserve(hand.size() - count);
    for (std::size_t i = 0; i < hand.size(); ++i)
      if (!removed.contains(i))
        survivors.push_back(hand[i]);
    hand.swap(survivors);
    mutation.removed += count;
    e.devil_stats[7] += static_cast<std::int64_t>(count);
  } else {
    ++e.devil_stats[8];
    ++e.devil_stats[13];
    const auto resource = random_rank(e.devil_charity_rng, 3);
    auto &value = resource == 0 ? mutation.statuses[owner][0]
                                : mutation.resources[owner][resource - 1];
    const auto gain =
        std::min<std::int64_t>(effect.value, resource_cap_ - value);
    value += gain;
    e.devil_stats[9 + resource] += gain;
  }
}

bool FullGameBatch::visible_weapon(std::size_t owner) const {
  for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot) {
    const auto &item = inventory_.items_[owner * capacity_ + slot];
    if (item[3] == 0 &&
        inventory_.category(item[2] == 0 ? item[1] : item[2]) == 1)
      return true;
  }
  return false;
}

std::int64_t FullGameBatch::mixed_element(std::int64_t first,
                                          std::int64_t added) noexcept {
  if (first == added)
    return first;
  if (first == 5 && added >= 1 && added <= 4)
    return added;
  if (added == 5 && first >= 1 && first <= 4)
    return first;
  return 0;
}

FullGameBatch::Composition FullGameBatch::compose(const Mutation &mutation,
                                                  bool actual) const {
  const auto actor = static_cast<std::size_t>(mutation.episode.actor);
  const auto owner = mutation.environment * player_count_ + actor;
  std::array<std::int64_t, 512> models{};
  const auto count = static_cast<std::size_t>(mutation.episode.attack_size);
  for (std::size_t i = 0; i < count; ++i) {
    const auto &item =
        inventory_.items_[owner * capacity_ +
                          static_cast<std::size_t>(mutation.order[i] - 1)];
    models[i] = actual || item[2] == 0 ? item[1] : item[2];
  }
  return compose_models({models.data(), count}, mutation.resources[actor][0],
                        mutation.episode.utility_selection, CardSource::Held,
                        actual && hidden_selection(mutation, count));
}

std::int64_t FullGameBatch::model_mp_cost(std::int64_t model) const noexcept {
  if (inventory_.category(model) != 4)
    return 0;
  if (const auto row = effects_.find(model); row != effects_.end())
    return row->second.cost;
  if (const auto row = attacks_.find(model); row != attacks_.end())
    return row->second.cost;
  if (const auto row = boosts_.find(model); row != boosts_.end())
    return row->second.cost;
  if (const auto row = specials_.find(model); row != specials_.end())
    return row->second.cost;
  return 0;
}

std::int64_t FullGameBatch::ordered_cost(std::size_t owner,
                                         const std::int64_t *order,
                                         std::size_t count, bool actual) const {
  std::array<std::int64_t, 512> models{};
  for (std::size_t i = 0; i < count; ++i) {
    const auto &item =
        inventory_
            .items_[owner * capacity_ + static_cast<std::size_t>(order[i] - 1)];
    models[i] = actual || item[2] == 0 ? item[1] : item[2];
  }
  return sequence_cost({models.data(), count}, CardSource::Held);
}

void FullGameBatch::record_waivers(Mutation &mutation,
                                   const Composition &composition,
                                   std::size_t kind) const {
  mutation.waived += static_cast<std::uint64_t>(composition.waived);
  mutation.waivers += static_cast<std::uint64_t>(composition.waivers);
  mutation.episode.cost_stats[0] += composition.waivers;
  mutation.episode.cost_stats[1] += composition.waived;
  mutation.episode.cost_stats[kind] += composition.waivers;
}

void FullGameBatch::update_preview(Mutation &mutation) const {
  const auto preview = compose(mutation, false);
  mutation.episode.preview_attack = preview.value;
  mutation.episode.preview_element = preview.element;
  mutation.episode.preview_cost = preview.cost;
  mutation.episode.preview_area_count = preview.area_count;
}

void FullGameBatch::consume_attack(Mutation &mutation, std::size_t seat,
                                   bool attack,
                                   const std::bitset<512> *ineffective) const {
  const auto owner = mutation.environment * player_count_ + seat;
  auto &hand = stage_hand(mutation, seat);
  hand.clear();
  for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot)
    if (mutation.selected[slot] == 0)
      hand.push_back(inventory_.items_[owner * capacity_ + slot]);
  for (std::int64_t index = 0; index < mutation.episode.attack_size; ++index) {
    auto item =
        inventory_.items_[owner * capacity_ +
                          static_cast<std::size_t>(mutation.order[index] - 1)];
    if (inventory_.category(item[1]) == 4) {
      item[3] = 1;
      hand.push_back(item);
      ++mutation.miracles;
    } else
      ++mutation.consumed;
    if (refill_on_use_)
      ++mutation.episode.gifts_due[seat];
    mutation.attack_components +=
        attack && (!ineffective || !(*ineffective)[index]) ? 1 : 0;
  }
  mutation.selected.fill(0);
  mutation.order.fill(0);
  mutation.episode.attack_size = 0;
}

std::int64_t FullGameBatch::hit_rate(std::int64_t model) const noexcept {
  const auto found = chances_.find(model);
  return found == chances_.end() ? 100 : found->second;
}

void FullGameBatch::cast_attack(Mutation &mutation, std::int64_t choice,
                                bool automatic) const {
  const auto &episode = mutation.episode;
  const auto actor = static_cast<std::size_t>(episode.actor);
  const auto owner = mutation.environment * player_count_ + actor;
  const auto slot = static_cast<std::size_t>(episode.attack_slot);
  const auto &item = inventory_.items_[owner * capacity_ + slot];
  Composition attack{};
  if (attack_order_.empty()) {
    const auto actual = attacks_.find(item[1]);
    if (actual == attacks_.end())
      throw std::invalid_argument(
          "full-game actual attack effect is not implemented yet");
    attack = {actual->second.value, actual->second.element, actual->second.cost,
              actual->second.origin, actual->second.origin == 0};
  } else
    attack = compose(mutation, true);
  if (attack.ineffective[0]) {
    if (mutation.resources[actor][0] < attack.cost)
      throw std::invalid_argument(
          "full-game hidden actual miracle cost is unaffordable");
    mutation.resources[actor][0] -= attack.cost;
    mutation.paid = static_cast<std::uint64_t>(attack.cost);
    record_waivers(mutation, attack, 3);
    record_ineffective(mutation, attack.ineffective,
                       static_cast<std::size_t>(episode.attack_size), 0);
    consume_attack(mutation, actor, false);
    finish_turn(mutation, actor);
    return;
  }
  const auto rate = hit_rate(item[1]);
  const bool actual_chance = rate < 100;
  const bool hidden_mode = automatic != actual_chance;
  if (hidden_mode && !resolve_hidden_targeting_)
    throw std::invalid_argument(
        "full-game hidden actual targeting mode differs from displayed card");
  if (hidden_mode) {
    ++mutation.episode.hidden_targeting_stats[0];
    ++mutation.episode.hidden_targeting_stats[actual_chance ? 1 : 2];
  }
  if (mutation.resources[actor][0] < attack.cost)
    throw std::invalid_argument(
        "full-game hidden actual miracle cost is unaffordable");
  record_ineffective(mutation, attack.ineffective,
                     static_cast<std::size_t>(episode.attack_size), 0);
  if (attack_order_.empty()) {
    consume_slot(mutation, actor, slot);
    ++mutation.attack_components;
  } else
    consume_attack(mutation, actor, true, &attack.ineffective);
  const auto complex = complex_weapons_.find(item[1]);
  const auto kind =
      complex == complex_weapons_.end() ? 0 : complex->second.kind;
  const auto paid = kind == 1 ? mutation.resources[actor][0] : attack.cost;
  mutation.resources[actor][0] -= paid;
  mutation.paid = static_cast<std::uint64_t>(paid);
  mutation.episode.weapon_kind = kind;
  mutation.episode.weapon_value =
      complex == complex_weapons_.end() ? 0 : complex->second.value;
  if (kind == 1) {
    ++mutation.episode.weapon_stats[0];
    mutation.episode.weapon_stats[1] += paid;
  } else if (kind == 2)
    ++mutation.episode.weapon_stats[2];
  else if (kind == 3)
    ++mutation.episode.weapon_stats[5];
  record_waivers(mutation, attack, 3);
  mutation.attack_cast = true;
  auto target = choice - static_cast<std::int64_t>(capacity_) - 1;
  const auto danger = dangers_.find(item[1]);
  const bool pestle = danger != dangers_.end() && danger->second.kind == 1;
  mutation.episode.area_family = attack.area_count != 0;
  mutation.episode.area_components = attack.area_count;
  if (mutation.episode.area_family) {
    mutation.area_cast = true;
    ++mutation.episode.area_stats[0];
    mutation.episode.area_stats[1] += attack.area_count;
    mutation.episode.area_stats[7] +=
        (mutation.statuses[actor][2] & kCurseFogBit) != 0 ? 1 : 0;
  }
  if (pestle) {
    // A displayed chance card supplies no public target. The shared danger
    // scheduler needs a living placeholder before sampling its true recipient.
    if (automatic)
      target = static_cast<std::int64_t>(actor);
    mutation.danger_cast = true;
    ++mutation.episode.danger_stats[0];
    mutation.episode.danger_family = true;
    mutation.episode.danger_value = danger->second.value;
    mutation.episode.danger_element = danger->second.element;
  } else if (!mutation.episode.area_family &&
             (actual_chance || automatic ||
              (mutation.statuses[actor][2] & kCurseFogBit) != 0)) {
    std::array<std::int64_t, 8> eligible{};
    std::size_t count = 0;
    for (std::size_t seat = 0; seat < player_count_; ++seat)
      if (are_enemies(episode, actor, seat) && mutation.statuses[seat][0] > 0)
        eligible[count++] = static_cast<std::int64_t>(seat);
    auto &rng = actual_chance ? mutation.episode.chance_target_rng
                : automatic   ? mutation.episode.hidden_targeting_rng
                              : mutation.episode.combat_rng;
    target = eligible[random_rank(rng, count)];
    if (automatic && !actual_chance)
      ++mutation.episode.hidden_targeting_stats[3];
  }
  mutation.episode.damage_source = static_cast<std::int64_t>(actor);
  mutation.episode.target = mutation.episode.actor = target;
  mutation.episode.attack = attack.value;
  mutation.episode.element = attack.element;
  mutation.episode.origin = attack.origin;
  mutation.episode.hit_rate = rate;
  auto shot = attack_payload(item[1], attack, static_cast<std::int64_t>(actor),
                             target, 2);
  shot.weapon_kind = kind;
  shot.weapon_value =
      complex == complex_weapons_.end() ? 0 : complex->second.value;
  shot.area_count = attack.area_count;
  shot.danger_value = pestle ? danger->second.value : 0;
  shot.danger_element = pestle ? danger->second.element : 0;
  mutation.episode.effect_kind = shot.effect_kind;
  mutation.episode.effect_value = shot.effect_value;
  std::array<std::int64_t, 9> recipients{};
  std::size_t count = 0;
  if (mutation.episode.area_family) {
    for (std::size_t seat = 0; seat < player_count_; ++seat)
      if (are_enemies(episode, actor, seat) && mutation.statuses[seat][0] > 0)
        recipients[count++] = static_cast<std::int64_t>(seat);
    mutation.episode.area_stats[2] += static_cast<std::int64_t>(count);
  } else
    recipients[count++] = target;
  const auto repeats = kind == 3 ? 2 : 1;
  mutation.episode.original_remaining =
      static_cast<std::int64_t>(count) * repeats;
  if (kind == 3)
    mutation.episode.strikes_remaining = mutation.episode.original_remaining;
  if (mutation.episode.area_family)
    mutation.episode.area_stats[3] += mutation.episode.original_remaining;
  // Provisional ascending seats, repeated shots grouped per recipient. Reversed
  // insertion preserves order; all nested reactions finish before siblings.
  for (std::size_t index = count; index-- > 0;) {
    shot.target = recipients[index];
    for (std::int64_t repeat = 1; repeat <= repeats; ++repeat) {
      shot.recipient_strikes = repeat;
      enqueue_attack(mutation, shot);
    }
  }
  resume_family(mutation);
}

void FullGameBatch::apply_attack_effect(Mutation &mutation) const {
  auto &episode = mutation.episode;
  const auto kind = episode.effect_kind;
  if (kind == 0 || mutation.special_kind == 1 ||
      (kind <= 3 && mutation.damage == 0))
    return;
  if (kind == 1) {
    auto &source =
        mutation.statuses[static_cast<std::size_t>(episode.damage_source)];
    if (source[0] <= 0)
      return; // Provisional: no resurrection after a lethal self-bounce.
    mutation.absorption = true;
    mutation.absorbed_hp = std::min<std::uint64_t>(
        mutation.damage, static_cast<std::uint64_t>(resource_cap_ - source[0]));
    source[0] += static_cast<std::int64_t>(mutation.absorbed_hp);
    if (episode.active_family_kind == 4 || episode.active_family_kind == 9)
      episode.guardian_stats[14] +=
          static_cast<std::int64_t>(mutation.absorbed_hp);
    ++episode.absorptions;
    episode.absorbed_hp += static_cast<std::int64_t>(mutation.absorbed_hp);
    return;
  }
  auto &target = mutation.statuses[static_cast<std::size_t>(episode.target)];
  if (target[0] <= 0)
    return; // Provisional: do not afflict already dead targets.
  if (kind == 12) {
    const auto flags =
        receive_artifact(mutation, static_cast<std::size_t>(episode.target),
                         episode.effect_value, episode.guardian_receipt_rng);
    ++episode.guardian_generated_stats[2];
    episode.guardian_generated_stats[3] += (flags & 1) != 0 ? 1 : 0;
    episode.guardian_generated_stats[4] += (flags & 2) != 0 ? 1 : 0;
    return;
  }
  if (kind == 10) {
    const auto source = static_cast<std::size_t>(episode.damage_source);
    auto &hp = mutation.statuses[source][0];
    if (hp <= 0 || mutation.damage == 0)
      return;
    // Evidence covers surviving-target recoil. Current-source ownership after
    // redirects and revival-before-recoil remain explicitly provisional.
    const auto recoil =
        std::min<std::int64_t>(hp, static_cast<std::int64_t>(mutation.damage));
    hp -= recoil;
    mutation.recoil_damage += static_cast<std::uint64_t>(recoil);
    ++episode.weapon_stats[3];
    episode.weapon_stats[4] += recoil;
    if (hp == 0)
      resolve_hp_zero(mutation, source, 1); // Weapon-derived HP-zero edge.
    guardian_damage(mutation, source, recoil);
    return;
  }
  if (kind == 8 || kind == 9) {
    apply_removal(mutation, kind - 7, episode.effect_value);
    return;
  }
  if (kind == 2 || kind == 4) {
    target[2] |= episode.effect_value;
    ++mutation.inflicted_curse;
    ++episode.inflicted_curses;
  } else {
    if (kind == 6) {
      auto &mp =
          mutation.resources[static_cast<std::size_t>(episode.target)][0];
      const auto gain =
          std::min<std::int64_t>(episode.effect_value, resource_cap_ - mp);
      mp += gain;
      episode.counter_stats[6] += gain;
    } else if (kind == 7) {
      const auto from = static_cast<std::size_t>(episode.target);
      const auto to = static_cast<std::size_t>(episode.damage_source);
      if (from != to) {
        const auto debit = pay_cp_waterfall({mutation.statuses[from][0],
                                             mutation.resources[from][0],
                                             mutation.resources[from][1]},
                                            episode.effect_value);
        mutation.statuses[from][0] = debit.wallet.hp;
        mutation.resources[from] = {debit.wallet.mp, debit.wallet.cp};
        const auto credit = credit_cp_capped(
            {mutation.statuses[to][0], mutation.resources[to][0],
             mutation.resources[to][1]},
            episode.effect_value, resource_cap_);
        mutation.resources[to][1] = credit.wallet.cp;
        if (episode.active_family_kind == 4) {
          episode.guardian_stats[16] += credit.credited;
          episode.guardian_stats[17] += debit.hp_debit;
        } else {
          episode.counter_stats[7] += credit.credited;
          episode.counter_stats[8] += debit.hp_debit;
        }
        if (debit.hp_debit > 0 && debit.wallet.hp == 0)
          resolve_hp_zero(mutation, from, 3);
        guardian_damage(mutation, from, debit.hp_debit);
      }
    } else if (kind == 11) {
      const auto seat = static_cast<std::size_t>(episode.target);
      const auto credit = credit_cp_capped(
          {target[0], mutation.resources[seat][0], mutation.resources[seat][1]},
          episode.effect_value, resource_cap_);
      mutation.resources[seat][1] = credit.wallet.cp;
      episode.guardian_stats[16] += credit.credited;
    } else {
      apply_illness(mutation, static_cast<std::size_t>(episode.target),
                    episode.effect_value);
    }
  }
}

void FullGameBatch::apply_removal(Mutation &mutation, std::int64_t kind,
                                  std::int64_t maximum) const {
  const auto target = static_cast<std::size_t>(mutation.episode.target);
  auto &hand = stage_hand(mutation, target);
  std::array<std::size_t, 512> eligible{};
  std::array<std::uint8_t, 512> victims{};
  std::size_t count = 0;
  for (std::size_t slot = 0; slot < hand.size(); ++slot) {
    const auto &item = hand[slot];
    const auto category = inventory_.category(item[1]);
    const bool performed = category == 4 && item[3] == 1;
    if ((kind == 1 && !performed) || (kind == 2 && performed))
      eligible[count++] = slot;
  }
  const auto removed = std::min(count, static_cast<std::size_t>(maximum));
  auto &stats = mutation.episode.removal_stats;
  ++stats[static_cast<std::size_t>(kind - 1)];
  stats[static_cast<std::size_t>(kind + 1)] +=
      static_cast<std::int64_t>(removed);
  stats[4] += count == 0 ? 1 : 0;
  stats[5] += count < static_cast<std::size_t>(maximum) ? 1 : 0;
  stats[6] += static_cast<std::int64_t>(count);
  for (std::size_t pick = 0; pick < removed; ++pick) {
    const auto remaining = count - pick;
    // No ticket for a singleton. Partial Fisher-Yates: uniform subset,
    // without replacement, actual eligibility only, never learner victim IDs.
    const auto offset =
        remaining == 1 ? 0
                       : random_rank(mutation.episode.removal_rng, remaining);
    stats[7] += remaining > 1 ? 1 : 0;
    std::swap(eligible[pick], eligible[pick + offset]);
    victims[eligible[pick]] = 1;
  }
  std::vector<DreamInventoryBatch::Item> survivors;
  survivors.reserve(hand.size() - removed);
  for (std::size_t slot = 0; slot < hand.size(); ++slot)
    if (victims[slot] == 0)
      survivors.push_back(hand[slot]);
  hand.swap(survivors);
  mutation.removed += removed;
  ++mutation.removal_effects;
  // Victims do not generate invented gifts; source/defense uses retain their
  // existing deferred provisional receipts. Flags/fakes/order stay unchanged.
}

void FullGameBatch::apply_dream_redraw(Mutation &mutation,
                                       std::size_t owner) const {
  auto &stats = mutation.episode.dream_defense_stats;
  ++stats[0];
  if (mutation.statuses[owner][0] <= 0) {
    ++stats[6];
    return;
  }
  mutation.statuses[owner][2] |= kCurseDreamBit;
  ++mutation.self_curses;
  ++stats[1];
  auto &hand = stage_hand(mutation, owner);
  const auto count = hand.size();
  // Provisional: all remaining held rows, including performed miracles, are
  // replaced by fresh weighted receipts. No gifts, overflow, resource changes
  // or additional owner ticks; the explicit Hat use still earns its usual due.
  hand.clear();
  ++mutation.redraws;
  mutation.redrawn += count;
  ++stats[2];
  stats[3] += static_cast<std::int64_t>(count);
  stats[7] += count == 0 ? 1 : 0;
  for (std::size_t index = 0; index < count; ++index) {
    if (mutation.episode.next_instance > kMaximumCounter)
      throw std::invalid_argument(
          "full-game instance IDs exhausted during redraw");
    const auto ticket =
        random_rank(mutation.episode.redraw_model_rng, gift_total_);
    const auto profile = std::upper_bound(
        gift_weights_.begin(), gift_weights_.end(), ticket,
        [](auto rank, const auto &row) { return rank < row.second; });
    const auto model = profile->first;
    DreamInventoryBatch::Item held{mutation.episode.next_instance++, model, 0,
                                   0};
    if (random_rank(mutation.episode.redraw_disguise_rng, 100) < 50) {
      const auto &pool = inventory_.fake_pools_[static_cast<std::size_t>(
          inventory_.category(model) - 1)];
      held[2] =
          pool[random_rank(mutation.episode.redraw_disguise_rng, pool.size())];
      ++stats[4];
      stats[5] += held[2] != model ? 1 : 0;
    }
    hand.push_back(held);
  }
}

void FullGameBatch::apply_illness(Mutation &mutation, std::size_t target,
                                  std::int64_t stage) const {
  auto &status = mutation.statuses[target];
  if (status[0] <= 0)
    return;
  const auto result = inflict_illness({static_cast<std::uint16_t>(status[0]),
                                       static_cast<std::uint8_t>(status[1])},
                                      static_cast<std::uint8_t>(stage));
  const auto damage = status[0] - result.hp;
  mutation.illness_effect_damage += static_cast<std::uint64_t>(damage);
  mutation.episode.illness_effect_damage += damage;
  status[0] = result.hp;
  status[1] = result.stage;
  ++mutation.inflicted_illness;
  ++mutation.episode.inflicted_illnesses;
  if (damage > 0 && status[0] == 0)
    resolve_hp_zero(mutation, target, 2);
  guardian_damage(mutation, target, damage);
}

void FullGameBatch::resolve_hp_zero(Mutation &mutation, std::size_t owner,
                                    std::int64_t cause) const {
  if (mutation.statuses[owner][0] != 0)
    return;
  auto &hand = stage_hand(mutation, owner);
  const auto found =
      std::find_if(hand.begin(), hand.end(), [this](const auto &item) {
        return passives_.contains(
            item[1]); // Actual ownership, never displayed disguise.
      });
  if (found == hand.end()) {
    // The pinned client's final-death handler clears lost-control turns.
    // A successful Sun revival does not run that death transition.
    mutation.episode.confusion[owner] = 0;
    if (mutation.episode.guardians[owner][0] != 0) {
      mutation.episode.guardians[owner] = {0, 0};
      ++mutation.episode.guardian_stats[12];
    }
    enqueue_ascension(mutation, owner);
    return;
  }
  const auto hp = std::min(passives_.at((*found)[1]), resource_cap_);
  hand.erase(
      found); // Provisional: first-held real copy, stable survivor order.
  mutation.statuses[owner][0] = hp;
  ++mutation.consumed;
  ++mutation.revivals;
  mutation.revived_hp += static_cast<std::uint64_t>(hp);
  ++mutation.episode.revival_stats[0];
  mutation.episode.revival_stats[1] += hp;
  ++mutation.episode.revival_stats[static_cast<std::size_t>(cause + 1)];
  if (refill_on_use_)
    ++mutation.episode.gifts_due[owner];
  // One copy per HP-zero edge. No recursive trigger, cure, resource reset or
  // tick.
}

void FullGameBatch::enqueue_attack(Mutation &mutation,
                                   const QueuedAttack &attack) const {
  // Consumed counter/Bow items share the inventory bound; area producers add
  // at most two shots per other living seat (and require at least two slots).
  // Counter depth plus at most one full held Bow hand per final-dead owner,
  // each against the other seats. A post-turn receipt frame adds at most one
  // full hand per seat; nested deaths still fit the shared square bound.
  // Sun-generated waves are separately bounded and final-dead seats stay dead.
  if (mutation.family.size() >= player_count_ * capacity_ * player_count_ + 2)
    throw std::invalid_argument("full-game attack-family queue bound exceeded");
  mutation.family.push_back(attack);
  auto &stats = mutation.episode.family_stats;
  ++stats[0];
  stats[5] =
      std::max(stats[5], static_cast<std::int64_t>(mutation.family.size()));
}

void FullGameBatch::enqueue_ascension(Mutation &mutation,
                                      std::size_t owner) const {
  auto &episode = mutation.episode;
  const auto bit = static_cast<std::uint16_t>(1U << owner);
  if ((episode.final_deaths & bit) != 0)
    return;
  episode.final_deaths |= bit;
  ++episode.family_stats[6];
  auto &hand = stage_hand(mutation, owner);
  std::vector<Ascension> bows;
  std::vector<DreamInventoryBatch::Item> survivors;
  survivors.reserve(hand.size());
  for (const auto &item : hand) {
    const auto bow = ascensions_by_model_.find(item[1]);
    if (bow == ascensions_by_model_.end())
      survivors.push_back(item);
    else
      bows.push_back(bow->second);
  }
  if (bows.empty())
    return;
  hand.swap(survivors);
  mutation.consumed += bows.size();
  mutation.ascensions += bows.size();
  episode.family_stats[7] += static_cast<std::int64_t>(bows.size());
  if (refill_on_use_)
    episode.gifts_due[owner] += static_cast<std::int64_t>(bows.size());
  // Provisional: held-copy order, ascending living recipient seats. The
  // recorded official edge proves post-death shots precede endGame, not this
  // multiplayer order, multiplicity, or per-recipient independent timing.
  for (auto bow = bows.rbegin(); bow != bows.rend(); ++bow)
    for (std::size_t seat = player_count_; seat-- > 0;)
      if (are_enemies(episode, owner, seat) && mutation.statuses[seat][0] > 0) {
        enqueue_attack(mutation,
                       {3, static_cast<std::int64_t>(owner),
                        static_cast<std::int64_t>(seat), bow->dying_attack,
                        bow->element, 0, bow->dying_rate});
        ++episode.family_stats[8];
      }
}

void FullGameBatch::complete_attack(Mutation &mutation,
                                    std::int64_t damage) const {
  auto &episode = mutation.episode;
  const auto kind = episode.active_family_kind;
  if (kind == 0)
    return;
  ++episode.family_stats[2];
  if (kind == 1) {
    ++mutation.counters_resolved;
    ++episode.counter_stats[2];
    episode.counter_stats[5] += damage;
  } else if (kind == 2) {
    if (episode.area_family) {
      ++episode.area_stats[4];
      episode.area_stats[6] += damage;
      mutation.area_damage += static_cast<std::uint64_t>(damage);
    }
    if (episode.strikes_remaining > 0) {
      --episode.strikes_remaining;
      ++episode.weapon_stats[6];
    }
    --episode.original_remaining;
    if (episode.recipient_strikes_remaining > 0)
      --episode.recipient_strikes_remaining;
    mutation.attack_resolved = episode.original_remaining == 0;
  } else if (kind == 4) {
    ++episode.guardian_stats[7];
    episode.guardian_stats[13] += damage;
    if (episode.guardian_model == 285 && mutation.special_kind == 1)
      ++episode.guardian_generated_stats[5];
  } else if (kind == 5) {
    ++episode.devil_stats[15];
  } else if (kind == 6) {
    ++episode.phenomenon_stats[4];
    episode.phenomenon_stats[7] += damage;
  } else if (kind == 8) {
    ++episode.guardian_stats[7]; // Producer completed; child outcomes are
                                 // separate.
  } else if (kind == 9) {
    ++episode.guardian_generated_stats[16];
    episode.guardian_generated_stats[18] += damage;
    episode.guardian_stats[13] += damage;
    if (episode.area_family) {
      ++episode.area_stats[4];
      episode.area_stats[6] += damage;
      mutation.area_damage += static_cast<std::uint64_t>(damage);
    }
    if (episode.weapon_kind == 3)
      ++episode.weapon_stats[6];
    if (episode.recipient_strikes_remaining > 0)
      --episode.recipient_strikes_remaining;
    if (episode.strikes_remaining > 0)
      --episode.strikes_remaining;
    if (episode.generated_virtual_leader == 285 && mutation.special_kind == 1)
      ++episode.guardian_generated_stats[5];
  } else if (kind == 7) {
    // Trades are not numeric attacks, counters or post-death Bow shots.
  } else {
    episode.family_stats[12] += damage;
    mutation.ascension_damage += static_cast<std::uint64_t>(damage);
  }
  episode.active_family_kind = 0;
}

void FullGameBatch::suppress_attack(Mutation &mutation,
                                    const QueuedAttack &attack) const {
  auto &episode = mutation.episode;
  ++episode.family_stats[3];
  if (attack.family_kind == 1) {
    ++mutation.counters_suppressed;
    ++episode.counter_stats[4];
  } else if (attack.family_kind == 2) {
    if (attack.area_count > 0)
      ++episode.area_stats[5];
    if (episode.strikes_remaining > 0) {
      --episode.strikes_remaining;
      ++episode.weapon_stats[7];
    }
    --episode.original_remaining;
    mutation.attack_resolved = episode.original_remaining == 0;
  } else if (attack.family_kind == 4) {
    ++episode.guardian_stats[9];
    episode.guardian_generated_stats[6] += attack.guardian_model == 285 ? 1 : 0;
  } else if (attack.family_kind == 8) {
    ++episode.guardian_stats[9];
    ++episode.guardian_generated_stats[6];
  } else if (attack.family_kind == 9) {
    ++episode.guardian_generated_stats[17];
    if (attack.area_count > 0)
      ++episode.area_stats[5];
    if (attack.weapon_kind == 3)
      ++episode.weapon_stats[7];
  } else if (attack.family_kind == 5) {
    ++episode.devil_stats[16];
    episode.sacrifice_stats[8] += attack.sacrifice_receipt ? 1 : 0;
    ++mutation.suppressed_gifts;
  } else if (attack.family_kind == 6)
    ++episode.phenomenon_stats[6];
  else if (attack.family_kind == 7) {
    episode.market_kind = attack.market_kind;
    episode.escrow = attack.escrow;
    episode.escrow_owner = attack.escrow_owner;
    restore_market_escrow(mutation);
    clear_market(mutation);
  } else
    ++episode.family_stats[11];
}

std::int64_t FullGameBatch::prepare_danger(Mutation &mutation,
                                           QueuedAttack &shot) const {
  const auto actor = static_cast<std::size_t>(shot.source);
  auto target = shot.target;
  std::int64_t fixed_damage = 0;
  auto &stats = mutation.episode.danger_stats;
  // Provisional priority: one equally weighted living owner, not one ticket
  // per held copy. Actual ownership comes from remaining staged hands.
  std::array<std::int64_t, 9> holders{}, living{};
  std::size_t holder_count = 0, living_count = 0;
  for (std::size_t seat = 0; seat < player_count_; ++seat) {
    if (mutation.statuses[seat][0] == 0)
      continue;
    living[living_count++] = static_cast<std::int64_t>(seat);
    const auto staged = mutation.hands.find(seat);
    const auto owner_index = mutation.environment * player_count_ + seat;
    const auto begin =
        staged == mutation.hands.end()
            ? inventory_.items_.begin() +
                  static_cast<std::ptrdiff_t>(owner_index * capacity_)
            : staged->second.begin();
    const auto size = staged == mutation.hands.end()
                          ? inventory_.sizes_[owner_index]
                          : staged->second.size();
    if (std::any_of(begin, begin + static_cast<std::ptrdiff_t>(size),
                    [this](const auto &held) {
                      const auto role = dangers_.find(held[1]);
                      return role != dangers_.end() && role->second.kind == 2;
                    }))
      holders[holder_count++] = static_cast<std::int64_t>(seat);
  }
  if (holder_count != 0) {
    const auto draw =
        holder_count == 1
            ? 0
            : random_rank(mutation.episode.attractor_rng, holder_count);
    target = holders[draw];
    stats[4] += holder_count > 1 ? 1 : 0;
    auto &hand = stage_hand(mutation, static_cast<std::size_t>(target));
    const auto mortar =
        std::find_if(hand.begin(), hand.end(), [this](const auto &held) {
          const auto role = dangers_.find(held[1]);
          return role != dangers_.end() && role->second.kind == 2;
        });
    fixed_damage = dangers_.at((*mortar)[1]).value;
    hand.erase(mortar); // First actual held copy; preserve survivor order.
    ++mutation.consumed;
    if (refill_on_use_)
      ++mutation.episode.gifts_due[static_cast<std::size_t>(target)];
    ++stats[3];
    stats[5] += target == static_cast<std::int64_t>(actor) ? 1 : 0;
  } else {
    target = living[random_rank(mutation.episode.danger_rng, living_count)];
    ++stats[1];
  }
  stats[2] += target == static_cast<std::int64_t>(actor) ? 1 : 0;
  shot.target = target;
  return fixed_damage;
}

void FullGameBatch::resume_family(Mutation &mutation) const {
  auto &episode = mutation.episode;
  // A completed utility can produce guardian/phenomenon responses. Its old
  // reservation must not suppress the revealed attack's public response views.
  episode.utility_selection = false;
  episode.selected_count = episode.defense_actions = 0;
  mutation.selected.fill(0);
  mutation.order.fill(0);
  do {
    while (!mutation.family.empty()) {
      auto shot = mutation.family.back();
      mutation.family.pop_back();
      if (shot.target < 0 ||
          static_cast<std::size_t>(shot.target) >= player_count_ ||
          (shot.family_kind != 3 && mutation.statuses[shot.source][0] <= 0) ||
          mutation.statuses[shot.target][0] <= 0 ||
          ((shot.family_kind == 4 || shot.family_kind == 8) &&
           episode.guardians[shot.source][1] != shot.guardian_instance)) {
        suppress_attack(mutation, shot);
        continue;
      }
      ++episode.family_stats[1];
      episode.active_family_kind = shot.family_kind;
      episode.guardian_model = shot.guardian_model;
      episode.phenomenon_model = shot.phenomenon_model;
      episode.market_kind = shot.market_kind;
      episode.escrow = shot.escrow;
      episode.escrow_owner = shot.escrow_owner;
      episode.forced_market = shot.forced_market;
      episode.automatic_buyer = shot.automatic_buyer;
      episode.generated_model = shot.generated_model;
      episode.generated_virtual_leader = shot.virtual_leader;
      episode.weapon_kind = shot.weapon_kind;
      episode.weapon_value = shot.weapon_value;
      episode.area_family = shot.area_count != 0;
      episode.area_components = shot.area_count;
      episode.danger_family = shot.danger;
      episode.danger_value = shot.danger_value;
      episode.danger_element = shot.danger_element;
      if (shot.family_kind == 8) {
        complete_attack(mutation, 0);
        execute_generated_guardian(mutation, shot);
        continue;
      }
      if (shot.family_kind == 5) {
        if (++episode.postturn_receipts >
            static_cast<std::int64_t>(2 * player_count_ * capacity_))
          throw std::invalid_argument(
              "full-game automatic post-turn receipt bound exceeded");
        const auto owner = static_cast<std::size_t>(shot.target);
        const auto receipt_model = grant_gift(mutation, owner);
        if (shot.sacrifice_receipt) {
          ++episode.sacrifice_stats[7];
          ++episode.sacrifice_model_counts[static_cast<std::size_t>(
              receipt_model - 3)];
        }
        apply_devil(mutation, owner);
        complete_attack(mutation, 0);
        continue;
      }
      if (shot.guardian_automatic) {
        apply_guardian_automatic(mutation, shot);
        complete_attack(mutation, 0);
        continue;
      }
      if (shot.family_kind == 2)
        episode.recipient_strikes_remaining = shot.recipient_strikes;
      if (shot.family_kind == 9) {
        episode.recipient_strikes_remaining = shot.recipient_strikes;
        episode.weapon_kind = shot.weapon_kind;
        episode.weapon_value = shot.weapon_value;
        episode.strikes_remaining =
            shot.weapon_kind == 3 ? shot.recipient_strikes : 0;
        episode.area_family = shot.area_count != 0;
        episode.area_components = shot.area_count;
      }
      if (shot.danger) {
        const auto fixed = prepare_danger(mutation, shot);
        if (fixed != 0 || shot.target == shot.source) {
          auto &hp =
              mutation.statuses[static_cast<std::size_t>(shot.target)][0];
          auto loss = std::min(hp, fixed == 0 ? shot.value : fixed);
          hp -= loss;
          if (fixed == 0 && shot.element == 6 && loss > 0) {
            loss += hp;
            hp = 0;
            ++mutation.darkness_finish;
          }
          if (loss > 0 && hp == 0)
            resolve_hp_zero(mutation, static_cast<std::size_t>(shot.target), 1);
          guardian_damage(mutation, static_cast<std::size_t>(shot.target),
                          loss);
          mutation.damage += static_cast<std::uint64_t>(loss);
          mutation.automatic_danger_damage += static_cast<std::uint64_t>(loss);
          ++episode.danger_stats[6];
          episode.danger_stats[7] += loss;
          complete_attack(mutation, loss);
          continue; // No response for initial self or attracted direct loss.
        }
      }
      if (shot.family_kind == 1) {
        ++mutation.counters_cast;
        ++episode.counter_stats[1];
      } else if (shot.family_kind == 2 && shot.rate < 100)
        ++episode.chance_casts;
      const auto mask =
          static_cast<std::uint8_t>(mutation.statuses[shot.target][2]);
      const auto rate = static_cast<std::uint8_t>(shot.rate);
      const bool roll = percentage_hit_requires_ticket(mask, rate);
      auto &rng = shot.family_kind == 6 ? episode.phenomenon_hit_rng
                  : shot.family_kind == 4 || shot.family_kind == 9
                      ? episode.guardian_hit_rng
                  : shot.family_kind == 1 ? episode.counter_rng
                  : shot.family_kind == 3 ? episode.ascension_rng
                                          : episode.chance_rng;
      const auto ticket =
          roll ? static_cast<std::uint8_t>(random_rank(rng, 100)) : 0;
      if (!percentage_attack_hits(mask, rate, ticket)) {
        ++episode.family_stats[4];
        if (shot.family_kind == 1) {
          ++mutation.counter_misses;
          ++episode.counter_stats[3];
        } else if (shot.family_kind == 3)
          ++episode.family_stats[10];
        else if (shot.family_kind == 4)
          ++episode.guardian_stats[8];
        else if (shot.family_kind == 9)
          ++episode.guardian_generated_stats[19];
        else if (shot.family_kind == 6)
          ++episode.phenomenon_stats[5];
        else {
          mutation.chance_result = -1;
          ++episode.chance_misses;
        }
        complete_attack(mutation, 0);
        continue;
      }
      if (shot.family_kind == 3)
        ++episode.family_stats[9];
      else if (shot.family_kind == 2 && shot.rate < 100) {
        mutation.chance_result = 1;
        ++episode.chance_hits;
        mutation.dark_cloud_hit = !roll;
        episode.dark_cloud_hits += !roll ? 1 : 0;
      }
      episode.phase = 4;
      episode.damage_source = shot.source;
      episode.target = episode.actor = shot.target;
      episode.attack = shot.value;
      episode.element = shot.element;
      episode.origin = shot.origin;
      episode.hit_rate = shot.rate;
      episode.effect_kind = shot.effect_kind;
      episode.effect_value = shot.effect_value;
      episode.counter_kind = shot.counter_kind;
      episode.counter_damage_basis = shot.damage_basis;
      episode.redirects = 0;
      return;
    }
    // A receipt can consume a Sun and owe another receipt. Process those waves
    // iteratively, not by recursively nesting finish_turn/resume_family frames.
  } while (apocalypse_after_turns_ != 0 && episode.turn_ticked &&
           episode.guardians_scheduled && schedule_receipts(mutation));
  finish_turn(mutation, static_cast<std::size_t>(episode.turn_owner));
}

std::int64_t
FullGameBatch::special_kind(std::int64_t model,
                            const Episode &episode) const noexcept {
  const auto found = specials_.find(model);
  if (found == specials_.end())
    return 0;
  const auto &effect = found->second;
  return (effect.origin == -1 || effect.origin == episode.origin) &&
                 (!effect.neutral_only || episode.element == 0)
             ? effect.kind
             : 0;
}

std::int64_t FullGameBatch::displayed_model(std::size_t env,
                                            std::size_t slot) const {
  const auto owner =
      env * player_count_ + static_cast<std::size_t>(episodes_[env].actor);
  const auto &item = inventory_.items_[owner * capacity_ + slot];
  return item[2] == 0 ? item[1] : item[2];
}

bool FullGameBatch::defense_choice(std::size_t env, std::int64_t choice,
                                   const std::int64_t *order,
                                   std::size_t count) const {
  auto context = episodes_[env];
  const auto owner =
      env * player_count_ + static_cast<std::size_t>(context.actor);
  if (flash_prevents_additional_defense(
          static_cast<std::uint8_t>(statuses_.states_[owner][2]), count))
    return false;
  const auto model = displayed_model(env, static_cast<std::size_t>(choice - 1));
  if (count > 0 && cost_reducers_.contains(model) &&
      inventory_.category(displayed_model(
          env, static_cast<std::size_t>(order[count - 1] - 1))) == 4)
    return true;
  bool prefix = true, special = false;
  for (std::size_t index = 0; index < count; ++index) {
    const auto model =
        displayed_model(env, static_cast<std::size_t>(order[index] - 1));
    const auto effect = defense_effects_.find(model);
    if (prefix && effect != defense_effects_.end() && effect->second.kind == 5)
      context.element = 0;
    else {
      prefix = false;
      special = special || special_kind(model, context) != 0;
    }
  }
  const auto effect = defense_effects_.find(model);
  if (effect != defense_effects_.end() && effect->second.kind == 5)
    return context.attack > 0 && prefix;
  const auto kind = special_kind(model, context);
  if (kind != 0)
    return prefix && (!cost_reducers_.empty() ||
                      resources_[owner][0] >= specials_.at(model).cost);
  const auto armor = armor_.find(model);
  return !special && context.attack > 0 && armor != armor_.end() &&
         compatible(context.element, armor->second.element);
}

std::int64_t FullGameBatch::displayed_defense_element(std::size_t env) const {
  const auto &episode = episodes_[env];
  if (attack_order_.empty() || episode.selected_count == 0)
    return episode.element;
  const auto first = attack_order_[env * capacity_];
  const auto effect = defense_effects_.find(
      displayed_model(env, static_cast<std::size_t>(first - 1)));
  return effect != defense_effects_.end() && effect->second.kind == 5
             ? 0
             : episode.element;
}

bool FullGameBatch::legal_choice(std::size_t env, std::int64_t choice) const {
  const auto &episode = episodes_[env];
  if (choice < 0 || static_cast<std::uint64_t>(choice) > capacity_ + 9)
    return false;
  if (episode.phase != 1 && episode.phase != 2 && episode.phase != 3 &&
      episode.phase != 4 && episode.phase != 6 && episode.phase != 7)
    return false;
  const auto owner =
      env * player_count_ + static_cast<std::size_t>(episode.actor);
  const auto discard_control = static_cast<std::int64_t>(capacity_) + 1;
  if (episode.phase == 1 &&
      episode.confusion[static_cast<std::size_t>(episode.actor)] > 0)
    return choice == 0;
  if (episode.phase == 6) {
    if (episode.trade_mode == 3)
      return choice == 0 ||
             choice == 1; // Refuse / purchase, by current source.
    if (episode.trade_mode == 2) {
      if (choice == static_cast<std::int64_t>(capacity_) + 1)
        return true;
      if (choice == 0)
        return episode.sale_slot >= 0;
      return episode.trade_actions < kFullGameMaxTradeActions && choice > 0 &&
             static_cast<std::uint64_t>(choice) <= inventory_.sizes_[owner] &&
             choice - 1 != episode.attack_slot &&
             inventory_.items_[owner * capacity_ + choice - 1][3] == 0;
    }
    if (episode.trade_mode != 1)
      return false;
    if (choice == 0 || choice == 9)
      return true; // Confirm and cancel survive the bounded edit limit.
    return episode.trade_actions < kFullGameMaxTradeActions &&
           exchange_delta(episode, choice) != 0;
  }
  if (episode.phase == 1 && choice == discard_control) {
    if (episode.apocalypse && !sacrifice_enabled_)
      return false; // Deliberately incomplete raw fixture, not factory
                    // behavior.
    for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot)
      if (discard_models_.contains(displayed_model(env, slot)))
        return true;
    return false;
  }
  if (episode.phase == 7) {
    if (choice == discard_control)
      return true; // Cancel always remains a bounded escape, without a tick.
    if (choice == 0)
      return episode.discard_size > 0;
    if (episode.discard_actions >= kFullGameMaxDiscardActions || choice < 1 ||
        static_cast<std::uint64_t>(choice) > inventory_.sizes_[owner])
      return false;
    return discard_models_.contains(
        displayed_model(env, static_cast<std::size_t>(choice - 1)));
  }
  if (episode.phase == 3) {
    const auto seat = choice - static_cast<std::int64_t>(capacity_) - 1;
    return seat >= 0 && static_cast<std::uint64_t>(seat) < player_count_ &&
           are_enemies(episode, static_cast<std::size_t>(episode.actor),
                       static_cast<std::size_t>(seat)) &&
           statuses_.states_[env * player_count_ + seat][0] > 0;
  }
  if (choice == 0) {
    if (episode.phase == 2)
      return resources_[owner][0] >= episode.preview_cost;
    if (episode.phase == 4)
      return cost_reducers_.empty() ||
             resources_[owner][0] >=
                 ordered_cost(owner, attack_order_.data() + env * capacity_,
                              static_cast<std::size_t>(episode.selected_count),
                              false);
    return !prayer_gifts_ || !visible_weapon(owner);
  }
  if (choice < 1 ||
      static_cast<std::uint64_t>(choice) > inventory_.sizes_[owner])
    return false;
  const auto slot = static_cast<std::size_t>(choice - 1);
  const auto &item = inventory_.items_[owner * capacity_ + slot];
  const auto display = item[2] == 0 ? item[1] : item[2];
  if (episode.phase == 1) {
    if (exchange_models_.contains(display))
      return true;
    if (!market_prices_.empty() && display == 5)
      return true; // Never inspect enemy hands to decide whether Buy is legal.
    if (!market_prices_.empty() && display == 4) {
      for (std::size_t other = 0; other < inventory_.sizes_[owner]; ++other)
        if (other != slot &&
            inventory_.items_[owner * capacity_ + other][3] == 0)
          return true;
      return false;
    }
    const auto utility = effects_.find(display);
    if (utility != effects_.end())
      return visible_utility_eligible(owner, utility->second);
    const auto attack = attacks_.find(display);
    const auto boost = boosts_.find(display);
    return (attack != attacks_.end() &&
            (!cost_reducers_.empty() ||
             resources_[owner][0] >= attack->second.cost)) ||
           (boost != boosts_.end() && boost->second.can_lead &&
            (!cost_reducers_.empty() ||
             resources_[owner][0] >= boost->second.cost));
  }
  if (episode.phase == 2) {
    if (episode.attack_actions >= kFullGameMaxAttackActions)
      return resources_[owner][0] < episode.preview_cost &&
             slot == static_cast<std::size_t>(
                         episode.attack_slot); // Bounded cancel escape, never
                                               // an empty mask.
    if (selected_[env * capacity_ + slot] != 0)
      return true;
    if (episode.attack_size > 0 && cost_reducers_.contains(display) &&
        inventory_.category(displayed_model(
            env,
            static_cast<std::size_t>(
                attack_order_[env * capacity_ + static_cast<std::size_t>(
                                                    episode.attack_size - 1)] -
                1))) == 4)
      return true;
    const auto boost = boosts_.find(display);
    const auto &leader =
        inventory_.items_[owner * capacity_ +
                          static_cast<std::size_t>(episode.attack_slot)];
    const auto leader_model = leader[2] == 0 ? leader[1] : leader[2];
    if (inventory_.category(leader_model) != 1 ||
        hit_rate(leader_model) != 100 || boost == boosts_.end())
      return false;
    const auto &effect = boost->second;
    return (!cost_reducers_.empty() ||
            resources_[owner][0] >= episode.preview_cost + effect.cost) &&
           episode.preview_attack <= (effect.kind == 2
                                          ? kMaximumCounter / 2
                                          : kMaximumCounter - effect.value);
  }
  if (episode.defense_actions >= kFullGameMaxDefenseActions)
    return !cost_reducers_.empty() && selected_[env * capacity_ + slot] != 0 &&
           !legal_choice(
               env,
               0); // Undo an unaffordable response when confirm is unavailable.
  if (selected_[env * capacity_ + slot] != 0)
    return true; // Flash still allows undo.
  std::array<std::int64_t, 512> order{};
  if (!attack_order_.empty())
    std::copy_n(attack_order_.begin() +
                    static_cast<std::ptrdiff_t>(env * capacity_),
                episode.selected_count, order.begin());
  else {
    std::size_t count = 0;
    for (std::size_t other = 0; other < inventory_.sizes_[owner]; ++other)
      if (selected_[env * capacity_ + other] != 0)
        order[count++] = static_cast<std::int64_t>(other + 1);
  }
  return defense_choice(env, choice, order.data(),
                        static_cast<std::size_t>(episode.selected_count));
}

void FullGameBatch::consume_slot(Mutation &mutation, std::size_t owner,
                                 std::size_t slot) const {
  const auto index = mutation.environment * player_count_ + owner;
  const auto item = inventory_.items_[index * capacity_ + slot];
  auto [found, inserted] = mutation.hands.try_emplace(owner);
  if (!inserted)
    throw std::logic_error("full-game hand staged twice");
  auto &hand = found->second;
  hand.reserve(inventory_.sizes_[index]);
  for (std::size_t other = 0; other < inventory_.sizes_[index]; ++other)
    if (other != slot)
      hand.push_back(inventory_.items_[index * capacity_ + other]);
  if (inventory_.category(item[1]) == 4) {
    auto reused = item;
    reused[3] = 1;
    hand.push_back(reused);
    ++mutation.miracles;
  } else
    ++mutation.consumed;
  if (refill_on_use_)
    ++mutation.episode.gifts_due[owner];
}

void FullGameBatch::execute_utility(Mutation &mutation, std::size_t slot,
                                    bool ordered) const {
  const auto &episode = mutation.episode;
  const auto actor = static_cast<std::size_t>(episode.actor);
  const auto owner = mutation.environment * player_count_ + actor;
  const auto item = inventory_.items_[owner * capacity_ + slot];
  const auto actual = effects_.find(item[1]);
  const bool tolerate =
      ordered &&
      hidden_selection(mutation, static_cast<std::size_t>(episode.attack_size));
  if (actual == effects_.end() && !tolerate) {
    throw std::invalid_argument(
        "full-game actual card effect is not implemented yet");
  }
  const auto composition =
      ordered ? compose(mutation, true)
              : Composition{0, 0, actual->second.cost, 0, false};
  const auto cost = composition.cost;
  if (mutation.resources[actor][0] < cost) {
    throw std::invalid_argument(
        "full-game hidden actual miracle cost is unaffordable");
  }
  mutation.resources[actor][0] -= cost;
  mutation.paid = static_cast<std::uint64_t>(cost);
  record_waivers(mutation, composition, 2);
  record_ineffective(mutation, composition.ineffective,
                     static_cast<std::size_t>(episode.attack_size), 1);
  // Stage the actual use before effects can consume a passive Amulet from the
  // same hand. Whole-batch validation still precedes all commits.
  if (ordered)
    consume_attack(mutation, actor, false);
  else
    consume_slot(mutation, actor, slot);
  if (composition.ineffective[0]) {
    finish_turn(mutation, actor);
    return;
  }
  mutation.utility = true;
  if (apply_utility_effect(mutation, actor, actual->second, cost))
    resume_family(mutation);
  else
    finish_turn(mutation, actor);
}

void FullGameBatch::execute_discard(Mutation &mutation) const {
  auto &episode = mutation.episode;
  const auto actor = static_cast<std::size_t>(episode.actor);
  const auto owner = mutation.environment * player_count_ + actor;
  if (episode.discard_size <= 0)
    throw std::invalid_argument("full-game discard confirmation is empty");
  // Validate every actual selected role before staging removal. Displayed
  // legal masks never inspect protected hidden Sun/Mortar identities.
  std::int64_t performed = 0, removed = 0, retained = 0;
  for (std::int64_t i = 0; i < episode.discard_size; ++i) {
    const auto slot = static_cast<std::size_t>(mutation.order[i] - 1);
    const auto &item = inventory_.items_[owner * capacity_ + slot];
    if (!discard_models_.contains(item[1])) {
      if (!resolve_hidden_removals_ || (item[1] != 208 && item[1] != 209) ||
          item[2] == 0 || !discard_models_.contains(item[2]))
        throw std::invalid_argument(
            episode.apocalypse
                ? "full-game hidden actual sacrifice model is forbidden"
                : "full-game hidden actual discard model is forbidden");
      // The actual protected artifact remains owned, with its original flags
      // and relative order. This is neither held use nor an acquisition
      // receipt.
      mutation.selected[slot] = 0;
      ++episode.hidden_removal_stats[item[1] == 208 ? 5 : 6];
      ++retained;
      continue;
    }
    ++removed;
    performed += inventory_.category(item[1]) == 4 && item[3] != 0 ? 1 : 0;
  }
  if (retained != 0) {
    ++episode.hidden_removal_stats[episode.apocalypse ? 1 : 0];
    episode.hidden_removal_stats[2] += retained;
    episode.hidden_removal_stats[3] += removed;
    episode.hidden_removal_stats[4] += removed == 0 ? 1 : 0;
  }
  auto &hand = stage_hand(mutation, actor);
  hand.clear();
  for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot)
    if (mutation.selected[slot] == 0)
      hand.push_back(inventory_.items_[owner * capacity_ + slot]);
  auto *statistics = episode.apocalypse ? episode.sacrifice_stats.data()
                                        : episode.discard_stats.data();
  ++statistics[3];
  statistics[4] += removed;
  statistics[5] += performed;
  if (episode.apocalypse) {
    episode.gifts_due[actor] += removed;
    episode.sacrifice_gifts_due[actor] += removed;
    episode.sacrifice_stats[6] += removed;
  } else {
    mutation.discard = true;
    mutation.discarded = static_cast<std::uint64_t>(removed);
  }
  episode.discard_size = episode.discard_actions = 0;
  // Both operations are removal, not held use/performance or price payment.
  // Only Sacrifice requests one provisional post-tick replacement per removal.
  mutation.selected.fill(0);
  mutation.order.fill(0);
  finish_turn(mutation, actor);
}

FullGameBatch::Mutation FullGameBatch::prepare(FullGameCommandInput commands,
                                               std::size_t row) const {
  const auto env = commands(row, 0);
  if (env < 0 || static_cast<std::uint64_t>(env) >= batch_size_) {
    throw std::invalid_argument(
        "full-game command environment is out of range");
  }
  const auto index = static_cast<std::size_t>(env);
  const auto &episode = episodes_[index];
  if ((episode.phase != 1 && episode.phase != 2 && episode.phase != 3 &&
       episode.phase != 4 && episode.phase != 6 && episode.phase != 7) ||
      commands(row, 1) != episode.epoch ||
      commands(row, 2) != episode.decision ||
      commands(row, 3) != episode.actor || commands(row, 4) != episode.phase) {
    throw std::invalid_argument(
        "full-game command is stale, mismatched or noninteractive");
  }
  const auto choice = commands(row, 5);
  const auto actor = static_cast<std::size_t>(episode.actor);
  const auto owner = index * player_count_ + actor;
  if (!legal_choice(index, choice))
    throw std::invalid_argument(
        "full-game displayed utility choice or phase choice is unavailable");
  auto mutation = staged_episode(index);
  if (episode.phase == 1 && episode.confusion[actor] > 0)
    execute_confused_turn(mutation);
  else if (episode.phase == 6) {
    auto &current = mutation.episode;
    if (episode.trade_mode == 3)
      decide_purchase(mutation, choice == 1);
    else if (episode.trade_mode == 2) {
      if (choice == static_cast<std::int64_t>(capacity_) + 1) {
        current.phase = 1;
        current.turn_owner = current.attack_slot = -1;
        clear_market(mutation);
      } else if (choice == 0) {
        current.phase = 3;
        current.trade_mode = 0;
      } else {
        const auto slot = choice - 1;
        current.sale_slot = current.sale_slot == slot ? -1 : slot;
        ++current.trade_actions;
        ++current.market_stats[2];
      }
    } else if (choice == 0)
      execute_exchange(mutation);
    else if (choice == 9) {
      ++current.trade_stats[2];
      current.phase = 1;
      current.turn_owner = current.attack_slot = -1;
      current.trade_mode = current.trade_actions = 0;
      current.trade_wallet.fill(0);
    } else {
      const auto delta = exchange_delta(current, choice);
      const auto axis = choice <= 4 ? 1 : 2;
      current.trade_wallet[0] -= delta;
      current.trade_wallet[axis] += delta;
      ++current.trade_actions;
      ++current.trade_stats[1];
    }
  } else if (episode.phase == 7) {
    auto &current = mutation.episode;
    auto *statistics = current.apocalypse ? current.sacrifice_stats.data()
                                          : current.discard_stats.data();
    if (choice == static_cast<std::int64_t>(capacity_) + 1) {
      ++statistics[2];
      current.phase = 1;
      current.turn_owner = -1;
      current.discard_size = current.discard_actions = 0;
      mutation.selected.fill(0);
      mutation.order.fill(0);
    } else if (choice == 0)
      execute_discard(mutation);
    else {
      const auto slot = static_cast<std::size_t>(choice - 1);
      ++current.discard_actions;
      ++statistics[1];
      if (mutation.selected[slot] == 0) {
        mutation.selected[slot] = 1;
        mutation.order[current.discard_size++] = choice;
      } else {
        mutation.selected[slot] = 0;
        const auto end = mutation.order.begin() + current.discard_size;
        const auto position = std::find(mutation.order.begin(), end, choice);
        std::move(position + 1, end, position);
        mutation.order[--current.discard_size] = 0;
      }
    }
  } else if (episode.phase == 1 &&
             choice == static_cast<std::int64_t>(capacity_) + 1) {
    mutation.episode.phase = 7;
    mutation.episode.turn_owner = episode.actor;
    mutation.episode.discard_size = mutation.episode.discard_actions = 0;
    if (episode.apocalypse)
      ++mutation.episode.sacrifice_stats[0];
    else
      ++mutation.episode.discard_stats[0];
    mutation.selected.fill(0);
    mutation.order.fill(0);
  } else if (episode.phase == 1 && choice == 0) {
    mutation.pass = true;
    if (prayer_gifts_) {
      mutation.prayer = true;
      ++mutation.episode.gifts_due[actor];
    }
    finish_turn(mutation, actor);
  } else if (episode.phase == 1) {
    const auto slot = static_cast<std::size_t>(choice - 1);
    auto item = inventory_.items_[owner * capacity_ + slot];
    const auto displayed = item[2] == 0 ? item[1] : item[2];
    if (exchange_models_.contains(displayed)) {
      begin_exchange(mutation, slot);
      advance_decision(mutation, choice);
      return mutation;
    }
    if (!market_prices_.empty() && (displayed == 4 || displayed == 5)) {
      begin_market(mutation, slot, displayed - 3);
      advance_decision(mutation, choice);
      return mutation;
    }
    const auto visible = effects_.find(displayed);
    if (visible == effects_.end() || !cost_reducers_.empty()) {
      // Reserve only a public displayed slot. True identity/cost resolves on
      // cast.
      mutation.episode.turn_owner = episode.actor;
      mutation.episode.utility_selection = visible != effects_.end();
      mutation.episode.attack_slot = static_cast<std::int64_t>(slot);
      mutation.episode.phase = attack_order_.empty() ? 3 : 2;
      if (!attack_order_.empty()) {
        mutation.order[0] = choice;
        mutation.selected[slot] = 1;
        mutation.episode.attack_size = 1;
        mutation.episode.attack_actions = 1;
        update_preview(mutation);
      }
      advance_decision(mutation, choice);
      return mutation;
    }
    execute_utility(mutation, slot, false);
  } else if (episode.phase == 2) {
    if (choice == 0) {
      if (episode.utility_selection)
        execute_utility(mutation, static_cast<std::size_t>(episode.attack_slot),
                        true);
      else {
        mutation.episode.phase = 3;
        mutation.attack_confirm = true;
        const auto &item =
            inventory_.items_[owner * capacity_ +
                              static_cast<std::size_t>(episode.attack_slot)];
        if (hit_rate(item[2] == 0 ? item[1] : item[2]) < 100)
          cast_attack(mutation, choice, true);
      }
    } else {
      const auto slot = static_cast<std::size_t>(choice - 1);
      mutation.attack_toggle = true;
      ++mutation.episode.attack_actions;
      if (slot == static_cast<std::size_t>(episode.attack_slot)) {
        // Provisional local cancel: undoing the leader clears all selections.
        mutation.order.fill(0);
        mutation.selected.fill(0);
        mutation.episode.attack_size = 0;
        mutation.episode.phase = 1;
        mutation.episode.turn_owner = -1;
        mutation.episode.attack_slot = -1;
        mutation.episode.utility_selection = false;
        mutation.episode.preview_attack = mutation.episode.preview_element =
            mutation.episode.preview_cost = 0;
        mutation.episode.preview_area_count = 0;
      } else if (mutation.selected[slot] != 0) {
        const auto end = mutation.order.begin() + episode.attack_size;
        const auto position = std::find(mutation.order.begin(), end, choice);
        std::move(position + 1, end, position);
        mutation.order[--mutation.episode.attack_size] = 0;
        mutation.selected[slot] = 0;
        if (!cost_reducers_.empty()) {
          const auto old = mutation.order;
          mutation.order.fill(0);
          mutation.selected.fill(0);
          const auto size = mutation.episode.attack_size;
          mutation.episode.attack_size = 0;
          for (std::int64_t index = 0; index < size; ++index) {
            const auto retained = old[index];
            const auto model = displayed_model(
                mutation.environment, static_cast<std::size_t>(retained - 1));
            const auto count = mutation.episode.attack_size;
            if (cost_reducers_.contains(model) && count > 0 &&
                inventory_.category(displayed_model(
                    mutation.environment,
                    static_cast<std::size_t>(mutation.order[count - 1] - 1))) !=
                    4)
              continue;
            mutation.order[mutation.episode.attack_size++] = retained;
            mutation.selected[static_cast<std::size_t>(retained - 1)] = 1;
          }
        }
        update_preview(mutation);
      } else {
        mutation.order[mutation.episode.attack_size++] = choice;
        mutation.selected[slot] = 1;
        update_preview(mutation);
      }
    }
  } else if (episode.phase == 3) {
    if (episode.market_kind != 0)
      cast_market(mutation, choice);
    else
      cast_attack(mutation, choice, false);
  } else if (choice > 0) {
    const auto slot = static_cast<std::size_t>(choice - 1);
    if (attack_order_.empty()) {
      mutation.selected[slot] ^= 1;
      mutation.episode.selected_count += mutation.selected[slot] != 0 ? 1 : -1;
    } else if (mutation.selected[slot] == 0) {
      mutation.order[mutation.episode.selected_count++] = choice;
      mutation.selected[slot] = 1;
    } else {
      // Client-style undo: rebuild remaining choices, pruning entries whose
      // compatibility depended on the removed filter. Never consult true IDs.
      const auto previous = mutation.order;
      mutation.order.fill(0);
      mutation.selected.fill(0);
      mutation.episode.selected_count = 0;
      for (std::int64_t index = 0; index < episode.selected_count; ++index) {
        const auto retained = previous[index];
        if (retained != choice &&
            defense_choice(
                mutation.environment, retained, mutation.order.data(),
                static_cast<std::size_t>(mutation.episode.selected_count))) {
          mutation.order[mutation.episode.selected_count++] = retained;
          mutation.selected[static_cast<std::size_t>(retained - 1)] = 1;
        }
      }
    }
    ++mutation.episode.defense_actions;
    mutation.defense_toggle = true;
  } else {
    std::int64_t defense = 0;
    std::vector<DreamInventoryBatch::Item> hand;
    std::vector<DreamInventoryBatch::Item> reused;
    std::vector<DefenseEffect> counters;
    std::vector<DefenseEffect> self_effects;
    hand.reserve(inventory_.sizes_[owner]);
    for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot) {
      const auto &item = inventory_.items_[owner * capacity_ + slot];
      if (mutation.selected[slot] == 0)
        hand.push_back(item);
    }
    if (attack_order_.empty()) {
      std::size_t count = 0;
      for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot)
        if (mutation.selected[slot] != 0)
          mutation.order[count++] = static_cast<std::int64_t>(slot + 1);
    }
    const bool tolerate = hidden_selection(
        mutation, static_cast<std::size_t>(episode.selected_count));
    if (tolerate)
      resolve_ineffective_defenses(mutation, defense, counters, self_effects);
    bool prefix = true;
    for (std::int64_t index = 0; index < episode.selected_count; ++index) {
      const auto slot = static_cast<std::size_t>(mutation.order[index] - 1);
      const auto &item = inventory_.items_[owner * capacity_ + slot];
      if (!tolerate) {
        const auto effect = defense_effects_.find(item[1]);
        const bool filter =
            effect != defense_effects_.end() && effect->second.kind == 5;
        const bool attached_reducer =
            index > 0 && cost_reducers_.contains(item[1]) &&
            inventory_.category(
                inventory_.items_[owner * capacity_ +
                                  static_cast<std::size_t>(
                                      mutation.order[index - 1] - 1)][1]) == 4;
        if (filter) {
          if (!prefix || episode.attack == 0)
            throw std::invalid_argument(
                "full-game hidden actual filter must precede other defenses");
          mutation.episode.element = 0;
          ++mutation.filters_used;
          ++mutation.episode.counter_stats[9];
        }
        const auto kind = special_kind(item[1], mutation.episode);
        if (attached_reducer) {
          // The preceding miracle supplies the response. Reducer stats do not
          // turn its exclusive special into numeric armor.
        } else if (kind != 0) {
          const bool waived =
              index + 1 < episode.selected_count &&
              inventory_.category(item[1]) == 4 &&
              cost_reducers_.contains(
                  inventory_.items_[owner * capacity_ +
                                    static_cast<std::size_t>(
                                        mutation.order[index + 1] - 1)][1]);
          if (!prefix || (index + 1 != episode.selected_count &&
                          !(waived && index + 2 == episode.selected_count)))
            throw std::invalid_argument(
                "full-game hidden special defense must be exclusive");
          const auto original_cost = specials_.at(item[1]).cost;
          const auto cost = waived ? 0 : original_cost;
          if (mutation.resources[actor][0] < cost)
            throw std::invalid_argument(
                "full-game hidden actual miracle cost is unaffordable");
          mutation.resources[actor][0] -= cost;
          mutation.paid += static_cast<std::uint64_t>(cost);
          if (waived)
            record_waivers(mutation,
                           Composition{0, 0, 0, 0, false, original_cost, 1}, 4);
          mutation.special_kind = kind;
          prefix = false;
        } else if (!filter) {
          const auto actual = armor_.find(item[1]);
          if (actual == armor_.end())
            throw std::invalid_argument(
                "full-game actual defense effect is not implemented yet");
          if (episode.attack == 0 ||
              !compatible(mutation.episode.element, actual->second.element))
            throw std::invalid_argument(
                "full-game hidden actual defense element is incompatible");
          defense += actual->second.value;
          prefix = false;
          if (effect != defense_effects_.end()) {
            if (effect->second.kind <= 4)
              counters.push_back(effect->second);
            else if (effect->second.kind == 6 || effect->second.kind == 7)
              self_effects.push_back(effect->second);
          }
        }
      }
      if (inventory_.category(item[1]) == 4) {
        auto retained = item;
        retained[3] = 1;
        reused.push_back(retained);
        ++mutation.miracles;
      } else
        ++mutation.consumed;
      if (refill_on_use_)
        ++mutation.episode.gifts_due[actor];
    }
    hand.insert(hand.end(), reused.begin(), reused.end());
    if (episode.selected_count != 0)
      mutation.hands.emplace(actor, std::move(hand));
    if (mutation.special_kind >= 2) {
      auto target = episode.damage_source;
      if (mutation.special_kind == 2)
        mutation.episode.damage_source = episode.actor;
      else {
        // Provisional: any living seat, including the defender, preserving
        // source.
        std::array<std::int64_t, 9> eligible{};
        std::size_t count = 0;
        for (std::size_t seat = 0; seat < player_count_; ++seat)
          if (mutation.statuses[seat][0] > 0)
            eligible[count++] = static_cast<std::int64_t>(seat);
        target = eligible[random_rank(mutation.episode.bounce_rng, count)];
      }
      mutation.episode.target = mutation.episode.actor = target;
      ++mutation.episode.redirects;
      if (episode.active_family_kind == 7)
        ++mutation.episode.market_stats[6];
      mutation.episode.selected_count = mutation.episode.defense_actions = 0;
      mutation.selected.fill(0);
      mutation.order.fill(0);
      if (mutation.statuses[static_cast<std::size_t>(target)][0] == 0) {
        // A reflected post-death shot cannot open a dead actor's response or
        // resurrect it. The redirect use still consumes its normal receipt.
        complete_attack(mutation, 0);
        resume_family(mutation);
      }
      advance_decision(mutation, choice);
      return mutation; // Fresh response; no owner tick or gifts between hops.
    }
    if (episode.active_family_kind == 7) {
      resolve_market(mutation, mutation.special_kind == 1);
      advance_decision(mutation, choice);
      return mutation;
    }
    const auto damage =
        mutation.special_kind == 1
            ? 0
            : std::max<std::int64_t>(0, episode.attack - defense);
    mutation.damage = static_cast<std::uint64_t>(
        std::min(damage, mutation.statuses[actor][0]));
    mutation.statuses[actor][0] -= static_cast<std::int64_t>(mutation.damage);
    if (mutation.episode.element == 6 && mutation.damage > 0) {
      mutation.damage +=
          static_cast<std::uint64_t>(mutation.statuses[actor][0]);
      mutation.statuses[actor][0] = 0;
      ++mutation.darkness_finish;
    }
    if (mutation.damage > 0 && mutation.statuses[actor][0] == 0)
      resolve_hp_zero(mutation, actor, 1);
    guardian_damage(mutation, actor,
                    static_cast<std::int64_t>(mutation.damage));
    apply_attack_effect(mutation);
    // Ordered self-effects after incoming effects/revival, before counters.
    // This order is explicit and provisional, including mixed Hat/Fever masks.
    for (const auto &effect : self_effects)
      if (effect.kind == 7)
        apply_dream_redraw(mutation, actor);
      else if (mutation.statuses[actor][0] > 0) {
        apply_illness(mutation, actor, effect.value);
        ++mutation.self_curses;
        ++mutation.episode.counter_stats[10];
      }
    complete_attack(mutation, static_cast<std::int64_t>(mutation.damage));
    if (mutation.damage > 0) {
      if (static_cast<std::size_t>(std::count_if(
              mutation.family.begin(), mutation.family.end(),
              [](const auto &shot) { return shot.family_kind == 1; })) +
              counters.size() >
          player_count_ * capacity_)
        throw std::invalid_argument(
            "full-game counter queue exceeds bounded inventory");
      // Private LIFO stack: reverse insertion preserves click order and
      // resolves nested reactions before the remaining siblings. Refills remain
      // deferred.
      for (auto it = counters.rbegin(); it != counters.rend(); ++it) {
        const auto basis = static_cast<std::int64_t>(mutation.damage);
        const auto value = it->kind == 2 ? it->value : it->value * basis;
        enqueue_attack(mutation,
                       {1, episode.actor,
                        it->kind == 3 ? episode.actor : episode.damage_source,
                        it->kind == 1 ? value : 0, it->element, 2, it->rate,
                        it->kind == 2   ? 4
                        : it->kind == 3 ? 6
                        : it->kind == 4 ? 7
                                        : 0,
                        it->kind == 1 ? 0 : value, it->kind, basis});
        ++mutation.episode.counter_stats[0];
      }
    }
    resume_family(mutation);
  }
  advance_decision(mutation, choice);
  return mutation;
}

void FullGameBatch::decide_outcome(Mutation &mutation) const noexcept {
  const auto count = living_factions(mutation);
  std::int64_t winner = -1;
  for (std::size_t seat = 0; seat < player_count_; ++seat)
    if (mutation.statuses[seat][0] > 0) {
      if (winner < 0)
        winner = static_cast<std::int64_t>(seat);
    }
  if (count < 2) {
    mutation.episode.phase = 12;
    mutation.episode.outcome = count == 1 ? 1 : 2;
    mutation.episode.winner = winner;
  }
}

void FullGameBatch::finish_turn(Mutation &mutation, std::size_t owner) const {
  auto &episode = mutation.episode;
  if (episode.turn_owner < 0)
    episode.turn_owner = static_cast<std::int64_t>(owner);
  // Generated post-turn effects may belong to another seat. The original
  // owner remains authoritative for the one tick, endings and next-seat walk.
  owner = static_cast<std::size_t>(episode.turn_owner);
  if (!mutation.family.empty()) {
    resume_family(mutation);
    return;
  }
  if (!episode.turn_ticked) {
    auto &status = mutation.statuses[owner];
    IllnessState state{static_cast<std::uint16_t>(status[0]),
                       static_cast<std::uint8_t>(status[1])};
    if (state.hp > 0)
      state = periodic_illness_effect(
          state); // Never resurrect a dead Heaven owner.
    const auto before_periodic = status[0];
    status[0] = state.hp = static_cast<std::uint16_t>(
        std::min<std::int64_t>(state.hp, resource_cap_));
    status[1] = state.stage;
    const auto periodic_loss = before_periodic - status[0];
    if (before_periodic > 0 && state.hp == 0)
      resolve_hp_zero(mutation, owner, 4);
    guardian_damage(mutation, owner, periodic_loss);
    state = {static_cast<std::uint16_t>(status[0]),
             static_cast<std::uint8_t>(status[1])};
    if (state.hp > 0 && state.stage != 0 &&
        random_rank(mutation.episode.illness_rng, 100) < 5) {
      const auto before_worsening = state.hp;
      state = worsen_illness(state);
      status[0] = state.hp = static_cast<std::uint16_t>(
          std::min<std::int64_t>(state.hp, resource_cap_));
      status[1] = state.stage;
      if (state.hp == 0)
        resolve_hp_zero(mutation, owner, 5);
      guardian_damage(mutation, owner, before_worsening - state.hp);
    }
    ++status[3];
    mutation.ticked_owner = static_cast<std::int64_t>(owner);
    ++episode.turns;
    episode.turn_ticked = true;
  }
  if (!mutation.family.empty()) {
    // A periodic/worsening death has already ticked once. Its Bow family
    // finishes before endings; resuming here must never tick a second time.
    resume_family(mutation);
    return;
  }
  if (!episode.guardians_scheduled) {
    episode.guardians_scheduled = true;
    schedule_guardians(mutation, owner);
    if (!mutation.family.empty()) {
      resume_family(mutation);
      return;
    }
  }
  if (apocalypse_after_turns_ != 0 && schedule_receipts(mutation)) {
    resume_family(mutation);
    return;
  }
  episode.guardians_scheduled = false;
  episode.guardian_model = 0;
  episode.generated_model = episode.generated_virtual_leader = 0;
  episode.phenomenon_model = 0;
  episode.turn_ticked = false;
  episode.postturn_receipts = 0;
  episode.phase = 1;
  episode.turn_owner = -1;
  episode.damage_source = -1;
  episode.redirects = 0;
  episode.attack_slot = -1;
  episode.target = -1;
  episode.attack = 0;
  episode.element = 0;
  episode.origin = -1;
  episode.hit_rate = 100;
  episode.effect_kind = episode.effect_value = 0;
  episode.counter_kind = episode.counter_damage_basis = 0;
  episode.defense_actions = 0;
  episode.selected_count = 0;
  episode.attack_size = episode.attack_actions = 0;
  episode.preview_attack = episode.preview_element = episode.preview_cost = 0;
  episode.preview_area_count = episode.area_components = 0;
  episode.area_family = false;
  episode.utility_selection = false;
  episode.trade_mode = episode.trade_actions = 0;
  episode.trade_wallet.fill(0);
  clear_market(mutation);
  episode.weapon_kind = episode.weapon_value = episode.strikes_remaining = 0;
  episode.recipient_strikes_remaining = 0;
  episode.discard_size = episode.discard_actions = 0;
  episode.active_family_kind = episode.original_remaining = 0;
  episode.danger_family = false;
  episode.danger_value = episode.danger_element = 0;
  mutation.selected.fill(0);
  mutation.order.fill(0);
  decide_outcome(mutation);
  if (episode.phase == 12)
    return; // Real endings take precedence over limits.
  for (std::size_t offset = 1; offset <= player_count_; ++offset) {
    const auto next = (owner + offset) % player_count_;
    if (mutation.statuses[next][0] > 0) {
      episode.actor = static_cast<std::int64_t>(next);
      break;
    }
  }
}

void FullGameBatch::advance_decision(Mutation &mutation,
                                     std::int64_t choice) const {
  auto &episode = mutation.episode;
  episode.last_choice = choice;
  ++episode.commands;
  ++episode.decision;
  mutation.accepted_command = true;
  const bool turn_limit =
      episode.phase != 4 &&
      !(episode.phase == 6 && episode.active_family_kind == 7) &&
      static_cast<std::uint64_t>(episode.turns) >= max_turns_;
  if (episode.phase != 12 &&
      (turn_limit ||
       static_cast<std::uint64_t>(episode.commands) >= max_decisions_)) {
    episode.phase = 13;
    episode.outcome = turn_limit ? 3 : 4;
  }
  if (episode.phase == 1 || episode.phase == 12 || episode.phase == 13)
    grant_pending_gifts(mutation);
}

void FullGameBatch::step(FullGameCommandInput commands) {
  if (commands.shape(0) > batch_size_)
    throw std::invalid_argument("full-game command row limit exceeded");
  std::vector<Mutation> staged;
  staged.reserve(commands.shape(0));
  std::set<std::size_t> seen;
  for (std::size_t row = 0; row < commands.shape(0); ++row) {
    auto mutation = prepare(commands, row);
    if (!seen.insert(mutation.environment).second)
      throw std::invalid_argument("duplicate full-game command environment");
    for (std::size_t seat = 0; seat < player_count_; ++seat)
      if (mutation.statuses[seat][0] < 0 ||
          mutation.statuses[seat][0] > resource_cap_ ||
          mutation.resources[seat][0] < 0 ||
          mutation.resources[seat][0] > resource_cap_ ||
          mutation.resources[seat][1] < 0 ||
          mutation.resources[seat][1] > resource_cap_)
        throw std::logic_error("full-game resource cap invariant violated");
    staged.push_back(std::move(mutation));
  }
  // Commit contains no validation, random draws, or allocation.
  for (auto &mutation : staged)
    commit(mutation);
}

void FullGameBatch::commit(Mutation &mutation) noexcept {
  for (std::size_t seat = 0; seat < player_count_; ++seat) {
    const auto owner = mutation.environment * player_count_ + seat;
    const auto before = statuses_.states_[owner];
    statuses_.states_[owner] = mutation.statuses[seat];
    if (before != mutation.statuses[seat])
      statuses_.record(owner, 5, before);
    resources_[owner] = mutation.resources[seat];
  }
  statuses_.tick_count_ += mutation.ticked_owner >= 0 ? 1 : 0;
  statuses_.cure_count_ += mutation.cured_owner >= 0 ? 1 : 0;
  statuses_.curse_count_ += mutation.inflicted_curse;
  statuses_.illness_count_ += mutation.inflicted_illness;
  for (const auto &[seat, hand] : mutation.hands)
    inventory_.commit_hand(mutation.environment * player_count_ + seat, hand);
  std::copy_n(mutation.selected.begin(), capacity_,
              selected_.begin() + static_cast<std::ptrdiff_t>(
                                      mutation.environment * capacity_));
  if (!attack_order_.empty())
    std::copy_n(mutation.order.begin(), capacity_,
                attack_order_.begin() + static_cast<std::ptrdiff_t>(
                                            mutation.environment * capacity_));
  inventory_.consumed_count_ += mutation.consumed;
  inventory_.miracle_use_count_ += mutation.miracles;
  inventory_.restored_count_ += mutation.restored;
  inventory_.removal_count_ += mutation.removed;
  removals_resolved_ += mutation.removal_effects;
  const auto &previous_guardians =
      episodes_[mutation.environment].guardian_stats;
  const auto &next_guardians = mutation.episode.guardian_stats;
  guardian_summons_ +=
      static_cast<std::uint64_t>(next_guardians[0] - previous_guardians[0]);
  guardian_activations_ +=
      static_cast<std::uint64_t>(next_guardians[3] - previous_guardians[3]);
  guardian_resolved_ +=
      static_cast<std::uint64_t>(next_guardians[7] - previous_guardians[7]);
  guardian_damage_ +=
      static_cast<std::uint64_t>(next_guardians[13] - previous_guardians[13]);
  guardian_departures_ += static_cast<std::uint64_t>(
      next_guardians[11] + next_guardians[12] - previous_guardians[11] -
      previous_guardians[12]);
  statuses_.cure_count_ +=
      static_cast<std::uint64_t>(next_guardians[18] - previous_guardians[18]);
  const auto &previous_devils = episodes_[mutation.environment].devil_stats;
  devils_ += static_cast<std::uint64_t>(mutation.episode.devil_stats[2] -
                                        previous_devils[2]);
  devil_damage_ += static_cast<std::uint64_t>(mutation.episode.devil_stats[4] -
                                              previous_devils[4]);
  devil_removed_ += static_cast<std::uint64_t>(mutation.episode.devil_stats[7] -
                                               previous_devils[7]);
  episodes_[mutation.environment] = mutation.episode;
  families_[mutation.environment].swap(mutation.family);
  actions_ += mutation.accepted_command ? 1 : 0;
  passes_ += mutation.pass ? 1 : 0;
  utilities_ += mutation.utility ? 1 : 0;
  cp_utilities_ += mutation.cp_utility;
  utility_cp_gain_ += mutation.utility_cp_gain;
  utility_hp_damage_ += mutation.utility_hp_damage;
  danger_casts_ += mutation.danger_cast ? 1 : 0;
  automatic_danger_damage_ += mutation.automatic_danger_damage;
  redraws_ += mutation.redraws;
  ascensions_ += mutation.ascensions;
  ascension_damage_ += mutation.ascension_damage;
  areas_ += mutation.area_cast ? 1 : 0;
  area_damage_ += mutation.area_damage;
  discards_ += mutation.discard ? 1 : 0;
  discarded_ += mutation.discarded;
  redrawn_ += mutation.redrawn;
  mp_spent_ += mutation.paid;
  attacks_cast_ += mutation.attack_cast ? 1 : 0;
  attacks_resolved_ += mutation.attack_resolved ? 1 : 0;
  defense_toggles_ += mutation.defense_toggle ? 1 : 0;
  hp_damage_ += mutation.damage;
  inventory_.gift_count_ += mutation.gifts;
  automatic_gifts_ += mutation.gifts;
  suppressed_gifts_ += mutation.suppressed_gifts;
  overflow_ += mutation.overflow;
  prayers_ += mutation.prayer ? 1 : 0;
  attack_toggles_ += mutation.attack_toggle ? 1 : 0;
  attack_confirms_ += mutation.attack_confirm ? 1 : 0;
  attack_components_ += mutation.attack_components;
  darkness_finishes_ += mutation.darkness_finish;
  blocks_ += mutation.special_kind == 1 ? 1 : 0;
  reflections_ += mutation.special_kind == 2 ? 1 : 0;
  bounces_ += mutation.special_kind == 3 ? 1 : 0;
  chances_cast_ += mutation.chance_result != 0 ? 1 : 0;
  chance_hits_ += mutation.chance_result == 1 ? 1 : 0;
  chance_misses_ += mutation.chance_result == -1 ? 1 : 0;
  absorbed_hp_ += mutation.absorbed_hp;
  absorptions_ += mutation.absorption ? 1 : 0;
  inflicted_curses_ += mutation.inflicted_curse;
  inflicted_illnesses_ += mutation.inflicted_illness;
  illness_effect_damage_ += mutation.illness_effect_damage;
  dark_cloud_hits_ += mutation.dark_cloud_hit ? 1 : 0;
  counters_cast_ += mutation.counters_cast;
  counters_resolved_ += mutation.counters_resolved;
  counter_misses_ += mutation.counter_misses;
  counters_suppressed_ += mutation.counters_suppressed;
  filters_used_ += mutation.filters_used;
  self_curses_ += mutation.self_curses;
  revivals_ += mutation.revivals;
  revived_hp_ += mutation.revived_hp;
  waived_mp_ += mutation.waived;
  cost_waivers_ += mutation.waivers;
  recoil_hp_damage_ += mutation.recoil_damage;
}

void FullGameBatch::reset_environments(ActionInput environments) {
  const auto indices = checked_environments(environments);
  for (const auto env : indices) {
    if (episodes_[env].epoch >= kMaximumCounter)
      throw std::invalid_argument("full-game episode epoch is exhausted");
  }
  for (const auto env : indices) {
    const auto first = env * player_count_;
    for (std::size_t player = 0; player < player_count_; ++player) {
      const auto index = first + player;
      statuses_.states_[index] = {statuses_.initial_hp_, 0, 0, 0};
      statuses_.transitions_[index] = {};
      resources_[index] = {initial_mp_, initial_cp_};
      inventory_.sizes_[index] = 0;
      std::fill_n(inventory_.items_.begin() +
                      static_cast<std::ptrdiff_t>(index * capacity_),
                  capacity_, DreamInventoryBatch::Item{});
    }
    episodes_[env] = fresh_episode(env, episodes_[env].epoch + 1);
    families_[env].clear();
    std::fill_n(selected_.begin() +
                    static_cast<std::ptrdiff_t>(env * capacity_),
                capacity_, 0);
    if (!attack_order_.empty())
      std::fill_n(attack_order_.begin() +
                      static_cast<std::ptrdiff_t>(env * capacity_),
                  capacity_, 0);
  }
}

Int64_2D FullGameBatch::episode_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 9);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    const std::array<std::int64_t, 9> row{
        episode.epoch,  episode.decision, episode.actor,
        episode.phase,  episode.turns,    episode.outcome,
        episode.winner, episode.commands, episode.last_choice};
    std::copy(row.begin(), row.end(), buffer.get() + env * 9);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 9});
}

CurseStateSnapshot FullGameBatch::diagnostic_players() const {
  auto buffer = std::make_unique<std::int64_t[]>(resources_.size() * 6);
  for (std::size_t index = 0; index < resources_.size(); ++index) {
    const auto &state = statuses_.states_[index];
    const std::array<std::int64_t, 6> row{state[0],
                                          resources_[index][0],
                                          resources_[index][1],
                                          state[1],
                                          state[2],
                                          state[3]};
    std::copy(row.begin(), row.end(), buffer.get() + index * 6);
  }
  return owned_array<CurseStateSnapshot>(std::move(buffer),
                                         {batch_size_, player_count_, 6});
}

CurseStateSnapshot FullGameBatch::acquisition_snapshot() const {
  auto buffer =
      std::make_unique<std::int64_t[]>(batch_size_ * player_count_ * 3);
  for (std::size_t env = 0; env < batch_size_; ++env)
    for (std::size_t seat = 0; seat < player_count_; ++seat) {
      const auto offset = (env * player_count_ + seat) * 3;
      buffer[offset] = episodes_[env].gifts_due[seat];
      buffer[offset + 1] = episodes_[env].gifts_given[seat];
      buffer[offset + 2] = episodes_[env].evicted[seat];
    }
  return owned_array<CurseStateSnapshot>(std::move(buffer),
                                         {batch_size_, player_count_, 3});
}

ActorInventorySnapshot FullGameBatch::actor_hands() const {
  std::vector<std::int64_t> envs(batch_size_), actors(batch_size_);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    envs[env] = static_cast<std::int64_t>(env);
    actors[env] = episodes_[env].actor;
  }
  return inventory_.actor_hands(ActionInput(envs.data(), {batch_size_}),
                                ActionInput(actors.data(), {batch_size_}));
}

Bool2D FullGameBatch::choice_masks() const {
  const auto width = capacity_ + 10;
  auto buffer = std::make_unique<bool[]>(batch_size_ * width);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    for (std::size_t choice = 0; choice < width; ++choice)
      buffer[env * width + choice] =
          legal_choice(env, static_cast<std::int64_t>(choice));
  }
  return owned_array<Bool2D>(std::move(buffer), {batch_size_, width});
}

Bool2D FullGameBatch::selected_defenses() const {
  auto buffer = std::make_unique<bool[]>(batch_size_ * capacity_);
  for (std::size_t env = 0; env < batch_size_; ++env)
    if (episodes_[env].phase == 4)
      for (std::size_t slot = 0; slot < capacity_; ++slot)
        buffer[env * capacity_ + slot] = selected_[env * capacity_ + slot] != 0;
  return owned_array<Bool2D>(std::move(buffer), {batch_size_, capacity_});
}

Bool2D FullGameBatch::selected_attacks() const {
  auto buffer = std::make_unique<bool[]>(batch_size_ * capacity_);
  for (std::size_t env = 0; env < batch_size_; ++env)
    if (episodes_[env].phase == 2 || episodes_[env].phase == 3)
      for (std::size_t slot = 0; slot < capacity_; ++slot)
        buffer[env * capacity_ + slot] =
            !attack_order_.empty() && selected_[env * capacity_ + slot] != 0;
  return owned_array<Bool2D>(std::move(buffer), {batch_size_, capacity_});
}

Int64_2D FullGameBatch::attack_order() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * capacity_);
  for (std::size_t env = 0; env < batch_size_; ++env)
    if (!attack_order_.empty() &&
        (episodes_[env].phase == 2 || episodes_[env].phase == 3))
      std::copy_n(attack_order_.begin() +
                      static_cast<std::ptrdiff_t>(env * capacity_),
                  capacity_, buffer.get() + env * capacity_);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, capacity_});
}

Int64_2D FullGameBatch::attack_selection_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 5);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    if (attack_order_.empty() || (episode.phase != 2 && episode.phase != 3))
      continue;
    const std::array<std::int64_t, 5> row{
        episode.attack_size, episode.preview_attack, episode.preview_element,
        episode.preview_cost, episode.attack_actions};
    std::copy(row.begin(), row.end(), buffer.get() + env * 5);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 5});
}

Int64_2D FullGameBatch::pending_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 10);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    if (episode.utility_selection ||
        (episode.market_kind != 0 && episode.phase != 4) ||
        (episode.phase != 2 && episode.phase != 3 && episode.phase != 4))
      continue;
    auto value = episode.attack, element = episode.element,
         origin = episode.origin;
    std::int64_t defense = 0;
    if (episode.phase == 2 || episode.phase == 3) {
      const auto owner =
          env * player_count_ + static_cast<std::size_t>(episode.actor);
      const auto &item =
          inventory_.items_[owner * capacity_ +
                            static_cast<std::size_t>(episode.attack_slot)];
      const auto model = item[2] == 0 ? item[1] : item[2];
      if (attack_order_.empty()) {
        const auto &visible = attacks_.at(model);
        value = visible.value;
        element = visible.element;
        origin = visible.origin;
      } else {
        value = episode.preview_attack;
        element = episode.preview_element;
        const auto category = inventory_.category(model);
        origin = category == 4 ? 1 : category == 3 ? 3 : 0;
      }
    } else {
      element = displayed_defense_element(env);
      auto context = episode;
      context.element = element;
      const auto owner =
          env * player_count_ + static_cast<std::size_t>(episode.actor);
      for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot) {
        if (selected_[env * capacity_ + slot] == 0)
          continue;
        const auto &item = inventory_.items_[owner * capacity_ + slot];
        const auto model = item[2] == 0 ? item[1] : item[2];
        bool attached = false;
        if (!cost_reducers_.empty() && cost_reducers_.contains(model)) {
          const auto begin = attack_order_.begin() +
                             static_cast<std::ptrdiff_t>(env * capacity_);
          const auto position = std::find(begin, begin + episode.selected_count,
                                          static_cast<std::int64_t>(slot + 1));
          attached =
              position != begin && position != begin + episode.selected_count &&
              inventory_.category(displayed_model(
                  env, static_cast<std::size_t>(*(position - 1) - 1))) == 4;
        }
        if (special_kind(model, context) == 0 && !attached)
          defense += armor_.at(model).value;
      }
    }
    const std::array<std::int64_t, 10> row{
        1,
        episode.turn_owner,
        episode.target,
        value,
        element,
        origin,
        defense,
        episode.phase == 2 || episode.phase == 3 ? episode.attack_size
                                                 : episode.selected_count,
        episode.phase == 2 || episode.phase == 3 ? episode.attack_actions
                                                 : episode.defense_actions,
        episode.phase == 2 || episode.phase == 3 ? episode.attack_slot + 1 : 0};
    std::copy(row.begin(), row.end(), buffer.get() + env * 10);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 10});
}

Int64_2D FullGameBatch::special_defense_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 5);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    auto episode = episodes_[env];
    if (episode.phase != 4)
      continue;
    episode.element = displayed_defense_element(env);
    const auto owner =
        env * player_count_ + static_cast<std::size_t>(episode.actor);
    std::int64_t kind = 0, cost = 0;
    for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot) {
      if (selected_[env * capacity_ + slot] == 0)
        continue;
      const auto &item = inventory_.items_[owner * capacity_ + slot];
      const auto model = item[2] == 0 ? item[1] : item[2];
      kind = special_kind(model, episode);
      if (kind != 0) {
        cost =
            cost_reducers_.empty()
                ? specials_.at(model).cost
                : ordered_cost(owner, attack_order_.data() + env * capacity_,
                               static_cast<std::size_t>(episode.selected_count),
                               false);
        break;
      }
    }
    const std::array<std::int64_t, 5> row{1, episode.damage_source,
                                          episode.redirects, kind, cost};
    std::copy(row.begin(), row.end(), buffer.get() + env * 5);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 5});
}

Int64_2D FullGameBatch::chance_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 4);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    if (episode.utility_selection || episode.market_kind != 0 ||
        episode.counter_kind != 0 ||
        (episode.phase != 2 && episode.phase != 3 && episode.phase != 4))
      continue;
    auto rate = episode.hit_rate;
    if (episode.phase != 4) {
      const auto owner =
          env * player_count_ + static_cast<std::size_t>(episode.actor);
      const auto &item =
          inventory_.items_[owner * capacity_ +
                            static_cast<std::size_t>(episode.attack_slot)];
      rate = hit_rate(item[2] == 0 ? item[1] : item[2]);
    }
    const std::array<std::int64_t, 4> row{
        1, rate, rate < 100 && episode.phase == 4 ? 1 : 0, rate < 100 ? 1 : 0};
    std::copy(row.begin(), row.end(), buffer.get() + env * 4);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 4});
}

Int64_2D FullGameBatch::attack_effect_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 4);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    if (episode.utility_selection ||
        (episode.phase != 2 && episode.phase != 3 && episode.phase != 4))
      continue;
    auto kind = episode.effect_kind, value = episode.effect_value;
    if (episode.phase != 4) {
      const auto owner =
          env * player_count_ + static_cast<std::size_t>(episode.actor);
      const auto &item =
          inventory_.items_[owner * capacity_ +
                            static_cast<std::size_t>(episode.attack_slot)];
      const auto found = attack_effects_.find(item[2] == 0 ? item[1] : item[2]);
      kind = found == attack_effects_.end() ? 0 : found->second.kind;
      value = found == attack_effects_.end() ? 0 : found->second.value;
      const auto removal = removals_.find(item[2] == 0 ? item[1] : item[2]);
      if (removal != removals_.end()) {
        kind = 7 + removal->second.kind;
        value = removal->second.value;
      }
      const auto weapon =
          complex_weapons_.find(item[2] == 0 ? item[1] : item[2]);
      if (weapon != complex_weapons_.end() && weapon->second.kind == 2)
        kind = 10;
    }
    const std::array<std::int64_t, 4> row{
        1, kind, value,
        episode.phase == 4 ? episode.damage_source : episode.actor};
    std::copy(row.begin(), row.end(), buffer.get() + env * 4);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 4});
}

Int64_2D FullGameBatch::attack_effect_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 6);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    const std::array<std::int64_t, 6> row{
        episode.absorptions,           episode.absorbed_hp,
        episode.inflicted_curses,      episode.inflicted_illnesses,
        episode.illness_effect_damage, episode.dark_cloud_hits};
    std::copy(row.begin(), row.end(), buffer.get() + env * 6);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 6});
}

Int64_2D FullGameBatch::chance_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 3);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    const std::array<std::int64_t, 3> row{
        episode.chance_casts, episode.chance_hits, episode.chance_misses};
    std::copy(row.begin(), row.end(), buffer.get() + env * 3);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 3});
}

Int64_2D FullGameBatch::defense_order() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * capacity_);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    if (episodes_[env].phase != 4)
      continue;
    if (!attack_order_.empty())
      std::copy_n(
          attack_order_.begin() + static_cast<std::ptrdiff_t>(env * capacity_),
          episodes_[env].selected_count, buffer.get() + env * capacity_);
    else {
      const auto owner =
          env * player_count_ + static_cast<std::size_t>(episodes_[env].actor);
      std::size_t count = 0;
      for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot)
        if (selected_[env * capacity_ + slot] != 0)
          buffer[env * capacity_ + count++] =
              static_cast<std::int64_t>(slot + 1);
    }
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, capacity_});
}

Int64_2D FullGameBatch::counter_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 6);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    if (episode.phase != 4 || episode.counter_kind == 0)
      continue;
    const std::array<std::int64_t, 6> row{1,
                                          episode.counter_kind,
                                          episode.damage_source,
                                          episode.target,
                                          episode.counter_damage_basis,
                                          episode.hit_rate};
    std::copy(row.begin(), row.end(), buffer.get() + env * 6);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 6});
}

Int64_2D FullGameBatch::counter_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 12);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    std::copy(episodes_[env].counter_stats.begin(),
              episodes_[env].counter_stats.end(), buffer.get() + env * 12);
    buffer[env * 12 + 11] = static_cast<std::int64_t>(
        std::count_if(families_[env].begin(), families_[env].end(),
                      [](const auto &shot) { return shot.family_kind == 1; }));
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 12});
}

ActorInventorySnapshot FullGameBatch::passive_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * capacity_ * 2);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    if (episode.phase < 1 || episode.phase > 4)
      continue;
    const auto owner =
        env * player_count_ + static_cast<std::size_t>(episode.actor);
    for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot) {
      const auto display = displayed_model(env, slot);
      const auto found = passives_.find(display);
      const auto danger = dangers_.find(display);
      const auto offset = (env * capacity_ + slot) * 2;
      if (found != passives_.end()) {
        buffer[offset] = 1; // Revive; displayed-only, not trigger eligibility.
        buffer[offset + 1] = found->second;
      } else if (danger != dangers_.end() && danger->second.kind == 2) {
        buffer[offset] = 2; // Attract danger; still not a manual use command.
        buffer[offset + 1] = danger->second.value;
      } else if (const auto bow = ascensions_by_model_.find(display);
                 bow != ascensions_by_model_.end()) {
        buffer[offset] =
            3; // Displayed dying ATK, not actual trigger ownership.
        buffer[offset + 1] = bow->second.dying_attack;
      }
    }
  }
  return owned_array<ActorInventorySnapshot>(std::move(buffer),
                                             {batch_size_, capacity_, 2});
}

Int64_2D FullGameBatch::revival_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 10);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].revival_stats.begin(),
              episodes_[env].revival_stats.end(), buffer.get() + env * 10);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 10});
}

Int64_2D FullGameBatch::hidden_targeting_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 4);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].hidden_targeting_stats.begin(),
              episodes_[env].hidden_targeting_stats.end(),
              buffer.get() + env * 4);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 4});
}

Int64_2D FullGameBatch::hidden_trade_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 9);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].hidden_trade_stats.begin(),
              episodes_[env].hidden_trade_stats.end(), buffer.get() + env * 9);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 9});
}

Int64_2D FullGameBatch::team_ids() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 9);
  for (std::size_t env = 0; env < batch_size_; ++env)
    for (std::size_t seat = 0; seat < 9; ++seat)
      buffer[env * 9 + seat] =
          seat < player_count_ ? episodes_[env].teams[seat] : -1;
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 9});
}

CurseStateSnapshot FullGameBatch::team_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 9 * 4);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &e = episodes_[env];
    const auto actor = static_cast<std::size_t>(e.actor);
    for (std::size_t offset = 0; offset < 9; ++offset) {
      const auto out = (env * 9 + offset) * 4;
      buffer[out] = buffer[out + 2] = -1;
      if (offset >= player_count_)
        continue;
      const auto seat = (actor + offset) % player_count_;
      buffer[out] = static_cast<std::int64_t>(seat);
      buffer[out + 1] = 1;
      buffer[out + 2] = e.teams[seat];
      buffer[out + 3] = seat == actor ? 1 : are_enemies(e, actor, seat) ? 3 : 2;
    }
  }
  return owned_array<CurseStateSnapshot>(std::move(buffer),
                                         {batch_size_, 9, 4});
}

Bool2D FullGameBatch::winning_seats() const {
  auto buffer = std::make_unique<bool[]>(batch_size_ * 9);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &e = episodes_[env];
    if (e.phase != 12 || e.outcome != 1)
      continue;
    for (std::size_t seat = 0; seat < player_count_; ++seat)
      buffer[env * 9 + seat] =
          !are_enemies(e, static_cast<std::size_t>(e.winner), seat);
  }
  return owned_array<Bool2D>(std::move(buffer), {batch_size_, 9});
}

Int64_2D FullGameBatch::hidden_removal_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 7);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].hidden_removal_stats.begin(),
              episodes_[env].hidden_removal_stats.end(),
              buffer.get() + env * 7);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 7});
}

Int64_2D FullGameBatch::role_profiles() const {
  auto buffer = std::make_unique<std::int64_t[]>(role_profiles_.size() * 2);
  std::size_t row = 0;
  for (const auto &[model, bits] : role_profiles_) {
    buffer[row * 2] = model;
    buffer[row * 2 + 1] = bits;
    ++row;
  }
  return owned_array<Int64_2D>(std::move(buffer), {role_profiles_.size(), 2});
}

Int64_2D FullGameBatch::ineffective_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 14);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].ineffective_stats.begin(),
              episodes_[env].ineffective_stats.end(), buffer.get() + env * 14);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 14});
}

Int64_2D FullGameBatch::ineffective_model_counts() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 237);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].ineffective_models.begin(),
              episodes_[env].ineffective_models.end(),
              buffer.get() + env * 237);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 237});
}

Int64_2D FullGameBatch::removal_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 8);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].removal_stats.begin(),
              episodes_[env].removal_stats.end(), buffer.get() + env * 8);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 8});
}

Int64_2D FullGameBatch::cp_utility_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 4);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].cp_utility_stats.begin(),
              episodes_[env].cp_utility_stats.end(), buffer.get() + env * 4);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 4});
}

Int64_2D FullGameBatch::utility_selection_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 4);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    if (episode.phase != 2 || !episode.utility_selection)
      continue;
    const auto effect = effects_.at(
        displayed_model(env, static_cast<std::size_t>(episode.attack_slot)));
    const std::array<std::int64_t, 4> row{1, effect.kind, effect.value,
                                          episode.preview_cost};
    std::copy(row.begin(), row.end(), buffer.get() + env * 4);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 4});
}

Int64_2D FullGameBatch::compound_utility_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 10);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].compound_utility_stats.begin(),
              episodes_[env].compound_utility_stats.end(),
              buffer.get() + env * 10);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 10});
}

Int64_2D FullGameBatch::cost_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 5);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].cost_stats.begin(),
              episodes_[env].cost_stats.end(), buffer.get() + env * 5);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 5});
}

Int64_2D FullGameBatch::complex_weapon_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 4);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    std::int64_t kind = 0, value = 0, remaining = 1;
    if ((episode.phase == 2 || episode.phase == 3) &&
        !episode.utility_selection) {
      const auto weapon = complex_weapons_.find(
          displayed_model(env, static_cast<std::size_t>(episode.attack_slot)));
      if (weapon != complex_weapons_.end()) {
        kind = weapon->second.kind;
        value = weapon->second.value;
        remaining = kind == 3 ? 2 : 1;
      }
    } else if (episode.phase == 4) {
      // Only the currently revealed payload owns this role. A nested counter
      // cannot inherit a queued original/generated weapon's metadata.
      kind = episode.weapon_kind;
      value = episode.weapon_value;
      remaining =
          kind == 3 ? (episode.area_family ? episode.recipient_strikes_remaining
                                           : episode.strikes_remaining)
                    : 1;
    }
    if (kind != 0) {
      const std::array<std::int64_t, 4> row{1, kind, value, remaining};
      std::copy(row.begin(), row.end(), buffer.get() + env * 4);
    }
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 4});
}

Int64_2D FullGameBatch::complex_weapon_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 8);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].weapon_stats.begin(),
              episodes_[env].weapon_stats.end(), buffer.get() + env * 8);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 8});
}

Int64_2D FullGameBatch::danger_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 3);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    std::int64_t value = 0, element = 0;
    if ((episode.phase == 2 || episode.phase == 3) &&
        !episode.utility_selection) {
      const auto danger = dangers_.find(
          displayed_model(env, static_cast<std::size_t>(episode.attack_slot)));
      if (danger != dangers_.end() && danger->second.kind == 1) {
        value = danger->second.value;
        element = danger->second.element;
      }
    } else if (episode.phase == 4 && episode.danger_family) {
      value = episode.danger_value;
      element = episode.danger_element;
    }
    if (value != 0) {
      const std::array<std::int64_t, 3> row{1, value, element};
      std::copy(row.begin(), row.end(), buffer.get() + env * 3);
    }
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 3});
}

Int64_2D FullGameBatch::danger_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 8);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].danger_stats.begin(),
              episodes_[env].danger_stats.end(), buffer.get() + env * 8);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 8});
}

Int64_2D FullGameBatch::dream_defense_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 8);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].dream_defense_stats.begin(),
              episodes_[env].dream_defense_stats.end(), buffer.get() + env * 8);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 8});
}

Int64_2D FullGameBatch::attack_family_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 16);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    std::copy(episode.family_stats.begin(), episode.family_stats.end(),
              buffer.get() + env * 16);
    buffer[env * 16 + 13] = static_cast<std::int64_t>(families_[env].size());
    buffer[env * 16 + 14] = episode.active_family_kind;
    buffer[env * 16 + 15] = episode.turn_ticked ? 1 : 0;
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 16});
}

Int64_2D FullGameBatch::area_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 3);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    const auto count = episode.phase == 2 || episode.phase == 3
                           ? episode.preview_area_count
                       : episode.phase == 4 ? episode.area_components
                                            : 0;
    if (count > 0) {
      buffer[env * 3] = 1;
      buffer[env * 3 + 1] = count;
      buffer[env * 3 + 2] = 1;
    }
  }
  // No future recipient count/order, RNG or true unplayed card is a policy
  // input.
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 3});
}

Int64_2D FullGameBatch::area_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 8);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].area_stats.begin(),
              episodes_[env].area_stats.end(), buffer.get() + env * 8);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 8});
}

Int64_2D FullGameBatch::discard_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 5);
  for (std::size_t env = 0; env < batch_size_; ++env)
    if (episodes_[env].phase == 7) {
      const auto &episode = episodes_[env];
      const std::array<std::int64_t, 5> row{
          1, episode.discard_size, episode.discard_actions,
          kFullGameMaxDiscardActions, episode.apocalypse ? 2 : 1};
      std::copy(row.begin(), row.end(), buffer.get() + env * 5);
    }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 5});
}

Int64_2D FullGameBatch::discard_order() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * capacity_);
  for (std::size_t env = 0; env < batch_size_; ++env)
    if (episodes_[env].phase == 7)
      std::copy_n(attack_order_.begin() +
                      static_cast<std::ptrdiff_t>(env * capacity_),
                  capacity_, buffer.get() + env * capacity_);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, capacity_});
}

Int64_2D FullGameBatch::discard_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 6);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].discard_stats.begin(),
              episodes_[env].discard_stats.end(), buffer.get() + env * 6);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 6});
}

Int64_2D FullGameBatch::sacrifice_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 9);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].sacrifice_stats.begin(),
              episodes_[env].sacrifice_stats.end(), buffer.get() + env * 9);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 9});
}

Int64_2D FullGameBatch::sacrifice_model_counts() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 237);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].sacrifice_model_counts.begin(),
              episodes_[env].sacrifice_model_counts.end(),
              buffer.get() + env * 237);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 237});
}

CurseStateSnapshot FullGameBatch::player_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 9 * 8);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto actor = static_cast<std::size_t>(episodes_[env].actor);
    const auto actor_mask = static_cast<std::uint8_t>(
        statuses_.states_[env * player_count_ + actor][2]);
    for (std::size_t offset = 0; offset < 9; ++offset) {
      const auto output = (env * 9 + offset) * 8;
      if (offset >= player_count_) {
        buffer[output] = -1;
        continue;
      }
      const auto seat = (actor + offset) % player_count_;
      const auto owner = env * player_count_ + seat;
      buffer[output] = static_cast<std::int64_t>(seat);
      buffer[output + 1] = 1;
      if (fog_hides_other_player(actor_mask, offset == 0))
        continue;
      const auto &state = statuses_.states_[owner];
      buffer[output + 2] = 1;
      buffer[output + 3] = state[0];
      buffer[output + 4] = resources_[owner][0];
      buffer[output + 5] = resources_[owner][1];
      buffer[output + 6] = state[1];
      buffer[output + 7] = state[2];
    }
  }
  return owned_array<CurseStateSnapshot>(std::move(buffer),
                                         {batch_size_, 9, 8});
}

CurseStateSnapshot FullGameBatch::guardian_snapshot() const {
  auto buffer =
      std::make_unique<std::int64_t[]>(batch_size_ * player_count_ * 2);
  for (std::size_t env = 0; env < batch_size_; ++env)
    for (std::size_t seat = 0; seat < player_count_; ++seat)
      std::copy(episodes_[env].guardians[seat].begin(),
                episodes_[env].guardians[seat].end(),
                buffer.get() + (env * player_count_ + seat) * 2);
  return owned_array<CurseStateSnapshot>(std::move(buffer),
                                         {batch_size_, player_count_, 2});
}

CurseStateSnapshot FullGameBatch::guardian_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 9 * 4);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &e = episodes_[env];
    if (e.phase == 0 || e.phase == 12 || e.phase == 13)
      continue;
    const auto actor = static_cast<std::size_t>(e.actor);
    const bool fog =
        (statuses_.states_[env * player_count_ + actor][2] & kCurseFogBit) != 0;
    for (std::size_t offset = 0; offset < player_count_; ++offset) {
      const auto seat = (actor + offset) % player_count_;
      const bool visible = offset == 0 || !fog;
      const std::array<std::int64_t, 4> row{static_cast<std::int64_t>(seat), 1,
                                            visible ? 1 : 0,
                                            visible ? e.guardians[seat][0] : 0};
      std::copy(row.begin(), row.end(), buffer.get() + (env * 9 + offset) * 4);
    }
  }
  return owned_array<CurseStateSnapshot>(std::move(buffer),
                                         {batch_size_, 9, 4});
}

Int64_2D FullGameBatch::guardian_effect_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 4);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &e = episodes_[env];
    if (e.phase == 4 &&
        (e.active_family_kind == 4 || e.active_family_kind == 9 ||
         (e.active_family_kind == 7 && e.generated_model != 0))) {
      const std::array<std::int64_t, 4> row{1, e.guardian_model,
                                            e.damage_source, e.target};
      std::copy(row.begin(), row.end(), buffer.get() + env * 4);
    }
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 4});
}

Int64_2D FullGameBatch::guardian_statistics() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 19);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].guardian_stats.begin(),
              episodes_[env].guardian_stats.end(), buffer.get() + env * 19);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 19});
}

Int64_2D FullGameBatch::guardian_model_counts() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 40);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].guardian_model_counts.begin(),
              episodes_[env].guardian_model_counts.end(),
              buffer.get() + env * 40);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 40});
}

Int64_2D FullGameBatch::guardian_generated_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 23);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].guardian_generated_stats.begin(),
              episodes_[env].guardian_generated_stats.end(),
              buffer.get() + env * 23);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 23});
}

Int64_2D FullGameBatch::generated_action_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 6);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &e = episodes_[env];
    if ((e.phase != 4 && !(e.phase == 6 && e.trade_mode == 3)) ||
        e.generated_model == 0 ||
        (e.active_family_kind != 9 && e.active_family_kind != 7))
      continue;
    const std::array<std::int64_t, 6> row{1,
                                          e.guardian_model,
                                          e.generated_model,
                                          e.generated_virtual_leader,
                                          e.damage_source,
                                          e.target};
    std::copy(row.begin(), row.end(), buffer.get() + env * 6);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 6});
}

Int64_2D FullGameBatch::guardian_generated_model_counts() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 237);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].guardian_generated_model_counts.begin(),
              episodes_[env].guardian_generated_model_counts.end(),
              buffer.get() + env * 237);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 237});
}

Int64_2D FullGameBatch::guardian_generated_execution_counts() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 237);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].guardian_generated_execution_counts.begin(),
              episodes_[env].guardian_generated_execution_counts.end(),
              buffer.get() + env * 237);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 237});
}

Int64_2D FullGameBatch::apocalypse_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 3);
  for (std::size_t env = 0; env < batch_size_; ++env)
    if (episodes_[env].phase != 0 && episodes_[env].phase < 12) {
      buffer[env * 3] = apocalypse_after_turns_ != 0 ? 1 : 0;
      buffer[env * 3 + 1] = episodes_[env].apocalypse ? 1 : 0;
      buffer[env * 3 + 2] = static_cast<std::int64_t>(apocalypse_after_turns_);
    }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 3});
}

Int64_2D FullGameBatch::devil_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 18);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].devil_stats.begin(),
              episodes_[env].devil_stats.end(), buffer.get() + env * 18);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 18});
}

Int64_2D FullGameBatch::devil_model_counts() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 5);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].devil_model_counts.begin(),
              episodes_[env].devil_model_counts.end(), buffer.get() + env * 5);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 5});
}

CurseStateSnapshot FullGameBatch::control_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 9 * 4);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &e = episodes_[env];
    if (e.phase == 0 || e.phase >= 12)
      continue;
    const auto actor = static_cast<std::size_t>(e.actor);
    const bool fog =
        (statuses_.states_[env * player_count_ + actor][2] & kCurseFogBit) != 0;
    for (std::size_t offset = 0; offset < player_count_; ++offset) {
      const auto seat = (actor + offset) % player_count_;
      const bool visible = offset == 0 || !fog;
      const std::array<std::int64_t, 4> row{static_cast<std::int64_t>(seat), 1,
                                            visible ? 1 : 0,
                                            visible ? e.confusion[seat] : 0};
      std::copy(row.begin(), row.end(), buffer.get() + (env * 9 + offset) * 4);
    }
  }
  return owned_array<CurseStateSnapshot>(std::move(buffer),
                                         {batch_size_, 9, 4});
}

Int64_2D FullGameBatch::confusion_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 17);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    std::copy(episodes_[env].confusion.begin(), episodes_[env].confusion.end(),
              buffer.get() + env * 17);
    std::copy(episodes_[env].confusion_stats.begin(),
              episodes_[env].confusion_stats.end(),
              buffer.get() + env * 17 + 9);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 17});
}

Bool2D FullGameBatch::policy_gradient_masks() const {
  auto buffer = std::make_unique<bool[]>(batch_size_);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &e = episodes_[env];
    buffer[env] =
        (e.phase == 1 || e.phase == 2 || e.phase == 3 || e.phase == 4 ||
         e.phase == 6 || e.phase == 7) &&
        !(e.phase == 1 && e.confusion[static_cast<std::size_t>(e.actor)] > 0);
  }
  return owned_array<Bool2D>(std::move(buffer), {batch_size_, 1});
}

Int64_2D FullGameBatch::phenomenon_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 4);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &e = episodes_[env];
    if (e.phase == 4 && e.active_family_kind == 6) {
      const std::array<std::int64_t, 4> row{1, e.phenomenon_model,
                                            e.damage_source, e.target};
      std::copy(row.begin(), row.end(), buffer.get() + env * 4);
    }
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 4});
}

Int64_2D FullGameBatch::phenomenon_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 23);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].phenomenon_stats.begin(),
              episodes_[env].phenomenon_stats.end(), buffer.get() + env * 23);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 23});
}

Int64_2D FullGameBatch::phenomenon_model_counts() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 10);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].phenomenon_model_counts.begin(),
              episodes_[env].phenomenon_model_counts.end(),
              buffer.get() + env * 10);
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 10});
}

void bind_full_game(nb::module_ &module) {
  module.attr("FULL_GAME_KERNEL_SCHEMA_VERSION") = kFullGameKernelSchemaVersion;
  module.attr("FULL_GAME_COMMAND_SCHEMA_VERSION") =
      kFullGameCommandSchemaVersion;
  module.attr("FULL_GAME_ATTACK_FAMILY_SCHEMA_VERSION") =
      kFullGameAttackFamilySchemaVersion;
  module.attr("FULL_GAME_OBSERVATION_SCHEMA_VERSION") =
      kFullGameKernelSchemaVersion;
  module.attr("FULL_GAME_RULESET_ID") = kFullGameRulesetId;
  module.attr("FULL_GAME_MAX_DEFENSE_ACTIONS") = kFullGameMaxDefenseActions;
  module.attr("FULL_GAME_MAX_ATTACK_ACTIONS") = kFullGameMaxAttackActions;
  module.attr("FULL_GAME_MAX_DISCARD_ACTIONS") = kFullGameMaxDiscardActions;
  module.attr("FULL_GAME_MAX_TRADE_ACTIONS") = kFullGameMaxTradeActions;
  module.attr("FULL_GAME_TRADE_CHOICE_SCHEMA_VERSION") =
      kFullGameTradeChoiceSchemaVersion;
  nb::class_<FullGameBatch>(module, "FullGameBatch")
      .def(nb::init<
               std::size_t, std::size_t, InventoryProfileInput, InventoryInput,
               std::size_t, std::uint64_t, std::uint64_t, std::uint64_t,
               std::uint16_t, std::uint16_t, std::uint16_t,
               std::optional<GuardianWeightInput>,
               std::optional<GuardianWeightInput>,
               std::optional<InventoryProfileInput>, std::size_t, bool, bool,
               std::size_t, bool, std::optional<FullGameBoostInput>,
               std::optional<GuardianWeightInput>,
               std::optional<InventoryProfileInput>,
               std::optional<FullGameAttackEffectInput>,
               std::optional<GuardianWeightInput>,
               std::optional<InventoryProfileInput>,
               std::optional<FullGameAttackEffectInput>,
               std::optional<InventoryInput>, std::optional<InventoryInput>,
               std::optional<InventoryInput>, std::optional<InventoryInput>,
               std::optional<FullGameBoostInput>,
               std::optional<InventoryProfileInput>, std::optional<ActionInput>,
               std::optional<FullGameGuardianInput>,
               std::optional<InventoryProfileInput>,
               std::optional<InventoryInput>, std::uint64_t,
               std::optional<FullGamePhenomenonInput>,
               std::optional<ActionInput>, std::optional<ActionInput>,
               std::optional<FullGameAttackEffectInput>,
               std::optional<InventoryInput>,
               std::optional<InventoryProfileInput>, bool, std::uint16_t, bool,
               bool, bool, std::optional<InventoryProfileInput>, bool, bool>(),
           nb::arg("batch_size"), nb::arg("player_count"),
           nb::arg("inventory_profiles").noconvert(),
           nb::arg("utility_profiles").noconvert(), nb::arg("capacity") = 512,
           nb::arg("seed") = 67, nb::arg("max_turns") = 1000,
           nb::arg("max_decisions") = 4000, nb::arg("initial_hp") = 40,
           nb::arg("initial_mp") = 10, nb::arg("initial_cp") = 0,
           nb::arg("attack_profiles").noconvert() = nb::none(),
           nb::arg("armor_profiles").noconvert() = nb::none(),
           nb::arg("gift_profiles").noconvert() = nb::none(),
           nb::arg("initial_cards") = 0, nb::arg("refill_on_use") = false,
           nb::arg("prayer_gifts") = false, nb::arg("hand_limit") = 0,
           nb::arg("oldest_overflow") = false,
           nb::arg("boost_profiles").noconvert() = nb::none(),
           nb::arg("special_profiles").noconvert() = nb::none(),
           nb::arg("chance_profiles").noconvert() = nb::none(),
           nb::arg("attack_effect_profiles").noconvert() = nb::none(),
           nb::arg("defense_effect_profiles").noconvert() = nb::none(),
           nb::arg("passive_profiles").noconvert() = nb::none(),
           nb::arg("removal_profiles").noconvert() = nb::none(),
           nb::arg("cost_reducer_profiles").noconvert() = nb::none(),
           nb::arg("complex_weapon_profiles").noconvert() = nb::none(),
           nb::arg("danger_profiles").noconvert() = nb::none(),
           nb::arg("dream_defense_profiles").noconvert() = nb::none(),
           nb::arg("ascension_profiles").noconvert() = nb::none(),
           nb::arg("area_profiles").noconvert() = nb::none(),
           nb::arg("discard_model_ids").noconvert() = nb::none(),
           nb::arg("guardian_profiles").noconvert() = nb::none(),
           nb::arg("summon_profiles").noconvert() = nb::none(),
           nb::arg("devil_profiles").noconvert() = nb::none(),
           nb::arg("apocalypse_after_turns") = 0,
           nb::arg("phenomenon_profiles").noconvert() = nb::none(),
           nb::arg("fate_model_ids").noconvert() = nb::none(),
           nb::arg("exchange_model_ids").noconvert() = nb::none(),
           nb::arg("market_profiles").noconvert() = nb::none(),
           nb::arg("guardian_generated_profiles").noconvert() = nb::none(),
           nb::arg("guardian_action_profiles").noconvert() = nb::none(),
           nb::arg("sacrifice_enabled") = false, nb::arg("resource_cap") = 100,
           nb::arg("resolve_hidden_targeting") = false,
           nb::arg("resolve_hidden_trades") = false,
           nb::arg("resolve_hidden_components") = false,
           nb::arg("role_profiles").noconvert() = nb::none(),
           nb::arg("resolve_hidden_removals") = false,
           nb::arg("teams_enabled") = false)
      .def_prop_ro("resource_cap", &FullGameBatch::resource_cap)
      .def_prop_ro("resolve_hidden_targeting",
                   &FullGameBatch::resolve_hidden_targeting)
      .def("hidden_targeting_snapshot",
           &FullGameBatch::hidden_targeting_snapshot)
      .def_prop_ro("resolve_hidden_trades",
                   &FullGameBatch::resolve_hidden_trades)
      .def("hidden_trade_snapshot", &FullGameBatch::hidden_trade_snapshot)
      .def_prop_ro("resolve_hidden_components",
                   &FullGameBatch::resolve_hidden_components)
      .def("role_profiles", &FullGameBatch::role_profiles)
      .def("ineffective_snapshot", &FullGameBatch::ineffective_snapshot)
      .def("ineffective_model_counts", &FullGameBatch::ineffective_model_counts)
      .def_prop_ro("resolve_hidden_removals",
                   &FullGameBatch::resolve_hidden_removals)
      .def("hidden_removal_snapshot", &FullGameBatch::hidden_removal_snapshot)
      .def_prop_ro("teams_enabled", &FullGameBatch::teams_enabled)
      .def("seed_teams", &FullGameBatch::seed_teams,
           nb::arg("environments").noconvert(), nb::arg("owners").noconvert(),
           nb::arg("teams").noconvert())
      .def("team_ids", &FullGameBatch::team_ids)
      .def("team_observations", &FullGameBatch::team_observations)
      .def("winning_seats", &FullGameBatch::winning_seats)
      .def("seed_confusion", &FullGameBatch::seed_confusion,
           nb::arg("environments").noconvert(), nb::arg("owners").noconvert(),
           nb::arg("remaining_turns").noconvert())
      .def("control_observations", &FullGameBatch::control_observations)
      .def("confusion_snapshot", &FullGameBatch::confusion_snapshot)
      .def("policy_gradient_masks", &FullGameBatch::policy_gradient_masks)
      .def("phenomenon_observations", &FullGameBatch::phenomenon_observations)
      .def("phenomenon_snapshot", &FullGameBatch::phenomenon_snapshot)
      .def("phenomenon_model_counts", &FullGameBatch::phenomenon_model_counts)
      .def("apocalypse_observations", &FullGameBatch::apocalypse_observations)
      .def("devil_snapshot", &FullGameBatch::devil_snapshot)
      .def("devil_model_counts", &FullGameBatch::devil_model_counts)
      .def_prop_ro("devil_count", &FullGameBatch::devil_count)
      .def_prop_ro("devil_hp_damage", &FullGameBatch::devil_hp_damage)
      .def_prop_ro("devil_removed_count", &FullGameBatch::devil_removed_count)
      .def("seed_guardians", &FullGameBatch::seed_guardians,
           nb::arg("environments").noconvert(), nb::arg("owners").noconvert(),
           nb::arg("groups").noconvert())
      .def("seed_players", &FullGameBatch::seed_players,
           nb::arg("environments").noconvert(), nb::arg("owners").noconvert(),
           nb::arg("hp_mp_cp_illness").noconvert(),
           nb::arg("curse_masks").noconvert())
      .def("seed_hand", &FullGameBatch::seed_hand, nb::arg("environment"),
           nb::arg("owner"), nb::arg("items").noconvert())
      .def("deal_cards", &FullGameBatch::deal_cards,
           nb::arg("environments").noconvert(), nb::arg("owners").noconvert(),
           nb::arg("instance_ids").noconvert(),
           nb::arg("model_ids").noconvert())
      .def("start_environments", &FullGameBatch::start_environments,
           nb::arg("environments").noconvert())
      .def("reset_environments", &FullGameBatch::reset_environments,
           nb::arg("environments").noconvert())
      .def("step", &FullGameBatch::step, nb::arg("commands").noconvert())
      .def("episode_snapshot", &FullGameBatch::episode_snapshot)
      .def("diagnostic_players", &FullGameBatch::diagnostic_players)
      .def("diagnostic_inventory", &FullGameBatch::diagnostic_inventory)
      .def("actor_hands", &FullGameBatch::actor_hands)
      .def("player_observations", &FullGameBatch::player_observations)
      .def("choice_masks", &FullGameBatch::choice_masks)
      .def("trade_observations", &FullGameBatch::trade_observations)
      .def("trade_snapshot", &FullGameBatch::trade_snapshot)
      .def("market_observations", &FullGameBatch::market_observations)
      .def("market_snapshot", &FullGameBatch::market_snapshot)
      .def("market_escrow_snapshot", &FullGameBatch::market_escrow_snapshot)
      .def("pending_observations", &FullGameBatch::pending_observations)
      .def("special_defense_observations",
           &FullGameBatch::special_defense_observations)
      .def("chance_observations", &FullGameBatch::chance_observations)
      .def("chance_snapshot", &FullGameBatch::chance_snapshot)
      .def("attack_effect_observations",
           &FullGameBatch::attack_effect_observations)
      .def("attack_effect_snapshot", &FullGameBatch::attack_effect_snapshot)
      .def("defense_order", &FullGameBatch::defense_order)
      .def("counter_observations", &FullGameBatch::counter_observations)
      .def("counter_snapshot", &FullGameBatch::counter_snapshot)
      .def("passive_observations", &FullGameBatch::passive_observations)
      .def("revival_snapshot", &FullGameBatch::revival_snapshot)
      .def("removal_snapshot", &FullGameBatch::removal_snapshot)
      .def_prop_ro("removal_count", &FullGameBatch::removal_count)
      .def_prop_ro("removal_effect_count", &FullGameBatch::removal_effect_count)
      .def_prop_ro("revival_count", &FullGameBatch::revival_count)
      .def_prop_ro("revived_hp", &FullGameBatch::revived_hp)
      .def_prop_ro("counter_count", &FullGameBatch::counter_count)
      .def_prop_ro("resolved_counter_count",
                   &FullGameBatch::resolved_counter_count)
      .def_prop_ro("counter_miss_count", &FullGameBatch::counter_miss_count)
      .def_prop_ro("suppressed_counter_count",
                   &FullGameBatch::suppressed_counter_count)
      .def_prop_ro("filtered_attack_count",
                   &FullGameBatch::filtered_attack_count)
      .def_prop_ro("self_curse_count", &FullGameBatch::self_curse_count)
      .def_prop_ro("absorbed_hp", &FullGameBatch::absorbed_hp)
      .def_prop_ro("absorption_count", &FullGameBatch::absorption_count)
      .def_prop_ro("inflicted_curse_count",
                   &FullGameBatch::inflicted_curse_count)
      .def_prop_ro("inflicted_illness_count",
                   &FullGameBatch::inflicted_illness_count)
      .def_prop_ro("illness_effect_damage",
                   &FullGameBatch::illness_effect_damage)
      .def_prop_ro("dark_cloud_hit_count", &FullGameBatch::dark_cloud_hit_count)
      .def_prop_ro("chance_count", &FullGameBatch::chance_count)
      .def_prop_ro("chance_hit_count", &FullGameBatch::chance_hit_count)
      .def_prop_ro("chance_miss_count", &FullGameBatch::chance_miss_count)
      .def_prop_ro("block_count", &FullGameBatch::block_count)
      .def_prop_ro("reflection_count", &FullGameBatch::reflection_count)
      .def_prop_ro("bounce_count", &FullGameBatch::bounce_count)
      .def("selected_defenses", &FullGameBatch::selected_defenses)
      .def("selected_attacks", &FullGameBatch::selected_attacks)
      .def("attack_order", &FullGameBatch::attack_order)
      .def("attack_selection_observations",
           &FullGameBatch::attack_selection_observations)
      .def_prop_ro("attack_toggle_count", &FullGameBatch::attack_toggle_count)
      .def_prop_ro("attack_confirm_count", &FullGameBatch::attack_confirm_count)
      .def_prop_ro("attack_component_count",
                   &FullGameBatch::attack_component_count)
      .def_prop_ro("darkness_finish_count",
                   &FullGameBatch::darkness_finish_count)
      .def("acquisition_snapshot", &FullGameBatch::acquisition_snapshot)
      .def_prop_ro("automatic_gift_count", &FullGameBatch::automatic_gift_count)
      .def_prop_ro("suppressed_gift_count",
                   &FullGameBatch::suppressed_gift_count)
      .def_prop_ro("overflow_count", &FullGameBatch::overflow_count)
      .def_prop_ro("prayer_count", &FullGameBatch::prayer_count)
      .def_prop_ro("attack_count", &FullGameBatch::attack_count)
      .def_prop_ro("resolved_attack_count",
                   &FullGameBatch::resolved_attack_count)
      .def_prop_ro("defense_toggle_count", &FullGameBatch::defense_toggle_count)
      .def_prop_ro("hp_damage", &FullGameBatch::hp_damage)
      .def_prop_ro("action_count", &FullGameBatch::action_count)
      .def_prop_ro("pass_count", &FullGameBatch::pass_count)
      .def_prop_ro("utility_count", &FullGameBatch::utility_count)
      .def("cp_utility_snapshot", &FullGameBatch::cp_utility_snapshot)
      .def("compound_utility_snapshot",
           &FullGameBatch::compound_utility_snapshot)
      .def_prop_ro("utility_hp_damage", &FullGameBatch::utility_hp_damage)
      .def("cost_snapshot", &FullGameBatch::cost_snapshot)
      .def("complex_weapon_observations",
           &FullGameBatch::complex_weapon_observations)
      .def("complex_weapon_snapshot", &FullGameBatch::complex_weapon_snapshot)
      .def("danger_observations", &FullGameBatch::danger_observations)
      .def("danger_snapshot", &FullGameBatch::danger_snapshot)
      .def("dream_defense_snapshot", &FullGameBatch::dream_defense_snapshot)
      .def("attack_family_snapshot", &FullGameBatch::attack_family_snapshot)
      .def("area_observations", &FullGameBatch::area_observations)
      .def("area_snapshot", &FullGameBatch::area_snapshot)
      .def("discard_observations", &FullGameBatch::discard_observations)
      .def("discard_order", &FullGameBatch::discard_order)
      .def("discard_snapshot", &FullGameBatch::discard_snapshot)
      .def("sacrifice_snapshot", &FullGameBatch::sacrifice_snapshot)
      .def("sacrifice_model_counts", &FullGameBatch::sacrifice_model_counts)
      .def("guardian_snapshot", &FullGameBatch::guardian_snapshot)
      .def("guardian_observations", &FullGameBatch::guardian_observations)
      .def("guardian_effect_observations",
           &FullGameBatch::guardian_effect_observations)
      .def("guardian_statistics", &FullGameBatch::guardian_statistics)
      .def("guardian_model_counts", &FullGameBatch::guardian_model_counts)
      .def("guardian_generated_snapshot",
           &FullGameBatch::guardian_generated_snapshot)
      .def("guardian_generated_model_counts",
           &FullGameBatch::guardian_generated_model_counts)
      .def("guardian_generated_execution_counts",
           &FullGameBatch::guardian_generated_execution_counts)
      .def("generated_action_observations",
           &FullGameBatch::generated_action_observations)
      .def_prop_ro("guardian_summon_count",
                   &FullGameBatch::guardian_summon_count)
      .def_prop_ro("guardian_activation_count",
                   &FullGameBatch::guardian_activation_count)
      .def_prop_ro("guardian_resolved_count",
                   &FullGameBatch::guardian_resolved_count)
      .def_prop_ro("guardian_hp_damage", &FullGameBatch::guardian_hp_damage)
      .def_prop_ro("guardian_departure_count",
                   &FullGameBatch::guardian_departure_count)
      .def_prop_ro("discard_count", &FullGameBatch::discard_count)
      .def_prop_ro("discarded_card_count", &FullGameBatch::discarded_card_count)
      .def_prop_ro("area_count", &FullGameBatch::area_count)
      .def_prop_ro("area_hp_damage", &FullGameBatch::area_hp_damage)
      .def_prop_ro("ascension_count", &FullGameBatch::ascension_count)
      .def_prop_ro("ascension_hp_damage", &FullGameBatch::ascension_hp_damage)
      .def_prop_ro("redraw_count", &FullGameBatch::redraw_count)
      .def_prop_ro("redrawn_count", &FullGameBatch::redrawn_count)
      .def_prop_ro("danger_count", &FullGameBatch::danger_count)
      .def_prop_ro("automatic_danger_hp_damage",
                   &FullGameBatch::automatic_danger_hp_damage)
      .def_prop_ro("recoil_hp_damage", &FullGameBatch::recoil_hp_damage)
      .def("utility_selection_observations",
           &FullGameBatch::utility_selection_observations)
      .def_prop_ro("waived_mp", &FullGameBatch::waived_mp)
      .def_prop_ro("cost_waiver_count", &FullGameBatch::cost_waiver_count)
      .def_prop_ro("cp_utility_count", &FullGameBatch::cp_utility_count)
      .def_prop_ro("utility_cp_gain", &FullGameBatch::utility_cp_gain)
      .def_prop_ro("mp_spent", &FullGameBatch::mp_spent)
      .def_prop_ro("gift_count", &FullGameBatch::gift_count)
      .def_prop_ro("consumed_count", &FullGameBatch::consumed_count)
      .def_prop_ro("miracle_use_count", &FullGameBatch::miracle_use_count)
      .def_prop_ro("restored_count", &FullGameBatch::restored_count);
}

} // namespace godfield_sim
