#include "guardian_combat_batch.h"

#include <algorithm>
#include <memory>
#include <set>
#include <stdexcept>

namespace godfield_sim {
namespace {
bool compatible(std::int64_t attack, std::int64_t defense) {
  if (attack == 5)
    return false;
  if (attack == 1)
    return defense == 2 || defense == 5;
  if (attack == 2)
    return defense == 1 || defense == 5;
  if (attack == 3)
    return defense == 4 || defense == 5;
  if (attack == 4)
    return defense == 3 || defense == 5;
  return true;
}
Int64_2D copied_matrix(const std::int64_t *source, std::size_t rows,
                       std::size_t columns) {
  const auto count = rows * columns;
  auto buffer =
      std::make_unique<std::int64_t[]>(std::max<std::size_t>(count, 1));
  std::copy_n(source, count, buffer.get());
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return Int64_2D(data, {rows, columns}, owner);
}
} // namespace

GuardianCombatBatch::GuardianCombatBatch(
    std::size_t batch_size, std::size_t player_count,
    std::size_t slots_per_environment, GuardianWeightInput weighted_profiles,
    GuardianWeightInput basic_attack_profiles, std::uint16_t initial_hp,
    std::uint16_t initial_mp, std::uint16_t initial_cp)
    : batch_size_(batch_size), player_count_(player_count),
      initial_hp_(initial_hp), initial_mp_(initial_mp), initial_cp_(initial_cp),
      guardians_(batch_size, player_count, slots_per_environment,
                 weighted_profiles) {
  const auto width = basic_attack_profiles.shape(1);
  if (initial_hp == 0 || initial_hp > 100 || initial_mp > 100 ||
      initial_cp > 100 || (width != 4 && width != 7) ||
      basic_attack_profiles.shape(0) == 0 ||
      basic_attack_profiles.shape(0) > 512) {
    throw std::invalid_argument("invalid basic guardian combat configuration");
  }
  std::set<std::int64_t> weighted_models;
  for (std::size_t row = 0; row < weighted_profiles.shape(0); ++row) {
    weighted_models.insert(weighted_profiles(row, 1));
  }
  for (std::size_t row = 0; row < basic_attack_profiles.shape(0); ++row) {
    const auto model = basic_attack_profiles(row, 0);
    const auto value = basic_attack_profiles(row, 1);
    const auto element = basic_attack_profiles(row, 2);
    const auto rate = basic_attack_profiles(row, 3);
    const auto effect = width == 7 ? basic_attack_profiles(row, 4) : 0;
    const auto utility = width == 7 ? basic_attack_profiles(row, 5) : 0;
    const auto curse = width == 7 ? basic_attack_profiles(row, 6) : 0;
    if (!weighted_models.contains(model) || attacks_.contains(model) ||
        value < 0 || value > 65535 || element < 0 || element > 6 || rate <= 0 ||
        rate > 100 || effect < 0 || effect > 10 || utility < 0 ||
        utility > 100 || (effect <= 2 && value == 0) ||
        (effect >= 3 && value != 0) || ((effect >= 5) != (utility > 0)) ||
        ((effect == 2 || effect == 3)
             ? (curse != 1 && curse != 2 && curse != 4 && curse != 8)
             : curse != 0)) {
      throw std::invalid_argument(
          "invalid or duplicate basic guardian attack profile");
    }
    attacks_.emplace(model,
                     BasicAttack{value, element, rate, effect, utility, curse});
  }
  hp_.assign(batch_size_ * player_count_, initial_hp_);
  mp_.assign(batch_size_ * player_count_, initial_mp_);
  cp_.assign(batch_size_ * player_count_, initial_cp_);
  curses_.assign(batch_size_ * player_count_, 0);
  pending_.resize(batch_size_, Pending{0, 0, 0, 0, 0, 0, 0});
}

void GuardianCombatBatch::same_length(std::size_t expected, ActionInput input) {
  if (input.shape(0) != expected) {
    throw std::invalid_argument("guardian combat input lengths differ");
  }
}
std::size_t
GuardianCombatBatch::checked_environment(std::int64_t environment) const {
  if (environment < 0 ||
      static_cast<std::uint64_t>(environment) >= batch_size_) {
    throw std::invalid_argument("guardian combat environment is out of range");
  }
  return static_cast<std::size_t>(environment);
}
void GuardianCombatBatch::require_idle(ActionInput environments) const {
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    if (pending_[checked_environment(environments(row))][0] != 0) {
      throw std::invalid_argument("guardian combat environment awaits defense");
    }
  }
}
void GuardianCombatBatch::summon(ActionInput environments, ActionInput slots,
                                 ActionInput instances, ActionInput owners,
                                 ActionInput groups) {
  require_idle(environments);
  guardians_.summon(environments, slots, instances, owners, groups);
}
void GuardianCombatBatch::remove(ActionInput environments, ActionInput slots,
                                 ActionInput instances) {
  require_idle(environments);
  guardians_.remove(environments, slots, instances);
}
void GuardianCombatBatch::reset_environments(ActionInput environments) {
  // Lifecycle reset validates every target before any game state is changed.
  guardians_.reset_environments(environments);
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    const auto environment = checked_environment(environments(row));
    std::fill_n(hp_.begin() + environment * player_count_, player_count_,
                initial_hp_);
    std::fill_n(mp_.begin() + environment * player_count_, player_count_,
                initial_mp_);
    std::fill_n(cp_.begin() + environment * player_count_, player_count_,
                initial_cp_);
    std::fill_n(curses_.begin() + environment * player_count_, player_count_,
                0);
    pending_[environment] = {0, 0, 0, 0, 0, 0, 0};
  }
}

