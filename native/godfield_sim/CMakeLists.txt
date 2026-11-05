cmake_minimum_required(VERSION 3.18...4.4)
project(godfield_sim LANGUAGES CXX)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(nanobind CONFIG REQUIRED)

# Embed the exact native build inputs, independently checked by local acceptance.
file(GLOB_RECURSE identity_sources CONFIGURE_DEPENDS RELATIVE "${CMAKE_CURRENT_SOURCE_DIR}"
  "src/*.cpp" "src/*.h" "src/*.hpp" "src/*.py" "src/*.pyi" "src/*.cmake" "src/py.typed")
list(APPEND identity_sources "CMakeLists.txt" "pyproject.toml")
list(SORT identity_sources)
set(identity_manifest "")
foreach(input IN LISTS identity_sources)
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/${input}")
  file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/${input}" input_hash)
  string(APPEND identity_manifest "${input}\n${input_hash}\n")
endforeach()
string(SHA256 identity_hash "${identity_manifest}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/build_identity.h"
  "#pragma once\n#define GODFIELD_BUILD_SOURCE_SHA256 \"${identity_hash}\"\n")

nanobind_add_module(
  _native
  NB_STATIC
  src/bindings.cpp
  src/attack_defense_batch.cpp
  src/fixed_attack_batch.cpp
  src/ordered_inventory.cpp
  src/provisional_soap.cpp
  src/provisional_guardian.cpp
  src/guardian_lifecycle_batch.cpp
  src/guardian_combat_batch.cpp
  src/guardian_turn_batch.cpp
  src/guardian_utility_turn_batch.cpp
  src/guardian_discard_turn_batch.cpp
  src/curse_dynamics_batch.cpp
  src/curse_decisions.cpp
  src/dream_inventory_batch.cpp
  src/full_game_batch.cpp
  src/full_game_events.cpp
  src/full_game_trade.cpp
  src/full_game_effects.cpp
  src/full_game_composition.cpp
  src/full_game_ineffective.cpp
  src/full_game_teams.cpp
  src/full_game_generated.cpp
)
target_compile_features(_native PRIVATE cxx_std_20)
target_include_directories(_native PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")

if(MSVC)
  target_compile_options(_native PRIVATE /W4 /permissive-)
else()
  target_compile_options(_native PRIVATE -Wall -Wextra -Wconversion -Wshadow)
endif()

install(TARGETS _native LIBRARY DESTINATION godfield_sim)
