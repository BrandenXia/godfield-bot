#pragma once

#include <cstdint>

namespace godfield_sim {

// Pure arithmetic shared by the established guardian arena and separate engine.
// Callers validate element IDs (NE=0, fire=1, water=2, wood=3, stone=4,
// light=5, darkness=6) and own costs, card identity, scheduling and mutation.
[[nodiscard]] inline constexpr bool
armor_element_compatible(std::int64_t attack, std::int64_t defense) noexcept {
  if (attack == 5)
    return false;
  if (attack == 1)
    return defense == 2 || defense == 5;
  if (attack == 2)
    return defense == 1 || defense == 5;
  if (attack == 3)
    return defense == 4 || defense == 5;
  if (attack == 4)
    return defense == 3 || defense == 5;
  return true;
}

} // namespace godfield_sim
