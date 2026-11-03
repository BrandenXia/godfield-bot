#pragma once

#include "curse_dynamics_batch.h"
#include "dream_inventory_batch.h"
#include "provisional_guardian.h"
#include <bitset>
#include <nanobind/stl/optional.h>
#include <optional>
#include <set>
#include <span>

namespace godfield_sim {

inline constexpr std::uint32_t kFullGameKernelSchemaVersion = 32;
inline constexpr std::uint32_t kFullGameTradeChoiceSchemaVersion = 2;
inline constexpr std::uint32_t kFullGameMaxTradeActions = 64;
inline constexpr std::uint32_t kFullGameAttackFamilySchemaVersion = 8;
inline constexpr std::uint32_t kFullGameCommandSchemaVersion = 1;
inline constexpr std::uint32_t kFullGameMaxDefenseActions = 64;
inline constexpr std::uint32_t kFullGameMaxAttackActions = 64;
inline constexpr std::uint32_t kFullGameMaxDiscardActions = 64;
inline constexpr const char *kFullGameRulesetId =
    "integrated-full-game-development-v32";
using FullGamePhenomenonInput =
    nb::ndarray<const std::int64_t, nb::numpy, nb::shape<-1, 5>, nb::c_contig,
                nb::device::cpu>;
using FullGameGuardianInput =
    nb::ndarray<const std::int64_t, nb::numpy, nb::shape<-1, 10>, nb::c_contig,
                nb::device::cpu>;
using FullGameAttackEffectInput =
    nb::ndarray<const std::int64_t, nb::numpy, nb::shape<-1, 3>, nb::c_contig,
                nb::device::cpu>;
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
      std::optional<FullGameBoostInput> boost_profiles = std::nullopt,
      std::optional<GuardianWeightInput> special_profiles = std::nullopt,
      std::optional<InventoryProfileInput> chance_profiles = std::nullopt,
      std::optional<FullGameAttackEffectInput> attack_effect_profiles =
          std::nullopt,
      std::optional<GuardianWeightInput> defense_effect_profiles = std::nullopt,
      std::optional<InventoryProfileInput> passive_profiles = std::nullopt,
      std::optional<FullGameAttackEffectInput> removal_profiles = std::nullopt,
      std::optional<InventoryInput> cost_reducer_profiles = std::nullopt,
      std::optional<InventoryInput> complex_weapon_profiles = std::nullopt,
      std::optional<InventoryInput> danger_profiles = std::nullopt,
      std::optional<InventoryInput> dream_defense_profiles = std::nullopt,
      std::optional<FullGameBoostInput> ascension_profiles = std::nullopt,
      std::optional<InventoryProfileInput> area_profiles = std::nullopt,
      std::optional<ActionInput> discard_model_ids = std::nullopt,
      std::optional<FullGameGuardianInput> guardian_profiles = std::nullopt,
      std::optional<InventoryProfileInput> summon_profiles = std::nullopt,
      std::optional<InventoryInput> devil_profiles = std::nullopt,
      std::uint64_t apocalypse_after_turns = 0,
      std::optional<FullGamePhenomenonInput> phenomenon_profiles = std::nullopt,
      std::optional<ActionInput> fate_model_ids = std::nullopt,
      std::optional<ActionInput> exchange_model_ids = std::nullopt,
      std::optional<FullGameAttackEffectInput> market_profiles = std::nullopt,
      std::optional<InventoryInput> guardian_generated_profiles = std::nullopt,
      std::optional<InventoryProfileInput> guardian_action_profiles =
          std::nullopt,
      bool sacrifice_enabled = false, std::uint16_t resource_cap = 100,
      bool resolve_hidden_targeting = false, bool resolve_hidden_trades = false,
      bool resolve_hidden_components = false,
      std::optional<InventoryProfileInput> role_profiles = std::nullopt,
      bool resolve_hidden_removals = false, bool teams_enabled = false);
  [[nodiscard]] std::int64_t resource_cap() const noexcept {
    return resource_cap_;
  }
  [[nodiscard]] bool resolve_hidden_targeting() const noexcept {
    return resolve_hidden_targeting_;
  }
  [[nodiscard]] Int64_2D hidden_targeting_snapshot() const;
  [[nodiscard]] bool resolve_hidden_trades() const noexcept {
    return resolve_hidden_trades_;
  }
  [[nodiscard]] Int64_2D hidden_trade_snapshot() const;
  [[nodiscard]] bool resolve_hidden_components() const noexcept {
    return resolve_hidden_components_;
  }
  [[nodiscard]] Int64_2D role_profiles() const;
  [[nodiscard]] Int64_2D ineffective_snapshot() const;
  [[nodiscard]] Int64_2D ineffective_model_counts() const;
  [[nodiscard]] bool resolve_hidden_removals() const noexcept {
    return resolve_hidden_removals_;
  }
  [[nodiscard]] Int64_2D hidden_removal_snapshot() const;
  [[nodiscard]] bool teams_enabled() const noexcept { return teams_enabled_; }
  void seed_teams(ActionInput environments, ActionInput owners,
                  ActionInput teams);
  [[nodiscard]] Int64_2D team_ids() const;
  [[nodiscard]] CurseStateSnapshot team_observations() const;
  [[nodiscard]] Bool2D winning_seats() const;
  // Trusted setup only, rejected once started. These are not learner actions.
  void seed_players(ActionInput environments, ActionInput owners,
                    InventoryInput hp_mp_cp_illness, ActionInput curse_masks);
  void seed_hand(std::size_t environment, std::size_t owner,
                 InventoryInput items);
  void seed_guardians(ActionInput environments, ActionInput owners,
                      ActionInput groups);
  void seed_confusion(ActionInput environments, ActionInput owners,
                      ActionInput remaining_turns);
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
  [[nodiscard]] Int64_2D special_defense_observations() const;
  [[nodiscard]] Int64_2D chance_observations() const;
  [[nodiscard]] Int64_2D chance_snapshot() const;
  [[nodiscard]] Int64_2D attack_effect_observations() const;
  [[nodiscard]] Int64_2D attack_effect_snapshot() const;
  [[nodiscard]] Int64_2D defense_order() const;
  [[nodiscard]] Int64_2D counter_observations() const;
  [[nodiscard]] Int64_2D counter_snapshot() const;
  [[nodiscard]] ActorInventorySnapshot passive_observations() const;
  [[nodiscard]] Int64_2D revival_snapshot() const;
  [[nodiscard]] Int64_2D removal_snapshot() const;
  [[nodiscard]] std::uint64_t removal_count() const noexcept {
    return inventory_.removal_count();
  }
  [[nodiscard]] std::uint64_t removal_effect_count() const noexcept {
    return removals_resolved_;
  }
  [[nodiscard]] std::uint64_t revival_count() const noexcept {
    return revivals_;
  }
  [[nodiscard]] std::uint64_t revived_hp() const noexcept {
    return revived_hp_;
  }
  [[nodiscard]] std::uint64_t counter_count() const noexcept {
    return counters_cast_;
  }
  [[nodiscard]] std::uint64_t resolved_counter_count() const noexcept {
    return counters_resolved_;
  }
  [[nodiscard]] std::uint64_t counter_miss_count() const noexcept {
    return counter_misses_;
  }
  [[nodiscard]] std::uint64_t suppressed_counter_count() const noexcept {
    return counters_suppressed_;
  }
  [[nodiscard]] std::uint64_t filtered_attack_count() const noexcept {
    return filters_used_;
  }
  [[nodiscard]] std::uint64_t self_curse_count() const noexcept {
    return self_curses_;
  }
  [[nodiscard]] std::uint64_t absorbed_hp() const noexcept {
    return absorbed_hp_;
  }
  [[nodiscard]] std::uint64_t absorption_count() const noexcept {
    return absorptions_;
  }
  [[nodiscard]] std::uint64_t inflicted_curse_count() const noexcept {
    return inflicted_curses_;
  }
  [[nodiscard]] std::uint64_t inflicted_illness_count() const noexcept {
    return inflicted_illnesses_;
  }
  [[nodiscard]] std::uint64_t illness_effect_damage() const noexcept {
    return illness_effect_damage_;
  }
  [[nodiscard]] std::uint64_t dark_cloud_hit_count() const noexcept {
    return dark_cloud_hits_;
  }
  [[nodiscard]] std::uint64_t chance_count() const noexcept {
    return chances_cast_;
  }
  [[nodiscard]] std::uint64_t chance_hit_count() const noexcept {
    return chance_hits_;
  }
  [[nodiscard]] std::uint64_t chance_miss_count() const noexcept {
    return chance_misses_;
  }
  [[nodiscard]] std::uint64_t block_count() const noexcept { return blocks_; }
  [[nodiscard]] std::uint64_t reflection_count() const noexcept {
    return reflections_;
  }
  [[nodiscard]] std::uint64_t bounce_count() const noexcept { return bounces_; }
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
  [[nodiscard]] Int64_2D cp_utility_snapshot() const;
  [[nodiscard]] Int64_2D compound_utility_snapshot() const;
  [[nodiscard]] std::uint64_t utility_hp_damage() const noexcept {
    return utility_hp_damage_;
  }
  [[nodiscard]] Int64_2D utility_selection_observations() const;
  [[nodiscard]] Int64_2D cost_snapshot() const;
  [[nodiscard]] Int64_2D complex_weapon_observations() const;
  [[nodiscard]] Int64_2D complex_weapon_snapshot() const;
  [[nodiscard]] Int64_2D danger_observations() const;
  [[nodiscard]] Int64_2D danger_snapshot() const;
  [[nodiscard]] Int64_2D dream_defense_snapshot() const;
  [[nodiscard]] Int64_2D attack_family_snapshot() const;
  [[nodiscard]] Int64_2D area_observations() const;
  [[nodiscard]] Int64_2D area_snapshot() const;
  [[nodiscard]] Int64_2D discard_observations() const;
  [[nodiscard]] Int64_2D discard_order() const;
  [[nodiscard]] Int64_2D discard_snapshot() const;
  [[nodiscard]] Int64_2D sacrifice_snapshot() const;
  [[nodiscard]] Int64_2D sacrifice_model_counts() const;
  [[nodiscard]] CurseStateSnapshot guardian_snapshot() const;
  [[nodiscard]] CurseStateSnapshot guardian_observations() const;
  [[nodiscard]] Int64_2D guardian_effect_observations() const;
  [[nodiscard]] Int64_2D guardian_statistics() const;
  [[nodiscard]] Int64_2D guardian_model_counts() const;
  [[nodiscard]] Int64_2D guardian_generated_snapshot() const;
  [[nodiscard]] Int64_2D guardian_generated_model_counts() const;
  [[nodiscard]] Int64_2D guardian_generated_execution_counts() const;
  [[nodiscard]] Int64_2D generated_action_observations() const;
  [[nodiscard]] Int64_2D apocalypse_observations() const;
  [[nodiscard]] Int64_2D devil_snapshot() const;
  [[nodiscard]] Int64_2D devil_model_counts() const;
  [[nodiscard]] CurseStateSnapshot control_observations() const;
  [[nodiscard]] Int64_2D confusion_snapshot() const;
  [[nodiscard]] Bool2D policy_gradient_masks() const;
  [[nodiscard]] Int64_2D phenomenon_observations() const;
  [[nodiscard]] Int64_2D phenomenon_snapshot() const;
  [[nodiscard]] Int64_2D phenomenon_model_counts() const;
  [[nodiscard]] Int64_2D trade_observations() const;
  [[nodiscard]] Int64_2D trade_snapshot() const;
  [[nodiscard]] Int64_2D market_observations() const;
  [[nodiscard]] Int64_2D market_snapshot() const;
  [[nodiscard]] Int64_2D market_escrow_snapshot() const;
  [[nodiscard]] std::uint64_t devil_count() const noexcept { return devils_; }
  [[nodiscard]] std::uint64_t devil_hp_damage() const noexcept {
    return devil_damage_;
  }
  [[nodiscard]] std::uint64_t devil_removed_count() const noexcept {
    return devil_removed_;
  }
  [[nodiscard]] std::uint64_t guardian_summon_count() const noexcept {
    return guardian_summons_;
  }
  [[nodiscard]] std::uint64_t guardian_activation_count() const noexcept {
    return guardian_activations_;
  }
  [[nodiscard]] std::uint64_t guardian_resolved_count() const noexcept {
    return guardian_resolved_;
  }
  [[nodiscard]] std::uint64_t guardian_hp_damage() const noexcept {
    return guardian_damage_;
  }
  [[nodiscard]] std::uint64_t guardian_departure_count() const noexcept {
    return guardian_departures_;
  }
  [[nodiscard]] std::uint64_t discard_count() const noexcept {
    return discards_;
  }
  [[nodiscard]] std::uint64_t discarded_card_count() const noexcept {
    return discarded_;
  }
  [[nodiscard]] std::uint64_t area_count() const noexcept { return areas_; }
  [[nodiscard]] std::uint64_t area_hp_damage() const noexcept {
    return area_damage_;
  }
  [[nodiscard]] std::uint64_t ascension_count() const noexcept {
    return ascensions_;
  }
  [[nodiscard]] std::uint64_t ascension_hp_damage() const noexcept {
    return ascension_damage_;
  }
  [[nodiscard]] std::uint64_t redraw_count() const noexcept { return redraws_; }
  [[nodiscard]] std::uint64_t redrawn_count() const noexcept {
    return redrawn_;
  }
  [[nodiscard]] std::uint64_t danger_count() const noexcept {
    return danger_casts_;
  }
  [[nodiscard]] std::uint64_t automatic_danger_hp_damage() const noexcept {
    return automatic_danger_damage_;
  }
  [[nodiscard]] std::uint64_t recoil_hp_damage() const noexcept {
    return recoil_hp_damage_;
  }
  [[nodiscard]] std::uint64_t waived_mp() const noexcept { return waived_mp_; }
  [[nodiscard]] std::uint64_t cost_waiver_count() const noexcept {
    return cost_waivers_;
  }
  [[nodiscard]] std::uint64_t cp_utility_count() const noexcept {
    return cp_utilities_;
  }
  [[nodiscard]] std::uint64_t utility_cp_gain() const noexcept {
    return utility_cp_gain_;
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
  // setup=0, ready=1, attack-selection=2, target=3, defense=4, trade=6,
  // discard=7, terminal=12, truncated=13.
  struct Episode {
    std::int64_t epoch = 1;
    std::int64_t decision = 1;
    std::int64_t actor = 0;
    std::int64_t phase = 0;
    std::int64_t turns = 0;
    // none=0, winner=1, all-dead-draw=2, turn-limit=3, decision-limit=4.
    std::int64_t outcome = 0;
    std::int64_t winner = -1;
    std::array<std::int64_t, 9> teams{};
    std::int64_t commands = 0;
    std::int64_t last_choice = -1;
    std::uint64_t illness_rng = 0;
    std::uint64_t gift_rng = 0;
    std::uint64_t combat_rng = 0;
    std::uint64_t model_rng = 0;
    std::uint64_t bounce_rng = 0;
    std::uint64_t chance_rng = 0, chance_target_rng = 0;
    std::uint64_t hidden_targeting_rng = 0;
    std::array<std::int64_t, 4> hidden_targeting_stats{};
    std::uint64_t counter_rng = 0;
    std::uint64_t removal_rng = 0;
    std::uint64_t utility_rng = 0;
    std::uint64_t danger_rng = 0, attractor_rng = 0;
    std::uint64_t redraw_model_rng = 0, redraw_disguise_rng = 0;
    std::uint64_t ascension_rng = 0;
    std::int64_t chance_casts = 0, chance_hits = 0, chance_misses = 0;
    std::int64_t absorptions = 0, absorbed_hp = 0, inflicted_curses = 0;
    std::int64_t inflicted_illnesses = 0, illness_effect_damage = 0,
                 dark_cloud_hits = 0;
    std::array<std::int64_t, 11> counter_stats{};
    std::array<std::int64_t, 10> revival_stats{};
    std::array<std::int64_t, 8> removal_stats{};
    std::array<std::int64_t, 4> cp_utility_stats{};
    std::array<std::int64_t, 10> compound_utility_stats{};
    std::array<std::int64_t, 5> cost_stats{};
    std::array<std::int64_t, 8> weapon_stats{};
    std::array<std::int64_t, 8> danger_stats{};
    std::array<std::int64_t, 8> dream_defense_stats{};
    std::array<std::int64_t, 13> family_stats{};
    std::array<std::int64_t, 8> area_stats{};
    std::array<std::int64_t, 6> discard_stats{};
    std::array<std::int64_t, 9> sacrifice_stats{};
    std::array<std::int64_t, 237> sacrifice_model_counts{};
    std::array<std::array<std::int64_t, 2>, 9>
        guardians{}; // group+1, identity.
    std::array<std::int64_t, 19> guardian_stats{};
    std::array<std::int64_t, 40> guardian_model_counts{};
    std::array<std::int64_t, 23> guardian_generated_stats{};
    std::array<std::int64_t, 237> guardian_generated_model_counts{};
    std::array<std::int64_t, 237> guardian_generated_execution_counts{};
    std::int64_t next_guardian_instance = 1, guardian_model = 0;
    bool guardians_scheduled = false;
    bool apocalypse = false;
    std::int64_t postturn_receipts = 0;
    std::array<std::int64_t, 18> devil_stats{};
    std::array<std::int64_t, 5> devil_model_counts{};
    std::uint64_t devil_rng = 0, devil_removal_rng = 0, devil_charity_rng = 0;
    std::array<std::int64_t, 9> confusion{};
    std::array<std::int64_t, 8> confusion_stats{};
    std::array<std::int64_t, 23> phenomenon_stats{};
    std::array<std::int64_t, 10> phenomenon_model_counts{};
    std::int64_t phenomenon_model = 0;
    std::uint64_t phenomenon_rng = 0, phenomenon_target_rng = 0,
                  phenomenon_hit_rng = 0;
    std::uint64_t phenomenon_shuffle_rng = 0, phenomenon_disguise_rng = 0;
    std::uint64_t confusion_rng = 0, confusion_target_rng = 0;
    std::uint64_t exchange_rng = 0;
    std::uint64_t hidden_exchange_rng = 0, hidden_sale_rng = 0,
                  hidden_market_target_rng = 0;
    std::array<std::int64_t, 9> hidden_trade_stats{};
    std::array<std::int64_t, 14> ineffective_stats{};
    std::array<std::int64_t, 237> ineffective_models{};
    std::array<std::int64_t, 7> hidden_removal_stats{};
    // Phase6: Exchange preview=1, Sell selection=2, current-source purchase=3.
    std::array<std::int64_t, 3> trade_wallet{}; // HP, MP, CP.
    std::int64_t trade_mode = 0, trade_actions = 0;
    std::array<std::int64_t, 10> trade_stats{};
    std::int64_t market_kind = 0, sale_slot = -1, escrow_owner = -1;
    DreamInventoryBatch::Item escrow{};
    bool forced_market = false;
    std::int64_t automatic_buyer = -1;
    std::array<std::int64_t, 25> market_stats{};
    std::uint64_t market_target_rng = 0, market_offer_rng = 0,
                  market_disguise_rng = 0, market_purchase_rng = 0,
                  market_sale_rng = 0;
    std::uint64_t guardian_summon_rng = 0, guardian_trigger_rng = 0,
                  guardian_model_rng = 0;
    std::uint64_t guardian_target_rng = 0, guardian_hit_rng = 0,
                  guardian_departure_rng = 0;
    std::uint64_t guardian_generated_rng = 0, guardian_receipt_rng = 0;
    std::uint64_t guardian_allocation_rng = 0;
    std::int64_t generated_model = 0, generated_virtual_leader = 0;
    std::int64_t discard_size = 0, discard_actions = 0;
    std::uint16_t final_deaths = 0;
    std::int64_t active_family_kind = 0, original_remaining = 0;
    bool turn_ticked = false;
    std::int64_t next_instance = 1;
    std::array<std::int64_t, 9> gifts_due{};
    std::array<std::int64_t, 9> sacrifice_gifts_due{};
    std::array<std::int64_t, 9> gifts_given{};
    std::array<std::int64_t, 9> evicted{};
    std::int64_t turn_owner = -1;
    std::int64_t damage_source = -1;
    std::int64_t redirects = 0;
    std::int64_t attack_slot = -1;
    std::int64_t target = -1;
    std::int64_t attack = 0;
    std::int64_t element = 0;
    std::int64_t origin = -1;
    std::int64_t hit_rate = 100;
    std::int64_t effect_kind = 0, effect_value = 0;
    std::int64_t counter_kind = 0, counter_damage_basis = 0;
    std::int64_t defense_actions = 0;
    std::int64_t selected_count = 0;
    std::int64_t attack_size = 0;
    std::int64_t attack_actions = 0;
    std::int64_t preview_attack = 0;
    std::int64_t preview_element = 0;
    std::int64_t preview_cost = 0;
    std::int64_t preview_area_count = 0, area_components = 0;
    bool area_family = false;
    bool utility_selection = false;
    std::int64_t weapon_kind = 0, weapon_value = 0;
    std::int64_t strikes_remaining = 0;
    std::int64_t recipient_strikes_remaining = 0;
    bool danger_family = false;
    std::int64_t danger_value = 0, danger_element = 0;
  };
  struct Effect {
    // HP=1, MP=2, mild-cure=3, full-cure=4, CP=5,
    // MP-and-Heaven=6, HP-or-self-damage=7.
    std::int64_t kind;
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
  struct ComplexWeapon {
    std::int64_t kind, value, element;
  };
  struct Danger {
    std::int64_t kind, value, element; // Pestle=1, passive Mortar=2.
  };
  struct GuardianEffect {
    std::int64_t group, weight, attack, element, rate, kind, value, curse,
        origin;
  };
  struct Devil {
    std::int64_t weight, kind, value;
  };
  struct Phenomenon {
    std::int64_t kind, value, element, rate;
  };
  struct AttackEffect {
    // Absorb=1, mask-on-damage=2, illness-on-damage=3, direct-mask=4,
    // direct-illness=5.
    std::int64_t kind, value;
  };
  struct DefenseEffect {
    // Counter ATK=1, curse=2, MP=3, CP=4; filter=5, self-illness=6,
    // self-Dream-and-redraw=7 (registered by separate optional profiles).
    std::int64_t kind, value, element, rate;
  };
  struct QueuedAttack {
    // Counter=1, original recipient/repeat=2, dead-owned Bow=3, guardian=4,
    // automatic post-turn receipt=5 (devil/Sun/Bow finish before siblings),
    // revealed phenomenon attack=6, market escrow/response=7,
    // generated guardian producer=8, generated attack/recipient/repeat=9.
    std::int64_t family_kind, source, target, value, element, origin, rate;
    std::int64_t effect_kind = 0, effect_value = 0;
    std::int64_t counter_kind = 0, damage_basis = 0;
    bool danger = false;
    std::int64_t recipient_strikes = 1;
    std::int64_t guardian_model = 0, guardian_instance = 0;
    bool guardian_automatic = false;
    std::int64_t phenomenon_model = 0;
    std::int64_t market_kind = 0, escrow_owner = -1;
    DreamInventoryBatch::Item escrow{};
    bool forced_market = false;
    std::int64_t automatic_buyer = -1;
    std::int64_t generated_model = 0, virtual_leader = 0;
    std::int64_t weapon_kind = 0, weapon_value = 0, area_count = 0;
    std::int64_t danger_value = 0, danger_element = 0;
    bool sacrifice_receipt = false;
  };
  struct Ascension {
    std::int64_t attack, rate, dying_attack, dying_rate, element;
  };
  struct Boost {
    std::int64_t value, element, cost, kind;
    bool can_lead;
  };
  struct Special {
    std::int64_t kind, origin, cost; // block=1, reflect=2, bounce=3; any=-1.
    bool neutral_only;
  };
  struct Composition {
    std::int64_t value, element, cost, origin;
    bool weapon;
    std::int64_t waived = 0, waivers = 0;
    std::int64_t area_count = 0;
    std::bitset<512> ineffective{};
  };
  enum class CardSource { Held, Generated };
  struct Mutation {
    std::size_t environment;
    Episode episode;
    std::array<CurseDynamicsBatch::State, 9> statuses{};
    std::array<Resources, 9> resources{};
    std::map<std::size_t, std::vector<DreamInventoryBatch::Item>> hands;
    std::array<std::uint8_t, 512> selected{};
    std::array<std::int64_t, 512> order{};
    std::vector<QueuedAttack> family;
    std::uint64_t consumed = 0;
    std::uint64_t miracles = 0;
    std::uint64_t restored = 0;
    std::uint64_t paid = 0;
    std::int64_t cured_owner = -1;
    std::int64_t ticked_owner = -1;
    bool pass = false;
    bool utility = false;
    std::uint64_t cp_utility = 0;
    std::uint64_t utility_cp_gain = 0;
    std::uint64_t utility_hp_damage = 0;
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
    std::uint64_t darkness_finish = 0;
    std::int64_t special_kind = 0;
    std::int64_t chance_result = 0; // not sampled=0, hit=1, miss=-1.
    std::uint64_t absorbed_hp = 0, illness_effect_damage = 0;
    bool absorption = false;
    std::uint64_t inflicted_curse = 0, inflicted_illness = 0;
    bool dark_cloud_hit = false;
    std::uint64_t counters_cast = 0, counters_resolved = 0, counter_misses = 0;
    std::uint64_t counters_suppressed = 0, filters_used = 0, self_curses = 0;
    std::uint64_t revivals = 0, revived_hp = 0;
    std::uint64_t removed = 0, removal_effects = 0;
    std::uint64_t waived = 0, waivers = 0;
    std::uint64_t recoil_damage = 0;
    bool danger_cast = false;
    std::uint64_t automatic_danger_damage = 0;
    std::uint64_t redraws = 0, redrawn = 0;
    std::uint64_t ascensions = 0, ascension_damage = 0;
    bool area_cast = false;
    std::uint64_t area_damage = 0;
    bool discard = false;
    std::uint64_t discarded = 0;
  };
  static std::size_t validate_dimensions(
      std::size_t batch_size, std::size_t player_count, std::size_t capacity,
      std::uint64_t max_turns, std::uint64_t max_decisions, std::uint16_t hp,
      std::uint16_t mp, std::uint16_t cp, std::uint16_t resource_cap);
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
  // Model-only effect calculation: never reads or mutates a physical hand.
  [[nodiscard]] Composition compose_models(std::span<const std::int64_t> models,
                                           std::int64_t owner_mp, bool utility,
                                           CardSource source,
                                           bool tolerate = false) const;
  [[nodiscard]] std::int64_t sequence_cost(std::span<const std::int64_t> models,
                                           CardSource source) const;
  void update_preview(Mutation &mutation) const;
  void consume_attack(Mutation &mutation, std::size_t owner, bool attack = true,
                      const std::bitset<512> *ineffective = nullptr) const;
  [[nodiscard]] std::int64_t registered_roles(std::int64_t model) const;
  [[nodiscard]] bool hidden_selection(const Mutation &mutation,
                                      std::size_t count) const;
  void record_ineffective(Mutation &mutation, const std::bitset<512> &mask,
                          std::size_t count, std::size_t kind) const;
  void
  resolve_ineffective_defenses(Mutation &mutation, std::int64_t &defense,
                               std::vector<DefenseEffect> &counters,
                               std::vector<DefenseEffect> &self_effects) const;
  void execute_utility(Mutation &mutation, std::size_t slot,
                       bool ordered) const;
  [[nodiscard]] bool apply_utility_effect(Mutation &mutation, std::size_t actor,
                                          const Effect &effect,
                                          std::int64_t cost) const;
  void execute_discard(Mutation &mutation) const;
  void summon_guardian(Mutation &mutation, std::size_t owner) const;
  void schedule_guardians(Mutation &mutation, std::size_t turn_owner) const;
  void guardian_damage(Mutation &mutation, std::size_t owner,
                       std::int64_t loss) const;
  void apply_guardian_automatic(Mutation &mutation,
                                const QueuedAttack &shot) const;
  void execute_generated_guardian(Mutation &mutation,
                                  const QueuedAttack &producer) const;
  [[nodiscard]] std::int64_t draw_generated_model(Mutation &mutation,
                                                  std::int64_t group) const;
  void enqueue_generated_market(Mutation &mutation,
                                const QueuedAttack &producer, std::int64_t kind,
                                std::int64_t target) const;
  void settle_exchange(Mutation &mutation, std::size_t actor,
                       const std::array<std::int64_t, 3> &wallet) const;
  [[nodiscard]] std::array<std::int64_t, 3>
  sample_exchange_wallet(const Mutation &mutation, std::size_t actor,
                         std::uint64_t &rng) const;
  void apply_devil(Mutation &mutation, std::size_t owner) const;
  [[nodiscard]] bool schedule_receipts(Mutation &mutation) const;
  [[nodiscard]] bool enqueue_phenomenon(Mutation &mutation,
                                        std::size_t owner) const;
  void shuffle_phenomenon_items(Mutation &mutation) const;
  void execute_confused_turn(Mutation &mutation) const;
  void begin_exchange(Mutation &mutation, std::size_t slot) const;
  void execute_exchange(Mutation &mutation) const;
  void execute_forced_exchange(Mutation &mutation, std::size_t slot) const;
  void begin_market(Mutation &mutation, std::size_t slot,
                    std::int64_t kind) const;
  void cast_market(Mutation &mutation, std::int64_t choice,
                   bool target_resolved = false) const;
  [[nodiscard]] bool resolve_hidden_trade(Mutation &mutation,
                                          std::int64_t choice) const;
  void resolve_market(Mutation &mutation, bool blocked) const;
  void decide_purchase(Mutation &mutation, bool bought) const;
  void settle_market(Mutation &mutation) const;
  void restore_market_escrow(Mutation &mutation) const;
  void receive_market_item(Mutation &mutation, std::size_t recipient) const;
  void clear_market(Mutation &mutation) const;
  [[nodiscard]] std::int64_t exchange_delta(const Episode &episode,
                                            std::int64_t choice) const noexcept;
  [[nodiscard]] std::int64_t model_mp_cost(std::int64_t model) const noexcept;
  [[nodiscard]] std::int64_t ordered_cost(std::size_t owner,
                                          const std::int64_t *order,
                                          std::size_t count, bool actual) const;
  void record_waivers(Mutation &mutation, const Composition &composition,
                      std::size_t kind) const;
  void cast_attack(Mutation &mutation, std::int64_t choice,
                   bool automatic) const;
  [[nodiscard]] QueuedAttack attack_payload(std::int64_t leader,
                                            const Composition &composition,
                                            std::int64_t source,
                                            std::int64_t target,
                                            std::int64_t family_kind) const;
  void apply_attack_effect(Mutation &mutation) const;
  void apply_removal(Mutation &mutation, std::int64_t kind,
                     std::int64_t maximum) const;
  void apply_dream_redraw(Mutation &mutation, std::size_t owner) const;
  void apply_illness(Mutation &mutation, std::size_t target,
                     std::int64_t stage) const;
  // Called only on a positive-to-zero HP edge, never on setup/deal/idle state.
  // Causes: attack=1, infliction=2, payment=3, periodic=4, worsening=5,
  // direct utility damage=6, automatic devil damage=7, Exchange HP-zero=8.
  void resolve_hp_zero(Mutation &mutation, std::size_t owner,
                       std::int64_t cause) const;
  void enqueue_attack(Mutation &mutation, const QueuedAttack &attack) const;
  void complete_attack(Mutation &mutation, std::int64_t damage) const;
  void suppress_attack(Mutation &mutation, const QueuedAttack &attack) const;
  void resume_family(Mutation &mutation) const;
  [[nodiscard]] std::int64_t prepare_danger(Mutation &mutation,
                                            QueuedAttack &shot) const;
  void enqueue_ascension(Mutation &mutation, std::size_t owner) const;
  [[nodiscard]] std::int64_t displayed_model(std::size_t environment,
                                             std::size_t slot) const;
  [[nodiscard]] bool defense_choice(std::size_t environment,
                                    std::int64_t choice,
                                    const std::int64_t *order,
                                    std::size_t count) const;
  [[nodiscard]] std::int64_t
  displayed_defense_element(std::size_t environment) const;
  [[nodiscard]] std::int64_t hit_rate(std::int64_t model) const noexcept;
  [[nodiscard]] static std::int64_t mixed_element(std::int64_t existing,
                                                  std::int64_t added) noexcept;
  [[nodiscard]] Mutation staged_episode(std::size_t environment) const;
  [[nodiscard]] std::vector<DreamInventoryBatch::Item> &
  stage_hand(Mutation &mutation, std::size_t owner) const;
  std::int64_t grant_gift(Mutation &mutation, std::size_t owner) const;
  // Fresh identity, receiver Dream and explicit cap; no use, gift or trade.
  // Return flags: disguise=1, oldest eviction=2. Caller owns accounting.
  [[nodiscard]] std::uint8_t receive_artifact(Mutation &mutation,
                                              std::size_t owner,
                                              std::int64_t model,
                                              std::uint64_t &rng) const;
  void grant_pending_gifts(Mutation &mutation) const;
  void commit(Mutation &mutation) noexcept;
  [[nodiscard]] bool visible_weapon(std::size_t owner) const;
  [[nodiscard]] bool legal_choice(std::size_t environment,
                                  std::int64_t choice) const;
  [[nodiscard]] std::int64_t
  special_kind(std::int64_t model, const Episode &episode) const noexcept;
  [[nodiscard]] static bool compatible(std::int64_t attack,
                                       std::int64_t defense) noexcept;
  void decide_outcome(Mutation &mutation) const noexcept;
  [[nodiscard]] static bool are_enemies(const Episode &episode,
                                        std::size_t source,
                                        std::size_t target) noexcept;
  [[nodiscard]] std::size_t
  living_factions(const Mutation &mutation) const noexcept;
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
  std::map<std::int64_t, Special> specials_;
  std::map<std::int64_t, std::int64_t> chances_;
  std::map<std::int64_t, AttackEffect> attack_effects_;
  std::map<std::int64_t, DefenseEffect> defense_effects_;
  std::map<std::int64_t, std::int64_t> passives_;
  std::map<std::int64_t, AttackEffect> removals_;
  std::set<std::int64_t> cost_reducers_;
  std::map<std::int64_t, ComplexWeapon> complex_weapons_;
  std::map<std::int64_t, Danger> dangers_;
  std::map<std::int64_t, Ascension> ascensions_by_model_;
  std::map<std::int64_t, std::int64_t> area_costs_;
  std::set<std::int64_t> discard_models_;
  std::map<std::int64_t, GuardianEffect> guardian_effects_;
  std::array<std::vector<std::pair<std::int64_t, std::uint64_t>>, 8>
      guardian_weights_;
  std::array<std::vector<std::pair<std::int64_t, std::uint64_t>>, 2>
      guardian_generated_weights_;
  std::map<std::int64_t, std::int64_t> guardian_action_routes_;
  std::set<std::int64_t> summon_models_;
  std::map<std::int64_t, Devil> devils_by_model_;
  std::vector<std::pair<std::int64_t, std::uint64_t>> devil_weights_;
  std::uint64_t apocalypse_after_turns_ = 0;
  bool sacrifice_enabled_ = false;
  std::int64_t resource_cap_ = 100;
  bool resolve_hidden_targeting_ = false;
  bool resolve_hidden_trades_ = false;
  bool resolve_hidden_components_ = false;
  bool resolve_hidden_removals_ = false;
  bool teams_enabled_ = false;
  std::map<std::int64_t, std::int64_t> role_profiles_;
  std::uint64_t devils_ = 0, devil_damage_ = 0, devil_removed_ = 0;
  std::map<std::int64_t, Phenomenon> phenomena_;
  std::set<std::int64_t> exchange_models_;
  std::map<std::int64_t, std::int64_t> market_prices_;
  std::vector<std::vector<QueuedAttack>> families_;
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
  std::uint64_t revivals_ = 0, revived_hp_ = 0;
  std::uint64_t removals_resolved_ = 0;
  std::uint64_t actions_ = 0;
  std::uint64_t passes_ = 0;
  std::uint64_t utilities_ = 0;
  std::uint64_t cp_utilities_ = 0, utility_cp_gain_ = 0;
  std::uint64_t utility_hp_damage_ = 0;
  std::uint64_t danger_casts_ = 0, automatic_danger_damage_ = 0;
  std::uint64_t redraws_ = 0, redrawn_ = 0;
  std::uint64_t ascensions_ = 0, ascension_damage_ = 0;
  std::uint64_t areas_ = 0, area_damage_ = 0;
  std::uint64_t discards_ = 0, discarded_ = 0;
  std::uint64_t guardian_summons_ = 0, guardian_activations_ = 0,
                guardian_resolved_ = 0;
  std::uint64_t guardian_damage_ = 0, guardian_departures_ = 0;
  std::uint64_t waived_mp_ = 0, cost_waivers_ = 0;
  std::uint64_t recoil_hp_damage_ = 0;
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
  std::uint64_t blocks_ = 0, reflections_ = 0, bounces_ = 0;
  std::uint64_t chances_cast_ = 0, chance_hits_ = 0, chance_misses_ = 0;
  std::uint64_t absorptions_ = 0, absorbed_hp_ = 0, inflicted_curses_ = 0;
  std::uint64_t inflicted_illnesses_ = 0, illness_effect_damage_ = 0,
                dark_cloud_hits_ = 0;
  std::uint64_t counters_cast_ = 0, counters_resolved_ = 0, counter_misses_ = 0;
  std::uint64_t counters_suppressed_ = 0, filters_used_ = 0, self_curses_ = 0;
};

} // namespace godfield_sim
