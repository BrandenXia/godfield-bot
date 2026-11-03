#include "curse_rules.h"
#include "full_game_batch.h"
#include "full_game_random.h"
#include "payment_rules.h"

#include <algorithm>
#include <stdexcept>

namespace godfield_sim {
using full_game_random::kMaximumCounter;
using full_game_random::random_rank;

void FullGameBatch::seed_confusion(ActionInput envs, ActionInput owners,
                                   ActionInput remaining) {
  const auto indices = inventory_.checked_owners(envs, owners);
  DreamInventoryBatch::same_length(indices.size(), remaining);
  std::map<std::size_t, Episode> staged;
  for (std::size_t i = 0; i < indices.size(); ++i) {
    const auto env = indices[i] / player_count_,
               owner = indices[i] % player_count_;
    require_setup(env);
    if (remaining(i) < 0 || remaining(i) > 1000000000)
      throw std::invalid_argument(
          "full-game confusion setup count is out of range");
    auto [row, inserted] = staged.try_emplace(env, episodes_[env]);
    static_cast<void>(inserted);
    row->second.confusion[owner] = remaining(i);
  }
  for (const auto &[env, episode] : staged)
    episodes_[env] = episode;
}

void FullGameBatch::shuffle_phenomenon_items(Mutation &mutation) const {
  auto &e = mutation.episode;
  std::vector<std::int64_t> models;
  for (std::size_t owner = 0; owner < player_count_; ++owner) {
    if (mutation.statuses[owner][0] <= 0)
      continue;
    for (const auto &held : stage_hand(mutation, owner)) {
      models.push_back(held[1]);
      e.phenomenon_stats[20] += held[3] != 0 ? 1 : 0;
    }
  }
  if (!models.empty() &&
      e.next_instance >
          kMaximumCounter - static_cast<std::int64_t>(models.size()) + 1)
    throw std::invalid_argument(
        "full-game phenomenon shuffle identities exhausted");
  for (std::size_t i = 0; i + 1 < models.size(); ++i)
    std::swap(
        models[i],
        models[i + random_rank(e.phenomenon_shuffle_rng, models.size() - i)]);
  std::size_t cursor = 0;
  for (std::size_t owner = 0; owner < player_count_; ++owner) {
    if (mutation.statuses[owner][0] <= 0)
      continue;
    auto &hand = stage_hand(mutation, owner);
    for (auto &held : hand) {
      const auto model = models[cursor++];
      held = {e.next_instance++, model, 0, 0};
      if ((mutation.statuses[owner][2] & kCurseDreamBit) != 0 &&
          random_rank(e.phenomenon_disguise_rng, 100) < 50) {
        const auto &pool = inventory_.fake_pools_[static_cast<std::size_t>(
            inventory_.category(model) - 1)];
        held[2] = pool[random_rank(e.phenomenon_disguise_rng, pool.size())];
        ++e.phenomenon_stats[19];
      }
    }
  }
  ++e.phenomenon_stats[17];
  e.phenomenon_stats[18] += static_cast<std::int64_t>(models.size());
}

bool FullGameBatch::enqueue_phenomenon(Mutation &mutation,
                                       std::size_t owner) const {
  auto &e = mutation.episode;
  if (e.turn_owner < 0)
    e.turn_owner = static_cast<std::int64_t>(owner);
  ++e.phenomenon_stats[0];
  const auto rank = random_rank(e.phenomenon_rng, phenomena_.size());
  const auto row =
      std::next(phenomena_.begin(), static_cast<std::ptrdiff_t>(rank));
  const auto model = row->first;
  const auto &effect = row->second;
  ++e.phenomenon_stats[1];
  ++e.phenomenon_model_counts[static_cast<std::size_t>(model - 287)];
  std::array<std::int64_t, 9> living{};
  std::size_t count = 0;
  for (std::size_t seat = 0; seat < player_count_; ++seat)
    if (mutation.statuses[seat][0] > 0 &&
        (effect.kind != 6 || are_enemies(e, owner, seat)))
      living[count++] = static_cast<std::int64_t>(seat);
  auto target = static_cast<std::int64_t>(owner);
  if (effect.kind == 6 && count == 0) {
    // A private absent-recipient sentinel is suppressed by the shared queue,
    // never sampled from an empty set or revealed as an invented self-target.
    QueuedAttack shot{6,
                      static_cast<std::int64_t>(owner),
                      -1,
                      effect.value,
                      effect.element,
                      5,
                      effect.rate};
    shot.phenomenon_model = model;
    enqueue_attack(mutation, shot);
    ++e.phenomenon_stats[3];
    return true;
  }
  if (effect.kind == 5 || effect.kind == 6 || effect.kind == 7 ||
      effect.kind == 8) {
    target = living[random_rank(e.phenomenon_target_rng, count)];
    ++e.phenomenon_stats[2];
  }
  if (effect.kind == 5 || effect.kind == 6) {
    QueuedAttack shot{6,
                      static_cast<std::int64_t>(owner),
                      target,
                      effect.value,
                      effect.element,
                      5,
                      effect.rate};
    shot.phenomenon_model = model;
    enqueue_attack(mutation, shot);
    ++e.phenomenon_stats[3];
    return true;
  }
  if (effect.kind <= 4) {
    for (std::size_t i = 0; i < count; ++i) {
      const auto seat = static_cast<std::size_t>(living[i]);
      auto &status = mutation.statuses[seat];
      if (effect.kind == 1) {
        status[1] = 2;
        ++e.phenomenon_stats[8];
      } else if (effect.kind == 2) {
        status[2] |= kCurseFogBit;
        ++e.phenomenon_stats[9];
      } else if (effect.kind == 3) {
        e.confusion[seat] += 3;
        e.phenomenon_stats[10] += 3;
      } else {
        e.phenomenon_stats[12] += std::max<std::int64_t>(0, status[0] - 1);
        status[0] = 1;
        ++e.phenomenon_stats[11];
      }
    }
  } else if (effect.kind == 7) {
    const auto gain = std::min<std::int64_t>(
        50, resource_cap_ - mutation.statuses[target][0]);
    mutation.statuses[target][0] += gain;
    e.phenomenon_stats[13] += gain;
  } else if (effect.kind == 8) {
    std::int64_t total = 0;
    for (std::size_t i = 0; i < count; ++i) {
      total += mutation.resources[living[i]][1];
      mutation.resources[living[i]][1] = 0;
    }
    const auto credit = credit_cp_capped(
        {mutation.statuses[target][0], mutation.resources[target][0], 0}, total,
        resource_cap_);
    mutation.resources[target][1] = credit.wallet.cp;
    e.phenomenon_stats[14] += total;
    e.phenomenon_stats[15] += credit.credited;
    e.phenomenon_stats[16] += total - credit.credited;
  } else if (effect.kind == 9)
    shuffle_phenomenon_items(mutation);
  else {
    for (std::size_t i = 0; i < count; ++i) {
      summon_guardian(mutation, static_cast<std::size_t>(living[i]));
      ++e.phenomenon_stats[21];
    }
  }
  ++e.phenomenon_stats[22];
  return false;
}

void FullGameBatch::execute_confused_turn(Mutation &mutation) const {
  auto &e = mutation.episode;
  const auto actor = static_cast<std::size_t>(e.actor);
  const auto owner = mutation.environment * player_count_ + actor;
  std::vector<std::pair<std::int64_t, std::int64_t>> choices;
  bool weapon = false;
  for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot) {
    const auto &held = inventory_.items_[owner * capacity_ + slot];
    const auto model = held[1];
    weapon = weapon || (inventory_.category(model) == 1 && held[3] == 0);
    const auto utility = effects_.find(model);
    const auto attack = attacks_.find(model);
    const auto boost = boosts_.find(model);
    const bool supported = (utility != effects_.end() &&
                            visible_utility_eligible(owner, utility->second)) ||
                           attack != attacks_.end() ||
                           (boost != boosts_.end() && boost->second.can_lead);
    bool sell_eligible = true;
    if (model == 4 && !market_prices_.empty()) {
      sell_eligible = false;
      for (std::size_t other = 0; other < inventory_.sizes_[owner]; ++other)
        sell_eligible = sell_eligible ||
                        (other != slot &&
                         inventory_.items_[owner * capacity_ + other][3] == 0);
    }
    if ((supported && model_mp_cost(model) <= mutation.resources[actor][0]) ||
        (model >= 3 && model <= 5 && sell_eligible) ||
        (model == 207 && !effects_.contains(model)))
      choices.emplace_back(1, static_cast<std::int64_t>(slot));
    if ((!e.apocalypse || sacrifice_enabled_) &&
        discard_models_.contains(model))
      choices.emplace_back(2, static_cast<std::int64_t>(slot));
  }
  if (!weapon)
    choices.emplace_back(0, 0);
  --e.confusion[actor];
  ++e.confusion_stats[0];
  ++e.confusion_stats[7];
  e.turn_owner = e.actor;
  auto chosen = std::pair<std::int64_t, std::int64_t>{0, 0};
  if (!choices.empty()) {
    chosen = choices[random_rank(e.confusion_rng, choices.size())];
    ++e.confusion_stats[1];
  }
  if (chosen.first == 0) {
    mutation.pass = true;
    if (!choices.empty() && prayer_gifts_) {
      mutation.prayer = true;
      ++e.gifts_due[actor];
      ++e.confusion_stats[4];
    } else
      ++e.confusion_stats[5];
    finish_turn(mutation, actor);
    return;
  }
  const auto slot = static_cast<std::size_t>(chosen.second);
  e.attack_slot = chosen.second;
  e.attack_size = 1;
  mutation.order[0] = static_cast<std::int64_t>(slot + 1);
  mutation.selected[slot] = 1;
  if (chosen.first == 2) {
    e.discard_size = 1;
    ++e.confusion_stats[3];
    execute_discard(mutation);
    return;
  }
  const auto model = inventory_.items_[owner * capacity_ + slot][1];
  if (exchange_models_.contains(model)) {
    ++e.confusion_stats[2];
    execute_forced_exchange(mutation, slot);
    return;
  }
  if (!market_prices_.empty() && (model == 4 || model == 5)) {
    ++e.confusion_stats[2];
    begin_market(mutation, slot, model - 3);
    e.forced_market = true;
    if (model == 4) {
      std::vector<std::size_t> candidates;
      for (std::size_t other = 0; other < inventory_.sizes_[owner]; ++other)
        if (other != slot &&
            inventory_.items_[owner * capacity_ + other][3] == 0)
          candidates.push_back(other);
      e.sale_slot = static_cast<std::int64_t>(
          candidates[random_rank(e.market_sale_rng, candidates.size())]);
    }
    std::int64_t target = -1;
    for (std::size_t seat = 0; seat < player_count_; ++seat)
      if (are_enemies(e, actor, seat) && mutation.statuses[seat][0] > 0) {
        target = static_cast<std::int64_t>(seat);
        break;
      }
    cast_market(mutation, static_cast<std::int64_t>(capacity_) + 1 + target);
    return;
  }
  e.utility_selection = effects_.contains(model);
  ++e.confusion_stats[2];
  if (e.utility_selection) {
    execute_utility(mutation, slot, !attack_order_.empty());
    return;
  }
  const auto rate = hit_rate(model);
  std::array<std::int64_t, 8> enemies{};
  std::size_t count = 0;
  for (std::size_t seat = 0; seat < player_count_; ++seat)
    if (are_enemies(e, actor, seat) && mutation.statuses[seat][0] > 0)
      enemies[count++] = static_cast<std::int64_t>(seat);
  auto target = enemies[0];
  if (rate == 100 && (mutation.statuses[actor][2] & kCurseFogBit) == 0) {
    target = enemies[random_rank(e.confusion_target_rng, count)];
    ++e.confusion_stats[6];
  }
  cast_attack(mutation, static_cast<std::int64_t>(capacity_) + 1 + target,
              rate < 100);
}
} // namespace godfield_sim
