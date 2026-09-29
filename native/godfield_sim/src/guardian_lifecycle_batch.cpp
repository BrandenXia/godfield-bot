#include "guardian_lifecycle_batch.h"

#include <algorithm>
#include <memory>
#include <set>
#include <stdexcept>
#include <utility>

namespace godfield_sim {

namespace {
constexpr std::size_t kMaximumPlayers = 9;
constexpr std::size_t kMaximumSlotsPerEnvironment = 64;
constexpr std::size_t kMaximumTotalSlots = 2000000;
constexpr std::int64_t kMaximumSafeInteger = 9007199254740991LL;
} // namespace

GuardianLifecycleBatch::GuardianLifecycleBatch(
    std::size_t batch_size, std::size_t player_count,
    std::size_t slots_per_environment, GuardianWeightInput profiles)
    : batch_size_(batch_size), player_count_(player_count),
      slots_per_environment_(slots_per_environment), picker_(profiles) {
  if (batch_size_ == 0 || player_count_ < 2 ||
      player_count_ > kMaximumPlayers || slots_per_environment_ == 0 ||
      slots_per_environment_ > kMaximumSlotsPerEnvironment ||
      batch_size_ > kMaximumTotalSlots / slots_per_environment_) {
    throw std::invalid_argument("guardian batch dimensions exceed bounded capacity");
  }
  state_.resize(batch_size_ * slots_per_environment_, Slot{0, 0, 0});
}

void GuardianLifecycleBatch::require_same_length(std::size_t expected,
                                                 ActionInput input) {
  if (input.shape(0) != expected) {
    throw std::invalid_argument("guardian batch input lengths differ");
  }
}

std::size_t GuardianLifecycleBatch::checked_index(
    std::int64_t environment, std::int64_t slot) const {
  if (environment < 0 || static_cast<std::uint64_t>(environment) >= batch_size_ ||
      slot < 0 || static_cast<std::uint64_t>(slot) >= slots_per_environment_) {
    throw std::invalid_argument("guardian environment or slot is out of range");
  }
  return static_cast<std::size_t>(environment) * slots_per_environment_ +
         static_cast<std::size_t>(slot);
}

void GuardianLifecycleBatch::summon(ActionInput environments, ActionInput slots,
                                    ActionInput instance_ids,
                                    ActionInput owners, ActionInput groups) {
  const auto count = environments.shape(0);
  require_same_length(count, slots);
  require_same_length(count, instance_ids);
  require_same_length(count, owners);
  require_same_length(count, groups);
  std::set<std::size_t> targets;
  std::set<std::pair<std::int64_t, std::int64_t>> instances;
  for (std::size_t row = 0; row < count; ++row) {
    const auto environment = environments(row);
    const auto index = checked_index(environment, slots(row));
    const auto instance_id = instance_ids(row);
    if (state_[index][0] != 0 || !targets.insert(index).second ||
        instance_id <= 0 || instance_id > kMaximumSafeInteger ||
        owners(row) < 0 || static_cast<std::uint64_t>(owners(row)) >= player_count_ ||
        !instances.insert({environment, instance_id}).second) {
      throw std::invalid_argument("guardian summon has occupied, duplicate, or invalid state");
    }
    (void)picker_.total_weight(groups(row));
    const auto begin = static_cast<std::size_t>(environment) * slots_per_environment_;
    for (std::size_t slot = 0; slot < slots_per_environment_; ++slot) {
      if (state_[begin + slot][0] == instance_id) {
        throw std::invalid_argument("guardian instance already exists in environment");
      }
    }
  }
  for (std::size_t row = 0; row < count; ++row) {
    state_[checked_index(environments(row), slots(row))] = {
        instance_ids(row), owners(row), groups(row)};
  }
  active_count_ += count;
  summon_count_ += count;
}

void GuardianLifecycleBatch::remove(ActionInput environments, ActionInput slots,
                                    ActionInput expected_instance_ids) {
  const auto count = environments.shape(0);
  require_same_length(count, slots);
  require_same_length(count, expected_instance_ids);
  std::set<std::size_t> targets;
  for (std::size_t row = 0; row < count; ++row) {
    const auto index = checked_index(environments(row), slots(row));
    if (!targets.insert(index).second || expected_instance_ids(row) <= 0 ||
        state_[index][0] != expected_instance_ids(row)) {
      throw std::invalid_argument("guardian removal differs from active instance");
    }
  }
  for (const auto index : targets) {
    state_[index] = {0, 0, 0};
  }
  active_count_ -= count;
  removal_count_ += count;
}

void GuardianLifecycleBatch::reset_environments(ActionInput environments) {
  std::set<std::int64_t> targets;
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    const auto environment = environments(row);
    (void)checked_index(environment, 0);
    if (!targets.insert(environment).second) {
      throw std::invalid_argument("guardian reset lists duplicate environments");
    }
  }
  for (const auto environment : targets) {
    const auto begin = static_cast<std::size_t>(environment) * slots_per_environment_;
    for (std::size_t slot = 0; slot < slots_per_environment_; ++slot) {
      auto &entry = state_[begin + slot];
      if (entry[0] != 0) {
        --active_count_;
      }
      entry = {0, 0, 0};
    }
  }
  reset_count_ += targets.size();
}

GuardianModelOutput GuardianLifecycleBatch::attack_models(
    ActionInput environments, ActionInput slots,
    ActionInput expected_instance_ids, ActionInput tickets) const {
  const auto count = environments.shape(0);
  require_same_length(count, slots);
  require_same_length(count, expected_instance_ids);
  require_same_length(count, tickets);
  auto buffer = std::make_unique<std::int64_t[]>(std::max<std::size_t>(count, 1));
  for (std::size_t row = 0; row < count; ++row) {
    const auto index = checked_index(environments(row), slots(row));
    const auto &entry = state_[index];
    if (expected_instance_ids(row) <= 0 ||
        entry[0] != expected_instance_ids(row)) {
      throw std::invalid_argument("guardian attack differs from active instance");
    }
    buffer[row] = picker_.model_for_ticket(entry[2], tickets(row));
  }
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return GuardianModelOutput(data, {count}, owner);
}

GuardianStateSnapshot GuardianLifecycleBatch::snapshot() const {
  const auto count = state_.size() * 3;
  auto buffer = std::make_unique<std::int64_t[]>(std::max<std::size_t>(count, 1));
  for (std::size_t index = 0; index < state_.size(); ++index) {
    std::copy(state_[index].begin(), state_[index].end(), buffer.get() + index * 3);
  }
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return GuardianStateSnapshot(data, {batch_size_, slots_per_environment_, 3}, owner);
}

} // namespace godfield_sim
