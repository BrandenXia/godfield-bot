#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <unordered_set>
#include <vector>

#include "batch_types.h"

namespace godfield_sim {

inline constexpr std::uint32_t kOrderedInventoryReplaySchemaVersion = 2;
inline constexpr const char *kOrderedInventoryReplayRulesetId =
    "explicit-ordinary-and-retained-miracle-ordered-gift-replay-v2";
// A replay resource bound, NOT an asserted official hand limit.
inline constexpr std::size_t kMaximumInventoryReplayItems = 512;

using InventoryInput =
    nb::ndarray<const std::int64_t, nb::numpy, nb::shape<-1, 4>, nb::c_contig,
                nb::device::cpu>;
using InventoryItemInput =
    nb::ndarray<const std::int64_t, nb::numpy, nb::shape<4>, nb::c_contig,
                nb::device::cpu>;

// Diagnostic building block, not a selectable training curriculum. Each row
// is [instance_id, model_id, fake_model_id, used]. Inputs must already have
// verified self ownership, pinned-client defaults, and catalog provenance.
class OrderedInventoryReplay {
public:
  OrderedInventoryReplay(InventoryInput initial_items,
                         ActionInput ordinary_consumable_model_ids,
                         std::size_t capacity = kMaximumInventoryReplayItems);

  void consume(InventoryInput expected_items);
  void gift(InventoryItemInput item);
  void configure_retained_miracles(ActionInput model_ids);
  void perform_retained_miracle(InventoryItemInput expected_item);
  [[nodiscard]] Int64_2D snapshot() const;
  [[nodiscard]] std::size_t size() const noexcept { return items_.size(); }
  [[nodiscard]] std::size_t capacity() const noexcept { return capacity_; }
  [[nodiscard]] std::uint64_t consumed_item_count() const noexcept {
    return consumed_item_count_;
  }
  [[nodiscard]] std::uint64_t gift_item_count() const noexcept {
    return gift_item_count_;
  }
  [[nodiscard]] bool retained_miracles_configured() const noexcept {
    return retained_miracles_configured_;
  }
  [[nodiscard]] std::uint64_t retained_miracle_use_count() const noexcept {
    return retained_miracle_use_count_;
  }

private:
  using Item = std::array<std::int64_t, 4>;
  static void validate_item(const Item &item);

  const std::size_t capacity_;
  std::vector<Item> items_;
  std::unordered_set<std::int64_t> ordinary_consumable_models_;
  std::unordered_set<std::int64_t> retained_miracle_models_;
  bool retained_miracles_configured_ = false;
  bool has_operations_ = false;
  std::uint64_t consumed_item_count_ = 0;
  std::uint64_t gift_item_count_ = 0;
  std::uint64_t retained_miracle_use_count_ = 0;
};

} // namespace godfield_sim
