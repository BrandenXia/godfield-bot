#include "curse_rules.h"
#include "full_game_batch.h"
#include "full_game_random.h"
#include "payment_rules.h"

#include <algorithm>
#include <memory>
#include <stdexcept>

namespace godfield_sim {

void FullGameBatch::clear_market(Mutation &mutation) const {
  auto &e = mutation.episode;
  if (e.escrow[0] != 0)
    throw std::logic_error(
        "full-game cannot discard an unsettled market escrow");
  e.market_kind = 0;
  e.sale_slot = e.escrow_owner = -1;
  e.trade_mode = e.trade_actions = 0;
  e.forced_market = false;
  e.automatic_buyer = -1;
}

void FullGameBatch::begin_market(Mutation &mutation, std::size_t slot,
                                 std::int64_t kind) const {
  auto &e = mutation.episode;
  e.turn_owner = e.actor;
  e.attack_slot = static_cast<std::int64_t>(slot);
  e.market_kind = kind;
  e.trade_mode = kind == 1 ? 2 : 0;
  e.trade_actions = 0;
  e.sale_slot = -1;
  e.phase = kind == 1 ? 6 : 3;
  e.utility_selection = false;
  ++e.market_stats[kind == 1 ? 0 : 1];
  mutation.selected.fill(0);
  mutation.order.fill(0);
}

bool FullGameBatch::resolve_hidden_trade(Mutation &mutation,
                                         std::int64_t choice) const {
  auto &e = mutation.episode;
  const auto actor = static_cast<std::size_t>(e.actor);
  const auto owner = mutation.environment * player_count_ + actor;
  if (!resolve_hidden_trades_ || e.attack_slot < 0 ||
      static_cast<std::uint64_t>(e.attack_slot) >= inventory_.sizes_[owner])
    return false;
  const auto slot = static_cast<std::size_t>(e.attack_slot);
  const auto actual = inventory_.items_[owner * capacity_ + slot][1];
  const bool exchange_ui = e.trade_mode == 1;
  const auto displayed = exchange_ui ? 3 : e.market_kind + 3;
  if (actual < 3 || actual > 5 || displayed < 3 || displayed > 5 ||
      actual == displayed || market_prices_.empty() ||
      !exchange_models_.contains(3))
    return false; // Incomplete raw fixtures retain explicit unsupported errors.
  auto &stats = e.hidden_trade_stats;
  ++stats[0];
  ++stats[static_cast<std::size_t>(actual - 2)];
  stats[8] += exchange_ui || displayed == 4 || actual == 3 ? 1 : 0;
  if (actual == 3) {
    e.market_kind = 0;
    e.sale_slot = -1;
    e.trade_mode = 1;
    e.trade_wallet =
        sample_exchange_wallet(mutation, actor, e.hidden_exchange_rng);
    ++stats[4];
    execute_exchange(mutation);
    return true;
  }
  // The public preview/parcel is not an actual transfer. Preserve a displayed
  // enemy selection when available; missing parameters use private streams.
  e.trade_wallet.fill(0);
  e.trade_actions = e.trade_mode = 0;
  e.market_kind = actual - 3;
  e.sale_slot = -1;
  if (actual == 4) {
    std::vector<std::size_t> candidates;
    for (std::size_t other = 0; other < inventory_.sizes_[owner]; ++other)
      if (other != slot && inventory_.items_[owner * capacity_ + other][3] == 0)
        candidates.push_back(other);
    if (candidates.empty()) {
      // Approved provisional empty sale: consume the actual leader, with no
      // parcel, transfer, payment, response family or extra owner tick.
      ++stats[7];
      ++e.market_stats[3];
      consume_slot(mutation, actor, slot);
      clear_market(mutation);
      finish_turn(mutation, actor);
      return true;
    }
    e.sale_slot =
        static_cast<std::int64_t>(candidates[full_game_random::random_rank(
            e.hidden_sale_rng, candidates.size())]);
    ++stats[5];
  }
  auto target = choice - static_cast<std::int64_t>(capacity_) - 1;
  if (exchange_ui) {
    std::array<std::int64_t, 8> candidates{};
    std::size_t count = 0;
    for (std::size_t seat = 0; seat < player_count_; ++seat)
      if (are_enemies(e, actor, seat) && mutation.statuses[seat][0] > 0)
        candidates[count++] = static_cast<std::int64_t>(seat);
    target = candidates[full_game_random::random_rank(
        e.hidden_market_target_rng, count)];
    ++stats[6];
    ++e.market_stats[5];
  }
  cast_market(mutation, static_cast<std::int64_t>(capacity_) + 1 + target,
              exchange_ui);
  return true;
}

void FullGameBatch::cast_market(Mutation &mutation, std::int64_t choice,
                                bool target_resolved) const {
  if (resolve_hidden_trade(mutation, choice))
    return;
  auto &e = mutation.episode;
  const auto actor = static_cast<std::size_t>(e.actor);
  const auto owner = mutation.environment * player_count_ + actor;
  const auto slot = static_cast<std::size_t>(e.attack_slot);
  if (slot >= inventory_.sizes_[owner] || e.market_kind < 1 ||
      e.market_kind > 2 ||
      inventory_.items_[owner * capacity_ + slot][1] != e.market_kind + 3 ||
      market_prices_.empty())
    throw std::invalid_argument(
        "full-game hidden actual Sell/Buy leader differs; cross-role "
        "resolution is not implemented");
  DreamInventoryBatch::Item sale{};
  if (e.market_kind == 1) {
    if (e.sale_slot < 0 ||
        static_cast<std::uint64_t>(e.sale_slot) >= inventory_.sizes_[owner] ||
        e.sale_slot == e.attack_slot)
      throw std::invalid_argument(
          "full-game Sell requires one different owned card");
    sale = inventory_.items_[owner * capacity_ + e.sale_slot];
    if (sale[3] != 0 || !market_prices_.contains(sale[1]))
      throw std::invalid_argument(
          "full-game actual performed miracle cannot be sold");
  }
  auto target = choice - static_cast<std::int64_t>(capacity_) - 1;
  if (!target_resolved &&
      (e.forced_market || (mutation.statuses[actor][2] & kCurseFogBit) != 0)) {
    std::array<std::int64_t, 8> enemies{};
    std::size_t count = 0;
    for (std::size_t seat = 0; seat < player_count_; ++seat)
      if (are_enemies(e, actor, seat) && mutation.statuses[seat][0] > 0)
        enemies[count++] = static_cast<std::int64_t>(seat);
    if (count == 0)
      throw std::invalid_argument("full-game market has no living enemy");
    target = enemies[full_game_random::random_rank(e.market_target_rng, count)];
    ++e.market_stats[5];
  }
  if (target < 0 || static_cast<std::uint64_t>(target) >= player_count_ ||
      !are_enemies(e, actor, static_cast<std::size_t>(target)) ||
      mutation.statuses[target][0] <= 0)
    throw std::invalid_argument("full-game market target is unavailable");
  consume_slot(mutation, actor, slot);
  if (sale[0] != 0) {
    auto &hand = stage_hand(mutation, actor);
    const auto found =
        std::find_if(hand.begin(), hand.end(),
                     [&](const auto &held) { return held[0] == sale[0]; });
    if (found == hand.end())
      throw std::logic_error("full-game sale reservation lost ownership");
    hand.erase(found); // Escrow is not consumption or a replacement gift.
  }
  ++e.market_stats[e.market_kind == 1 ? 3 : 4];
  QueuedAttack shot{7, e.actor, target, 0, 0, 6, 100};
  shot.market_kind = e.market_kind;
  shot.escrow = sale;
  shot.escrow_owner = sale[0] != 0 ? e.actor : -1;
  shot.forced_market = e.forced_market;
  e.trade_mode = 0;
  mutation.selected.fill(0);
  mutation.order.fill(0);
  enqueue_attack(mutation, shot);
  resume_family(mutation);
}

void FullGameBatch::restore_market_escrow(Mutation &mutation) const {
  auto &e = mutation.episode;
  if (e.escrow[0] == 0)
    return;
  if (e.escrow_owner == -2) {
    e.escrow.fill(0);
    e.escrow_owner = -1;
    ++e.guardian_generated_stats[22];
    return; // A generated parcel is retired, never refunded into an owned hand.
  }
  if (e.escrow_owner < 0 ||
      static_cast<std::uint64_t>(e.escrow_owner) >= player_count_)
    throw std::logic_error("full-game market escrow has no original owner");
  auto &hand = stage_hand(mutation, static_cast<std::size_t>(e.escrow_owner));
  if (hand.size() >= hand_limit_ ||
      std::any_of(hand.begin(), hand.end(),
                  [&](const auto &held) { return held[0] == e.escrow[0]; }))
    throw std::invalid_argument(
        "full-game market refund would overflow or duplicate an item");
  hand.push_back(
      e.escrow); // Provisional tail return, same ID/disguise/unused flag.
  e.escrow.fill(0);
  e.escrow_owner = -1;
  ++e.market_stats[14];
}

void FullGameBatch::receive_market_item(Mutation &mutation,
                                        std::size_t recipient) const {
  auto &e = mutation.episode;
  if (e.escrow[0] == 0 || e.next_instance > full_game_random::kMaximumCounter)
    throw std::invalid_argument(
        "full-game market transfer lacks an item or native identity");
  const auto flags =
      receive_artifact(mutation, recipient, e.escrow[1], e.market_disguise_rng);
  e.market_stats[22] += (flags & 1) != 0 ? 1 : 0;
  e.market_stats[24] += (flags & 2) != 0 ? 1 : 0;
  e.escrow.fill(0);
  e.escrow_owner = -1;
  ++e.market_stats[13];
}

void FullGameBatch::settle_market(Mutation &mutation) const {
  auto &e = mutation.episode;
  const auto buyer =
      static_cast<std::size_t>(e.market_kind == 1 ? e.target : e.damage_source);
  const auto seller =
      static_cast<std::size_t>(e.market_kind == 1 ? e.damage_source : e.target);
  if (buyer == seller || e.escrow[0] == 0 || e.escrow[3] != 0)
    throw std::logic_error("full-game market settlement lacks distinct "
                           "counterparties or eligible custody");
  const auto price = market_prices_.at(e.escrow[1]);
  // Provisional compound order: receive first (including local cap/Dream),
  // debit and credit both wallets, then actual Sun/final-death/Bow reactions.
  receive_market_item(mutation, buyer);
  const auto payment = pay_cp_waterfall({mutation.statuses[buyer][0],
                                         mutation.resources[buyer][0],
                                         mutation.resources[buyer][1]},
                                        price);
  const auto credit = credit_cp_capped({mutation.statuses[seller][0],
                                        mutation.resources[seller][0],
                                        mutation.resources[seller][1]},
                                       price, resource_cap_);
  mutation.statuses[buyer][0] = payment.wallet.hp;
  mutation.resources[buyer] = {payment.wallet.mp, payment.wallet.cp};
  mutation.resources[seller][1] = credit.wallet.cp;
  e.market_stats[15] += payment.cp_debit;
  e.market_stats[16] += payment.mp_debit;
  e.market_stats[17] += payment.hp_debit;
  e.market_stats[18] += payment.unpaid;
  e.market_stats[19] += credit.credited;
  e.market_stats[20] += credit.capped;
  if (payment.hp_debit > 0 && payment.wallet.hp == 0)
    resolve_hp_zero(mutation, buyer, 3);
  guardian_damage(mutation, buyer, payment.hp_debit);
  complete_attack(mutation, 0);
  clear_market(mutation);
  resume_family(mutation);
}

void FullGameBatch::decide_purchase(Mutation &mutation, bool bought) const {
  auto &e = mutation.episode;
  if (e.active_family_kind != 7 || e.market_kind != 2 || e.trade_mode != 3 ||
      e.actor != e.damage_source || e.escrow[0] == 0)
    throw std::logic_error(
        "full-game purchase decision has no matching current buyer");
  if (bought) {
    ++e.market_stats[11];
    settle_market(mutation);
  } else {
    ++e.market_stats[12];
    restore_market_escrow(mutation);
    complete_attack(mutation, 0);
    clear_market(mutation);
    resume_family(mutation);
  }
}

void FullGameBatch::resolve_market(Mutation &mutation, bool blocked) const {
  auto &e = mutation.episode;
  if (blocked) {
    ++e.market_stats[7];
    restore_market_escrow(mutation);
    complete_attack(mutation, 0);
    clear_market(mutation);
    resume_family(mutation);
    return;
  }
  if (e.market_kind == 1) {
    ++e.market_stats[8];
    settle_market(mutation);
    return;
  }
  if (e.market_kind != 2)
    throw std::logic_error("full-game trade family has no market kind");
  auto &hand = stage_hand(mutation, static_cast<std::size_t>(e.target));
  std::vector<std::size_t> candidates;
  for (std::size_t slot = 0; slot < hand.size(); ++slot)
    if (hand[slot][3] == 0)
      candidates.push_back(slot);
  if (candidates.empty()) {
    ++e.market_stats[10];
    complete_attack(mutation, 0);
    clear_market(mutation);
    resume_family(mutation);
    return;
  }
  const auto slot = candidates[full_game_random::random_rank(
      e.market_offer_rng, candidates.size())];
  ++e.market_stats[9];
  ++e.market_stats[21];
  e.escrow = hand[slot];
  e.escrow_owner = e.target;
  hand.erase(hand.begin() + static_cast<std::ptrdiff_t>(slot));
  e.actor = e.damage_source;
  e.trade_mode = 3;
  e.phase = 6;
  e.selected_count = e.defense_actions = 0;
  mutation.selected.fill(0);
  mutation.order.fill(0);
  if ((e.forced_market && e.actor == e.turn_owner) ||
      e.actor == e.automatic_buyer) {
    ++e.market_stats[23];
    decide_purchase(
        mutation, full_game_random::random_rank(e.market_purchase_rng, 2) != 0);
  }
}

std::int64_t FullGameBatch::exchange_delta(const Episode &e,
                                           std::int64_t choice) const noexcept {
  if (choice < 1 || choice > 8)
    return 0;
  constexpr std::array<std::int64_t, 4> increments{10, 1, -1, -10};
  const auto increment = increments[static_cast<std::size_t>((choice - 1) % 4)];
  const auto axis = choice <= 4 ? 1 : 2;
  // Same clipped one-for-one arithmetic as the pinned client's +/-10/1
  // controls and the explicit client99 or legacy100 resource cap.
  if (increment > 0)
    return std::min(
        {increment, e.trade_wallet[0], resource_cap_ - e.trade_wallet[axis]});
  return -std::min(
      {-increment, e.trade_wallet[axis], resource_cap_ - e.trade_wallet[0]});
}

void FullGameBatch::begin_exchange(Mutation &mutation, std::size_t slot) const {
  auto &e = mutation.episode;
  const auto actor = static_cast<std::size_t>(e.actor);
  e.turn_owner = e.actor;
  e.attack_slot = static_cast<std::int64_t>(slot);
  e.trade_mode = 1;
  e.trade_actions = 0;
  e.trade_wallet = {mutation.statuses[actor][0], mutation.resources[actor][0],
                    mutation.resources[actor][1]};
  ++e.trade_stats[0];
  e.phase = 6;
  e.utility_selection = false;
  mutation.selected.fill(0);
  mutation.order.fill(0);
}

void FullGameBatch::execute_exchange(Mutation &mutation) const {
  if (resolve_hidden_trade(mutation, 0))
    return;
  auto &e = mutation.episode;
  const auto actor = static_cast<std::size_t>(e.actor);
  const auto owner = mutation.environment * player_count_ + actor;
  if (e.trade_mode != 1 || e.attack_slot < 0 ||
      static_cast<std::uint64_t>(e.attack_slot) >= inventory_.sizes_[owner] ||
      !exchange_models_.contains(
          inventory_.items_[owner * capacity_ + e.attack_slot][1]))
    throw std::invalid_argument(
        "full-game hidden actual Exchange role differs; cross-role resolution "
        "is not implemented");
  const auto wallet = e.trade_wallet;
  consume_slot(mutation, actor, static_cast<std::size_t>(e.attack_slot));
  settle_exchange(mutation, actor, wallet);
  e.trade_mode = e.trade_actions = 0;
  e.trade_wallet.fill(0);
  mutation.selected.fill(0);
  mutation.order.fill(0);
  finish_turn(mutation, actor);
}

void FullGameBatch::settle_exchange(
    Mutation &mutation, std::size_t actor,
    const std::array<std::int64_t, 3> &wallet) const {
  auto &e = mutation.episode;
  const auto before_hp = mutation.statuses[actor][0];
  const auto before_mp = mutation.resources[actor][0];
  const auto before_cp = mutation.resources[actor][1];
  if (std::any_of(
          wallet.begin(), wallet.end(),
          [this](auto value) { return value < 0 || value > resource_cap_; }) ||
      wallet[0] + wallet[1] + wallet[2] != before_hp + before_mp + before_cp)
    throw std::logic_error("full-game Exchange wallet conservation differs");
  mutation.statuses[actor][0] = wallet[0];
  mutation.resources[actor] = {wallet[1], wallet[2]};
  ++e.trade_stats[3];
  e.trade_stats[4] += std::max<std::int64_t>(0, wallet[1] - before_mp);
  e.trade_stats[5] += std::max<std::int64_t>(0, before_mp - wallet[1]);
  e.trade_stats[6] += std::max<std::int64_t>(0, wallet[2] - before_cp);
  e.trade_stats[7] += std::max<std::int64_t>(0, before_cp - wallet[2]);
  // Zero-HP conversion timing and Sun/Bow composition remain provisional.
  // This is not attack damage, payment-waterfall loss, or guardian departure.
  if (before_hp > 0 && mutation.statuses[actor][0] == 0)
    resolve_hp_zero(mutation, actor, 8);
}

void FullGameBatch::execute_forced_exchange(Mutation &mutation,
                                            std::size_t slot) const {
  begin_exchange(mutation, slot);
  auto &e = mutation.episode;
  e.trade_wallet = sample_exchange_wallet(
      mutation, static_cast<std::size_t>(e.actor), e.exchange_rng);
  ++e.trade_stats[8];
  ++e.trade_stats[9];
  execute_exchange(mutation);
}

std::array<std::int64_t, 3> FullGameBatch::sample_exchange_wallet(
    const Mutation &mutation, std::size_t actor, std::uint64_t &rng) const {
  const auto total = mutation.statuses[actor][0] +
                     mutation.resources[actor][0] +
                     mutation.resources[actor][1];
  std::uint64_t count = 0;
  // Bounded exact enumeration, not rejection sampling or a policy edit loop.
  // Uniform final allocations under confusion are explicitly provisional.
  for (std::int64_t mp = 0; mp <= resource_cap_; ++mp)
    for (std::int64_t cp = 0; cp <= resource_cap_; ++cp)
      count += total - mp - cp >= 0 && total - mp - cp <= resource_cap_ ? 1 : 0;
  auto rank = full_game_random::random_rank(rng, count);
  for (std::int64_t mp = 0; mp <= resource_cap_; ++mp)
    for (std::int64_t cp = 0; cp <= resource_cap_; ++cp) {
      const auto hp = total - mp - cp;
      if (hp >= 0 && hp <= resource_cap_) {
        if (rank == 0) {
          return {hp, mp, cp};
        }
        --rank;
      }
    }
  throw std::logic_error("full-game forced Exchange allocation is unreachable");
}

Int64_2D FullGameBatch::trade_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 7);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &e = episodes_[env];
    if (e.phase == 6 && e.trade_mode >= 1 && e.trade_mode <= 3) {
      const std::array<std::int64_t, 7> row{
          1,
          e.trade_mode,
          e.trade_mode == 1 ? e.trade_wallet[0] : 0,
          e.trade_mode == 1 ? e.trade_wallet[1] : 0,
          e.trade_mode == 1 ? e.trade_wallet[2] : 0,
          e.trade_mode == 3 ? 0 : e.trade_actions,
          e.trade_mode == 3 ? 0 : e.attack_slot + 1};
      std::copy(row.begin(), row.end(), buffer.get() + env * 7);
    }
  }
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return Int64_2D(data, {batch_size_, 7}, owner);
}

