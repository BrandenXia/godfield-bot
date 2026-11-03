#include "full_game_batch.h"
#include "full_game_random.h"

#include <algorithm>
#include <stdexcept>

namespace godfield_sim {
using full_game_random::kMaximumCounter;

std::int64_t FullGameBatch::sequence_cost(std::span<const std::int64_t> models,
                                          CardSource source) const {
  if (source == CardSource::Generated)
    return 0; // Generated artifacts have no ordinary held-miracle use debit.
  std::int64_t cost = 0;
  for (std::size_t i = 0; i < models.size(); ++i) {
    if (i + 1 < models.size() && inventory_.category(models[i]) == 4 &&
        cost_reducers_.contains(models[i + 1]))
      continue;
    cost += model_mp_cost(models[i]);
  }
  return cost;
}

FullGameBatch::Composition
FullGameBatch::compose_models(std::span<const std::int64_t> models,
                              std::int64_t owner_mp, bool utility,
                              CardSource source, bool tolerate) const {
  Composition result{};
  const bool held = source == CardSource::Held;
  for (std::size_t index = 0; index < models.size(); ++index) {
    const auto model = models[index];
    if (index == 0 && model == 286 && !held) {
      result = {10, 0, 0, 0, true};
      continue; // Pinned Full Moon Blade base ATK and weapon-origin override.
    }
    const auto category = inventory_.category(model);
    const auto attack = attacks_.find(model);
    const auto boost = boosts_.find(model);
    if (index == 0) {
      const auto effect = effects_.find(model);
      if (utility) {
        if (effect == effects_.end()) {
          if (!tolerate)
            throw std::invalid_argument(
                "full-game actual card effect is not implemented yet");
          result.ineffective.set(0);
        } else
          result = {0, 0, held ? effect->second.cost : 0, category == 4 ? 1 : 3,
                    false};
      } else if (attack != attacks_.end())
        result = {attack->second.value, attack->second.element,
                  held ? attack->second.cost : 0, attack->second.origin,
                  category == 1 && hit_rate(model) == 100};
      else if (boost != boosts_.end() && boost->second.can_lead)
        result = {boost->second.value, boost->second.element,
                  held ? boost->second.cost : 0, category == 4 ? 1 : 0,
                  category == 1};
      else {
        if (!tolerate)
          throw std::invalid_argument(
              "full-game actual attack leader effect is "
              "not implemented or cannot lead");
        result.ineffective.set(0);
      }
      const auto weapon = complex_weapons_.find(model);
      if (weapon != complex_weapons_.end() && weapon->second.kind == 1) {
        // The generated context skips normal selected-miracle costs; the
        // MP-powered weapon's special owner-MP debit belongs to its caller.
        const auto remaining =
            std::max<std::int64_t>(0, owner_mp - sequence_cost(models, source));
        result.value = remaining * weapon->second.value;
      }
    } else if (cost_reducers_.contains(model)) {
      if (inventory_.category(models[index - 1]) != 4) {
        if (!tolerate)
          throw std::invalid_argument("full-game hidden cost reducer must "
                                      "immediately follow a miracle");
        result.ineffective.set(index);
        continue;
      }
      if (held) {
        const auto cost = model_mp_cost(models[index - 1]);
        result.cost -= cost;
        result.waived += cost;
        ++result.waivers;
      }
      continue;
    } else {
      if (!held && models.front() == 286 && (model == 233 || model == 234) &&
          specials_.contains(model))
        continue; // A defense-only addition has no offensive first-card
                  // ability.
      if (!result.weapon || boost == boosts_.end()) {
        if (!tolerate)
          throw std::invalid_argument(
              "full-game actual attack addition effect is "
              "not implemented or incompatible");
        result.ineffective.set(index);
        continue;
      }
      const auto &effect = boost->second;
      if (effect.kind == 3) {
        ++result.area_count;
        result.cost += held ? effect.cost : 0;
        continue;
      }
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
      result.cost += held ? effect.cost : 0;
    }
  }
  // Costs belong to the actual physical selection, not just its effective
  // components. Adjacent true reducers waive once even when the preceding
  // miracle's selected role cannot act. No free hidden use or invented base.
  if (tolerate)
    result.cost = sequence_cost(models, source);
  return result;
}
} // namespace godfield_sim
