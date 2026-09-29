#include "provisional_guardian.h"

#include <stdexcept>
#include <unordered_set>

namespace godfield_sim {

namespace {
constexpr std::int64_t kMaximumSafeInteger = 9007199254740991LL;
constexpr std::size_t kMaximumProfiles = 512;
constexpr std::int64_t kMaximumGroup = 31;
} // namespace

ProvisionalGuardianPicker::ProvisionalGuardianPicker(GuardianWeightInput profiles) {
  if (profiles.shape(1) != 3 || profiles.shape(0) == 0 ||
      profiles.shape(0) > kMaximumProfiles) {
    throw std::invalid_argument(
        "provisional guardian profiles require 1..512 rows of group/model/weight");
  }
  std::unordered_set<std::int64_t> models;
  for (std::size_t row = 0; row < profiles.shape(0); ++row) {
    const auto group = profiles(row, 0);
    const auto model_id = profiles(row, 1);
    const auto weight = profiles(row, 2);
    if (group < 0 || group > kMaximumGroup || model_id <= 0 ||
        model_id > kMaximumSafeInteger || weight <= 0 ||
        weight > kMaximumSafeInteger) {
      throw std::invalid_argument(
          "provisional guardian profile requires bounded group, safe model ID, "
          "and positive safe weight");
    }
    if (!models.insert(model_id).second) {
      throw std::invalid_argument("provisional guardian model IDs must be distinct");
    }
    auto &entries = groups_[group];
    const auto previous = entries.empty() ? 0 : entries.back().cumulative_weight;
    if (weight > kMaximumSafeInteger - previous) {
      throw std::invalid_argument("provisional guardian group weight overflow");
    }
    entries.push_back({model_id, previous + weight});
    ++profile_count_;
  }
}

std::int64_t ProvisionalGuardianPicker::total_weight(std::int64_t group) const {
  const auto found = groups_.find(group);
  if (found == groups_.end()) {
    throw std::invalid_argument("unknown provisional guardian group");
  }
  return found->second.back().cumulative_weight;
}

std::int64_t ProvisionalGuardianPicker::model_for_ticket(
    std::int64_t group, std::int64_t ticket) const {
  const auto found = groups_.find(group);
  if (found == groups_.end()) {
    throw std::invalid_argument("unknown provisional guardian group");
  }
  const auto &entries = found->second;
  if (ticket < 0 || ticket >= entries.back().cumulative_weight) {
    throw std::invalid_argument("provisional guardian ticket is out of range");
  }
  for (const auto &entry : entries) {
    if (ticket < entry.cumulative_weight) {
      return entry.model_id;
    }
  }
  throw std::logic_error("provisional guardian ticket lookup failed");
}

} // namespace godfield_sim
