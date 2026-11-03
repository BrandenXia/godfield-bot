#pragma once

#include <cstdint>
#include <stdexcept>

namespace godfield_sim::full_game_random {
inline constexpr std::int64_t kMaximumCounter = 9007199254740991;
inline std::uint64_t random_word(std::uint64_t &state) noexcept {
  state += 0x9e3779b97f4a7c15ULL;
  auto word = state;
  word = (word ^ (word >> 30)) * 0xbf58476d1ce4e5b9ULL;
  word = (word ^ (word >> 27)) * 0x94d049bb133111ebULL;
  return word ^ (word >> 31);
}
inline std::uint64_t random_rank(std::uint64_t &state, std::uint64_t bound) {
  if (bound == 0)
    throw std::invalid_argument("full-game random pool is empty");
  const auto threshold = (std::uint64_t{0} - bound) % bound;
  for (int attempt = 0; attempt < 16; ++attempt) {
    const auto value = random_word(state);
    if (value >= threshold)
      return value % bound;
  }
  throw std::runtime_error("full-game bounded random sampling failed");
}
} // namespace godfield_sim::full_game_random
