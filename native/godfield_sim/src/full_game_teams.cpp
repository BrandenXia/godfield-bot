#include "full_game_batch.h"

#include <stdexcept>

namespace godfield_sim {

bool FullGameBatch::are_enemies(const Episode &episode, std::size_t source,
                                std::size_t target) noexcept {
  return source != target && (episode.teams[source] == 0 ||
                              episode.teams[source] != episode.teams[target]);
}

std::size_t
FullGameBatch::living_factions(const Mutation &mutation) const noexcept {
  std::bitset<14> factions;
  for (std::size_t seat = 0; seat < player_count_; ++seat)
    if (mutation.statuses[seat][0] > 0) {
      const auto team = mutation.episode.teams[seat];
      factions.set(team == 0 ? seat + 5 : static_cast<std::size_t>(team));
    }
  return factions.count();
}

void FullGameBatch::seed_teams(ActionInput environments, ActionInput owners,
                               ActionInput teams) {
  if (!teams_enabled_)
    throw std::invalid_argument(
        "full-game team setup requires explicit teams_enabled");
  if (environments.shape(0) > statuses_.states_.size())
    throw std::invalid_argument(
        "full-game team setup owner row limit exceeded");
  const auto indices = statuses_.checked_players(environments, owners, false);
  CurseDynamicsBatch::same_length(indices.size(), teams);
  for (std::size_t row = 0; row < indices.size(); ++row) {
    require_setup(indices[row] / player_count_);
    if (teams(row) < 0 || teams(row) > 4)
      throw std::invalid_argument("full-game team ID must be in 0..4");
  }
  for (std::size_t row = 0; row < indices.size(); ++row)
    episodes_[indices[row] / player_count_]
        .teams[indices[row] % player_count_] = teams(row);
}
} // namespace godfield_sim
