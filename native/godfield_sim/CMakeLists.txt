cmake_minimum_required(VERSION 3.18...4.4)
project(godfield_sim LANGUAGES CXX)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(nanobind CONFIG REQUIRED)

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
)
target_compile_features(_native PRIVATE cxx_std_20)

if(MSVC)
  target_compile_options(_native PRIVATE /W4 /permissive-)
else()
  target_compile_options(_native PRIVATE -Wall -Wextra -Wconversion -Wshadow)
endif()

install(TARGETS _native LIBRARY DESTINATION godfield_sim)
