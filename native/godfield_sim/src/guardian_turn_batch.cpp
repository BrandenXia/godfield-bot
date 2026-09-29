#include "guardian_turn_batch.h"

#include <algorithm>
#include <memory>
#include <set>
#include <stdexcept>

namespace godfield_sim {
namespace {
constexpr std::int64_t kMaxExactId = (std::int64_t{1} << 53) - 1;
ActionInput input(const std::vector<std::int64_t> &values) {
  return ActionInput(values.data(), {values.size()});
}
} // namespace

GuardianTurnBatch::GuardianTurnBatch(
    std::size_t batch_size, std::size_t player_count,
    std::size_t guardian_slots, GuardianWeightInput weighted_profiles,
    GuardianWeightInput effect_profiles, GuardianWeightInput defense_profiles,
    std::size_t hand_slots, std::uint64_t max_turns, std::uint16_t initial_hp,
    std::uint16_t initial_mp, std::uint16_t initial_cp)
    : batch_size_(batch_size), player_count_(player_count),
      hand_slots_(hand_slots), max_turns_(max_turns),
      combat_(batch_size, player_count, guardian_slots, weighted_profiles,
              effect_profiles, initial_hp, initial_mp, initial_cp) {
  if (hand_slots == 0 || hand_slots > 18 || max_turns == 0 ||
      max_turns > 1000000000 ||
      batch_size > 2000000 / (player_count * hand_slots) ||
      defense_profiles.shape(1) != 3 || defense_profiles.shape(0) == 0 ||
      defense_profiles.shape(0) > 512) {
    throw std::invalid_argument("invalid guardian turn configuration");
  }
  for (std::size_t row = 0; row < defense_profiles.shape(0); ++row) {
    const auto model = defense_profiles(row, 0);
    const auto value = defense_profiles(row, 1);
    const auto element = defense_profiles(row, 2);
    if (model <= 0 || model > kMaxExactId || defenses_.contains(model) ||
        value <= 0 || value > 65535 || element < 0 || element > 6) {
      throw std::invalid_argument(
          "invalid or duplicate guardian defense profile");
    }
    defenses_.emplace(model, Defense{value, element});
  }
  cards_.resize(batch_size * player_count * hand_slots);
  selected_.assign(batch_size * hand_slots, 0);
  turns_.resize(batch_size);
}

void GuardianTurnBatch::validate_unique(ActionInput environments) const {
  std::set<std::size_t> seen;
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    if (!seen.insert(combat_.checked_environment(environments(row))).second)
      throw std::invalid_argument("duplicate guardian turn environment");
  }
}
void GuardianTurnBatch::require_ready(ActionInput environments) const {
  combat_.require_idle(environments);
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    const auto &turn = turns_[combat_.checked_environment(environments(row))];
    if (turn.winner >= 0 || turn.truncated)
      throw std::invalid_argument("guardian turn environment is finished");
  }
}
std::size_t GuardianTurnBatch::card_offset(std::size_t environment,
                                           std::int64_t player,
                                           std::size_t slot) const {
  return (environment * player_count_ + static_cast<std::size_t>(player)) *
             hand_slots_ +
         slot;
}
void GuardianTurnBatch::summon(ActionInput environments, ActionInput slots,
                               ActionInput instances, ActionInput owners,
                               ActionInput groups) {
  require_ready(environments);
  GuardianCombatBatch::same_length(environments.shape(0), owners);
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    const auto environment = combat_.checked_environment(environments(row));
    if (owners(row) < 0 ||
        static_cast<std::uint64_t>(owners(row)) >= player_count_ ||
        combat_.hp_[environment * player_count_ + owners(row)] == 0)
      throw std::invalid_argument("invalid or eliminated guardian owner");
  }
  combat_.summon(environments, slots, instances, owners, groups);
}
void GuardianTurnBatch::remove(ActionInput environments, ActionInput slots,
                               ActionInput instances) {
  require_ready(environments);
  combat_.remove(environments, slots, instances);
}

void GuardianTurnBatch::deal_defenses(ActionInput environments,
                                      ActionInput players, ActionInput slots,
                                      ActionInput instances,
                                      ActionInput models) {
  const auto count = environments.shape(0);
  for (const auto &values : {players, slots, instances, models})
    GuardianCombatBatch::same_length(count, values);
  require_ready(environments);
  std::set<std::size_t> seen_slots;
  std::set<std::pair<std::size_t, std::int64_t>> seen_instances;
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = combat_.checked_environment(environments(row));
    if (players(row) < 0 ||
        static_cast<std::uint64_t>(players(row)) >= player_count_ ||
        slots(row) < 0 ||
        static_cast<std::uint64_t>(slots(row)) >= hand_slots_ ||
        instances(row) <= 0 || instances(row) > kMaxExactId ||
        !defenses_.contains(models(row)) ||
        combat_.hp_[environment * player_count_ + players(row)] == 0)
      throw std::invalid_argument("invalid guardian defense card");
    const auto offset = card_offset(environment, players(row),
                                    static_cast<std::size_t>(slots(row)));
    if (!seen_slots.insert(offset).second || cards_[offset].instance != 0 ||
        !seen_instances.emplace(environment, instances(row)).second)
      throw std::invalid_argument(
          "duplicate or occupied guardian defense slot/instance");
    for (std::size_t index = environment * player_count_ * hand_slots_;
         index < (environment + 1) * player_count_ * hand_slots_; ++index) {
      if (cards_[index].instance == instances(row))
        throw std::invalid_argument("guardian defense instance already exists");
    }
  }
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = combat_.checked_environment(environments(row));
    cards_[card_offset(environment, players(row),
                       static_cast<std::size_t>(slots(row)))] =
        Card{instances(row), models(row)};
  }
}

