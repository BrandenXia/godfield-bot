#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <unordered_set>
#include <vector>

#include "ordered_inventory.h"

namespace godfield_sim {

inline constexpr std::uint32_t kProvisionalSoapSchemaVersion = 1;
inline constexpr const char *kProvisionalSoapRulesetId =
    "catalog-derived-selected-two-used-miracles-provisional-v1";

// A provisional item-effect primitive, deliberately separate from the
// observed ordered replay and from every trainable batch. The caller provides
// the selection; this class makes no claim about how the official game chooses
// which performed miracles are washed away.
class ProvisionalSoapProjection {
public:
  ProvisionalSoapProjection(InventoryInput initial_items,
                            ActionInput miracle_model_ids,
                            std::size_t capacity = kMaximumInventoryReplayItems);

  void wash_selected_two(InventoryInput expected_items);
  [[nodiscard]] Int64_2D snapshot() const;
  [[nodiscard]] std::size_t size() const noexcept { return items_.size(); }
  [[nodiscard]] std::uint64_t removed_item_count() const noexcept {
    return removed_item_count_;
  }

private:
  using Item = std::array<std::int64_t, 4>;
  static void validate_item(const Item &item);

  const std::size_t capacity_;
  std::vector<Item> items_;
  std::unordered_set<std::int64_t> miracle_models_;
  std::uint64_t removed_item_count_ = 0;
};

} // namespace godfield_sim
