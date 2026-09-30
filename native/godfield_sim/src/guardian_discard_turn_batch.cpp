#include "guardian_discard_turn_batch.h"

#include <memory>
#include <stdexcept>

namespace godfield_sim {

GuardianDiscardTurnBatch::GuardianDiscardTurnBatch(
    std::size_t batch_size, std::size_t player_count,
    std::size_t guardian_slots, GuardianWeightInput weighted_profiles,
    GuardianWeightInput effect_profiles, GuardianWeightInput defense_profiles,
    GuardianWeightInput attack_profiles, GuardianWeightInput utility_profiles,
    ActionInput discard_models, std::size_t hand_slots,
    std::uint64_t max_turns, std::uint16_t initial_hp,
    std::uint16_t initial_mp, std::uint16_t initial_cp)
    : GuardianUtilityTurnBatch(
          batch_size, player_count, guardian_slots, weighted_profiles,
          effect_profiles, defense_profiles, attack_profiles, utility_profiles,
          hand_slots, max_turns, initial_hp, initial_mp, initial_cp) {
  if (discard_models.shape(0) == 0 || discard_models.shape(0) > 512)
    throw std::invalid_argument("invalid discard allowlist size");
  for (std::size_t row = 0; row < discard_models.shape(0); ++row) {
    const auto model = discard_models(row);
    const auto attack = turns_.attacks_.find(model);
    // Source-pinned exceptions: Sun Amulet and Dangerous Mortar. Weapons
    // remain prohibited independently of the caller's discard allowlist.
    if (model == 208 || model == 209 ||
        (attack != turns_.attacks_.end() && attack->second.origin == 0) ||
        (!turns_.defenses_.contains(model) &&
         attack == turns_.attacks_.end() && !utilities_.contains(model)) ||
        !discard_models_.insert(model).second)
      throw std::invalid_argument("unsupported, prohibited, or duplicate discard model");
  }
}

bool GuardianDiscardTurnBatch::legal_discard(std::size_t environment,
                                             std::size_t slot) const {
  if (turns_.finished(environment) ||
      turns_.combat_.pending_[environment][0] != 0)
    return false;
  const auto owner = turns_.turns_[environment].owner;
  const auto &card = turns_.cards_[turns_.card_offset(environment, owner, slot)];
  return card.instance != 0 && discard_models_.contains(card.model) &&
         turns_.combat_.hp_[environment * turns_.player_count_ +
                            static_cast<std::size_t>(owner)] > 0;
}

void GuardianDiscardTurnBatch::discard_cards(ActionInput environments,
                                             ActionInput players,
                                             ActionInput slots) {
  const auto count = environments.shape(0);
  GuardianCombatBatch::same_length(count, players);
  GuardianCombatBatch::same_length(count, slots);
  turns_.validate_unique(environments);
  turns_.require_ready(environments);
  for (std::size_t row = 0; row < count; ++row) {
    const auto env = turns_.combat_.checked_environment(environments(row));
    if (players(row) != turns_.turns_[env].owner || slots(row) < 0 ||
        static_cast<std::uint64_t>(slots(row)) >= turns_.hand_slots_ ||
        !legal_discard(env, static_cast<std::size_t>(slots(row))))
      throw std::invalid_argument("discard owner, slot, or phase unavailable");
  }
  // No removal, counters, resource writes, or turn changes before every row
  // validates. Discarded cards are not reported as used combat/utility cards.
  for (std::size_t row = 0; row < count; ++row) {
    const auto env = turns_.combat_.checked_environment(environments(row));
    auto &card = turns_.cards_[turns_.card_offset(
        env, players(row), static_cast<std::size_t>(slots(row)))];
    const auto model = card.model;
    card = GuardianTurnBatch::Card{};
    ++discarded_card_count_;
    turns_.combat_.pending_[env] = {0, model, players(row), players(row),
                                    0, 0, 0, 0, 0, 0};
    turns_.turns_[env].origin = 4;
    turns_.turns_[env].bounced = false;
    turns_.finish_turn(env);
  }
}

Bool2D GuardianDiscardTurnBatch::discard_action_masks() const {
  auto buffer = std::make_unique<bool[]>(turns_.batch_size_ * turns_.hand_slots_);
  for (std::size_t env = 0; env < turns_.batch_size_; ++env)
    for (std::size_t slot = 0; slot < turns_.hand_slots_; ++slot)
      buffer[env * turns_.hand_slots_ + slot] = legal_discard(env, slot);
  nb::capsule owner(buffer.get(),
                    [](void *p) noexcept { delete[] static_cast<bool *>(p); });
  const auto *data = buffer.release();
  return Bool2D(data, {turns_.batch_size_, turns_.hand_slots_}, owner);
}

} // namespace godfield_sim
