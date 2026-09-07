#include "fixed_attack_batch.h"

#include <nanobind/nanobind.h>

namespace nb = nanobind;
using godfield_sim::FixedAttackBatch;

NB_MODULE(_native, module) {
  module.doc() = "Native batched God Field curriculum kernels";
  module.attr("KERNEL_SCHEMA_VERSION") = godfield_sim::kKernelSchemaVersion;
  module.attr("OBSERVATION_SCHEMA_VERSION") =
      godfield_sim::kObservationSchemaVersion;
  module.attr("RULESET_ID") = godfield_sim::kRulesetId;
  module.attr("ACTION_COUNT") = godfield_sim::kActionCount;
  module.attr("HAND_SLOTS") = godfield_sim::kHandSlots;

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
}
