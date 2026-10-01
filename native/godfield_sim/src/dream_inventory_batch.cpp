#include "dream_inventory_batch.h"
#include "curse_rules.h"

#include <algorithm>
#include <memory>
#include <set>
#include <stdexcept>

namespace godfield_sim {
namespace {
constexpr std::size_t kMaximumSlots = 2000000;
constexpr std::size_t kMaximumRows = 1000000;
constexpr std::int64_t kMaximumId = 9007199254740991;
} // namespace

DreamInventoryBatch::DreamInventoryBatch(std::size_t batch_size,
                                         std::size_t player_count,
                                         InventoryProfileInput profiles,
                                         std::size_t capacity)
    : batch_size_(batch_size), player_count_(player_count),
      capacity_(capacity) {
  if (batch_size == 0 || player_count < 2 || player_count > 9 ||
      capacity == 0 || capacity > kMaximumInventoryReplayItems ||
      batch_size > kMaximumSlots / player_count / capacity) {
    throw std::invalid_argument("dream inventory dimensions are invalid");
  }
  if (profiles.shape(0) == 0 || profiles.shape(0) > 296) {
    throw std::invalid_argument("dream inventory profile count is invalid");
  }
  for (std::size_t row = 0; row < profiles.shape(0); ++row) {
    const auto model = profiles(row, 0);
    const auto kind = profiles(row, 1);
    if (model < 1 || model > 296 || kind < 1 || kind > 5 ||
        !categories_.emplace(model, kind).second) {
      throw std::invalid_argument(
          "dream inventory profile is invalid or duplicate");
    }
    fake_pools_[static_cast<std::size_t>(kind - 1)].push_back(model);
  }
  for (auto &pool : fake_pools_) {
    std::sort(pool.begin(), pool.end());
  }
  sizes_.resize(batch_size * player_count, 0);
  items_.resize(batch_size * player_count * capacity, Item{});
}

void DreamInventoryBatch::same_length(std::size_t expected, ActionInput input) {
  if (input.shape(0) != expected) {
    throw std::invalid_argument("dream inventory input lengths differ");
  }
}

std::size_t DreamInventoryBatch::checked_owner(std::int64_t environment,
                                               std::int64_t owner) const {
  if (environment < 0 ||
      static_cast<std::uint64_t>(environment) >= batch_size_ || owner < 0 ||
      static_cast<std::uint64_t>(owner) >= player_count_) {
    throw std::invalid_argument(
        "dream inventory environment or owner is out of range");
  }
  return static_cast<std::size_t>(environment) * player_count_ +
         static_cast<std::size_t>(owner);
}

std::vector<std::size_t>
DreamInventoryBatch::checked_owners(ActionInput environments,
                                    ActionInput owners, bool unique) const {
  same_length(environments.shape(0), owners);
  if (environments.shape(0) > kMaximumRows) {
    throw std::invalid_argument("dream inventory operation row limit exceeded");
  }
  std::vector<std::size_t> indices;
  indices.reserve(environments.shape(0));
  std::set<std::size_t> seen;
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    const auto index = checked_owner(environments(row), owners(row));
    if (unique && !seen.insert(index).second) {
      throw std::invalid_argument("dream inventory owner is duplicate");
    }
    indices.push_back(index);
  }
  return indices;
}

std::int64_t DreamInventoryBatch::category(std::int64_t model) const {
  const auto found = categories_.find(model);
  if (found == categories_.end()) {
    throw std::invalid_argument("dream inventory model is not registered");
  }
  return found->second;
}

void DreamInventoryBatch::validate_item(const Item &item) const {
  if (item[0] < 1 || item[0] > kMaximumId || item[2] < 0 ||
      (item[3] != 0 && item[3] != 1)) {
    throw std::invalid_argument("dream inventory item fields are invalid");
  }
  const auto kind = category(item[1]);
  if ((item[2] != 0 && category(item[2]) != kind) ||
      (item[3] == 1 && kind != 4)) {
    throw std::invalid_argument(
        "dream inventory fake category or used flag is invalid");
  }
}