Int64_2D FullGameBatch::trade_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 10);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].trade_stats.begin(),
              episodes_[env].trade_stats.end(), buffer.get() + env * 10);
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return Int64_2D(data, {batch_size_, 10}, owner);
}

Int64_2D FullGameBatch::market_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 9);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &e = episodes_[env];
    if (e.market_kind == 0 || e.phase == 0 || e.phase >= 12)
      continue;
    const bool revealed = e.active_family_kind == 7;
    const auto stage = e.phase == 3        ? 2
                       : e.phase == 4      ? 3
                       : e.trade_mode == 2 ? 1
                                           : 4;
    const auto model = revealed && e.escrow[0] != 0 ? e.escrow[1] : 0;
    const std::array<std::int64_t, 9> row{1,
                                          e.market_kind,
                                          stage,
                                          revealed ? e.damage_source : e.actor,
                                          revealed ? e.target : -1,
                                          revealed ? 0 : e.sale_slot + 1,
                                          model,
                                          model != 0 ? market_prices_.at(model)
                                                     : 0,
                                          revealed ? 0 : e.trade_actions};
    std::copy(row.begin(), row.end(), buffer.get() + env * 9);
  }
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return Int64_2D(data, {batch_size_, 9}, owner);
}

Int64_2D FullGameBatch::market_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 25);
  for (std::size_t env = 0; env < batch_size_; ++env)
    std::copy(episodes_[env].market_stats.begin(),
              episodes_[env].market_stats.end(), buffer.get() + env * 25);
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return Int64_2D(data, {batch_size_, 25}, owner);
}

Int64_2D FullGameBatch::market_escrow_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 6);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &e = episodes_[env];
    if (e.escrow[0] == 0)
      continue;
    const std::array<std::int64_t, 6> row{
        e.escrow_owner, e.escrow[0], e.escrow[1], e.escrow[2], e.escrow[3], 1};
    std::copy(row.begin(), row.end(), buffer.get() + env * 6);
  }
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return Int64_2D(data, {batch_size_, 6}, owner);
}
} // namespace godfield_sim
