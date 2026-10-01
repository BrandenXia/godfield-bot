#pragma once

#include <array>
#include <map>
#include <vector>

#include "ordered_inventory.h"

namespace godfield_sim {

inline constexpr std::uint32_t kDreamInventorySchemaVersion = 1;
inline constexpr const char *kDreamInventoryRulesetId =
    "caller-driven-ordered-dream-inventory-provisional-v1";
using InventoryProfileInput =
    nb::ndarray<const std::int64_t, nb::numpy, nb::shape<-1, 2>, nb::c_contig,
                nb::device::cpu>;
using InventorySnapshot =
    nb::ndarray<const std::int64_t, nb::numpy, nb::ndim<4>, nb::c_contig>;
using ActorInventorySnapshot =
    nb::ndarray<const std::int64_t, nb::numpy, nb::ndim<3>, nb::c_contig>;
void bind_dream_inventory(nb::module_ &module);

// Portable trusted-scheduler storage, NOT a battle environment. No cost,
// phase, effect, gift cadence, overflow resolution, or team legality is
// inferred.
class DreamInventoryBatch {
public:
  DreamInventoryBatch(std::size_t batch_size, std::size_t player_count,
                      InventoryProfileInput profiles,
                      std::size_t capacity = kMaximumInventoryReplayItems);
  void seed_hand(std::size_t environment, std::size_t owner,
                 InventoryInput items);
  void add_cards(ActionInput environments, ActionInput owners,
                 ActionInput instance_ids, ActionInput model_ids,
                 ActionInput curse_masks, ActionInput disguise_tickets,
                 ActionInput fake_tickets);
  // Exact trusted rows are stale-state tokens, never inputs from a policy.
  void use_cards(ActionInput environments, ActionInput owners,
                 InventoryInput expected_items);
  void remove_cards(ActionInput environments, ActionInput owners,
                    InventoryInput expected_items);
  void restore_displays(ActionInput environments, ActionInput owners);
  void reset_environments(ActionInput environments);
  [[nodiscard]] InventorySnapshot snapshot() const;
  [[nodiscard]] ActorInventorySnapshot actor_hands(ActionInput environments,
                                                   ActionInput actors) const;
  [[nodiscard]] std::size_t capacity() const noexcept { return capacity_; }
  [[nodiscard]] std::uint64_t gift_count() const noexcept {
    return gift_count_;
  }
  [[nodiscard]] std::uint64_t consumed_count() const noexcept {
    return consumed_count_;
  }
  [[nodiscard]] std::uint64_t miracle_use_count() const noexcept {
    return miracle_use_count_;
  }
  [[nodiscard]] std::uint64_t removal_count() const noexcept {
    return removal_count_;
  }
  [[nodiscard]] std::uint64_t restored_count() const noexcept {
    return restored_count_;
  }

private:
  using Item = std::array<std::int64_t, 4>;
  [[nodiscard]] std::size_t checked_owner(std::int64_t environment,
                                          std::int64_t owner) const;
  [[nodiscard]] std::vector<std::size_t>
  checked_owners(ActionInput environments, ActionInput owners,
                 bool unique = false) const;
  static void same_length(std::size_t expected, ActionInput input);
  [[nodiscard]] std::int64_t category(std::int64_t model) const;
  void validate_item(const Item &item) const;
  [[nodiscard]] bool has_instance(std::size_t environment, std::int64_t id,
                                  std::size_t excluded_owner) const noexcept;
  [[nodiscard]] Item item_at(InventoryInput items, std::size_t row) const;
  void selected_operation(ActionInput environments, ActionInput owners,
                          InventoryInput expected_items, bool use);
  void commit_hand(std::size_t owner, const std::vector<Item> &items) noexcept;
  const std::size_t batch_size_;
  const std::size_t player_count_;
  const std::size_t capacity_;
  std::map<std::int64_t, std::int64_t> categories_;
  std::array<std::vector<std::int64_t>, 5> fake_pools_;
  std::vector<Item> items_;
  std::vector<std::size_t> sizes_;
  std::uint64_t gift_count_ = 0;
  std::uint64_t consumed_count_ = 0;
  std::uint64_t miracle_use_count_ = 0;
  std::uint64_t removal_count_ = 0;
  std::uint64_t restored_count_ = 0;
};

} // namespace godfield_sim
