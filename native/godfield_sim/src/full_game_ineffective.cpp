#include "full_game_batch.h"

#include <stdexcept>

namespace godfield_sim {

std::int64_t FullGameBatch::registered_roles(std::int64_t model) const {
  std::int64_t bits = 0;
  const auto boost = boosts_.find(model);
  if (attacks_.contains(model) ||
      (boost != boosts_.end() && boost->second.can_lead))
    bits |= 1;
  if (effects_.contains(model))
    bits |= 2;
  if (boost != boosts_.end())
    bits |= 4;
  if (armor_.contains(model))
    bits |= 8;
  if (specials_.contains(model))
    bits |= 16;
  const auto effect = defense_effects_.find(model);
  if (effect != defense_effects_.end() && effect->second.kind == 5)
    bits |= 32;
  if (cost_reducers_.contains(model))
    bits |= 64;
  const auto danger = dangers_.find(model);
  if (passives_.contains(model) || ascensions_by_model_.contains(model) ||
      (danger != dangers_.end() && danger->second.kind == 2))
    bits |= 128;
  if (exchange_models_.contains(model) ||
      ((model == 4 || model == 5) && market_prices_.contains(model)))
    bits |= 256;
  return bits;
}

bool FullGameBatch::hidden_selection(const Mutation &mutation,
                                     std::size_t count) const {
  if (!resolve_hidden_components_)
    return false;
  const auto owner = mutation.environment * player_count_ +
                     static_cast<std::size_t>(mutation.episode.actor);
  for (std::size_t i = 0; i < count; ++i) {
    const auto &item =
        inventory_.items_[owner * capacity_ +
                          static_cast<std::size_t>(mutation.order[i] - 1)];
    if (item[2] != 0 && item[2] != item[1])
      return true;
  }
  return false;
}

void FullGameBatch::record_ineffective(Mutation &mutation,
                                       const std::bitset<512> &mask,
                                       std::size_t count,
                                       std::size_t kind) const {
  if (mask.none())
    return;
  auto &e = mutation.episode;
  ++e.ineffective_stats[kind];
  if (kind < 2) {
    e.ineffective_stats[3] += mask[0] ? 1 : 0;
    e.ineffective_stats[4] +=
        static_cast<std::int64_t>(mask.count()) - (mask[0] ? 1 : 0);
    ++e.ineffective_stats[mask[0] ? 9 : 10];
  } else {
    e.ineffective_stats[5] += static_cast<std::int64_t>(mask.count());
    e.ineffective_stats[13] += mask.count() == count ? 1 : 0;
  }
  const auto owner =
      mutation.environment * player_count_ + static_cast<std::size_t>(e.actor);
  for (std::size_t i = 0; i < count; ++i) {
    if (!mask[i])
      continue;
    const auto model =
        inventory_.items_[owner * capacity_ +
                          static_cast<std::size_t>(mutation.order[i] - 1)][1];
    ++e.ineffective_models[static_cast<std::size_t>(model - 3)];
    const bool miracle = inventory_.category(model) == 4;
    ++e.ineffective_stats[miracle ? 7 : 6];
    const bool waived =
        i + 1 < count && miracle &&
        cost_reducers_.contains(
            inventory_
                .items_[owner * capacity_ + static_cast<std::size_t>(
                                                mutation.order[i + 1] - 1)][1]);
    if (!waived)
      e.ineffective_stats[8] += model_mp_cost(model);
    if (kind < 2 && i > 0 && cost_reducers_.contains(model))
      ++e.ineffective_stats[12];
  }
}

void FullGameBatch::resolve_ineffective_defenses(
    Mutation &mutation, std::int64_t &defense,
    std::vector<DefenseEffect> &counters,
    std::vector<DefenseEffect> &self_effects) const {
  auto &e = mutation.episode;
  const auto actor = static_cast<std::size_t>(e.actor);
  const auto owner = mutation.environment * player_count_ + actor;
  const auto count = static_cast<std::size_t>(e.selected_count);
  std::array<std::int64_t, 512> models{};
  for (std::size_t i = 0; i < count; ++i)
    models[i] =
        inventory_.items_[owner * capacity_ +
                          static_cast<std::size_t>(mutation.order[i] - 1)][1];
  const auto cost = sequence_cost({models.data(), count}, CardSource::Held);
  if (mutation.resources[actor][0] < cost)
    throw std::invalid_argument(
        "full-game hidden actual miracle cost is unaffordable");
  mutation.resources[actor][0] -= cost;
  mutation.paid += static_cast<std::uint64_t>(cost);
  Composition waived{};
  std::bitset<512> ineffective;
  bool prefix = true, exclusive = false;
  for (std::size_t i = 0; i < count; ++i) {
    const auto model = models[i];
    const bool attached = i > 0 && cost_reducers_.contains(model) &&
                          inventory_.category(models[i - 1]) == 4;
    if (attached) {
      ++waived.waivers;
      waived.waived += model_mp_cost(models[i - 1]);
      continue;
    }
    const auto effect = defense_effects_.find(model);
    const bool filter =
        effect != defense_effects_.end() && effect->second.kind == 5;
    if (filter) {
      if (!prefix || e.attack == 0 || exclusive) {
        ineffective.set(i);
        ++e.ineffective_stats[12];
      } else {
        e.element = 0;
        ++mutation.filters_used;
        ++e.counter_stats[9];
      }
      continue;
    }
    const auto special = special_kind(model, e);
    if (special != 0) {
      if (prefix && !exclusive) {
        mutation.special_kind = special;
        exclusive = true;
        prefix = false;
      } else {
        ineffective.set(i);
        ++e.ineffective_stats[12];
      }
      continue;
    }
    const auto armor = armor_.find(model);
    if (exclusive || armor == armor_.end() || e.attack == 0) {
      ineffective.set(i);
      if (exclusive)
        ++e.ineffective_stats[12];
      continue;
    }
    if (!compatible(e.element, armor->second.element)) {
      ineffective.set(i);
      ++e.ineffective_stats[11];
      continue;
    }
    defense += armor->second.value;
    prefix = false;
    if (effect != defense_effects_.end()) {
      if (effect->second.kind <= 4)
        counters.push_back(effect->second);
      else if (effect->second.kind == 6 || effect->second.kind == 7)
        self_effects.push_back(effect->second);
    }
  }
  record_waivers(mutation, waived, 4);
  record_ineffective(mutation, ineffective, count, 2);
}
} // namespace godfield_sim
