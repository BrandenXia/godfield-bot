#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

#include "provisional_guardian.h"

namespace godfield_sim {

inline constexpr std::uint32_t kGuardianLifecycleKernelSchemaVersion = 1;
inline constexpr std::uint32_t kGuardianLifecycleObservationSchemaVersion = 1;
inline constexpr const char *kGuardianLifecycleRulesetId =
    "caller-driven-guardian-lifecycle-provisional-v1";

using GuardianStateSnapshot =
    nb::ndarray<const std::int64_t, nb::numpy, nb::ndim<3>, nb::c_contig>;
using GuardianModelOutput =
    nb::ndarray<const std::int64_t, nb::numpy, nb::ndim<1>, nb::c_contig>;

// A separate, batched state container. Callers explicitly provide all
// lifecycle events; no official timing, summon policy, or attack resolution
// is implied. Empty slots have three zero fields: instance, owner, group.
class GuardianLifecycleBatch {
public:
  GuardianLifecycleBatch(std::size_t batch_size, std::size_t player_count,
                         std::size_t slots_per_environment,
                         GuardianWeightInput profiles);

  void summon(ActionInput environments, ActionInput slots,
              ActionInput instance_ids, ActionInput owners,
              ActionInput groups);
  void remove(ActionInput environments, ActionInput slots,
              ActionInput expected_instance_ids);
  void reset_environments(ActionInput environments);
  [[nodiscard]] GuardianModelOutput attack_models(
      ActionInput environments, ActionInput slots,
      ActionInput expected_instance_ids, ActionInput tickets) const;
  [[nodiscard]] GuardianStateSnapshot snapshot() const;
  [[nodiscard]] std::int64_t owner_for(std::int64_t environment,
                                      std::int64_t slot,
                                      std::int64_t expected_instance_id) const;
  [[nodiscard]] std::int64_t attack_model_for(
      std::int64_t environment, std::int64_t slot,
      std::int64_t expected_instance_id, std::int64_t ticket) const;

  [[nodiscard]] std::size_t batch_size() const noexcept { return batch_size_; }
  [[nodiscard]] std::size_t player_count() const noexcept { return player_count_; }
  [[nodiscard]] std::size_t slots_per_environment() const noexcept {
    return slots_per_environment_;
  }
  [[nodiscard]] std::size_t active_count() const noexcept { return active_count_; }
  [[nodiscard]] std::uint64_t summon_count() const noexcept {
    return summon_count_;
  }
  [[nodiscard]] std::uint64_t removal_count() const noexcept {
    return removal_count_;
  }
  [[nodiscard]] std::uint64_t reset_count() const noexcept { return reset_count_; }

private:
  using Slot = std::array<std::int64_t, 3>;
  [[nodiscard]] std::size_t checked_index(std::int64_t environment,
                                          std::int64_t slot) const;
  static void require_same_length(std::size_t expected, ActionInput input);

  const std::size_t batch_size_;
  const std::size_t player_count_;
  const std::size_t slots_per_environment_;
  const ProvisionalGuardianPicker picker_;
  std::vector<Slot> state_;
  std::size_t active_count_ = 0;
  std::uint64_t summon_count_ = 0;
  std::uint64_t removal_count_ = 0;
  std::uint64_t reset_count_ = 0;
};

} // namespace godfield_sim