bool DreamInventoryBatch::has_instance(
    std::size_t environment, std::int64_t id,
    std::size_t excluded_owner) const noexcept {
  for (std::size_t player = 0; player < player_count_; ++player) {
    const auto index = environment * player_count_ + player;
    if (index == excluded_owner) {
      continue;
    }
    for (std::size_t slot = 0; slot < sizes_[index]; ++slot) {
      if (items_[index * capacity_ + slot][0] == id) {
        return true;
      }
    }
  }
  return false;
}

DreamInventoryBatch::Item DreamInventoryBatch::item_at(InventoryInput items,
                                                       std::size_t row) const {
  return {items(row, 0), items(row, 1), items(row, 2), items(row, 3)};
}

void DreamInventoryBatch::commit_hand(std::size_t owner,
                                      const std::vector<Item> &items) noexcept {
  const auto offset = owner * capacity_;
  std::copy(items.begin(), items.end(),
            items_.begin() + static_cast<std::ptrdiff_t>(offset));
  std::fill(items_.begin() + static_cast<std::ptrdiff_t>(offset + items.size()),
            items_.begin() + static_cast<std::ptrdiff_t>(offset + capacity_),
            Item{});
  sizes_[owner] = items.size();
}

void DreamInventoryBatch::seed_hand(std::size_t environment, std::size_t owner,
                                    InventoryInput items) {
  if (environment >= batch_size_ || owner >= player_count_ ||
      items.shape(0) > capacity_) {
    throw std::invalid_argument("dream inventory seed dimensions are invalid");
  }
  const auto index = environment * player_count_ + owner;
  std::set<std::int64_t> seen;
  std::vector<Item> staged;
  staged.reserve(items.shape(0));
  for (std::size_t row = 0; row < items.shape(0); ++row) {
    const auto item = item_at(items, row);
    validate_item(item);
    if (!seen.insert(item[0]).second ||
        has_instance(environment, item[0], index)) {
      throw std::invalid_argument("dream inventory instance is duplicate");
    }
    staged.push_back(item);
  }
  commit_hand(index, staged);
}

void DreamInventoryBatch::add_cards(
    ActionInput environments, ActionInput owners, ActionInput instance_ids,
    ActionInput model_ids, ActionInput curse_masks,
    ActionInput disguise_tickets, ActionInput fake_tickets) {
  const auto indices = checked_owners(environments, owners);
  for (const auto input :
       {instance_ids, model_ids, curse_masks, disguise_tickets, fake_tickets}) {
    same_length(indices.size(), input);
  }
  std::map<std::size_t, std::size_t> additions;
  std::set<std::pair<std::int64_t, std::int64_t>> seen;
  std::vector<Item> staged;
  staged.reserve(indices.size());
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto kind = category(model_ids(row));
    const auto &pool = fake_pools_[static_cast<std::size_t>(kind - 1)];
    if (curse_masks(row) < 0 || curse_masks(row) > kCurseMask ||
        disguise_tickets(row) < 0 || disguise_tickets(row) > 99 ||
        fake_tickets(row) < 0 ||
        static_cast<std::uint64_t>(fake_tickets(row)) >= pool.size()) {
      throw std::invalid_argument("dream inventory mask or ticket is invalid");
    }
    const auto fake =
        (curse_masks(row) & kCurseDreamBit) != 0 && disguise_tickets(row) < 50
            ? pool[static_cast<std::size_t>(fake_tickets(row))]
            : 0;
    const Item item = {instance_ids(row), model_ids(row), fake, 0};
    validate_item(item);
    if (!seen.emplace(environments(row), item[0]).second ||
        has_instance(static_cast<std::size_t>(environments(row)), item[0],
                     sizes_.size())) {
      throw std::invalid_argument("dream inventory instance is duplicate");
    }
    if (sizes_[indices[row]] + ++additions[indices[row]] > capacity_) {
      throw std::invalid_argument(
          "dream inventory capacity exceeded; no overflow is inferred");
    }
    staged.push_back(item);
  }
  // All validation/allocation precedes mutation; the fixed buffers cannot grow.
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto index = indices[row];
    items_[index * capacity_ + sizes_[index]++] = staged[row];
  }
  gift_count_ += indices.size();
}

