#include "ordered_inventory.h"

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

void OrderedInventoryReplay::validate_item(const Item &item) {
  if (!positive_safe_integer(item[0]) || !positive_safe_integer(item[1]) ||
      item[2] < 0 || item[2] > kMaximumSafeInteger ||
      (item[3] != 0 && item[3] != 1)) {
    throw std::invalid_argument(
        "inventory requires positive safe instance/model IDs, a nonnegative "
        "safe fake-model ID, and a boolean used flag");
  }
}

OrderedInventoryReplay::OrderedInventoryReplay(
    InventoryInput initial_items, ActionInput ordinary_consumable_model_ids,
    std::size_t capacity)
    : capacity_(capacity) {
  if (capacity_ == 0 || capacity_ > kMaximumInventoryReplayItems) {
    throw std::invalid_argument("replay capacity must be between 1 and 512");
  }
  if (initial_items.shape(0) > capacity_) {
    throw std::invalid_argument("initial inventory exceeds replay capacity");
  }
  if (ordinary_consumable_model_ids.shape(0) > kMaximumInventoryReplayItems) {
    throw std::invalid_argument(
        "ordinary model allowlist exceeds replay bound");
  }
  for (std::size_t index = 0; index < ordinary_consumable_model_ids.shape(0);
       ++index) {
    const auto model_id = ordinary_consumable_model_ids(index);
    if (!positive_safe_integer(model_id) ||
        !ordinary_consumable_models_.insert(model_id).second) {
      throw std::invalid_argument(
          "ordinary model allowlist requires distinct positive safe IDs");
    }
  }
  items_.reserve(capacity_);
  std::unordered_set<std::int64_t> identities;
  for (std::size_t row = 0; row < initial_items.shape(0); ++row) {
    const Item item{initial_items(row, 0), initial_items(row, 1),
                    initial_items(row, 2), initial_items(row, 3)};
    validate_item(item);
    if (!identities.insert(item[0]).second) {
      throw std::invalid_argument("initial inventory contains duplicate IDs");
    }
    items_.push_back(item);
  }
}

void OrderedInventoryReplay::consume(InventoryInput expected_items) {
  if (expected_items.shape(0) > items_.size()) {
    throw std::invalid_argument("consumption exceeds owned inventory");
  }
  std::unordered_set<std::int64_t> selected;
  // Validate the entire selection before mutation; a late invalid item must
  // not partially consume earlier items or change counters.
  for (std::size_t row = 0; row < expected_items.shape(0); ++row) {
    const Item item{expected_items(row, 0), expected_items(row, 1),
                    expected_items(row, 2), expected_items(row, 3)};
    validate_item(item);
    if (!selected.insert(item[0]).second) {
      throw std::invalid_argument("consumption contains duplicate IDs");
    }
    if (item[2] != 0 || item[3] != 0 ||
        !ordinary_consumable_models_.contains(item[1])) {
      throw std::invalid_argument(
          "consumption requires an allowlisted unused undisguised ordinary "
          "artifact; miracles and other lifecycle effects are unsupported");
    }
    const auto owned = std::find_if(
        items_.begin(), items_.end(),
        [&item](const Item &candidate) { return candidate[0] == item[0]; });
    if (owned == items_.end() || *owned != item) {
      throw std::invalid_argument("consumed item differs from owned artifact");
    }
  }
  std::erase_if(items_, [&selected](const Item &item) {
    return selected.contains(item[0]);
  });
  consumed_item_count_ += static_cast<std::uint64_t>(selected.size());
  has_operations_ = true;
}

void OrderedInventoryReplay::gift(InventoryItemInput input) {
  const Item item{input(0), input(1), input(2), input(3)};
  validate_item(item);
  if (items_.size() == capacity_) {
    throw std::invalid_argument(
        "gift exceeds replay capacity; overflow removal is not inferred");
  }
  if (std::any_of(items_.begin(), items_.end(),
                  [&item](const Item &owned) { return owned[0] == item[0]; })) {
    throw std::invalid_argument("gift cannot overwrite an owned instance ID");
  }
  items_.push_back(item);
  ++gift_item_count_;
  has_operations_ = true;
}

void OrderedInventoryReplay::configure_retained_miracles(
    ActionInput model_ids) {
  if (retained_miracles_configured_ || has_operations_) {
    throw std::invalid_argument("retained miracle configuration requires an "
                                "unconfigured unstepped replay");
  }
  if (model_ids.shape(0) > kMaximumInventoryReplayItems) {
    throw std::invalid_argument(
        "retained miracle allowlist exceeds replay bound");
  }
  std::unordered_set<std::int64_t> models;
  for (std::size_t index = 0; index < model_ids.shape(0); ++index) {
    const auto model_id = model_ids(index);
    if (!positive_safe_integer(model_id) || !models.insert(model_id).second) {
      throw std::invalid_argument(
          "retained miracle allowlist requires distinct positive safe IDs");
    }
    if (ordinary_consumable_models_.contains(model_id)) {
      throw std::invalid_argument(
          "retained miracle and ordinary model allowlists must be disjoint");
    }
  }
  retained_miracle_models_ = std::move(models);
  retained_miracles_configured_ = true;
}

void OrderedInventoryReplay::perform_retained_miracle(
    InventoryItemInput input) {
  Item item{input(0), input(1), input(2), input(3)};
  validate_item(item);
  if (!retained_miracles_configured_ ||
      !retained_miracle_models_.contains(item[1]) || item[2] != 0) {
    throw std::invalid_argument(
        "retention requires a configured allowlisted undisguised miracle");
  }
  const auto owned = std::find_if(
      items_.begin(), items_.end(),
      [&item](const Item &candidate) { return candidate[0] == item[0]; });
  if (owned == items_.end() || *owned != item) {
    throw std::invalid_argument("retained miracle differs from owned artifact");
  }
  // This is an explicit, single-item inventory operation, NOT automatic
  // consumption dispatch or a claim about all official miracle combinations.
  // The witnessed Flame transitions retain the ID/model, mark it used, and
  // move it to the tail on both first use and reuse. MP/combat are untouched.
  item[3] = 1;
  items_.erase(owned);
  items_.push_back(item); // capacity was reserved; population is unchanged.
  ++retained_miracle_use_count_;
  has_operations_ = true;
}

Int64_2D OrderedInventoryReplay::snapshot() const {
  const auto count = items_.size() * 4;
  // Independently owned snapshots survive mutation, resizing, and destruction
  // of the replay object. Empty snapshots still have shape (0, 4).
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
