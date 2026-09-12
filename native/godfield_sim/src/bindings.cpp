#include "attack_defense_batch.h"
#include "fixed_attack_batch.h"

#include <nanobind/nanobind.h>

namespace nb = nanobind;
using godfield_sim::AbsorptionWeaponResourceAttackDefenseBatch;
using godfield_sim::AttackDefenseBatch;
using godfield_sim::ChanceWeaponResourceAttackDefenseBatch;
using godfield_sim::ComboAttackDefenseBatch;
using godfield_sim::DualRoleResourceAttackDefenseBatch;
using godfield_sim::ElementalAttackDefenseBatch;
using godfield_sim::ExpandedResourceAttackDefenseBatch;
using godfield_sim::FixedAttackBatch;
using godfield_sim::ReflectionResourceAttackDefenseBatch;
using godfield_sim::ReflectionWeaponResourceAttackDefenseBatch;
using godfield_sim::ResourceAttackDefenseBatch;
using godfield_sim::StochasticResourceAttackDefenseBatch;

NB_MODULE(_native, module) {
  module.doc() = "Native batched God Field curriculum kernels";
  module.attr("KERNEL_SCHEMA_VERSION") = godfield_sim::kKernelSchemaVersion;
  module.attr("OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::kObservationSchemaVersion;
  module.attr("RULESET_ID") = godfield_sim::kRulesetId;
  module.attr("ACTION_COUNT") = godfield_sim::kActionCount;
  module.attr("HAND_SLOTS") = godfield_sim::kHandSlots;
  module.attr("GLOBAL_FEATURE_COUNT") = godfield_sim::kGlobalFeatureCount;
  module.attr("FORGIVE_ACTION_INDEX") = godfield_sim::kForgiveActionIndex;
  module.attr("CONFIRM_ACTION_INDEX") = godfield_sim::kConfirmActionIndex;
  module.attr("ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION") =
      godfield_sim::kAttackDefenseKernelSchemaVersion;
  module.attr("ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::kAttackDefenseObservationSchemaVersion;
  module.attr("ATTACK_DEFENSE_RULESET_ID") =
      godfield_sim::kAttackDefenseRulesetId;
  module.attr("MIXED_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION") =
      godfield_sim::kMixedAttackDefenseKernelSchemaVersion;
  module.attr("MIXED_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::kMixedAttackDefenseObservationSchemaVersion;
  module.attr("MIXED_ATTACK_DEFENSE_RULESET_ID") =
      godfield_sim::kMixedAttackDefenseRulesetId;
  module.attr("ELEMENTAL_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION") =
      godfield_sim::kElementalAttackDefenseKernelSchemaVersion;
  module.attr("ELEMENTAL_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::kElementalAttackDefenseObservationSchemaVersion;
  module.attr("ELEMENTAL_ATTACK_DEFENSE_RULESET_ID") =
      godfield_sim::kElementalAttackDefenseRulesetId;
  module.attr("COMBO_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION") =
      godfield_sim::kComboAttackDefenseKernelSchemaVersion;
  module.attr("COMBO_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::kComboAttackDefenseObservationSchemaVersion;
  module.attr("COMBO_ATTACK_DEFENSE_RULESET_ID") =
      godfield_sim::kComboAttackDefenseRulesetId;
  module.attr("RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION") =
      godfield_sim::kResourceAttackDefenseKernelSchemaVersion;
  module.attr("RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::kResourceAttackDefenseObservationSchemaVersion;
  module.attr("RESOURCE_ATTACK_DEFENSE_RULESET_ID") =
      godfield_sim::kResourceAttackDefenseRulesetId;
  module.attr("STOCHASTIC_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION") =
      godfield_sim::kStochasticResourceAttackDefenseKernelSchemaVersion;
  module.attr("STOCHASTIC_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::kStochasticResourceAttackDefenseObservationSchemaVersion;
  module.attr("STOCHASTIC_RESOURCE_ATTACK_DEFENSE_RULESET_ID") =
      godfield_sim::kStochasticResourceAttackDefenseRulesetId;
  module.attr("STOCHASTIC_RESOURCE_GLOBAL_FEATURE_COUNT") =
      godfield_sim::kStochasticResourceGlobalFeatureCount;
  module.attr("EXPANDED_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION") =
      godfield_sim::kExpandedResourceAttackDefenseKernelSchemaVersion;
  module.attr("EXPANDED_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::kExpandedResourceAttackDefenseObservationSchemaVersion;
  module.attr("EXPANDED_RESOURCE_ATTACK_DEFENSE_RULESET_ID") =
      godfield_sim::kExpandedResourceAttackDefenseRulesetId;
  module.attr("REFLECTION_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION") =
      godfield_sim::kReflectionResourceAttackDefenseKernelSchemaVersion;
  module.attr("REFLECTION_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::kReflectionResourceAttackDefenseObservationSchemaVersion;
  module.attr("REFLECTION_RESOURCE_ATTACK_DEFENSE_RULESET_ID") =
      godfield_sim::kReflectionResourceAttackDefenseRulesetId;
  module.attr(
      "REFLECTION_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION") =
      godfield_sim::kReflectionWeaponResourceAttackDefenseKernelSchemaVersion;
  module.attr(
      "REFLECTION_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::
          kReflectionWeaponResourceAttackDefenseObservationSchemaVersion;
  module.attr("REFLECTION_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID") =
      godfield_sim::kReflectionWeaponResourceAttackDefenseRulesetId;
  module.attr("DUAL_ROLE_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION") =
      godfield_sim::kDualRoleResourceAttackDefenseKernelSchemaVersion;
  module.attr("DUAL_ROLE_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::kDualRoleResourceAttackDefenseObservationSchemaVersion;
  module.attr("DUAL_ROLE_RESOURCE_ATTACK_DEFENSE_RULESET_ID") =
      godfield_sim::kDualRoleResourceAttackDefenseRulesetId;
  module.attr("CHANCE_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION") =
      godfield_sim::kChanceWeaponResourceAttackDefenseKernelSchemaVersion;
  module.attr(
      "CHANCE_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::kChanceWeaponResourceAttackDefenseObservationSchemaVersion;
  module.attr("CHANCE_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID") =
      godfield_sim::kChanceWeaponResourceAttackDefenseRulesetId;
  module.attr(
      "ABSORPTION_WEAPON_RESOURCE_ATTACK_DEFENSE_KERNEL_SCHEMA_VERSION") =
      godfield_sim::kAbsorptionWeaponResourceAttackDefenseKernelSchemaVersion;
  module.attr(
      "ABSORPTION_WEAPON_RESOURCE_ATTACK_DEFENSE_OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::
          kAbsorptionWeaponResourceAttackDefenseObservationSchemaVersion;
  module.attr("ABSORPTION_WEAPON_RESOURCE_ATTACK_DEFENSE_RULESET_ID") =
      godfield_sim::kAbsorptionWeaponResourceAttackDefenseRulesetId;
  module.attr("ELEMENT_COUNT") = godfield_sim::kElementCount;
  module.attr("ELEMENTAL_GLOBAL_FEATURE_COUNT") =
      godfield_sim::kElementalGlobalFeatureCount;
  module.attr("ELEMENT_NON_ELEMENT") =
      static_cast<std::uint8_t>(godfield_sim::CombatElement::NonElement);
  module.attr("ELEMENT_FIRE") =
      static_cast<std::uint8_t>(godfield_sim::CombatElement::Fire);
  module.attr("ELEMENT_WATER") =
      static_cast<std::uint8_t>(godfield_sim::CombatElement::Water);
  module.attr("ELEMENT_WOOD") =
      static_cast<std::uint8_t>(godfield_sim::CombatElement::Wood);
  module.attr("ELEMENT_STONE") =
      static_cast<std::uint8_t>(godfield_sim::CombatElement::Stone);
  module.attr("ELEMENT_LIGHT") =
      static_cast<std::uint8_t>(godfield_sim::CombatElement::Light);
  module.attr("ELEMENT_DARKNESS") =
      static_cast<std::uint8_t>(godfield_sim::CombatElement::Darkness);
  module.attr("WEAPON_SLOTS") = godfield_sim::kWeaponSlots;
  module.attr("ARMOR_SLOTS") = godfield_sim::kArmorSlots;
  module.attr("PHASE_ATTACK") =
      static_cast<std::uint8_t>(godfield_sim::TurnPhase::Attack);
  module.attr("PHASE_DEFENSE") =
      static_cast<std::uint8_t>(godfield_sim::TurnPhase::Defense);
  module.attr("PHASE_TERMINAL") =
      static_cast<std::uint8_t>(godfield_sim::TurnPhase::Terminal);
  module.attr("CARD_KIND_WEAPON") = std::uint8_t{1U};
  module.attr("CARD_KIND_ARMOR") = std::uint8_t{2U};
  module.attr("CARD_KIND_ATTACK_BOOSTER") = std::uint8_t{3U};
  module.attr("CARD_KIND_HP_UTILITY") = std::uint8_t{4U};
  module.attr("CARD_KIND_MP_UTILITY") = std::uint8_t{5U};
  module.attr("CARD_KIND_ATTACK_MIRACLE") = std::uint8_t{6U};
  module.attr("CARD_KIND_HP_MIRACLE") = std::uint8_t{7U};
  module.attr("CARD_KIND_CHANCE_ATTACK_MIRACLE") = std::uint8_t{8U};
  module.attr("CARD_KIND_EFFECT_ATTACK_MIRACLE") = std::uint8_t{9U};
  module.attr("CARD_KIND_ADDITIVE_MIRACLE") = std::uint8_t{10U};
  module.attr("CARD_KIND_REFLECTION_ARMOR") = std::uint8_t{11U};
  module.attr("CARD_KIND_REFLECTION_WEAPON") = std::uint8_t{12U};
  module.attr("CARD_KIND_DUAL_ROLE") = std::uint8_t{13U};
  module.attr("CARD_KIND_CHANCE_WEAPON") = std::uint8_t{14U};
  module.attr("CARD_KIND_CHANCE_DUAL_ROLE") = std::uint8_t{15U};
  module.attr("CARD_KIND_ABSORPTION_WEAPON") = std::uint8_t{16U};
  module.attr("CARD_KIND_CHANCE_ABSORPTION_WEAPON") = std::uint8_t{17U};

  nb::class_<FixedAttackBatch>(module, "FixedAttackBatch")
      .def(nb::init<std::size_t, godfield_sim::TokenInput,
                    godfield_sim::AttackInput, std::uint64_t, std::uint16_t>(),
           nb::arg("batch_size"), nb::arg("token_ids"),
           nb::arg("attack_values"), nb::arg("seed") = 67U,
           nb::arg("initial_hp") = 40U)
      .def_prop_ro("batch_size", &FixedAttackBatch::batch_size)
      .def_prop_ro("seed", &FixedAttackBatch::seed)
      .def_prop_ro("initial_hp", &FixedAttackBatch::initial_hp)
      .def_prop_ro("global_features", &FixedAttackBatch::global_features_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("player_features", &FixedAttackBatch::player_features_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("player_mask", &FixedAttackBatch::player_mask_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("hand_token_ids", &FixedAttackBatch::hand_token_ids_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("hand_mask", &FixedAttackBatch::hand_mask_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("action_mask", &FixedAttackBatch::action_mask_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("active_players", &FixedAttackBatch::active_players_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("terminal_returns", &FixedAttackBatch::terminal_returns_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("terminated", &FixedAttackBatch::terminated_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("episode_ids", &FixedAttackBatch::episode_ids_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("turn_numbers", &FixedAttackBatch::turn_numbers_view,
                   nb::rv_policy::reference_internal)
      .def("reset", &FixedAttackBatch::reset,
           nb::call_guard<nb::gil_scoped_release>())
      .def("reset_done", &FixedAttackBatch::reset_done,
           nb::call_guard<nb::gil_scoped_release>())
      .def("step", &FixedAttackBatch::step, nb::arg("actions"),
           nb::call_guard<nb::gil_scoped_release>());

  nb::class_<AttackDefenseBatch>(module, "AttackDefenseBatch")
      .def(nb::init<std::size_t, godfield_sim::TokenInput,
                    godfield_sim::ValueInput, godfield_sim::TokenInput,
                    godfield_sim::ValueInput, std::uint64_t, std::uint16_t,
                    bool>(),
           nb::arg("batch_size"), nb::arg("weapon_token_ids"),
           nb::arg("attack_values"), nb::arg("armor_token_ids"),
           nb::arg("defense_values"), nb::arg("seed") = 67U,
           nb::arg("initial_hp") = 40U, nb::arg("mixed_hands") = false)
      .def_prop_ro("batch_size", &AttackDefenseBatch::batch_size)
      .def_prop_ro("seed", &AttackDefenseBatch::seed)
      .def_prop_ro("initial_hp", &AttackDefenseBatch::initial_hp)
      .def_prop_ro("mixed_hands", &AttackDefenseBatch::mixed_hands)
      .def_prop_ro("elemental", &AttackDefenseBatch::elemental)
      .def_prop_ro("combo", &AttackDefenseBatch::combo)
      .def_prop_ro("resource_curriculum",
                   &AttackDefenseBatch::resource_curriculum)
      .def_prop_ro("stochastic_resource_curriculum",
                   &AttackDefenseBatch::stochastic_resource_curriculum)
      .def_prop_ro("additive_miracle_curriculum",
                   &AttackDefenseBatch::additive_miracle_curriculum)
      .def_prop_ro("reflection_curriculum",
                   &AttackDefenseBatch::reflection_curriculum)
      .def_prop_ro("reflection_weapon_curriculum",
                   &AttackDefenseBatch::reflection_weapon_curriculum)
      .def_prop_ro("dual_role_curriculum",
                   &AttackDefenseBatch::dual_role_curriculum)
      .def_prop_ro("chance_weapon_curriculum",
                   &AttackDefenseBatch::chance_weapon_curriculum)
      .def_prop_ro("absorption_weapon_curriculum",
                   &AttackDefenseBatch::absorption_weapon_curriculum)
      .def_prop_ro("initial_mp", &AttackDefenseBatch::initial_mp)
      .def_prop_ro("global_feature_count",
                   &AttackDefenseBatch::global_feature_count)
      .def_prop_ro("global_features", &AttackDefenseBatch::global_features_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("player_features", &AttackDefenseBatch::player_features_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("player_mask", &AttackDefenseBatch::player_mask_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("hand_token_ids", &AttackDefenseBatch::hand_token_ids_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("hand_mask", &AttackDefenseBatch::hand_mask_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("hand_card_kinds", &AttackDefenseBatch::hand_card_kinds_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("hand_elements", &AttackDefenseBatch::hand_elements_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("action_mask", &AttackDefenseBatch::action_mask_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("active_players", &AttackDefenseBatch::active_players_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("phases", &AttackDefenseBatch::phases_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("pending_attacks", &AttackDefenseBatch::pending_attacks_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("pending_elements",
                   &AttackDefenseBatch::pending_elements_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("pending_reflected",
                   &AttackDefenseBatch::pending_reflected_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("selected_hand_mask",
                   &AttackDefenseBatch::selected_hand_mask_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("selected_counts", &AttackDefenseBatch::selected_counts_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("selected_values", &AttackDefenseBatch::selected_values_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("selected_elements",
                   &AttackDefenseBatch::selected_elements_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("terminal_returns",
                   &AttackDefenseBatch::terminal_returns_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("terminated", &AttackDefenseBatch::terminated_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("episode_ids", &AttackDefenseBatch::episode_ids_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("turn_numbers", &AttackDefenseBatch::turn_numbers_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("magic_points", &AttackDefenseBatch::magic_points_view,
                   nb::rv_policy::reference_internal)
      .def("reset", &AttackDefenseBatch::reset,
           nb::call_guard<nb::gil_scoped_release>())
      .def("reset_done", &AttackDefenseBatch::reset_done,
           nb::call_guard<nb::gil_scoped_release>())
      .def("step", &AttackDefenseBatch::step, nb::arg("actions"),
           nb::call_guard<nb::gil_scoped_release>());

  nb::class_<ElementalAttackDefenseBatch, AttackDefenseBatch>(
      module, "ElementalAttackDefenseBatch")
      .def(nb::init<std::size_t, godfield_sim::TokenInput,
                    godfield_sim::ValueInput, godfield_sim::ElementInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::ElementInput, std::uint64_t, std::uint16_t>(),
           nb::arg("batch_size"), nb::arg("weapon_token_ids"),
           nb::arg("attack_values"), nb::arg("weapon_elements"),
           nb::arg("armor_token_ids"), nb::arg("defense_values"),
           nb::arg("armor_elements"), nb::arg("seed") = 67U,
           nb::arg("initial_hp") = 40U);

  nb::class_<ComboAttackDefenseBatch, AttackDefenseBatch>(
      module, "ComboAttackDefenseBatch")
      .def(nb::init<std::size_t, godfield_sim::TokenInput,
                    godfield_sim::ValueInput, godfield_sim::ElementInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::ElementInput, godfield_sim::TokenInput,
                    godfield_sim::ValueInput, godfield_sim::ElementInput,
                    std::uint64_t, std::uint16_t>(),
           nb::arg("batch_size"), nb::arg("weapon_token_ids"),
           nb::arg("attack_values"), nb::arg("weapon_elements"),
           nb::arg("booster_token_ids"), nb::arg("booster_values"),
           nb::arg("booster_elements"), nb::arg("armor_token_ids"),
           nb::arg("defense_values"), nb::arg("armor_elements"),
           nb::arg("seed") = 67U, nb::arg("initial_hp") = 40U);

  nb::class_<ResourceAttackDefenseBatch, AttackDefenseBatch>(
      module, "ResourceAttackDefenseBatch")
      .def(nb::init<std::size_t, godfield_sim::TokenInput,
                    godfield_sim::ValueInput, godfield_sim::ElementInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::ElementInput, godfield_sim::TokenInput,
                    godfield_sim::ValueInput, godfield_sim::ElementInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::ElementInput, godfield_sim::ValueInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::ValueInput, std::uint64_t, std::uint16_t,
                    std::uint16_t>(),
           nb::arg("batch_size"), nb::arg("weapon_token_ids"),
           nb::arg("attack_values"), nb::arg("weapon_elements"),
           nb::arg("booster_token_ids"), nb::arg("booster_values"),
           nb::arg("booster_elements"), nb::arg("armor_token_ids"),
           nb::arg("defense_values"), nb::arg("armor_elements"),
           nb::arg("hp_utility_token_ids"), nb::arg("hp_utility_values"),
           nb::arg("mp_utility_token_ids"), nb::arg("mp_utility_values"),
           nb::arg("attack_miracle_token_ids"),
           nb::arg("attack_miracle_values"), nb::arg("attack_miracle_elements"),
           nb::arg("attack_miracle_costs"), nb::arg("hp_miracle_token_ids"),
           nb::arg("hp_miracle_values"), nb::arg("hp_miracle_costs"),
           nb::arg("seed") = 67U, nb::arg("initial_hp") = 40U,
           nb::arg("initial_mp") = 10U);

  nb::class_<StochasticResourceAttackDefenseBatch, AttackDefenseBatch>(
      module, "StochasticResourceAttackDefenseBatch")
      .def(nb::init<std::size_t, godfield_sim::TokenInput,
                    godfield_sim::ValueInput, godfield_sim::ElementInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::ElementInput, godfield_sim::TokenInput,
                    godfield_sim::ValueInput, godfield_sim::ElementInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::ElementInput, godfield_sim::ValueInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::ValueInput, godfield_sim::TokenInput,
                    godfield_sim::ValueInput, godfield_sim::ElementInput,
                    godfield_sim::ValueInput, godfield_sim::ValueInput,
                    godfield_sim::TokenInput, godfield_sim::ValueInput,
                    godfield_sim::ElementInput, godfield_sim::ValueInput,
                    std::uint64_t, std::uint16_t, std::uint16_t>(),
           nb::arg("batch_size"), nb::arg("weapon_token_ids"),
           nb::arg("attack_values"), nb::arg("weapon_elements"),
           nb::arg("booster_token_ids"), nb::arg("booster_values"),
           nb::arg("booster_elements"), nb::arg("armor_token_ids"),
           nb::arg("defense_values"), nb::arg("armor_elements"),
           nb::arg("hp_utility_token_ids"), nb::arg("hp_utility_values"),
           nb::arg("mp_utility_token_ids"), nb::arg("mp_utility_values"),
           nb::arg("attack_miracle_token_ids"),
           nb::arg("attack_miracle_values"), nb::arg("attack_miracle_elements"),
           nb::arg("attack_miracle_costs"), nb::arg("hp_miracle_token_ids"),
           nb::arg("hp_miracle_values"), nb::arg("hp_miracle_costs"),
           nb::arg("chance_miracle_token_ids"),
           nb::arg("chance_miracle_values"), nb::arg("chance_miracle_elements"),
           nb::arg("chance_miracle_costs"), nb::arg("chance_miracle_hit_rates"),
           nb::arg("effect_miracle_token_ids"),
           nb::arg("effect_miracle_values"), nb::arg("effect_miracle_elements"),
           nb::arg("effect_miracle_costs"), nb::arg("seed") = 67U,
           nb::arg("initial_hp") = 40U, nb::arg("initial_mp") = 10U);

  nb::class_<ExpandedResourceAttackDefenseBatch, AttackDefenseBatch>(
      module, "ExpandedResourceAttackDefenseBatch")
      .def(
          nb::init<std::size_t, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ValueInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::ValueInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   std::uint64_t, std::uint16_t, std::uint16_t>(),
          nb::arg("batch_size"), nb::arg("weapon_token_ids"),
          nb::arg("attack_values"), nb::arg("weapon_elements"),
          nb::arg("booster_token_ids"), nb::arg("booster_values"),
          nb::arg("booster_elements"), nb::arg("armor_token_ids"),
          nb::arg("defense_values"), nb::arg("armor_elements"),
          nb::arg("hp_utility_token_ids"), nb::arg("hp_utility_values"),
          nb::arg("mp_utility_token_ids"), nb::arg("mp_utility_values"),
          nb::arg("attack_miracle_token_ids"), nb::arg("attack_miracle_values"),
          nb::arg("attack_miracle_elements"), nb::arg("attack_miracle_costs"),
          nb::arg("hp_miracle_token_ids"), nb::arg("hp_miracle_values"),
          nb::arg("hp_miracle_costs"), nb::arg("chance_miracle_token_ids"),
          nb::arg("chance_miracle_values"), nb::arg("chance_miracle_elements"),
          nb::arg("chance_miracle_costs"), nb::arg("chance_miracle_hit_rates"),
          nb::arg("effect_miracle_token_ids"), nb::arg("effect_miracle_values"),
          nb::arg("effect_miracle_elements"), nb::arg("effect_miracle_costs"),
          nb::arg("additive_miracle_token_ids"),
          nb::arg("additive_miracle_values"),
          nb::arg("additive_miracle_elements"),
          nb::arg("additive_miracle_costs"), nb::arg("seed") = 67U,
          nb::arg("initial_hp") = 40U, nb::arg("initial_mp") = 10U);

  nb::class_<ReflectionResourceAttackDefenseBatch, AttackDefenseBatch>(
      module, "ReflectionResourceAttackDefenseBatch")
      .def(
          nb::init<std::size_t, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ValueInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::ValueInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, std::uint64_t, std::uint16_t,
                   std::uint16_t>(),
          nb::arg("batch_size"), nb::arg("weapon_token_ids"),
          nb::arg("attack_values"), nb::arg("weapon_elements"),
          nb::arg("booster_token_ids"), nb::arg("booster_values"),
          nb::arg("booster_elements"), nb::arg("armor_token_ids"),
          nb::arg("defense_values"), nb::arg("armor_elements"),
          nb::arg("hp_utility_token_ids"), nb::arg("hp_utility_values"),
          nb::arg("mp_utility_token_ids"), nb::arg("mp_utility_values"),
          nb::arg("attack_miracle_token_ids"), nb::arg("attack_miracle_values"),
          nb::arg("attack_miracle_elements"), nb::arg("attack_miracle_costs"),
          nb::arg("hp_miracle_token_ids"), nb::arg("hp_miracle_values"),
          nb::arg("hp_miracle_costs"), nb::arg("chance_miracle_token_ids"),
          nb::arg("chance_miracle_values"), nb::arg("chance_miracle_elements"),
          nb::arg("chance_miracle_costs"), nb::arg("chance_miracle_hit_rates"),
          nb::arg("effect_miracle_token_ids"), nb::arg("effect_miracle_values"),
          nb::arg("effect_miracle_elements"), nb::arg("effect_miracle_costs"),
          nb::arg("additive_miracle_token_ids"),
          nb::arg("additive_miracle_values"),
          nb::arg("additive_miracle_elements"),
          nb::arg("additive_miracle_costs"),
          nb::arg("reflection_armor_token_ids"), nb::arg("seed") = 67U,
          nb::arg("initial_hp") = 40U, nb::arg("initial_mp") = 10U);

  nb::class_<ReflectionWeaponResourceAttackDefenseBatch, AttackDefenseBatch>(
      module, "ReflectionWeaponResourceAttackDefenseBatch")
      .def(
          nb::init<std::size_t, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ValueInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::ValueInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, std::uint64_t, std::uint16_t,
                   std::uint16_t>(),
          nb::arg("batch_size"), nb::arg("weapon_token_ids"),
          nb::arg("attack_values"), nb::arg("weapon_elements"),
          nb::arg("booster_token_ids"), nb::arg("booster_values"),
          nb::arg("booster_elements"), nb::arg("armor_token_ids"),
          nb::arg("defense_values"), nb::arg("armor_elements"),
          nb::arg("hp_utility_token_ids"), nb::arg("hp_utility_values"),
          nb::arg("mp_utility_token_ids"), nb::arg("mp_utility_values"),
          nb::arg("attack_miracle_token_ids"), nb::arg("attack_miracle_values"),
          nb::arg("attack_miracle_elements"), nb::arg("attack_miracle_costs"),
          nb::arg("hp_miracle_token_ids"), nb::arg("hp_miracle_values"),
          nb::arg("hp_miracle_costs"), nb::arg("chance_miracle_token_ids"),
          nb::arg("chance_miracle_values"), nb::arg("chance_miracle_elements"),
          nb::arg("chance_miracle_costs"), nb::arg("chance_miracle_hit_rates"),
          nb::arg("effect_miracle_token_ids"), nb::arg("effect_miracle_values"),
          nb::arg("effect_miracle_elements"), nb::arg("effect_miracle_costs"),
          nb::arg("additive_miracle_token_ids"),
          nb::arg("additive_miracle_values"),
          nb::arg("additive_miracle_elements"),
          nb::arg("additive_miracle_costs"),
          nb::arg("reflection_armor_token_ids"),
          nb::arg("reflection_weapon_token_ids"),
          nb::arg("reflection_weapon_values"), nb::arg("seed") = 67U,
          nb::arg("initial_hp") = 40U, nb::arg("initial_mp") = 10U);

  nb::class_<DualRoleResourceAttackDefenseBatch, AttackDefenseBatch>(
      module, "DualRoleResourceAttackDefenseBatch")
      .def(
          nb::init<std::size_t, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ValueInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::ValueInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, std::uint64_t, std::uint16_t,
                   std::uint16_t>(),
          nb::arg("batch_size"), nb::arg("weapon_token_ids"),
          nb::arg("attack_values"), nb::arg("weapon_elements"),
          nb::arg("booster_token_ids"), nb::arg("booster_values"),
          nb::arg("booster_elements"), nb::arg("armor_token_ids"),
          nb::arg("defense_values"), nb::arg("armor_elements"),
          nb::arg("hp_utility_token_ids"), nb::arg("hp_utility_values"),
          nb::arg("mp_utility_token_ids"), nb::arg("mp_utility_values"),
          nb::arg("attack_miracle_token_ids"), nb::arg("attack_miracle_values"),
          nb::arg("attack_miracle_elements"), nb::arg("attack_miracle_costs"),
          nb::arg("hp_miracle_token_ids"), nb::arg("hp_miracle_values"),
          nb::arg("hp_miracle_costs"), nb::arg("chance_miracle_token_ids"),
          nb::arg("chance_miracle_values"), nb::arg("chance_miracle_elements"),
          nb::arg("chance_miracle_costs"), nb::arg("chance_miracle_hit_rates"),
          nb::arg("effect_miracle_token_ids"), nb::arg("effect_miracle_values"),
          nb::arg("effect_miracle_elements"), nb::arg("effect_miracle_costs"),
          nb::arg("additive_miracle_token_ids"),
          nb::arg("additive_miracle_values"),
          nb::arg("additive_miracle_elements"),
          nb::arg("additive_miracle_costs"),
          nb::arg("reflection_armor_token_ids"),
          nb::arg("reflection_weapon_token_ids"),
          nb::arg("reflection_weapon_values"), nb::arg("dual_role_token_ids"),
          nb::arg("dual_role_attack_values"),
          nb::arg("dual_role_defense_values"), nb::arg("dual_role_elements"),
          nb::arg("seed") = 67U, nb::arg("initial_hp") = 40U,
          nb::arg("initial_mp") = 10U);

  nb::class_<ChanceWeaponResourceAttackDefenseBatch, AttackDefenseBatch>(
      module, "ChanceWeaponResourceAttackDefenseBatch")
      .def(
          nb::init<std::size_t, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ValueInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::ValueInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::ValueInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   std::uint64_t, std::uint16_t, std::uint16_t>(),
          nb::arg("batch_size"), nb::arg("weapon_token_ids"),
          nb::arg("attack_values"), nb::arg("weapon_elements"),
          nb::arg("booster_token_ids"), nb::arg("booster_values"),
          nb::arg("booster_elements"), nb::arg("armor_token_ids"),
          nb::arg("defense_values"), nb::arg("armor_elements"),
          nb::arg("hp_utility_token_ids"), nb::arg("hp_utility_values"),
          nb::arg("mp_utility_token_ids"), nb::arg("mp_utility_values"),
          nb::arg("attack_miracle_token_ids"), nb::arg("attack_miracle_values"),
          nb::arg("attack_miracle_elements"), nb::arg("attack_miracle_costs"),
          nb::arg("hp_miracle_token_ids"), nb::arg("hp_miracle_values"),
          nb::arg("hp_miracle_costs"), nb::arg("chance_miracle_token_ids"),
          nb::arg("chance_miracle_values"), nb::arg("chance_miracle_elements"),
          nb::arg("chance_miracle_costs"), nb::arg("chance_miracle_hit_rates"),
          nb::arg("effect_miracle_token_ids"), nb::arg("effect_miracle_values"),
          nb::arg("effect_miracle_elements"), nb::arg("effect_miracle_costs"),
          nb::arg("additive_miracle_token_ids"),
          nb::arg("additive_miracle_values"),
          nb::arg("additive_miracle_elements"),
          nb::arg("additive_miracle_costs"),
          nb::arg("reflection_armor_token_ids"),
          nb::arg("reflection_weapon_token_ids"),
          nb::arg("reflection_weapon_values"), nb::arg("dual_role_token_ids"),
          nb::arg("dual_role_attack_values"),
          nb::arg("dual_role_defense_values"), nb::arg("dual_role_elements"),
          nb::arg("chance_weapon_token_ids"),
          nb::arg("chance_weapon_attack_values"),
          nb::arg("chance_weapon_elements"), nb::arg("chance_weapon_hit_rates"),
          nb::arg("chance_dual_role_token_ids"),
          nb::arg("chance_dual_role_attack_values"),
          nb::arg("chance_dual_role_defense_values"),
          nb::arg("chance_dual_role_elements"),
          nb::arg("chance_dual_role_hit_rates"), nb::arg("seed") = 67U,
          nb::arg("initial_hp") = 40U, nb::arg("initial_mp") = 10U);

  nb::class_<AbsorptionWeaponResourceAttackDefenseBatch, AttackDefenseBatch>(
      module, "AbsorptionWeaponResourceAttackDefenseBatch")
      .def(
          nb::init<std::size_t, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ValueInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::ValueInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::ValueInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::ValueInput,
                   godfield_sim::TokenInput, godfield_sim::ValueInput,
                   godfield_sim::ElementInput, godfield_sim::TokenInput,
                   godfield_sim::ValueInput, godfield_sim::ElementInput,
                   godfield_sim::ValueInput, std::uint64_t, std::uint16_t,
                   std::uint16_t>(),
          nb::arg("batch_size"), nb::arg("weapon_token_ids"),
          nb::arg("attack_values"), nb::arg("weapon_elements"),
          nb::arg("booster_token_ids"), nb::arg("booster_values"),
          nb::arg("booster_elements"), nb::arg("armor_token_ids"),
          nb::arg("defense_values"), nb::arg("armor_elements"),
          nb::arg("hp_utility_token_ids"), nb::arg("hp_utility_values"),
          nb::arg("mp_utility_token_ids"), nb::arg("mp_utility_values"),
          nb::arg("attack_miracle_token_ids"), nb::arg("attack_miracle_values"),
          nb::arg("attack_miracle_elements"), nb::arg("attack_miracle_costs"),
          nb::arg("hp_miracle_token_ids"), nb::arg("hp_miracle_values"),
          nb::arg("hp_miracle_costs"), nb::arg("chance_miracle_token_ids"),
          nb::arg("chance_miracle_values"), nb::arg("chance_miracle_elements"),
          nb::arg("chance_miracle_costs"), nb::arg("chance_miracle_hit_rates"),
          nb::arg("effect_miracle_token_ids"), nb::arg("effect_miracle_values"),
          nb::arg("effect_miracle_elements"), nb::arg("effect_miracle_costs"),
          nb::arg("additive_miracle_token_ids"),
          nb::arg("additive_miracle_values"),
          nb::arg("additive_miracle_elements"),
          nb::arg("additive_miracle_costs"),
          nb::arg("reflection_armor_token_ids"),
          nb::arg("reflection_weapon_token_ids"),
          nb::arg("reflection_weapon_values"), nb::arg("dual_role_token_ids"),
          nb::arg("dual_role_attack_values"),
          nb::arg("dual_role_defense_values"), nb::arg("dual_role_elements"),
          nb::arg("chance_weapon_token_ids"),
          nb::arg("chance_weapon_attack_values"),
          nb::arg("chance_weapon_elements"), nb::arg("chance_weapon_hit_rates"),
          nb::arg("chance_dual_role_token_ids"),
          nb::arg("chance_dual_role_attack_values"),
          nb::arg("chance_dual_role_defense_values"),
          nb::arg("chance_dual_role_elements"),
          nb::arg("chance_dual_role_hit_rates"),
          nb::arg("absorption_weapon_token_ids"),
          nb::arg("absorption_weapon_attack_values"),
          nb::arg("absorption_weapon_elements"),
          nb::arg("chance_absorption_weapon_token_ids"),
          nb::arg("chance_absorption_weapon_attack_values"),
          nb::arg("chance_absorption_weapon_elements"),
          nb::arg("chance_absorption_weapon_hit_rates"), nb::arg("seed") = 67U,
          nb::arg("initial_hp") = 40U, nb::arg("initial_mp") = 10U);
}
