#include "guardian_utility_turn_batch.h"

#include <algorithm>
#include <memory>
#include <stdexcept>

namespace godfield_sim {
namespace {
constexpr std::int64_t kMaxExactId = (std::int64_t{1} << 53) - 1;
}

GuardianUtilityTurnBatch::GuardianUtilityTurnBatch(
    std::size_t batch_size, std::size_t player_count,
    std::size_t guardian_slots, GuardianWeightInput weighted_profiles,
    GuardianWeightInput effect_profiles, GuardianWeightInput defense_profiles,
    GuardianWeightInput attack_profiles, GuardianWeightInput utility_profiles,
    std::size_t hand_slots, std::uint64_t max_turns, std::uint16_t initial_hp,
    std::uint16_t initial_mp, std::uint16_t initial_cp)
    : turns_(batch_size, player_count, guardian_slots, weighted_profiles,
             effect_profiles, defense_profiles, hand_slots, max_turns,
             initial_hp, initial_mp, initial_cp, attack_profiles) {
  if (utility_profiles.shape(1) != 5 || utility_profiles.shape(0) == 0 ||
      utility_profiles.shape(0) > 512)
    throw std::invalid_argument("invalid utility profile dimensions");
  for (std::size_t row = 0; row < utility_profiles.shape(0); ++row) {
    const auto model = utility_profiles(row, 0),
               resource = utility_profiles(row, 1),
               value = utility_profiles(row, 2),
               reusable = utility_profiles(row, 3),
               cost = utility_profiles(row, 4);
    if (model <= 0 || model > kMaxExactId || utilities_.contains(model) ||
        turns_.defenses_.contains(model) || turns_.attacks_.contains(model) ||
        resource < 0 || resource > 1 || value <= 0 || value > 100 ||
        reusable < 0 || reusable > 1 || cost < 0 || cost > 100 ||
        (reusable == 0 ? cost != 0 : (cost == 0 || resource != 0)))
      throw std::invalid_argument("invalid or duplicate utility profile");
    utilities_.emplace(model, Utility{resource, value, reusable, cost});
    utility_models_.insert(model);
  }
}

void GuardianUtilityTurnBatch::deal_cards(ActionInput environments,
                                          ActionInput players,
                                          ActionInput slots,
                                          ActionInput instances,
                                          ActionInput models) {
  turns_.deal_cards_impl(environments, players, slots, instances, models, false,
                         utility_models_);
}

bool GuardianUtilityTurnBatch::legal_utility(std::size_t environment,
                                             std::size_t slot) const {
  if (turns_.finished(environment) ||
      turns_.combat_.pending_[environment][0] != 0)
    return false;
  const auto player = turns_.turns_[environment].owner;
  const auto &card =
      turns_.cards_[turns_.card_offset(environment, player, slot)];
  const auto found = utilities_.find(card.model);
  if (card.instance == 0 || found == utilities_.end())
    return false;
  const auto offset =
      environment * turns_.player_count_ + static_cast<std::size_t>(player);
  const auto &utility = found->second;
  const auto resource = utility.resource == 0 ? turns_.combat_.hp_[offset]
                                              : turns_.combat_.mp_[offset];
  return turns_.combat_.hp_[offset] > 0 && resource < 100 &&
         utility.cost <= turns_.combat_.mp_[offset];
}

void GuardianUtilityTurnBatch::use_utility_cards(ActionInput environments,
                                                 ActionInput players,
                                                 ActionInput slots) {
  const auto count = environments.shape(0);
  GuardianCombatBatch::same_length(count, players);
  GuardianCombatBatch::same_length(count, slots);
  turns_.validate_unique(environments);
  turns_.require_ready(environments);
  // Validate the whole batch first: rejected rows must not spend MP, consume a
  // card, heal another row, increment counters, or advance any turn.
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment =
        turns_.combat_.checked_environment(environments(row));
    if (players(row) != turns_.turns_[environment].owner || slots(row) < 0 ||
        static_cast<std::uint64_t>(slots(row)) >= turns_.hand_slots_ ||
        !legal_utility(environment, static_cast<std::size_t>(slots(row))))
      throw std::invalid_argument(
          "utility card owner, slot, or resources unavailable");
  }
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment =
        turns_.combat_.checked_environment(environments(row));
    auto &card = turns_.cards_[turns_.card_offset(
        environment, players(row), static_cast<std::size_t>(slots(row)))];
    const auto model = card.model;
    const auto utility = utilities_.at(model);
    const auto offset = environment * turns_.player_count_ +
                        static_cast<std::size_t>(players(row));
    auto &mp = turns_.combat_.mp_[offset];
    auto &resource = utility.resource == 0 ? turns_.combat_.hp_[offset] : mp;
    const auto gained = std::min<std::int64_t>(utility.value, 100 - resource);
    mp -= utility.cost;
    resource += gained;
    if (utility.reusable == 0) {
      card = GuardianTurnBatch::Card{};
      ++turns_.consumed_card_count_;
    } else {
      ++turns_.miracle_cast_count_;
      turns_.mp_spent_ += static_cast<std::uint64_t>(utility.cost);
    }
    ++utility_use_count_;
    (utility.resource == 0 ? hp_gained_ : mp_gained_) +=
        static_cast<std::uint64_t>(gained);
    turns_.combat_.pending_[environment] = {0,
                                            model,
                                            players(row),
                                            players(row),
                                            0,
                                            0,
                                            0,
                                            utility.resource == 0 ? 5 : 6,
                                            utility.value,
                                            0};
    turns_.turns_[environment].origin =
        3; // Immediate self utility; not an attack.
    turns_.turns_[environment].bounced = false;
    turns_.finish_turn(environment);
  }
}