void DreamInventoryBatch::selected_operation(ActionInput environments,
                                             ActionInput owners,
                                             InventoryInput expected_items,
                                             bool use) {
  const auto indices = checked_owners(environments, owners);
  if (expected_items.shape(0) != indices.size()) {
    throw std::invalid_argument("dream inventory selection lengths differ");
  }
  std::map<std::size_t, std::vector<Item>> selected;
  std::set<std::pair<std::int64_t, std::int64_t>> unique;
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto item = item_at(expected_items, row);
    const auto offset = indices[row] * capacity_;
    const auto begin = items_.begin() + static_cast<std::ptrdiff_t>(offset);
    const auto end = begin + static_cast<std::ptrdiff_t>(sizes_[indices[row]]);
    if (!unique.emplace(environments(row), item[0]).second ||
        std::find(begin, end, item) == end) {
      throw std::invalid_argument(
          "dream inventory selection is duplicate, stale or not owned");
    }
    selected[indices[row]].push_back(item);
  }
  std::map<std::size_t, std::vector<Item>> staged;
  std::uint64_t consumed = 0;
  std::uint64_t miracles = 0;
  for (const auto &[owner, selection] : selected) {
    auto &after = staged[owner];
    after.reserve(sizes_[owner]);
    for (std::size_t slot = 0; slot < sizes_[owner]; ++slot) {
      const auto &item = items_[owner * capacity_ + slot];
      if (std::find(selection.begin(), selection.end(), item) ==
          selection.end()) {
        after.push_back(item);
      }
    }
    if (use) {
      for (auto item : selection) {
        // Effects resolve the actual identity, never the Dream display.
        if (category(item[1]) == 4) {
          item[3] = 1;
          after.push_back(item);
          ++miracles;
        } else {
          ++consumed;
        }
      }
    }
  }
  for (const auto &[owner, after] : staged) {
    commit_hand(owner, after);
  }
  consumed_count_ += consumed;
  miracle_use_count_ += miracles;
  if (!use) {
    removal_count_ += indices.size();
  }
}

void DreamInventoryBatch::use_cards(ActionInput environments,
                                    ActionInput owners,
                                    InventoryInput expected_items) {
  selected_operation(environments, owners, expected_items, true);
}

void DreamInventoryBatch::remove_cards(ActionInput environments,
                                       ActionInput owners,
                                       InventoryInput expected_items) {
  selected_operation(environments, owners, expected_items, false);
}

void DreamInventoryBatch::restore_displays(ActionInput environments,
                                           ActionInput owners) {
  const auto indices = checked_owners(environments, owners, true);
  for (const auto index : indices) {
    for (std::size_t slot = 0; slot < sizes_[index]; ++slot) {
      auto &item = items_[index * capacity_ + slot];
      restored_count_ += item[2] != 0 ? 1 : 0;
      item[2] = 0;
    }
  }
}

void DreamInventoryBatch::reset_environments(ActionInput environments) {
  if (environments.shape(0) > batch_size_) {
    throw std::invalid_argument("dream inventory reset row limit exceeded");
  }
  std::set<std::int64_t> seen;
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    static_cast<void>(checked_owner(environments(row), 0));
    if (!seen.insert(environments(row)).second) {
      throw std::invalid_argument(
          "dream inventory reset environment is duplicate");
    }
  }
  for (const auto environment : seen) {
    const auto first = static_cast<std::size_t>(environment) * player_count_;
    std::fill(
        sizes_.begin() + static_cast<std::ptrdiff_t>(first),
        sizes_.begin() + static_cast<std::ptrdiff_t>(first + player_count_), 0);
    std::fill(items_.begin() + static_cast<std::ptrdiff_t>(first * capacity_),
              items_.begin() + static_cast<std::ptrdiff_t>(
                                   (first + player_count_) * capacity_),
              Item{});
  }
}

