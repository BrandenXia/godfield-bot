cmake_minimum_required(VERSION 3.18...4.4)
project(godfield_sim LANGUAGES CXX)

find_package(Python 3.12 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(nanobind CONFIG REQUIRED)

nanobind_add_module(
  _native
  NB_STATIC
  src/bindings.cpp
  src/fixed_attack_batch.cpp
)
target_compile_features(_native PRIVATE cxx_std_20)

if(MSVC)
  target_compile_options(_native PRIVATE /W4 /permissive-)
else()
  target_compile_options(_native PRIVATE -Wall -Wextra -Wconversion -Wshadow)
endif()

install(TARGETS _native LIBRARY DESTINATION godfield_sim)
