#include "full_game_batch.h"
#include "combat_rules.h"
#include "curse_rules.h"

#include <algorithm>
#include <memory>
#include <set>
#include <stdexcept>

namespace godfield_sim {
namespace {
constexpr std::int64_t kMaximumCounter = 9007199254740991;
std::uint64_t random_word(std::uint64_t &state) noexcept {
  // Separate provisional SplitMix streams; not the official random stream.
  state += 0x9e3779b97f4a7c15ULL;
  auto word = state;
  word = (word ^ (word >> 30)) * 0xbf58476d1ce4e5b9ULL;
  word = (word ^ (word >> 27)) * 0x94d049bb133111ebULL;
  return word ^ (word >> 31);
}
std::uint64_t random_rank(std::uint64_t &state, std::uint64_t bound) {
  const auto threshold = (std::uint64_t{0} - bound) % bound;
  for (int attempt = 0; attempt < 16; ++attempt) {
    const auto value = random_word(state);
    if (value >= threshold)
      return value % bound;
  }
  throw std::runtime_error("full-game bounded random sampling failed");
}
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

std::size_t
FullGameBatch::validate_dimensions(std::size_t batch_size, std::size_t players,
                                   std::size_t capacity, std::uint64_t turns,
                                   std::uint64_t decisions, std::uint16_t hp,
                                   std::uint16_t mp, std::uint16_t cp) {
  if (batch_size == 0 || players < 2 || players > 9 || capacity == 0 ||
      capacity > 512 || batch_size > 2000000 / players / capacity ||
      turns < 1 || turns > 1000000000 || decisions < 1 ||
      decisions > 1000000000 || hp < 1 || hp > 100 || mp > 100 || cp > 100) {
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
    std::optional<FullGameAttackEffectInput> attack_effect_profiles)
    : batch_size_(validate_dimensions(batch_size, player_count, capacity,
                                      max_turns, max_decisions, initial_hp,
                                      initial_mp, initial_cp)),
      player_count_(player_count), capacity_(capacity), seed_(seed),
      max_turns_(max_turns), max_decisions_(max_decisions),
      initial_mp_(initial_mp), initial_cp_(initial_cp),
      statuses_(batch_size_, player_count, initial_hp),
      inventory_(batch_size_, player_count, inventory_profiles, capacity),
      selected_(batch_size_ * capacity, 0),
      resources_(batch_size_ * player_count, Resources{initial_mp, initial_cp}),
      episodes_(batch_size_) {
  if (utility_profiles.shape(0) == 0 || utility_profiles.shape(0) > 237) {
    throw std::invalid_argument("full-game utility profile count is invalid");
  }
  for (std::size_t row = 0; row < utility_profiles.shape(0); ++row) {
    const auto model = utility_profiles(row, 0);
    const Effect effect{utility_profiles(row, 1), utility_profiles(row, 2),
                        utility_profiles(row, 3)};
    const auto category = inventory_.category(model);
    if ((category != 3 && category != 4) || effect.kind < 1 ||
        effect.kind > 4 ||
        (effect.kind <= 2 && (effect.value < 1 || effect.value > 100)) ||
        (effect.kind > 2 && effect.value != 0) || effect.cost < 0 ||
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
          effect.value < 1 || effect.value > 65535 || effect.element < 0 ||
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
  if (!boosts_.empty() || !chances_.empty())
    attack_order_.resize(batch_size_ * capacity_, 0);
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
    if (state(row, 0) < 0 || state(row, 0) > 100 || state(row, 1) < 0 ||
        state(row, 1) > 100 || state(row, 2) < 0 || state(row, 2) > 100 ||
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
  for (const auto &mutation : staged)
    commit(mutation);
}

bool FullGameBatch::visible_utility_eligible(
    std::size_t owner, const Effect &effect) const noexcept {
  const auto &status = statuses_.states_[owner];
  if (status[0] == 0 || resources_[owner][0] < effect.cost)
    return false;
  if (effect.kind == 1)
    return status[0] < 100;
  if (effect.kind == 2)
    return resources_[owner][0] < 100;
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

void FullGameBatch::grant_gift(Mutation &mutation, std::size_t seat) const {
  if (mutation.episode.next_instance > kMaximumCounter)
    throw std::invalid_argument("full-game native instance IDs are exhausted");
  auto &hand = stage_hand(mutation, seat);
  if (hand.size() >= hand_limit_) {
    if (!oldest_overflow_)
      throw std::invalid_argument(
          "full-game provisional hand limit would overflow");
    hand.erase(hand.begin()); // Approved provisional oldest-held eviction, not
                              // official proof.
    ++mutation.overflow;
    ++mutation.episode.evicted[seat];
  }
  const auto ticket = random_rank(mutation.episode.model_rng, gift_total_);
  const auto profile = std::upper_bound(
      gift_weights_.begin(), gift_weights_.end(), ticket,
      [](auto rank, const auto &row) { return rank < row.second; });
  const auto model =
      profile->first; // Positive bounded cumulative weights guarantee a match.
  DreamInventoryBatch::Item item{mutation.episode.next_instance++, model, 0, 0};
  if ((mutation.statuses[seat][2] & kCurseDreamBit) != 0 &&
      random_rank(mutation.episode.gift_rng, 100) < 50) {
    const auto category =
        static_cast<std::size_t>(inventory_.category(model) - 1);
    const auto &pool = inventory_.fake_pools_[category];
    item[2] = pool[random_rank(mutation.episode.gift_rng, pool.size())];
  }
  hand.push_back(item);
  ++mutation.gifts;
  ++mutation.episode.gifts_given[seat];
}

void FullGameBatch::grant_pending_gifts(Mutation &mutation) const {
  for (std::size_t seat = 0; seat < player_count_; ++seat) {
    const auto count = mutation.episode.gifts_due[seat];
    if (mutation.episode.phase != 1 || mutation.statuses[seat][0] == 0)
      mutation.suppressed_gifts += count;
    else
      for (std::size_t item = 0; item < count; ++item)
        grant_gift(mutation, seat);
    mutation.episode.gifts_due[seat] = 0;
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
  Composition result{};
  const auto owner = mutation.environment * player_count_ +
                     static_cast<std::size_t>(mutation.episode.actor);
  for (std::int64_t index = 0; index < mutation.episode.attack_size; ++index) {
    const auto &item =
        inventory_.items_[owner * capacity_ +
                          static_cast<std::size_t>(mutation.order[index] - 1)];
    const auto model = actual || item[2] == 0 ? item[1] : item[2];
    const auto category = inventory_.category(model);
    const auto attack = attacks_.find(model);
    const auto boost = boosts_.find(model);
    if (index == 0) {
      if (attack != attacks_.end())
        result = {attack->second.value, attack->second.element,
                  attack->second.cost, attack->second.origin,
                  category == 1 && hit_rate(model) == 100};
      else if (boost != boosts_.end() && boost->second.can_lead)
        result = {boost->second.value, boost->second.element,
                  boost->second.cost, category == 4 ? 1 : 0, category == 1};
      else
        throw std::invalid_argument("full-game actual attack leader effect is "
                                    "not implemented or cannot lead");
      continue;
    }
    if (!result.weapon || boost == boosts_.end())
      throw std::invalid_argument("full-game actual attack addition effect is "
                                  "not implemented or incompatible");
    const auto &effect = boost->second;
    if (effect.kind == 2) {
      if (result.value > kMaximumCounter / 2)
        throw std::invalid_argument(
            "full-game attack composition exceeds exact integer bound");
      result.value *= 2;
    } else {
      if (result.value > kMaximumCounter - effect.value)
        throw std::invalid_argument(
            "full-game attack composition exceeds exact integer bound");
      result.value += effect.value;
    }
    result.element = effect.kind == 1
                         ? effect.element
                         : mixed_element(result.element, effect.element);
    result.cost += effect.cost;
  }
  return result;
}

void FullGameBatch::update_preview(Mutation &mutation) const {
  const auto preview = compose(mutation, false);
  mutation.episode.preview_attack = preview.value;
  mutation.episode.preview_element = preview.element;
  mutation.episode.preview_cost = preview.cost;
}

void FullGameBatch::consume_attack(Mutation &mutation, std::size_t seat) const {
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
    ++mutation.attack_components;
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
  const auto rate = hit_rate(item[1]);
  if (automatic != (rate < 100))
    throw std::invalid_argument(
        "full-game hidden actual targeting mode differs from displayed card");
  if (mutation.resources[actor][0] < attack.cost)
    throw std::invalid_argument(
        "full-game hidden actual miracle cost is unaffordable");
  if (attack_order_.empty()) {
    consume_slot(mutation, actor, slot);
    ++mutation.attack_components;
  } else
    consume_attack(mutation, actor);
  mutation.resources[actor][0] -= attack.cost;
  mutation.paid = static_cast<std::uint64_t>(attack.cost);
  mutation.attack_cast = true;
  auto target = choice - static_cast<std::int64_t>(capacity_) - 1;
  if (automatic || (mutation.statuses[actor][2] & kCurseFogBit) != 0) {
    std::array<std::int64_t, 8> eligible{};
    std::size_t count = 0;
    for (std::size_t seat = 0; seat < player_count_; ++seat)
      if (seat != actor && mutation.statuses[seat][0] > 0)
        eligible[count++] = static_cast<std::int64_t>(seat);
    auto &rng = automatic ? mutation.episode.chance_target_rng
                          : mutation.episode.combat_rng;
    target = eligible[random_rank(rng, count)];
  }
  if (automatic) {
    // The target's Dark Cloud determines whether a hit ticket is needed.
    // Target first even on a miss; each independent stream remains staged.
    ++mutation.episode.chance_casts;
    const auto mask = static_cast<std::uint8_t>(mutation.statuses[target][2]);
    const auto percentage = static_cast<std::uint8_t>(rate);
    const bool roll = percentage_hit_requires_ticket(mask, percentage);
    const auto ticket = roll ? static_cast<std::uint8_t>(random_rank(
                                   mutation.episode.chance_rng, 100))
                             : 0;
    if (!percentage_attack_hits(mask, percentage, ticket)) {
      mutation.chance_result = -1;
      ++mutation.episode.chance_misses;
      mutation.attack_resolved = true;
      finish_turn(mutation, actor);
      return;
    }
    mutation.dark_cloud_hit = !roll;
    mutation.episode.dark_cloud_hits += !roll ? 1 : 0;
    mutation.chance_result = 1;
    ++mutation.episode.chance_hits;
  }
  mutation.episode.damage_source = static_cast<std::int64_t>(actor);
  mutation.episode.target = mutation.episode.actor = target;
  mutation.episode.attack = attack.value;
  mutation.episode.element = attack.element;
  mutation.episode.origin = attack.origin;
  mutation.episode.hit_rate = rate;
  const auto effect = attack_effects_.find(item[1]);
  mutation.episode.effect_kind =
      effect == attack_effects_.end() ? 0 : effect->second.kind;
  mutation.episode.effect_value =
      effect == attack_effects_.end() ? 0 : effect->second.value;
  mutation.episode.phase = 4;
}

void FullGameBatch::apply_attack_effect(Mutation &mutation) const noexcept {
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
        mutation.damage, static_cast<std::uint64_t>(100 - source[0]));
    source[0] += static_cast<std::int64_t>(mutation.absorbed_hp);
    ++episode.absorptions;
    episode.absorbed_hp += static_cast<std::int64_t>(mutation.absorbed_hp);
    return;
  }
  auto &target = mutation.statuses[static_cast<std::size_t>(episode.target)];
  if (target[0] <= 0)
    return; // Provisional: do not afflict already dead targets.
  if (kind == 2 || kind == 4) {
    target[2] |= episode.effect_value;
    mutation.inflicted_curse = true;
    ++episode.inflicted_curses;
  } else {
    const auto result =
        inflict_illness({static_cast<std::uint16_t>(target[0]),
                         static_cast<std::uint8_t>(target[1])},
                        static_cast<std::uint8_t>(episode.effect_value));
    mutation.illness_effect_damage =
        static_cast<std::uint64_t>(target[0] - result.hp);
    target[0] = result.hp;
    target[1] = result.stage;
    mutation.inflicted_illness = true;
    ++episode.inflicted_illnesses;
    episode.illness_effect_damage +=
        static_cast<std::int64_t>(mutation.illness_effect_damage);
  }
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

bool FullGameBatch::legal_choice(std::size_t env, std::int64_t choice) const {
  const auto &episode = episodes_[env];
  if (choice < 0 || static_cast<std::uint64_t>(choice) > capacity_ + 9)
    return false;
  if (episode.phase != 1 && episode.phase != 2 && episode.phase != 3 &&
      episode.phase != 4)
    return false;
  const auto owner =
      env * player_count_ + static_cast<std::size_t>(episode.actor);
  if (episode.phase == 3) {
    const auto seat = choice - static_cast<std::int64_t>(capacity_) - 1;
    return seat >= 0 && static_cast<std::uint64_t>(seat) < player_count_ &&
           seat != episode.actor &&
           statuses_.states_[env * player_count_ + seat][0] > 0;
  }
  if (choice == 0)
    return episode.phase == 2 || episode.phase == 4 || !prayer_gifts_ ||
           !visible_weapon(owner);
  if (choice < 1 ||
      static_cast<std::uint64_t>(choice) > inventory_.sizes_[owner])
    return false;
  const auto slot = static_cast<std::size_t>(choice - 1);
  const auto &item = inventory_.items_[owner * capacity_ + slot];
  const auto display = item[2] == 0 ? item[1] : item[2];
  if (episode.phase == 1) {
    const auto utility = effects_.find(display);
    if (utility != effects_.end())
      return visible_utility_eligible(owner, utility->second);
    const auto attack = attacks_.find(display);
    const auto boost = boosts_.find(display);
    return (attack != attacks_.end() &&
            resources_[owner][0] >= attack->second.cost) ||
           (boost != boosts_.end() && boost->second.can_lead &&
            resources_[owner][0] >= boost->second.cost);
  }
  if (episode.phase == 2) {
    if (episode.attack_actions >= kFullGameMaxAttackActions)
      return false;
    if (selected_[env * capacity_ + slot] != 0)
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
    return resources_[owner][0] >= episode.preview_cost + effect.cost &&
           episode.preview_attack <= (effect.kind == 2
                                          ? kMaximumCounter / 2
                                          : kMaximumCounter - effect.value);
  }
  if (episode.defense_actions >= kFullGameMaxDefenseActions)
    return false;
  if (selected_[env * capacity_ + slot] != 0)
    return true; // Flash still allows undo.
  if (flash_prevents_additional_defense(
          static_cast<std::uint8_t>(statuses_.states_[owner][2]),
          static_cast<std::size_t>(episode.selected_count)))
    return false;
  const auto kind = special_kind(display, episode);
  if (kind != 0)
    return episode.selected_count == 0 &&
           resources_[owner][0] >= specials_.at(display).cost;
  for (std::size_t other = 0; other < inventory_.sizes_[owner]; ++other) {
    if (selected_[env * capacity_ + other] == 0)
      continue;
    const auto &held = inventory_.items_[owner * capacity_ + other];
    if (special_kind(held[2] == 0 ? held[1] : held[2], episode) != 0)
      return false;
  }
  const auto defense = armor_.find(display);
  return episode.attack > 0 && defense != armor_.end() &&
         compatible(episode.element, defense->second.element);
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
       episode.phase != 4) ||
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
  if (episode.phase == 1 && choice == 0) {
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
    const auto visible = effects_.find(displayed);
    if (visible == effects_.end()) {
      // Reserve only a public displayed slot. True identity/cost resolves on
      // cast.
      mutation.episode.turn_owner = episode.actor;
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
    const auto actual = effects_.find(item[1]);
    if (actual == effects_.end()) {
      throw std::invalid_argument(
          "full-game actual card effect is not implemented yet");
    }
    const auto &effect = actual->second;
    if (mutation.resources[actor][0] < effect.cost) {
      throw std::invalid_argument(
          "full-game hidden actual miracle cost is unaffordable");
    }
    mutation.resources[actor][0] -= effect.cost;
    mutation.paid = static_cast<std::uint64_t>(effect.cost);
    if (effect.kind == 1)
      mutation.statuses[actor][0] = std::min<std::int64_t>(
          100, mutation.statuses[actor][0] + effect.value);
    else if (effect.kind == 2)
      mutation.resources[actor][0] = std::min<std::int64_t>(
          100, mutation.resources[actor][0] + effect.value);
    else {
      mutation.cured_owner = episode.actor;
      mutation.statuses[actor][1] = cured_illness_stage(
          static_cast<std::uint8_t>(mutation.statuses[actor][1]),
          effect.kind == 4);
      mutation.statuses[actor][2] = cured_documented_mask(
          static_cast<std::uint8_t>(mutation.statuses[actor][2]),
          effect.kind == 4);
    }
    consume_slot(mutation, actor, slot);
    if ((statuses_.states_[owner][2] & kCurseDreamBit) != 0 &&
        (mutation.statuses[actor][2] & kCurseDreamBit) == 0) {
      for (auto &held : mutation.hands.at(actor)) {
        mutation.restored += held[2] != 0 ? 1 : 0;
        held[2] = 0;
      }
    }
    mutation.utility = true;
    finish_turn(mutation, actor);
  } else if (episode.phase == 2) {
    if (choice == 0) {
      mutation.episode.phase = 3;
      mutation.attack_confirm = true;
      const auto &item =
          inventory_.items_[owner * capacity_ +
                            static_cast<std::size_t>(episode.attack_slot)];
      if (hit_rate(item[2] == 0 ? item[1] : item[2]) < 100)
        cast_attack(mutation, choice, true);
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
        mutation.episode.preview_attack = mutation.episode.preview_element =
            mutation.episode.preview_cost = 0;
      } else if (mutation.selected[slot] != 0) {
        const auto end = mutation.order.begin() + episode.attack_size;
        const auto position = std::find(mutation.order.begin(), end, choice);
        std::move(position + 1, end, position);
        mutation.order[--mutation.episode.attack_size] = 0;
        mutation.selected[slot] = 0;
        update_preview(mutation);
      } else {
        mutation.order[mutation.episode.attack_size++] = choice;
        mutation.selected[slot] = 1;
        update_preview(mutation);
      }
    }
  } else if (episode.phase == 3) {
    cast_attack(mutation, choice, false);
  } else if (choice > 0) {
    const auto slot = static_cast<std::size_t>(choice - 1);
    mutation.selected[slot] ^= 1;
    mutation.episode.selected_count += mutation.selected[slot] != 0 ? 1 : -1;
    ++mutation.episode.defense_actions;
    mutation.defense_toggle = true;
  } else {
    std::int64_t defense = 0;
    std::vector<DreamInventoryBatch::Item> hand;
    std::vector<DreamInventoryBatch::Item> reused;
    hand.reserve(inventory_.sizes_[owner]);
    for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot) {
      const auto &item = inventory_.items_[owner * capacity_ + slot];
      if (mutation.selected[slot] == 0) {
        hand.push_back(item);
        continue;
      }
      const auto kind = special_kind(item[1], episode);
      if (kind != 0) {
        if (episode.selected_count != 1)
          throw std::invalid_argument(
              "full-game hidden special defense must be exclusive");
        const auto cost = specials_.at(item[1]).cost;
        if (mutation.resources[actor][0] < cost)
          throw std::invalid_argument(
              "full-game hidden actual miracle cost is unaffordable");
        mutation.resources[actor][0] -= cost;
        mutation.paid += static_cast<std::uint64_t>(cost);
        mutation.special_kind = kind;
      } else {
        const auto actual = armor_.find(item[1]);
        if (actual == armor_.end())
          throw std::invalid_argument(
              "full-game actual defense effect is not implemented yet");
        if (episode.attack == 0 ||
            !compatible(episode.element, actual->second.element))
          throw std::invalid_argument(
              "full-game hidden actual defense element is incompatible");
        defense += actual->second.value;
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
      mutation.episode.selected_count = mutation.episode.defense_actions = 0;
      mutation.selected.fill(0);
      advance_decision(mutation, choice);
      return mutation; // Fresh response; no owner tick or gifts between hops.
    }
    const auto damage =
        mutation.special_kind == 1
            ? 0
            : std::max<std::int64_t>(0, episode.attack - defense);
    mutation.damage = static_cast<std::uint64_t>(
        std::min(damage, mutation.statuses[actor][0]));
    mutation.statuses[actor][0] -= static_cast<std::int64_t>(mutation.damage);
    if (episode.element == 6 && mutation.damage > 0) {
      mutation.damage +=
          static_cast<std::uint64_t>(mutation.statuses[actor][0]);
      mutation.statuses[actor][0] = 0;
      mutation.darkness_finish = true;
    }
    apply_attack_effect(mutation);
    mutation.attack_resolved = true;
    finish_turn(mutation, static_cast<std::size_t>(episode.turn_owner));
  }
  advance_decision(mutation, choice);
  return mutation;
}

void FullGameBatch::decide_outcome(Mutation &mutation) const noexcept {
  std::size_t count = 0;
  std::int64_t winner = -1;
  for (std::size_t seat = 0; seat < player_count_; ++seat)
    if (mutation.statuses[seat][0] > 0) {
      ++count;
      winner = static_cast<std::int64_t>(seat);
    }
  if (count < 2) {
    mutation.episode.phase = 12;
    mutation.episode.outcome = count == 1 ? 1 : 2;
    mutation.episode.winner = winner;
  }
}

void FullGameBatch::finish_turn(Mutation &mutation, std::size_t owner) const {
  auto &status = mutation.statuses[owner];
  IllnessState state{static_cast<std::uint16_t>(status[0]),
                     static_cast<std::uint8_t>(status[1])};
  if (state.hp > 0)
    state =
        periodic_illness_effect(state); // Never resurrect a dead Heaven owner.
  if (state.hp > 0 && state.stage != 0 &&
      random_rank(mutation.episode.illness_rng, 100) < 5) {
    state = worsen_illness(state);
  }
  status[0] = state.hp;
  status[1] = state.stage;
  ++status[3];
  mutation.ticked_owner = static_cast<std::int64_t>(owner);
  auto &episode = mutation.episode;
  ++episode.turns;
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
  episode.defense_actions = 0;
  episode.selected_count = 0;
  episode.attack_size = episode.attack_actions = 0;
  episode.preview_attack = episode.preview_element = episode.preview_cost = 0;
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
  if (episode.phase != 12 &&
      (static_cast<std::uint64_t>(episode.turns) >= max_turns_ ||
       static_cast<std::uint64_t>(episode.commands) >= max_decisions_)) {
    episode.phase = 13;
    episode.outcome =
        static_cast<std::uint64_t>(episode.turns) >= max_turns_ ? 3 : 4;
  }
  if (mutation.ticked_owner >= 0 || episode.phase == 12 || episode.phase == 13)
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
    staged.push_back(std::move(mutation));
  }
  // Commit contains no validation, random draws, or allocation.
  for (const auto &mutation : staged)
    commit(mutation);
}

void FullGameBatch::commit(const Mutation &mutation) noexcept {
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
  statuses_.curse_count_ += mutation.inflicted_curse ? 1 : 0;
  statuses_.illness_count_ += mutation.inflicted_illness ? 1 : 0;
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
  episodes_[mutation.environment] = mutation.episode;
  actions_ += mutation.accepted_command ? 1 : 0;
  passes_ += mutation.pass ? 1 : 0;
  utilities_ += mutation.utility ? 1 : 0;
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
  darkness_finishes_ += mutation.darkness_finish ? 1 : 0;
  blocks_ += mutation.special_kind == 1 ? 1 : 0;
  reflections_ += mutation.special_kind == 2 ? 1 : 0;
  bounces_ += mutation.special_kind == 3 ? 1 : 0;
  chances_cast_ += mutation.chance_result != 0 ? 1 : 0;
  chance_hits_ += mutation.chance_result == 1 ? 1 : 0;
  chance_misses_ += mutation.chance_result == -1 ? 1 : 0;
  absorbed_hp_ += mutation.absorbed_hp;
  absorptions_ += mutation.absorption ? 1 : 0;
  inflicted_curses_ += mutation.inflicted_curse ? 1 : 0;
  inflicted_illnesses_ += mutation.inflicted_illness ? 1 : 0;
  illness_effect_damage_ += mutation.illness_effect_damage;
  dark_cloud_hits_ += mutation.dark_cloud_hit ? 1 : 0;
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
    if (episode.phase != 2 && episode.phase != 3 && episode.phase != 4)
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
        origin = inventory_.category(model) == 4 ? 1 : 0;
      }
    } else {
      const auto owner =
          env * player_count_ + static_cast<std::size_t>(episode.actor);
      for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot) {
        if (selected_[env * capacity_ + slot] == 0)
          continue;
        const auto &item = inventory_.items_[owner * capacity_ + slot];
        const auto model = item[2] == 0 ? item[1] : item[2];
        if (special_kind(model, episode) == 0)
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
    const auto &episode = episodes_[env];
    if (episode.phase != 4)
      continue;
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
        cost = specials_.at(model).cost;
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
    if (episode.phase != 2 && episode.phase != 3 && episode.phase != 4)
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
    if (episode.phase != 2 && episode.phase != 3 && episode.phase != 4)
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

void bind_full_game(nb::module_ &module) {
  module.attr("FULL_GAME_KERNEL_SCHEMA_VERSION") = kFullGameKernelSchemaVersion;
  module.attr("FULL_GAME_COMMAND_SCHEMA_VERSION") =
      kFullGameCommandSchemaVersion;
  module.attr("FULL_GAME_OBSERVATION_SCHEMA_VERSION") =
      kFullGameKernelSchemaVersion;
  module.attr("FULL_GAME_RULESET_ID") = kFullGameRulesetId;
  module.attr("FULL_GAME_MAX_DEFENSE_ACTIONS") = kFullGameMaxDefenseActions;
  module.attr("FULL_GAME_MAX_ATTACK_ACTIONS") = kFullGameMaxAttackActions;
  nb::class_<FullGameBatch>(module, "FullGameBatch")
      .def(nb::init<std::size_t, std::size_t, InventoryProfileInput,
                    InventoryInput, std::size_t, std::uint64_t, std::uint64_t,
                    std::uint64_t, std::uint16_t, std::uint16_t, std::uint16_t,
                    std::optional<GuardianWeightInput>,
                    std::optional<GuardianWeightInput>,
                    std::optional<InventoryProfileInput>, std::size_t, bool,
                    bool, std::size_t, bool, std::optional<FullGameBoostInput>,
                    std::optional<GuardianWeightInput>,
                    std::optional<InventoryProfileInput>,
                    std::optional<FullGameAttackEffectInput>>(),
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
           nb::arg("attack_effect_profiles").noconvert() = nb::none())
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
      .def("pending_observations", &FullGameBatch::pending_observations)
      .def("special_defense_observations",
           &FullGameBatch::special_defense_observations)
      .def("chance_observations", &FullGameBatch::chance_observations)
      .def("chance_snapshot", &FullGameBatch::chance_snapshot)
      .def("attack_effect_observations",
           &FullGameBatch::attack_effect_observations)
      .def("attack_effect_snapshot", &FullGameBatch::attack_effect_snapshot)
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
      .def_prop_ro("mp_spent", &FullGameBatch::mp_spent)
      .def_prop_ro("gift_count", &FullGameBatch::gift_count)
      .def_prop_ro("consumed_count", &FullGameBatch::consumed_count)
      .def_prop_ro("miracle_use_count", &FullGameBatch::miracle_use_count)
      .def_prop_ro("restored_count", &FullGameBatch::restored_count);
}

} // namespace godfield_sim
