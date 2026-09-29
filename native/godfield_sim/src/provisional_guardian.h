#pragma once

#include <cstddef>
#include <cstdint>
#include <unordered_map>
#include <vector>

#include "batch_types.h"

namespace godfield_sim {

inline constexpr std::uint32_t kProvisionalGuardianSchemaVersion = 1;
inline constexpr const char *kProvisionalGuardianRulesetId =
    "catalog-derived-guardian-weight-ticket-provisional-v1";

using GuardianWeightInput =
    nb::ndarray<const std::int64_t, nb::numpy, nb::ndim<2>, nb::c_contig,
                nb::device::cpu>;

// Maps a caller-supplied weight ticket to an attack model. This is a catalog
// hypothesis only: it neither decides when a guardian acts nor resolves the
// attack. Supplying the ticket keeps random-number policy outside this class.
class ProvisionalGuardianPicker {
public:
  explicit ProvisionalGuardianPicker(GuardianWeightInput profiles);

  [[nodiscard]] std::int64_t model_for_ticket(std::int64_t group,
                                               std::int64_t ticket) const;
  [[nodiscard]] std::int64_t total_weight(std::int64_t group) const;
  [[nodiscard]] std::size_t profile_count() const noexcept {
    return profile_count_;
  }
  [[nodiscard]] std::size_t group_count() const noexcept {
    return groups_.size();
  }

private:
  struct Profile {
    std::int64_t model_id;
    std::int64_t cumulative_weight;
  };
  std::unordered_map<std::int64_t, std::vector<Profile>> groups_;
  std::size_t profile_count_ = 0;
};

} // namespace godfield_sim