void GuardianCombatBatch::begin_attacks(ActionInput environments,
                                        ActionInput slots,
                                        ActionInput instances,
                                        ActionInput targets,
                                        ActionInput selection_tickets,
                                        ActionInput hit_tickets) {
  const auto count = environments.shape(0);
  same_length(count, slots);
  same_length(count, instances);
  same_length(count, targets);
  same_length(count, selection_tickets);
  same_length(count, hit_tickets);
  require_idle(environments);
  std::set<std::size_t> seen;
  std::vector<Pending> next;
  next.reserve(count);
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = checked_environment(environments(row));
    const auto owner =
        guardians_.owner_for(environments(row), slots(row), instances(row));
    const auto target = targets(row);
    const auto hit_ticket = hit_tickets(row);
    if (!seen.insert(environment).second || target < 0 ||
        static_cast<std::uint64_t>(target) >= player_count_ ||
        hp_[environment * player_count_ + owner] == 0 ||
        hp_[environment * player_count_ + target] == 0 || hit_ticket < 0 ||
        hit_ticket >= 100) {
      throw std::invalid_argument(
          "invalid guardian combat target, ticket, or duplicate event");
    }
    const auto model = guardians_.attack_model_for(
        environments(row), slots(row), instances(row), selection_tickets(row));
    const auto found = attacks_.find(model);
    if (found == attacks_.end()) {
      throw std::invalid_argument(
          "selected guardian effect is unsupported by basic combat");
    }
    const auto &attack = found->second;
    const auto self_effect = attack.effect >= 4 && attack.effect <= 8;
    if ((self_effect && target != owner) || (!self_effect && target == owner)) {
      throw std::invalid_argument(
          "guardian effect target does not match its role");
    }
    const auto hit = hit_ticket < attack.hit_rate;
    next.push_back({attack.effect <= 2 ? 1 : 0, model, owner, target,
                    hit_ticket < attack.hit_rate ? attack.value : 0,
                    attack.element, 0, hit ? attack.effect : -1, attack.utility,
                    attack.curse});
  }
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = checked_environment(environments(row));
    const auto &effect = next[row];
    const auto owner_offset = environment * player_count_ + effect[2];
    const auto target_offset = environment * player_count_ + effect[3];
    if (effect[0] == 0) {
      if (effect[7] == 3)
        curses_[target_offset] |= effect[9];
      if (effect[7] == 4)
        curses_[owner_offset] = 0;
      if (effect[7] == 5)
        hp_[owner_offset] =
            std::min<std::int64_t>(100, hp_[owner_offset] + effect[8]);
      if (effect[7] == 6)
        mp_[owner_offset] =
            std::min<std::int64_t>(100, mp_[owner_offset] + effect[8]);
      if (effect[7] == 7)
        cp_[owner_offset] =
            std::min<std::int64_t>(100, cp_[owner_offset] + effect[8]);
      if (effect[7] == 8) {
        for (std::size_t player = 0; player < player_count_; ++player) {
          const auto offset = environment * player_count_ + player;
          if (hp_[offset] > 0)
            cp_[offset] = std::min<std::int64_t>(100, cp_[offset] + effect[8]);
        }
      }
      if (effect[7] == 9)
        cp_[target_offset] =
            std::min<std::int64_t>(100, cp_[target_offset] + effect[8]);
      if (effect[7] == 10) {
        const auto transfer =
            std::min({effect[8], cp_[target_offset], 100 - cp_[owner_offset]});
        cp_[target_offset] -= transfer;
        cp_[owner_offset] += transfer;
      }
      ++resolved_effect_count_;
    }
    pending_[environment] = effect;
  }
}

