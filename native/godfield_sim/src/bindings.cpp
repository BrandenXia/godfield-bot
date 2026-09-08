#include "attack_defense_batch.h"
#include "fixed_attack_batch.h"

#include <nanobind/nanobind.h>

namespace nb = nanobind;
using godfield_sim::AttackDefenseBatch;
using godfield_sim::ElementalAttackDefenseBatch;
using godfield_sim::FixedAttackBatch;

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
      .def_prop_ro("terminal_returns",
                   &AttackDefenseBatch::terminal_returns_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("terminated", &AttackDefenseBatch::terminated_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("episode_ids", &AttackDefenseBatch::episode_ids_view,
                   nb::rv_policy::reference_internal)
      .def_prop_ro("turn_numbers", &AttackDefenseBatch::turn_numbers_view,
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
}
