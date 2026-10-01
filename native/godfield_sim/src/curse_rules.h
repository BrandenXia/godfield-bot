#pragma once

#include <algorithm>
#include <cstdint>

namespace godfield_sim {

// This pure, allocation-free kernel can be composed with either arena's state.
// The caller owns scheduling, random streams, resources, and terminal
// decisions.
// Validate living-player eligibility and stage ranges before invoking effects;
// these helpers deliberately preserve the legacy arithmetic without validation.
struct IllnessState {
  std::uint16_t hp;
  std::uint8_t stage; // None=0, Cold=1, Fever=2, Hell=3, Heaven=4.
};

inline constexpr std::uint8_t kCurseFogBit = 1;
inline constexpr std::uint8_t kCurseDreamBit = 2;
inline constexpr std::uint8_t kCurseFlashBit = 4;
inline constexpr std::uint8_t kCurseDarkCloudBit = 8;
inline constexpr std::uint8_t kCurseMask = 15;
inline constexpr std::uint8_t kDocumentedMildCurseMask =
    kCurseFogBit | kCurseFlashBit;

[[nodiscard]] inline constexpr IllnessState
worsen_illness(IllnessState state) noexcept {
  if (state.stage == 4) {
    state.hp = 0;
  } else if (state.stage != 0) {
    ++state.stage;
  }
  return state;
}

[[nodiscard]] inline constexpr IllnessState
inflict_illness(IllnessState state, std::uint8_t incoming_stage) noexcept {
  if (state.stage == 0) {
    state.stage = incoming_stage;
    return state;
  }
  return worsen_illness(state);
}

[[nodiscard]] inline constexpr IllnessState
periodic_illness_effect(IllnessState state) noexcept {
  if (state.stage == 0) {
    return state;
  }
  if (state.stage == 4) {
    state.hp = static_cast<std::uint16_t>(
        std::min<unsigned int>(100, static_cast<unsigned int>(state.hp) + 5U));
  } else {
    const std::uint16_t damage =
        state.stage == 1 ? 1 : (state.stage == 2 ? 2 : 5);
    state.hp =
        damage >= state.hp ? 0 : static_cast<std::uint16_t>(state.hp - damage);
  }
  return state;
}

[[nodiscard]] inline constexpr std::uint8_t
cured_illness_stage(std::uint8_t stage, bool all_curses) noexcept {
  return all_curses || stage <= 2 ? std::uint8_t{0} : stage;
}

[[nodiscard]] inline constexpr std::uint8_t
cured_documented_mask(std::uint8_t mask, bool all_curses) noexcept {
  return all_curses
             ? std::uint8_t{0}
             : static_cast<std::uint8_t>(mask & ~kDocumentedMildCurseMask);
}

} // namespace godfield_sim