Bool2D GuardianUtilityTurnBatch::utility_action_masks() const {
  const auto size = turns_.batch_size_ * turns_.hand_slots_;
  auto buffer = std::make_unique<bool[]>(size);
  for (std::size_t env = 0; env < turns_.batch_size_; ++env)
    for (std::size_t slot = 0; slot < turns_.hand_slots_; ++slot)
      buffer[env * turns_.hand_slots_ + slot] = legal_utility(env, slot);
  nb::capsule owner(buffer.get(),
                    [](void *p) noexcept { delete[] static_cast<bool *>(p); });
  const auto *data = buffer.release();
  return Bool2D(data, {turns_.batch_size_, turns_.hand_slots_}, owner);
}

Bool2D GuardianUtilityTurnBatch::ready_action_masks() const {
  const auto width = turns_.hand_slots_ + 1;
  auto buffer = std::make_unique<bool[]>(turns_.batch_size_ * width);
  const auto attacks = turns_.attack_action_masks();
  for (std::size_t env = 0; env < turns_.batch_size_; ++env) {
    for (std::size_t slot = 0; slot < turns_.hand_slots_; ++slot)
      buffer[env * width + slot] =
          attacks(env, slot) || legal_utility(env, slot);
    buffer[env * width + turns_.hand_slots_] = attacks(env, turns_.hand_slots_);
  }
  nb::capsule owner(buffer.get(),
                    [](void *p) noexcept { delete[] static_cast<bool *>(p); });
  const auto *data = buffer.release();
  return Bool2D(data, {turns_.batch_size_, width}, owner);
}

std::array<std::int64_t, 8> GuardianUtilityTurnBatch::hand_features(
    const GuardianTurnBatch::Card &card) const {
  const auto found = utilities_.find(card.model);
  if (card.instance != 0 && found != utilities_.end()) {
    const auto &utility = found->second;
    return {utility.resource == 0 ? 6 : 7,
            0,
            0,
            0,
            utility.cost,
            utility.reusable,
            utility.resource == 0 ? utility.value : 0,
            utility.resource == 1 ? utility.value : 0};
  }
  std::array<std::int64_t, 8> result{};
  const auto base = turns_.hand_features(card);
  std::copy(base.begin(), base.end(), result.begin());
  return result;
}

GuardianStateSnapshot GuardianUtilityTurnBatch::actor_hand_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(turns_.batch_size_ *
                                                 turns_.hand_slots_ * 11);
  std::fill_n(buffer.get(), turns_.batch_size_ * turns_.hand_slots_ * 11, 0);
  for (std::size_t env = 0; env < turns_.batch_size_; ++env) {
    if (turns_.finished(env))
      continue;
    const auto &pending = turns_.combat_.pending_[env];
    const auto player = pending[0] == 1 ? pending[3] : turns_.turns_[env].owner;
    for (std::size_t slot = 0; slot < turns_.hand_slots_; ++slot) {
      const auto &card = turns_.cards_[turns_.card_offset(env, player, slot)];
      const auto offset = (env * turns_.hand_slots_ + slot) * 11;
      buffer[offset] = card.instance;
      buffer[offset + 1] = card.model;
      buffer[offset + 2] =
          pending[0] == 1 ? turns_.selected_[env * turns_.hand_slots_ + slot]
                          : 0;
      const auto features = hand_features(card);
      std::copy(features.begin(), features.end(), buffer.get() + offset + 3);
    }
  }
  nb::capsule owner(buffer.get(), [](void *p) noexcept {
    delete[] static_cast<std::int64_t *>(p);
  });
  const auto *data = buffer.release();
  return GuardianStateSnapshot(
      data, {turns_.batch_size_, turns_.hand_slots_, 11}, owner);
}

GuardianInventorySnapshot
GuardianUtilityTurnBatch::hand_feature_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(turns_.cards_.size() * 8);
  for (std::size_t offset = 0; offset < turns_.cards_.size(); ++offset) {
    const auto features = hand_features(turns_.cards_[offset]);
    std::copy(features.begin(), features.end(), buffer.get() + offset * 8);
  }
  nb::capsule owner(buffer.get(), [](void *p) noexcept {
    delete[] static_cast<std::int64_t *>(p);
  });
  const auto *data = buffer.release();
  return GuardianInventorySnapshot(
      data, {turns_.batch_size_, turns_.player_count_, turns_.hand_slots_, 8},
      owner);
}

} // namespace godfield_sim