InventorySnapshot DreamInventoryBatch::snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(items_.size() * 4);
  for (std::size_t index = 0; index < items_.size(); ++index) {
    std::copy(items_[index].begin(), items_[index].end(),
              buffer.get() + index * 4);
  }
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return InventorySnapshot(data, {batch_size_, player_count_, capacity_, 4},
                           owner);
}

ActorInventorySnapshot
DreamInventoryBatch::actor_hands(ActionInput environments,
                                 ActionInput actors) const {
  // Bound output allocation before creating even the index vector.
  if (environments.shape(0) > kMaximumSlots / capacity_) {
    throw std::invalid_argument(
        "dream inventory actor query slot limit exceeded");
  }
  const auto indices = checked_owners(environments, actors);
  auto buffer = std::make_unique<std::int64_t[]>(
      std::max<std::size_t>(1, indices.size() * capacity_ * 3));
  for (std::size_t row = 0; row < indices.size(); ++row) {
    for (std::size_t slot = 0; slot < sizes_[indices[row]]; ++slot) {
      const auto &item = items_[indices[row] * capacity_ + slot];
      const auto offset = (row * capacity_ + slot) * 3;
      buffer[offset] = item[0];
      buffer[offset + 1] = item[2] != 0 ? item[2] : item[1];
      buffer[offset + 2] = item[3];
    }
  }
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<std::int64_t *>(pointer);
  });
  const auto *data = buffer.release();
  return ActorInventorySnapshot(data, {indices.size(), capacity_, 3}, owner);
}

void bind_dream_inventory(nb::module_ &module) {
  module.attr("DREAM_INVENTORY_SCHEMA_VERSION") = kDreamInventorySchemaVersion;
  module.attr("DREAM_INVENTORY_RULESET_ID") = kDreamInventoryRulesetId;
  nb::class_<DreamInventoryBatch>(module, "DreamInventoryBatch")
      .def(nb::init<std::size_t, std::size_t, InventoryProfileInput,
                    std::size_t>(),
           nb::arg("batch_size"), nb::arg("player_count"),
           nb::arg("profiles").noconvert(),
           nb::arg("capacity") = kMaximumInventoryReplayItems)
      .def("seed_hand", &DreamInventoryBatch::seed_hand, nb::arg("environment"),
           nb::arg("owner"), nb::arg("items").noconvert())
      .def("add_cards", &DreamInventoryBatch::add_cards,
           nb::arg("environments").noconvert(), nb::arg("owners").noconvert(),
           nb::arg("instance_ids").noconvert(),
           nb::arg("model_ids").noconvert(), nb::arg("curse_masks").noconvert(),
           nb::arg("disguise_tickets").noconvert(),
           nb::arg("fake_tickets").noconvert())
      .def("use_cards", &DreamInventoryBatch::use_cards,
           nb::arg("environments").noconvert(), nb::arg("owners").noconvert(),
           nb::arg("expected_items").noconvert())
      .def("remove_cards", &DreamInventoryBatch::remove_cards,
           nb::arg("environments").noconvert(), nb::arg("owners").noconvert(),
           nb::arg("expected_items").noconvert())
      .def("restore_displays", &DreamInventoryBatch::restore_displays,
           nb::arg("environments").noconvert(), nb::arg("owners").noconvert())
      .def("reset_environments", &DreamInventoryBatch::reset_environments,
           nb::arg("environments").noconvert())
      .def("snapshot", &DreamInventoryBatch::snapshot)
      .def("actor_hands", &DreamInventoryBatch::actor_hands,
           nb::arg("environments").noconvert(), nb::arg("actors").noconvert())
      .def_prop_ro("capacity", &DreamInventoryBatch::capacity)
      .def_prop_ro("gift_count", &DreamInventoryBatch::gift_count)
      .def_prop_ro("consumed_count", &DreamInventoryBatch::consumed_count)
      .def_prop_ro("miracle_use_count", &DreamInventoryBatch::miracle_use_count)
      .def_prop_ro("removal_count", &DreamInventoryBatch::removal_count)
      .def_prop_ro("restored_count", &DreamInventoryBatch::restored_count);
}

} // namespace godfield_sim