void GuardianTurnBatch::begin_effects(ActionInput environments,
                                      ActionInput slots, ActionInput instances,
                                      ActionInput targets,
                                      ActionInput selection_tickets,
                                      ActionInput hit_tickets) {
  const auto count = environments.shape(0);
  GuardianCombatBatch::same_length(count, slots);
  GuardianCombatBatch::same_length(count, instances);
  require_ready(environments);
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = combat_.checked_environment(environments(row));
    if (combat_.guardians_.owner_for(environments(row), slots(row),
                                     instances(row)) !=
        turns_[environment].owner)
      throw std::invalid_argument(
          "guardian does not belong to the current turn owner");
  }
  // The combat kernel validates the entire call before mutating anything.
  combat_.begin_attacks(environments, slots, instances, targets,
                        selection_tickets, hit_tickets);
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = combat_.checked_environment(environments(row));
    if (combat_.pending_[environment][0] == 0)
      finish_turn(environment);
  }
}

void GuardianTurnBatch::finish_turn(std::size_t environment) {
  auto &turn = turns_[environment];
  turn.defense_actions = 0;
  ++turn.completed;
  std::int64_t survivor = -1;
  std::size_t living = 0;
  for (std::size_t player = 0; player < player_count_; ++player) {
    if (combat_.hp_[environment * player_count_ + player] > 0) {
      ++living;
      survivor = static_cast<std::int64_t>(player);
    }
  }
  if (living == 1) {
    turn.winner = survivor;
    return;
  }
  if (turn.completed >= max_turns_) {
    turn.truncated = true;
    return;
  }
  for (std::size_t offset = 1; offset <= player_count_; ++offset) {
    const auto candidate =
        (static_cast<std::size_t>(turn.owner) + offset) % player_count_;
    if (combat_.hp_[environment * player_count_ + candidate] > 0) {
      turn.owner = static_cast<std::int64_t>(candidate);
      return;
    }
  }
}
void GuardianTurnBatch::pass_turns(ActionInput environments,
                                   ActionInput players) {
  GuardianCombatBatch::same_length(environments.shape(0), players);
  validate_unique(environments);
  require_ready(environments);
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    if (players(row) !=
        turns_[combat_.checked_environment(environments(row))].owner)
      throw std::invalid_argument("pass requires the current turn owner");
  }
  for (std::size_t row = 0; row < environments.shape(0); ++row)
    finish_turn(combat_.checked_environment(environments(row)));
}

bool GuardianTurnBatch::legal_card(std::size_t environment,
                                   std::size_t slot) const {
  const auto &pending = combat_.pending_[environment];
  if (pending[0] != 1)
    return false;
  const auto &card = cards_[card_offset(environment, pending[3], slot)];
  return card.instance != 0 &&
         GuardianCombatBatch::compatible(pending[5],
                                         defenses_.at(card.model).element);
}
std::int64_t
GuardianTurnBatch::selected_defense(std::size_t environment) const {
  std::int64_t value = 0;
  for (std::size_t slot = 0; slot < hand_slots_; ++slot) {
    if (selected_[environment * hand_slots_ + slot])
      value +=
          defenses_
              .at(cards_[card_offset(environment,
                                     combat_.pending_[environment][3], slot)]
                      .model)
              .value;
  }
  return std::min<std::int64_t>(65535, value);
}
void GuardianTurnBatch::step_defenses(ActionInput environments,
                                      ActionInput players,
                                      ActionInput actions) {
  const auto count = environments.shape(0);
  GuardianCombatBatch::same_length(count, players);
  GuardianCombatBatch::same_length(count, actions);
  validate_unique(environments);
  std::vector<std::int64_t> resolving, values, elements;
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = combat_.checked_environment(environments(row));
    const auto &pending = combat_.pending_[environment];
    const auto action = actions(row);
    if (turns_[environment].truncated || turns_[environment].winner >= 0 ||
        pending[0] != 1 || players(row) != pending[3] || action < 0 ||
        static_cast<std::uint64_t>(action) >= action_count())
      throw std::invalid_argument(
          "invalid guardian defense actor, phase, or action");
    if (static_cast<std::uint64_t>(action) < hand_slots_) {
      if (!legal_card(environment, static_cast<std::size_t>(action)))
        throw std::invalid_argument("guardian defense card is not legal");
    } else {
      std::int64_t value = 0, element = 0;
      if (static_cast<std::uint64_t>(action) == hand_slots_ + 1) {
        value = selected_defense(environment);
        if (value == 0)
          throw std::invalid_argument(
              "guardian defense confirm requires selected armor");
        for (std::size_t slot = 0; slot < hand_slots_; ++slot) {
          if (selected_[environment * hand_slots_ + slot]) {
            element = defenses_
                          .at(cards_[card_offset(environment, pending[3], slot)]
                                  .model)
                          .element;
            break;
          }
        }
      }
      resolving.push_back(environments(row));
      values.push_back(value);
      elements.push_back(element);
    }
  }
  // Resolve all confirmation/forgiveness rows first: validation failures cannot
  // partially toggle cards or consume inventory in other environments.
  if (!resolving.empty())
    combat_.resolve_defenses(input(resolving), input(values), input(elements));
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = combat_.checked_environment(environments(row));
    const auto action = static_cast<std::size_t>(actions(row));
    if (action < hand_slots_) {
      selected_[environment * hand_slots_ + action] ^= 1;
      if (++turns_[environment].defense_actions >=
          kGuardianTurnMaxDefenseActions)
        turns_[environment].truncated = true;
      continue;
    }
    for (std::size_t slot = 0; slot < hand_slots_; ++slot) {
      auto &selection = selected_[environment * hand_slots_ + slot];
      if (action == hand_slots_ + 1 && selection) {
        cards_[card_offset(environment, players(row), slot)] = Card{};
        ++consumed_card_count_;
      }
      selection = 0;
    }
    finish_turn(environment);
  }
}

