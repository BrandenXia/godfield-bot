#pragma once

#include "curse_dynamics_batch.h"
#include "dream_inventory_batch.h"
#include "provisional_guardian.h"
#include <nanobind/stl/optional.h>
#include <optional>

namespace godfield_sim {

inline constexpr std::uint32_t kFullGameKernelSchemaVersion = 4;
inline constexpr std::uint32_t kFullGameCommandSchemaVersion = 1;
inline constexpr std::uint32_t kFullGameMaxDefenseActions = 64;
inline constexpr std::uint32_t kFullGameMaxAttackActions = 64;
inline constexpr const char *kFullGameRulesetId =
    "integrated-full-game-development-v4";
using FullGameBoostInput =
    nb::ndarray<const std::int64_t, nb::numpy, nb::shape<-1, 6>, nb::c_contig,
                nb::device::cpu>;
using FullGameCommandInput =
    nb::ndarray<const std::int64_t, nb::numpy, nb::shape<-1, 6>, nb::c_contig,
                nb::device::cpu>;
void bind_full_game(nb::module_ &module);

// The separate engine's joined development loop, NOT a complete game.
// Subcomponents are private owned state, never separately driven schedulers.
class FullGameBatch {
public:
  FullGameBatch(
      std::size_t batch_size, std::size_t player_count,
      InventoryProfileInput inventory_profiles, InventoryInput utility_profiles,
      std::size_t capacity = 512, std::uint64_t seed = 67,
      std::uint64_t max_turns = 1000, std::uint64_t max_decisions = 4000,
      std::uint16_t initial_hp = 40, std::uint16_t initial_mp = 10,
      std::uint16_t initial_cp = 0,
      std::optional<GuardianWeightInput> attack_profiles = std::nullopt,
      std::optional<GuardianWeightInput> armor_profiles = std::nullopt,
      std::optional<InventoryProfileInput> gift_profiles = std::nullopt,
      std::size_t initial_cards = 0, bool refill_on_use = false,
      bool prayer_gifts = false, std::size_t hand_limit = 0,
      bool oldest_overflow = false,
      std::optional<FullGameBoostInput> boost_profiles = std::nullopt);
  // Trusted setup only, rejected once started. These are not learner actions.
  void seed_players(ActionInput environments, ActionInput owners,
                    InventoryInput hp_mp_cp_illness, ActionInput curse_masks);
  void seed_hand(std::size_t environment, std::size_t owner,
                 InventoryInput items);
  void deal_cards(ActionInput environments, ActionInput owners,
                  ActionInput instance_ids, ActionInput model_ids);
  void start_environments(ActionInput environments);
  void reset_environments(ActionInput environments);
  // [environment, episode, decision, actor, phase, choice_id].
  void step(FullGameCommandInput commands);
  [[nodiscard]] Int64_2D episode_snapshot() const;
  [[nodiscard]] CurseStateSnapshot diagnostic_players() const;
  [[nodiscard]] InventorySnapshot diagnostic_inventory() const {
    return inventory_.snapshot();
  }
  [[nodiscard]] ActorInventorySnapshot actor_hands() const;
  [[nodiscard]] CurseStateSnapshot player_observations() const;
  [[nodiscard]] Bool2D choice_masks() const;
  [[nodiscard]] Int64_2D pending_observations() const;
  [[nodiscard]] Bool2D selected_defenses() const;
  [[nodiscard]] Int64_2D attack_selection_observations() const;
  [[nodiscard]] Int64_2D attack_order() const;
  [[nodiscard]] Bool2D selected_attacks() const;
  [[nodiscard]] std::uint64_t attack_toggle_count() const noexcept {
    return attack_toggles_;
  }
  [[nodiscard]] std::uint64_t attack_confirm_count() const noexcept {
    return attack_confirms_;
  }
  [[nodiscard]] std::uint64_t attack_component_count() const noexcept {
    return attack_components_;
  }
  [[nodiscard]] std::uint64_t darkness_finish_count() const noexcept {
    return darkness_finishes_;
  }
  [[nodiscard]] CurseStateSnapshot acquisition_snapshot() const;
  [[nodiscard]] std::uint64_t automatic_gift_count() const noexcept {
    return automatic_gifts_;
  }
  [[nodiscard]] std::uint64_t suppressed_gift_count() const noexcept {
    return suppressed_gifts_;
  }
  [[nodiscard]] std::uint64_t overflow_count() const noexcept {
    return overflow_;
  }
  [[nodiscard]] std::uint64_t prayer_count() const noexcept { return prayers_; }
  [[nodiscard]] std::uint64_t attack_count() const noexcept {
    return attacks_cast_;
  }
  [[nodiscard]] std::uint64_t resolved_attack_count() const noexcept {
    return attacks_resolved_;
  }
  [[nodiscard]] std::uint64_t defense_toggle_count() const noexcept {
    return defense_toggles_;
  }
  [[nodiscard]] std::uint64_t hp_damage() const noexcept { return hp_damage_; }
  [[nodiscard]] std::uint64_t action_count() const noexcept { return actions_; }
  [[nodiscard]] std::uint64_t pass_count() const noexcept { return passes_; }
  [[nodiscard]] std::uint64_t utility_count() const noexcept {
    return utilities_;
  }
  [[nodiscard]] std::uint64_t mp_spent() const noexcept { return mp_spent_; }
  [[nodiscard]] std::uint64_t gift_count() const noexcept {
    return inventory_.gift_count();
  }
  [[nodiscard]] std::uint64_t consumed_count() const noexcept {
    return inventory_.consumed_count();
  }
  [[nodiscard]] std::uint64_t miracle_use_count() const noexcept {
    return inventory_.miracle_use_count();
  }
  [[nodiscard]] std::uint64_t restored_count() const noexcept {
    return inventory_.restored_count();
  }

private:
  // setup=0, ready=1, attack-selection=2, target=3, defense=4, terminal=12,
  // truncated=13.
  struct Episode {
    std::int64_t epoch = 1;
    std::int64_t decision = 1;
    std::int64_t actor = 0;
    std::int64_t phase = 0;
    std::int64_t turns = 0;
    // none=0, winner=1, all-dead-draw=2, turn-limit=3, decision-limit=4.
    std::int64_t outcome = 0;
    std::int64_t winner = -1;
    std::int64_t commands = 0;
    std::int64_t last_choice = -1;
    std::uint64_t illness_rng = 0;
    std::uint64_t gift_rng = 0;
    std::uint64_t combat_rng = 0;
    std::uint64_t model_rng = 0;
    std::int64_t next_instance = 1;
    std::array<std::uint16_t, 9> gifts_due{};
    std::array<std::int64_t, 9> gifts_given{};
    std::array<std::int64_t, 9> evicted{};
    std::int64_t turn_owner = -1;
    std::int64_t attack_slot = -1;
    std::int64_t target = -1;
    std::int64_t attack = 0;
    std::int64_t element = 0;
    std::int64_t origin = -1;
    std::int64_t defense_actions = 0;
    std::int64_t selected_count = 0;
    std::int64_t attack_size = 0;
    std::int64_t attack_actions = 0;
    std::int64_t preview_attack = 0;
    std::int64_t preview_element = 0;
    std::int64_t preview_cost = 0;
  };
  struct Effect {
    std::int64_t kind; // HP=1, MP=2, mild-cure=3, full-cure=4.
    std::int64_t value;
    std::int64_t cost;
  };
  using Resources =
      std::array<std::int64_t, 2>; // MP, CP; HP owned by statuses.
  struct Attack {
    std::int64_t value, element, origin, cost;
  };
  struct Armor {
    std::int64_t value, element;
  };
  struct Boost {
    std::int64_t value, element, cost, kind;
    bool can_lead;
  };
  struct Composition {
    std::int64_t value, element, cost, origin;
    bool weapon;
  };
  struct Mutation {
    std::size_t environment;
    Episode episode;
    std::array<CurseDynamicsBatch::State, 9> statuses{};
    std::array<Resources, 9> resources{};
    std::map<std::size_t, std::vector<DreamInventoryBatch::Item>> hands;
    std::array<std::uint8_t, 512> selected{};
    std::array<std::int64_t, 512> order{};
    std::uint64_t consumed = 0;
    std::uint64_t miracles = 0;
    std::uint64_t restored = 0;
    std::uint64_t paid = 0;
    std::int64_t cured_owner = -1;
    std::int64_t ticked_owner = -1;
    bool pass = false;
    bool utility = false;
    bool attack_cast = false;
    bool attack_resolved = false;
    bool defense_toggle = false;
    std::uint64_t damage = 0;
    std::uint64_t gifts = 0;
    std::uint64_t suppressed_gifts = 0;
    std::uint64_t overflow = 0;
    bool prayer = false;
    bool accepted_command = false;
    bool attack_toggle = false;
    bool attack_confirm = false;
    std::uint64_t attack_components = 0;
    bool darkness_finish = false;
  };
  static std::size_t
  validate_dimensions(std::size_t batch_size, std::size_t player_count,
                      std::size_t capacity, std::uint64_t max_turns,
                      std::uint64_t max_decisions, std::uint16_t hp,
                      std::uint16_t mp, std::uint16_t cp);
  [[nodiscard]] std::vector<std::size_t>
  checked_environments(ActionInput environments) const;
  void require_setup(std::size_t environment) const;
  [[nodiscard]] bool
  visible_utility_eligible(std::size_t owner,
                           const Effect &effect) const noexcept;
  [[nodiscard]] Mutation prepare(FullGameCommandInput commands,
                                 std::size_t row) const;
  void finish_turn(Mutation &mutation, std::size_t owner) const;
  void advance_decision(Mutation &mutation, std::int64_t choice) const;
  void consume_slot(Mutation &mutation, std::size_t owner,
                    std::size_t slot) const;
  [[nodiscard]] Composition compose(const Mutation &mutation,
                                    bool actual) const;
  void update_preview(Mutation &mutation) const;
  void consume_attack(Mutation &mutation, std::size_t owner) const;
  [[nodiscard]] static std::int64_t mixed_element(std::int64_t existing,
                                                  std::int64_t added) noexcept;
  [[nodiscard]] Mutation staged_episode(std::size_t environment) const;
  [[nodiscard]] std::vector<DreamInventoryBatch::Item> &
  stage_hand(Mutation &mutation, std::size_t owner) const;
  void grant_gift(Mutation &mutation, std::size_t owner) const;
  void grant_pending_gifts(Mutation &mutation) const;
  void commit(const Mutation &mutation) noexcept;
  [[nodiscard]] bool visible_weapon(std::size_t owner) const;
  [[nodiscard]] bool legal_choice(std::size_t environment,
                                  std::int64_t choice) const;
  [[nodiscard]] static bool compatible(std::int64_t attack,
                                       std::int64_t defense) noexcept;
  void decide_outcome(Mutation &mutation) const noexcept;
  [[nodiscard]] Episode fresh_episode(std::size_t environment,
                                      std::int64_t epoch) const noexcept;
  const std::size_t batch_size_;
  const std::size_t player_count_;
  const std::size_t capacity_;
  const std::uint64_t seed_;
  const std::uint64_t max_turns_;
  const std::uint64_t max_decisions_;
  const std::uint16_t initial_mp_;
  const std::uint16_t initial_cp_;
  CurseDynamicsBatch statuses_;
  DreamInventoryBatch inventory_;
  std::map<std::int64_t, Effect> effects_;
  std::map<std::int64_t, Attack> attacks_;
  std::map<std::int64_t, Armor> armor_;
  std::map<std::int64_t, Boost> boosts_;
  std::vector<std::int64_t> attack_order_;
  std::vector<std::pair<std::int64_t, std::uint64_t>> gift_weights_;
  std::uint64_t gift_total_ = 0;
  std::size_t initial_cards_ = 0;
  bool refill_on_use_ = false;
  bool prayer_gifts_ = false;
  std::size_t hand_limit_ = 0;
  bool oldest_overflow_ = false;
  std::vector<std::uint8_t> selected_;
  std::vector<Resources> resources_;
  std::vector<Episode> episodes_;
  std::uint64_t actions_ = 0;
  std::uint64_t passes_ = 0;
  std::uint64_t utilities_ = 0;
  std::uint64_t mp_spent_ = 0;
  std::uint64_t attacks_cast_ = 0;
  std::uint64_t attacks_resolved_ = 0;
  std::uint64_t defense_toggles_ = 0;
  std::uint64_t hp_damage_ = 0;
  std::uint64_t automatic_gifts_ = 0;
  std::uint64_t suppressed_gifts_ = 0;
  std::uint64_t overflow_ = 0;
  std::uint64_t prayers_ = 0;
  std::uint64_t attack_toggles_ = 0;
  std::uint64_t attack_confirms_ = 0;
  std::uint64_t attack_components_ = 0;
  std::uint64_t darkness_finishes_ = 0;
};

} // namespace godfield_sim
