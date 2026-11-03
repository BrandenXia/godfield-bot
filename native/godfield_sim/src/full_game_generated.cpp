#include "full_game_batch.h"
#include "full_game_random.h"

#include <algorithm>
#include <stdexcept>

namespace godfield_sim {
using full_game_random::kMaximumCounter;
using full_game_random::random_rank;

std::int64_t FullGameBatch::draw_generated_model(Mutation &mutation,
                                                 std::int64_t group) const {
  const auto &pool =
      guardian_generated_weights_.at(static_cast<std::size_t>(group - 9));
  if (pool.empty())
    throw std::invalid_argument(
        "full-game generated guardian category pool is empty");
  const auto ticket =
      random_rank(mutation.episode.guardian_generated_rng, pool.back().second);
  return std::upper_bound(
             pool.begin(), pool.end(), ticket,
             [](auto rank, const auto &row) { return rank < row.second; })
      ->first;
}

void FullGameBatch::execute_generated_guardian(
    Mutation &mutation, const QueuedAttack &producer) const {
  auto &e = mutation.episode;
  const auto owner = static_cast<std::size_t>(producer.source);
  const auto model = producer.generated_model;
  const auto route = guardian_action_routes_.at(model);
  auto &stats = e.guardian_generated_stats;
  if (route == 2) {
    const auto effect = effects_.find(model);
    if (effect == effects_.end())
      throw std::invalid_argument(
          "full-game generated utility dependency is unavailable");
    ++stats[9];
    ++e.guardian_generated_execution_counts[static_cast<std::size_t>(model -
                                                                     3)];
    const auto hp = mutation.statuses[owner][0],
               mp = mutation.resources[owner][0],
               cp = mutation.resources[owner][1];
    static_cast<void>(apply_utility_effect(mutation, owner, effect->second, 0));
    e.guardian_stats[14] +=
        std::max<std::int64_t>(0, mutation.statuses[owner][0] - hp);
    e.guardian_stats[15] +=
        std::max<std::int64_t>(0, mutation.resources[owner][0] - mp);
    e.guardian_stats[16] +=
        std::max<std::int64_t>(0, mutation.resources[owner][1] - cp);
    return; // The outer family loop, never this effect, drives queued children.
  }
  if (route == 3) {
    if (!exchange_models_.contains(model))
      throw std::invalid_argument(
          "full-game generated Exchange dependency is unavailable");
    ++stats[10];
    ++e.guardian_generated_execution_counts[static_cast<std::size_t>(model -
                                                                     3)];
    const auto wallet =
        sample_exchange_wallet(mutation, owner, e.guardian_allocation_rng);
    settle_exchange(mutation, owner, wallet);
    return;
  }
  Composition composition{};
  std::int64_t leader = model, virtual_leader = 0;
  if (route == 6) {
    composition = {0, 0, 0, 4, false};
    virtual_leader = 285;
  } else if (route == 7) {
    const std::array<std::int64_t, 2> models{286, model};
    composition = compose_models(models, mutation.resources[owner][0], false,
                                 CardSource::Generated);
    leader = virtual_leader = 286;
  } else if (route == 1) {
    composition = compose_models({&model, 1}, mutation.resources[owner][0],
                                 false, CardSource::Generated);
  }
  const auto weapon = complex_weapons_.find(model);
  const auto weapon_kind =
      weapon == complex_weapons_.end() ? 0 : weapon->second.kind;
  const bool pestle = dangers_.contains(model) && dangers_.at(model).kind == 1;
  std::array<std::int64_t, 9> recipients{};
  std::size_t count = 0;
  if (composition.area_count > 0) {
    for (std::size_t seat = 0; seat < player_count_; ++seat)
      if (seat != owner && mutation.statuses[seat][0] > 0)
        recipients[count++] = static_cast<std::int64_t>(seat);
    mutation.area_cast = true;
    ++e.area_stats[0];
    e.area_stats[1] += composition.area_count;
    e.area_stats[2] += static_cast<std::int64_t>(count);
    e.area_stats[3] += static_cast<std::int64_t>(count);
  } else if (pestle) {
    recipients[count++] =
        producer.source; // prepare_danger owns the actual draw.
    mutation.danger_cast = true;
    ++e.danger_stats[0];
  } else {
    std::array<std::int64_t, 8> enemies{};
    std::size_t enemies_count = 0;
    for (std::size_t seat = 0; seat < player_count_; ++seat)
      if (seat != owner && mutation.statuses[seat][0] > 0)
        enemies[enemies_count++] = static_cast<std::int64_t>(seat);
    if (enemies_count == 0) {
      ++stats[6];
      return; // Explicit no-recipient suppression, no invented
              // self-target/debit.
    }
    recipients[count++] =
        enemies[random_rank(e.guardian_target_rng, enemies_count)];
    ++e.guardian_stats[5];
  }
  if (count == 0) {
    ++stats[6];
    return;
  }
  ++e.guardian_generated_execution_counts[static_cast<std::size_t>(model - 3)];
  ++stats[static_cast<std::size_t>(route == 1 ? 8 : route + 7)];
  if (route == 4 || route == 5) {
    enqueue_generated_market(mutation, producer, route - 3, recipients[0]);
    return;
  }
  if (route == 1 && weapon_kind == 1) {
    const auto debit = mutation.resources[owner][0];
    mutation.resources[owner][0] = 0;
    mutation.paid += static_cast<std::uint64_t>(debit);
    ++e.weapon_stats[0];
    e.weapon_stats[1] += debit;
    stats[20] += debit;
  } else if (route == 1 && weapon_kind == 2)
    ++e.weapon_stats[2];
  else if (route == 1 && weapon_kind == 3)
    ++e.weapon_stats[5];
  auto shot =
      attack_payload(leader, composition, producer.source, recipients[0], 9);
  shot.guardian_model = producer.guardian_model;
  shot.generated_model = model;
  shot.virtual_leader = virtual_leader;
  shot.weapon_kind = weapon_kind;
  shot.weapon_value =
      weapon == complex_weapons_.end() ? 0 : weapon->second.value;
  shot.area_count = composition.area_count;
  if (pestle) {
    shot.danger_value = dangers_.at(model).value;
    shot.danger_element = dangers_.at(model).element;
  }
  if (route == 6) {
    shot.effect_kind = 12;
    shot.effect_value = model;
  }
  const auto repeats = weapon_kind == 3 ? 2 : 1;
  for (std::size_t i = count; i-- > 0;) {
    shot.target = recipients[i];
    for (std::int64_t repeat = 1; repeat <= repeats; ++repeat) {
      shot.recipient_strikes = repeat;
      enqueue_attack(mutation, shot);
      ++stats[15];
    }
  }
}

void FullGameBatch::enqueue_generated_market(Mutation &mutation,
                                             const QueuedAttack &producer,
                                             std::int64_t kind,
                                             std::int64_t target) const {
  auto &e = mutation.episode;
  if (market_prices_.empty())
    throw std::invalid_argument(
        "full-game generated market dependency is unavailable");
  QueuedAttack shot{7, producer.source, target, 0, 0, 6, 100};
  shot.market_kind = kind;
  shot.guardian_model = producer.guardian_model;
  shot.generated_model = producer.generated_model;
  shot.automatic_buyer = producer.source;
  if (kind == 1) {
    const auto parcel_model = draw_generated_model(mutation, 9);
    if (e.next_instance > kMaximumCounter)
      throw std::invalid_argument(
          "full-game generated parcel identities exhausted");
    shot.escrow = {e.next_instance++, parcel_model, 0, 0};
    shot.escrow_owner =
        -2; // Explicit generated custody, never a real held slot.
    ++e.guardian_generated_stats[21];
  }
  ++e.market_stats[kind == 1 ? 3 : 4];
  enqueue_attack(mutation, shot);
}
} // namespace godfield_sim