void GuardianTurnBatch::reset_environments(ActionInput environments) {
  combat_.reset_environments(environments);
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    const auto environment = combat_.checked_environment(environments(row));
    std::fill_n(cards_.begin() + environment * player_count_ * hand_slots_,
                player_count_ * hand_slots_, Card{});
    std::fill_n(selected_.begin() + environment * hand_slots_, hand_slots_, 0);
    turns_[environment] = Turn{};
  }
}
Bool2D GuardianTurnBatch::defense_action_masks() const {
  auto buffer = std::make_unique<bool[]>(batch_size_ * action_count());
  std::fill_n(buffer.get(), batch_size_ * action_count(), false);
  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    if (turns_[environment].truncated || turns_[environment].winner >= 0 ||
        combat_.pending_[environment][0] != 1)
      continue;
    for (std::size_t slot = 0; slot < hand_slots_; ++slot)
      buffer[environment * action_count() + slot] =
          legal_card(environment, slot);
    buffer[environment * action_count() + hand_slots_] = true;
    buffer[environment * action_count() + hand_slots_ + 1] =
        selected_defense(environment) > 0;
  }
  nb::capsule owner(buffer.get(),
                    [](void *p) noexcept { delete[] static_cast<bool *>(p); });
  const auto *data = buffer.release();
  return Bool2D(data, {batch_size_, action_count()}, owner);
}
Int64_2D GuardianTurnBatch::turn_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 8);
  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    const auto &turn = turns_[environment];
    const auto defense = combat_.pending_[environment][0] == 1;
    const auto done = turn.winner >= 0 || turn.truncated;
    const std::array<std::int64_t, 8> state = {
        turn.winner >= 0 ? 2
        : turn.truncated ? 3
        : defense        ? 1
                         : 0,
        turn.owner,
        done      ? -1
        : defense ? combat_.pending_[environment][3]
                  : turn.owner,
        static_cast<std::int64_t>(turn.completed),
        turn.winner,
        turn.truncated ? 1 : 0,
        defense ? selected_defense(environment) : 0,
        turn.defense_actions};
    std::copy(state.begin(), state.end(), buffer.get() + environment * 8);
  }
  nb::capsule owner(buffer.get(), [](void *p) noexcept {
    delete[] static_cast<std::int64_t *>(p);
  });
  const auto *data = buffer.release();
  return Int64_2D(data, {batch_size_, 8}, owner);
}
GuardianInventorySnapshot GuardianTurnBatch::inventory_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(cards_.size() * 3);
  for (std::size_t environment = 0; environment < batch_size_; ++environment) {
    for (std::size_t player = 0; player < player_count_; ++player) {
      for (std::size_t slot = 0; slot < hand_slots_; ++slot) {
        const auto offset =
            card_offset(environment, static_cast<std::int64_t>(player), slot);
        buffer[offset * 3] = cards_[offset].instance;
        buffer[offset * 3 + 1] = cards_[offset].model;
        buffer[offset * 3 + 2] =
            combat_.pending_[environment][0] == 1 &&
                    combat_.pending_[environment][3] ==
                        static_cast<std::int64_t>(player) &&
                    selected_[environment * hand_slots_ + slot]
                ? 1
                : 0;
      }
    }
  }
  nb::capsule owner(buffer.get(), [](void *p) noexcept {
    delete[] static_cast<std::int64_t *>(p);
  });
  const auto *data = buffer.release();
  return GuardianInventorySnapshot(
      data, {batch_size_, player_count_, hand_slots_, 3}, owner);
}
} // namespace godfield_sim
