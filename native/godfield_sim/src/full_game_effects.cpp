#include "curse_rules.h"
#include "full_game_batch.h"
#include "full_game_random.h"
#include "payment_rules.h"

#include <algorithm>

namespace godfield_sim {
using full_game_random::random_rank;

// Apply an already-admitted effect. Ownership/use, MP payment, artifacts and
// replacement gifts belong to the caller, not this reusable effect layer.
// true means a revealed phenomenon attack was enqueued. The caller drives the
// shared scheduler; this layer never recursively finishes another owner's turn.
bool FullGameBatch::apply_utility_effect(Mutation &mutation, std::size_t actor,
                                         const Effect &effect,
                                         std::int64_t cost) const {
  const bool had_dream = (mutation.statuses[actor][2] & kCurseDreamBit) != 0;
  if (effect.kind == 1)
    mutation.statuses[actor][0] = std::min<std::int64_t>(
        resource_cap_, mutation.statuses[actor][0] + effect.value);
  else if (effect.kind == 2)
    mutation.resources[actor][0] = std::min<std::int64_t>(
        resource_cap_, mutation.resources[actor][0] + effect.value);
  else if (effect.kind == 5) {
    const auto credit = credit_cp_capped({mutation.statuses[actor][0],
                                          mutation.resources[actor][0],
                                          mutation.resources[actor][1]},
                                         effect.value, resource_cap_);
    mutation.resources[actor][1] = credit.wallet.cp;
    ++mutation.cp_utility;
    mutation.utility_cp_gain += static_cast<std::uint64_t>(credit.credited);
    ++mutation.episode.cp_utility_stats[0];
    mutation.episode.cp_utility_stats[1] += credit.credited;
    mutation.episode.cp_utility_stats[2] += cost;
    mutation.episode.cp_utility_stats[3] += credit.capped > 0 ? 1 : 0;
  } else if (effect.kind == 6) {
    auto &stats = mutation.episode.compound_utility_stats;
    ++stats[0];
    const auto gain = std::min<std::int64_t>(
        effect.value, resource_cap_ - mutation.resources[actor][0]);
    mutation.resources[actor][0] += gain;
    stats[1] += gain;
    stats[2] += gain < effect.value ? 1 : 0;
    auto &status = mutation.statuses[actor];
    const auto result = inflict_illness(
        {static_cast<std::uint16_t>(status[0]),
         static_cast<std::uint8_t>(status[1])},
        4); // Source-pinned Heaven; compound order remains provisional.
    const auto damage = status[0] - result.hp;
    status[0] = result.hp;
    status[1] = result.stage;
    ++stats[3];
    stats[4] += damage;
    ++mutation.inflicted_illness;
    mutation.utility_hp_damage += static_cast<std::uint64_t>(damage);
    if (damage > 0 && status[0] == 0)
      resolve_hp_zero(mutation, actor, 2);
    guardian_damage(mutation, actor, damage);
  } else if (effect.kind == 7) {
    auto &stats = mutation.episode.compound_utility_stats;
    ++stats[5];
    auto &hp = mutation.statuses[actor][0];
    // The source does not specify probabilities. Local 50/50 sampling uses a
    // dedicated staged stream, independent of illness/chance/combat/gifts.
    if (random_rank(mutation.episode.utility_rng, 2) == 0) {
      const auto gain =
          std::min<std::int64_t>(effect.value, resource_cap_ - hp);
      hp += gain;
      ++stats[6];
      stats[7] += gain;
    } else {
      const auto damage = std::min(hp, effect.value);
      hp -= damage;
      ++stats[8];
      stats[9] += damage;
      mutation.utility_hp_damage += static_cast<std::uint64_t>(damage);
      if (damage > 0 && hp == 0)
        resolve_hp_zero(mutation, actor, 6);
      guardian_damage(mutation, actor, damage);
    }
  } else if (effect.kind == 8) {
    summon_guardian(mutation, actor);
  } else if (effect.kind == 9) {
    return enqueue_phenomenon(mutation, actor);
  } else {
    mutation.cured_owner = static_cast<std::int64_t>(actor);
    mutation.statuses[actor][1] = cured_illness_stage(
        static_cast<std::uint8_t>(mutation.statuses[actor][1]),
        effect.kind == 4);
    mutation.statuses[actor][2] = cured_documented_mask(
        static_cast<std::uint8_t>(mutation.statuses[actor][2]),
        effect.kind == 4);
  }
  if (had_dream && (mutation.statuses[actor][2] & kCurseDreamBit) == 0) {
    for (auto &held : stage_hand(mutation, actor)) {
      mutation.restored += held[2] != 0 ? 1 : 0;
      held[2] = 0;
    }
  }
  return false;
}

FullGameBatch::QueuedAttack FullGameBatch::attack_payload(
    std::int64_t leader, const Composition &composition, std::int64_t source,
    std::int64_t target, std::int64_t family_kind) const {
  QueuedAttack shot{family_kind,
                    source,
                    target,
                    composition.value,
                    composition.element,
                    composition.origin,
                    hit_rate(leader)};
  if (const auto effect = attack_effects_.find(leader);
      effect != attack_effects_.end()) {
    shot.effect_kind = effect->second.kind;
    shot.effect_value = effect->second.value;
  }
  if (const auto effect = removals_.find(leader); effect != removals_.end()) {
    shot.effect_kind = 7 + effect->second.kind;
    shot.effect_value = effect->second.value;
  }
  if (const auto weapon = complex_weapons_.find(leader);
      weapon != complex_weapons_.end() && weapon->second.kind == 2)
    shot.effect_kind = 10;
  if (const auto danger = dangers_.find(leader); danger != dangers_.end())
    shot.danger = danger->second.kind == 1;
  return shot;
}
} // namespace godfield_sim