void GuardianCombatBatch::resolve_defenses(ActionInput environments,
                                           ActionInput defense_values,
                                           ActionInput defense_elements) {
  const auto count = environments.shape(0);
  same_length(count, defense_values);
  same_length(count, defense_elements);
  std::set<std::size_t> seen;
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = checked_environment(environments(row));
    const auto &pending = pending_[environment];
    const auto defense = defense_values(row);
    const auto element = defense_elements(row);
    if (!seen.insert(environment).second || pending[0] != 1 || defense < 0 ||
        defense > 65535 || element < 0 || element > 6 ||
        (defense > 0 && !compatible(pending[5], element))) {
      throw std::invalid_argument(
          "invalid guardian defense phase, value, or element");
    }
  }
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = checked_environment(environments(row));
    auto &pending = pending_[environment];
    auto &hp = hp_[environment * player_count_ + pending[3]];
    auto damage = std::max<std::int64_t>(0, pending[4] - defense_values(row));
    if (pending[5] == 6 && damage > 0)
      damage = hp;
    damage = std::min(hp, damage);
    hp -= damage;
    const auto owner_offset = environment * player_count_ + pending[2];
    const auto target_offset = environment * player_count_ + pending[3];
    if (pending[7] == 1)
      hp_[owner_offset] =
          std::min<std::int64_t>(100, hp_[owner_offset] + damage);
    if (pending[7] == 2 && damage > 0 && hp > 0)
      curses_[target_offset] |= pending[9];
    pending[0] = 0;
    pending[6] = damage;
  }
  resolved_attack_count_ += count;
  resolved_effect_count_ += count;
}

Int64_2D GuardianCombatBatch::hp_snapshot() const {
  return copied_matrix(hp_.data(), batch_size_, player_count_);
}
Int64_2D GuardianCombatBatch::combat_snapshot() const {
  std::vector<std::int64_t> flat;
  flat.reserve(batch_size_ * 10);
  for (const auto &pending : pending_)
    flat.insert(flat.end(), pending.begin(), pending.end());
  return copied_matrix(flat.data(), batch_size_, 10);
}

GuardianStateSnapshot GuardianCombatBatch::resource_snapshot() const {
  auto buffer =
      std::make_unique<std::int64_t[]>(batch_size_ * player_count_ * 4);
  for (std::size_t offset = 0; offset < hp_.size(); ++offset) {
    buffer[offset * 4] = hp_[offset];
    buffer[offset * 4 + 1] = mp_[offset];
    buffer[offset * 4 + 2] = cp_[offset];
    buffer[offset * 4 + 3] = curses_[offset];
  }
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return GuardianStateSnapshot(data, {batch_size_, player_count_, 4}, owner);
}
} // namespace godfield_sim
