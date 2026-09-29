#include "provisional_soap.h"

#include <algorithm>
#include <memory>
#include <stdexcept>

namespace godfield_sim {

namespace {
constexpr std::int64_t kMaximumSafeInteger = 9007199254740991LL;

bool positive_safe_integer(std::int64_t value) noexcept {
  return value > 0 && value <= kMaximumSafeInteger;
}
} // namespace

void ProvisionalSoapProjection::validate_item(const Item &item) {
  if (!positive_safe_integer(item[0]) || !positive_safe_integer(item[1]) ||
      item[2] < 0 || item[2] > kMaximumSafeInteger ||
      (item[3] != 0 && item[3] != 1)) {
    throw std::invalid_argument(
        "provisional Soap requires safe instance/model IDs, a nonnegative "
        "safe fake-model ID, and a boolean used flag");
  }
}

ProvisionalSoapProjection::ProvisionalSoapProjection(
    InventoryInput initial_items, ActionInput miracle_model_ids,
    std::size_t capacity)
    : capacity_(capacity) {
  if (capacity_ == 0 || capacity_ > kMaximumInventoryReplayItems ||
      initial_items.shape(0) > capacity_) {
    throw std::invalid_argument("provisional Soap inventory exceeds capacity");
  }
  if (miracle_model_ids.shape(0) == 0 ||
      miracle_model_ids.shape(0) > kMaximumInventoryReplayItems) {
    throw std::invalid_argument("provisional Soap requires a bounded miracle allowlist");
  }
  for (std::size_t index = 0; index < miracle_model_ids.shape(0); ++index) {
    const auto model_id = miracle_model_ids(index);
    if (!positive_safe_integer(model_id) ||
        !miracle_models_.insert(model_id).second) {
      throw std::invalid_argument(
          "provisional Soap miracle allowlist requires distinct safe IDs");
    }
  }
  items_.reserve(capacity_);
  std::unordered_set<std::int64_t> identities;
  for (std::size_t row = 0; row < initial_items.shape(0); ++row) {
    const Item item{initial_items(row, 0), initial_items(row, 1),
                    initial_items(row, 2), initial_items(row, 3)};
    validate_item(item);
    if (!identities.insert(item[0]).second) {
      throw std::invalid_argument("provisional Soap inventory contains duplicate IDs");
    }
    items_.push_back(item);
  }
}

void ProvisionalSoapProjection::wash_selected_two(
    InventoryInput expected_items) {
  if (expected_items.shape(0) != 2 || items_.size() < 2) {
    throw std::invalid_argument("provisional Soap requires exactly two owned miracles");
  }
  std::unordered_set<std::int64_t> selected;
  // Validate the complete explicit selection before mutating inventory.
  for (std::size_t row = 0; row < expected_items.shape(0); ++row) {
    const Item item{expected_items(row, 0), expected_items(row, 1),
                    expected_items(row, 2), expected_items(row, 3)};
    validate_item(item);
    if (!selected.insert(item[0]).second) {
      throw std::invalid_argument("provisional Soap selection contains duplicate IDs");
    }
    if (item[2] != 0 || item[3] != 1 ||
        !miracle_models_.contains(item[1])) {
      throw std::invalid_argument(
          "provisional Soap requires used undisguised catalog miracles");
    }
    const auto owned = std::find_if(
        items_.begin(), items_.end(),
        [&item](const Item &candidate) { return candidate[0] == item[0]; });
    if (owned == items_.end() || *owned != item) {
      throw std::invalid_argument("washed miracle differs from owned item");
    }
  }
  std::erase_if(items_, [&selected](const Item &item) {
    return selected.contains(item[0]);
  });
  removed_item_count_ += 2;
}

Int64_2D ProvisionalSoapProjection::snapshot() const {
  const auto count = items_.size() * 4;
  auto buffer =
      std::make_unique<std::int64_t[]>(std::max<std::size_t>(count, 1));
  for (std::size_t row = 0; row < items_.size(); ++row) {
    std::copy(items_[row].begin(), items_[row].end(), buffer.get() + row * 4);
  }
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return Int64_2D(data, {items_.size(), 4}, owner);
}

} // namespace godfield_sim
