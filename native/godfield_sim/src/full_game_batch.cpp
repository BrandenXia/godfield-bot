#include "full_game_batch.h"
#include "curse_rules.h"

#include <algorithm>
#include <memory>
#include <set>
#include <stdexcept>

namespace godfield_sim {
namespace {
constexpr std::int64_t kMaximumCounter = 9007199254740991;
std::uint64_t random_word(std::uint64_t &state) noexcept {
  // Separate provisional SplitMix streams; not the official random stream.
  state += 0x9e3779b97f4a7c15ULL;
  auto word = state;
  word = (word ^ (word >> 30)) * 0xbf58476d1ce4e5b9ULL;
  word = (word ^ (word >> 27)) * 0x94d049bb133111ebULL;
  return word ^ (word >> 31);
}
std::uint64_t random_rank(std::uint64_t &state, std::uint64_t bound) {
  const auto threshold = (std::uint64_t{0} - bound) % bound;
  for (int attempt = 0; attempt < 16; ++attempt) {
    const auto value = random_word(state);
    if (value >= threshold)
      return value % bound;
  }
  throw std::runtime_error("full-game bounded random sampling failed");
}
template <typename Output, typename T>
Output owned_array(std::unique_ptr<T[]> buffer,
                   std::initializer_list<std::size_t> shape) {
  nb::capsule owner(buffer.get(), [](void *pointer) noexcept {
    delete[] static_cast<T *>(pointer);
  });
  const auto *data = buffer.release();
  return Output(data, shape, owner);
}
} // namespace

std::size_t
FullGameBatch::validate_dimensions(std::size_t batch_size, std::size_t players,
                                   std::size_t capacity, std::uint64_t turns,
                                   std::uint64_t decisions, std::uint16_t hp,
                                   std::uint16_t mp, std::uint16_t cp) {
  if (batch_size == 0 || players < 2 || players > 9 || capacity == 0 ||
      capacity > 512 || batch_size > 2000000 / players / capacity ||
      turns < 1 || turns > 1000000000 || decisions < 1 ||
      decisions > 1000000000 || hp < 1 || hp > 100 || mp > 100 || cp > 100) {
    throw std::invalid_argument(
        "full-game dimensions or resource bounds are invalid");
  }
  return batch_size;
}

FullGameBatch::FullGameBatch(std::size_t batch_size, std::size_t player_count,
                             InventoryProfileInput inventory_profiles,
                             InventoryInput utility_profiles,
                             std::size_t capacity, std::uint64_t seed,
                             std::uint64_t max_turns,
                             std::uint64_t max_decisions,
                             std::uint16_t initial_hp, std::uint16_t initial_mp,
                             std::uint16_t initial_cp)
    : batch_size_(validate_dimensions(batch_size, player_count, capacity,
                                      max_turns, max_decisions, initial_hp,
                                      initial_mp, initial_cp)),
      player_count_(player_count), capacity_(capacity), seed_(seed),
      max_turns_(max_turns), max_decisions_(max_decisions),
      initial_mp_(initial_mp), initial_cp_(initial_cp),
      statuses_(batch_size_, player_count, initial_hp),
      inventory_(batch_size_, player_count, inventory_profiles, capacity),
      resources_(batch_size_ * player_count, Resources{initial_mp, initial_cp}),
      episodes_(batch_size_) {
  if (utility_profiles.shape(0) == 0 || utility_profiles.shape(0) > 237) {
    throw std::invalid_argument("full-game utility profile count is invalid");
  }
  for (std::size_t row = 0; row < utility_profiles.shape(0); ++row) {
    const auto model = utility_profiles(row, 0);
    const Effect effect{utility_profiles(row, 1), utility_profiles(row, 2),
                        utility_profiles(row, 3)};
    const auto category = inventory_.category(model);
    if ((category != 3 && category != 4) || effect.kind < 1 ||
        effect.kind > 4 ||
        (effect.kind <= 2 && (effect.value < 1 || effect.value > 100)) ||
        (effect.kind > 2 && effect.value != 0) || effect.cost < 0 ||
        effect.cost > 100 || (category == 3 && effect.cost != 0) ||
        !effects_.emplace(model, effect).second) {
      throw std::invalid_argument(
          "full-game utility profile is invalid or duplicate");
    }
  }
  for (std::size_t env = 0; env < batch_size_; ++env) {
    episodes_[env] = fresh_episode(env, 1);
  }
}

FullGameBatch::Episode
FullGameBatch::fresh_episode(std::size_t env,
                             std::int64_t epoch) const noexcept {
  Episode episode;
  episode.epoch = epoch;
  episode.illness_rng =
      seed_ ^ (static_cast<std::uint64_t>(env) + 1) * 0x9e3779b97f4a7c15ULL ^
      static_cast<std::uint64_t>(epoch) * 0xbf58476d1ce4e5b9ULL;
  episode.gift_rng = episode.illness_rng ^ 0x94d049bb133111ebULL;
  return episode;
}

std::vector<std::size_t>
FullGameBatch::checked_environments(ActionInput environments) const {
  if (environments.shape(0) > batch_size_) {
    throw std::invalid_argument("full-game environment row limit exceeded");
  }
  std::vector<std::size_t> result;
  result.reserve(environments.shape(0));
  std::set<std::size_t> seen;
  for (std::size_t row = 0; row < environments.shape(0); ++row) {
    const auto env = environments(row);
    if (env < 0 || static_cast<std::uint64_t>(env) >= batch_size_ ||
        !seen.insert(static_cast<std::size_t>(env)).second) {
      throw std::invalid_argument(
          "full-game environment is invalid or duplicate");
    }
    result.push_back(static_cast<std::size_t>(env));
  }
  return result;
}

void FullGameBatch::require_setup(std::size_t environment) const {
  if (episodes_[environment].phase != 0) {
    throw std::invalid_argument("full-game setup is sealed after starting");
  }
}

void FullGameBatch::seed_players(ActionInput environments, ActionInput owners,
                                 InventoryInput state, ActionInput masks) {
  if (environments.shape(0) > statuses_.states_.size()) {
    throw std::invalid_argument("full-game setup owner row limit exceeded");
  }
  const auto indices = statuses_.checked_players(environments, owners, false);
  CurseDynamicsBatch::same_length(indices.size(), masks);
  if (state.shape(0) != indices.size()) {
    throw std::invalid_argument("full-game setup input lengths differ");
  }
  for (std::size_t row = 0; row < indices.size(); ++row) {
    require_setup(indices[row] / player_count_);
    if (state(row, 0) < 0 || state(row, 0) > 100 || state(row, 1) < 0 ||
        state(row, 1) > 100 || state(row, 2) < 0 || state(row, 2) > 100 ||
        state(row, 3) < 0 || state(row, 3) > 4 || masks(row) < 0 ||
        masks(row) > 15) {
      throw std::invalid_argument(
          "full-game setup resource or status is out of range");
    }
  }
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto index = indices[row];
    const auto before = statuses_.states_[index];
    statuses_.states_[index] = {state(row, 0), state(row, 3), masks(row), 0};
    resources_[index] = {state(row, 1), state(row, 2)};
    statuses_.record(index, 1, before);
  }
}

void FullGameBatch::seed_hand(std::size_t env, std::size_t owner,
                              InventoryInput items) {
  if (env >= batch_size_)
    throw std::invalid_argument("full-game environment is out of range");
  require_setup(env);
  inventory_.seed_hand(env, owner, items);
}

void FullGameBatch::deal_cards(ActionInput envs, ActionInput owners,
                               ActionInput instances, ActionInput models) {
  const auto indices = inventory_.checked_owners(envs, owners);
  DreamInventoryBatch::same_length(indices.size(), instances);
  DreamInventoryBatch::same_length(indices.size(), models);
  if (indices.empty())
    return;
  std::vector<std::int64_t> masks(indices.size()), disguise(indices.size(), 99),
      fake(indices.size(), 0);
  std::map<std::size_t, Episode> staged;
  for (std::size_t row = 0; row < indices.size(); ++row) {
    const auto env = indices[row] / player_count_;
    require_setup(env);
    const auto category = inventory_.category(models(row));
    auto [found, inserted] = staged.try_emplace(env, episodes_[env]);
    static_cast<void>(inserted);
    masks[row] = statuses_.states_[indices[row]][2];
    if ((masks[row] & kCurseDreamBit) != 0) {
      disguise[row] =
          static_cast<std::int64_t>(random_rank(found->second.gift_rng, 100));
      if (disguise[row] < 50) {
        fake[row] = static_cast<std::int64_t>(random_rank(
            found->second.gift_rng,
            inventory_.fake_pools_[static_cast<std::size_t>(category - 1)]
                .size()));
      }
    }
  }
  const ActionInput mask_input(masks.data(), {masks.size()});
  const ActionInput disguise_input(disguise.data(), {disguise.size()});
  const ActionInput fake_input(fake.data(), {fake.size()});
  inventory_.add_cards(envs, owners, instances, models, mask_input,
                       disguise_input, fake_input);
  // Gift mutation succeeded: committing its RNG cannot throw.
  for (const auto &[env, episode] : staged)
    episodes_[env] = episode;
}

void FullGameBatch::decide_outcome(std::size_t env, Episode &episode,
                                   std::size_t changed_owner,
                                   std::int64_t changed_hp) const noexcept {
  std::size_t living = 0;
  std::int64_t survivor = -1;
  for (std::size_t player = 0; player < player_count_; ++player) {
    const auto index = env * player_count_ + player;
    const auto hp =
        index == changed_owner ? changed_hp : statuses_.states_[index][0];
    if (hp > 0) {
      ++living;
      survivor = static_cast<std::int64_t>(player);
    }
  }
  if (living < 2) {
    episode.phase = 12;
    episode.outcome = living == 1 ? 1 : 2;
    episode.winner = survivor;
  }
}

void FullGameBatch::start_environments(ActionInput environments) {
  const auto indices = checked_environments(environments);
  for (const auto env : indices)
    require_setup(env);
  for (const auto env : indices) {
    auto &episode = episodes_[env];
    episode.phase = 1;
    decide_outcome(env, episode, statuses_.states_.size(), 0);
    if (episode.phase == 1) {
      for (std::size_t player = 0; player < player_count_; ++player) {
        if (statuses_.states_[env * player_count_ + player][0] > 0) {
          episode.actor = static_cast<std::int64_t>(player);
          break;
        }
      }
    }
  }
}

bool FullGameBatch::visible_utility_eligible(
    std::size_t owner, const Effect &effect) const noexcept {
  const auto &status = statuses_.states_[owner];
  if (status[0] == 0 || resources_[owner][0] < effect.cost)
    return false;
  if (effect.kind == 1)
    return status[0] < 100;
  if (effect.kind == 2)
    return resources_[owner][0] < 100;
  const auto stage = static_cast<std::uint8_t>(status[1]);
  const auto mask = static_cast<std::uint8_t>(status[2]);
  return cured_illness_stage(stage, effect.kind == 4) != stage ||
         cured_documented_mask(mask, effect.kind == 4) != mask;
}

FullGameBatch::Mutation FullGameBatch::prepare(FullGameCommandInput commands,
                                               std::size_t row) const {
  const auto env = commands(row, 0);
  if (env < 0 || static_cast<std::uint64_t>(env) >= batch_size_) {
    throw std::invalid_argument(
        "full-game command environment is out of range");
  }
  const auto index = static_cast<std::size_t>(env);
  const auto &episode = episodes_[index];
  if (episode.phase != 1 || commands(row, 1) != episode.epoch ||
      commands(row, 2) != episode.decision ||
      commands(row, 3) != episode.actor || commands(row, 4) != episode.phase) {
    throw std::invalid_argument(
        "full-game command is stale, mismatched or noninteractive");
  }
  const auto choice = commands(row, 5);
  const auto owner =
      index * player_count_ + static_cast<std::size_t>(episode.actor);
  if (choice < 0 ||
      static_cast<std::uint64_t>(choice) > inventory_.sizes_[owner]) {
    throw std::invalid_argument("full-game choice is not in the active hand");
  }
  Mutation mutation{
      index, owner, episode, statuses_.states_[owner], resources_[owner], {}};
  if (choice > 0) {
    const auto slot = static_cast<std::size_t>(choice - 1);
    auto item = inventory_.items_[owner * capacity_ + slot];
    const auto displayed = item[2] == 0 ? item[1] : item[2];
    const auto visible = effects_.find(displayed);
    if (visible == effects_.end() ||
        !visible_utility_eligible(owner, visible->second)) {
      throw std::invalid_argument(
          "full-game displayed utility choice is unavailable");
    }
    const auto actual = effects_.find(item[1]);
    if (actual == effects_.end()) {
      throw std::invalid_argument(
          "full-game actual card effect is not implemented yet");
    }
    const auto &effect = actual->second;
    if (mutation.resources[0] < effect.cost) {
      throw std::invalid_argument(
          "full-game hidden actual miracle cost is unaffordable");
    }
    mutation.resources[0] -= effect.cost;
    mutation.paid = static_cast<std::uint64_t>(effect.cost);
    if (effect.kind == 1)
      mutation.status[0] =
          std::min<std::int64_t>(100, mutation.status[0] + effect.value);
    else if (effect.kind == 2)
      mutation.resources[0] =
          std::min<std::int64_t>(100, mutation.resources[0] + effect.value);
    else {
      mutation.cure = true;
      mutation.status[1] = cured_illness_stage(
          static_cast<std::uint8_t>(mutation.status[1]), effect.kind == 4);
      mutation.status[2] = cured_documented_mask(
          static_cast<std::uint8_t>(mutation.status[2]), effect.kind == 4);
    }
    mutation.hand.reserve(inventory_.sizes_[owner]);
    for (std::size_t other = 0; other < inventory_.sizes_[owner]; ++other) {
      if (other != slot)
        mutation.hand.push_back(inventory_.items_[owner * capacity_ + other]);
    }
    if (inventory_.category(item[1]) == 4) {
      item[3] = 1;
      mutation.hand.push_back(item);
      mutation.miracles = 1;
    } else
      mutation.consumed = 1;
    if ((statuses_.states_[owner][2] & kCurseDreamBit) != 0 &&
        (mutation.status[2] & kCurseDreamBit) == 0) {
      for (auto &held : mutation.hand) {
        mutation.restored += held[2] != 0 ? 1 : 0;
        held[2] = 0;
      }
    }
    mutation.update_hand = true;
  }
  mutation.episode.last_choice = choice;
  finish(mutation);
  return mutation;
}

void FullGameBatch::finish(Mutation &mutation) const {
  auto &status = mutation.status;
  auto state = periodic_illness_effect({static_cast<std::uint16_t>(status[0]),
                                        static_cast<std::uint8_t>(status[1])});
  if (state.hp > 0 && state.stage != 0 &&
      random_rank(mutation.episode.illness_rng, 100) < 5) {
    state = worsen_illness(state);
  }
  status[0] = state.hp;
  status[1] = state.stage;
  ++status[3];
  auto &episode = mutation.episode;
  ++episode.turns;
  ++episode.commands;
  ++episode.decision;
  decide_outcome(mutation.environment, episode, mutation.owner, status[0]);
  if (episode.phase == 12)
    return; // Real endings take precedence over limits.
  if (static_cast<std::uint64_t>(episode.turns) >= max_turns_ ||
      static_cast<std::uint64_t>(episode.commands) >= max_decisions_) {
    episode.phase = 13;
    episode.outcome =
        static_cast<std::uint64_t>(episode.turns) >= max_turns_ ? 3 : 4;
    return;
  }
  for (std::size_t offset = 1; offset <= player_count_; ++offset) {
    const auto next =
        (static_cast<std::size_t>(episode.actor) + offset) % player_count_;
    if (statuses_.states_[mutation.environment * player_count_ + next][0] > 0) {
      episode.actor = static_cast<std::int64_t>(next);
      break;
    }
  }
}

void FullGameBatch::step(FullGameCommandInput commands) {
  if (commands.shape(0) > batch_size_)
    throw std::invalid_argument("full-game command row limit exceeded");
  std::vector<Mutation> staged;
  staged.reserve(commands.shape(0));
  std::set<std::size_t> seen;
  for (std::size_t row = 0; row < commands.shape(0); ++row) {
    auto mutation = prepare(commands, row);
    if (!seen.insert(mutation.environment).second)
      throw std::invalid_argument("duplicate full-game command environment");
    staged.push_back(std::move(mutation));
  }
  // Commit contains no validation, random draws, or allocation.
  for (const auto &mutation : staged) {
    const auto before = statuses_.states_[mutation.owner];
    statuses_.states_[mutation.owner] = mutation.status;
    statuses_.record(mutation.owner, 5, before);
    ++statuses_.tick_count_;
    statuses_.cure_count_ += mutation.cure ? 1 : 0;
    resources_[mutation.owner] = mutation.resources;
    if (mutation.update_hand)
      inventory_.commit_hand(mutation.owner, mutation.hand);
    inventory_.consumed_count_ += mutation.consumed;
    inventory_.miracle_use_count_ += mutation.miracles;
    inventory_.restored_count_ += mutation.restored;
    episodes_[mutation.environment] = mutation.episode;
    ++actions_;
    passes_ += mutation.update_hand ? 0 : 1;
    utilities_ += mutation.update_hand ? 1 : 0;
    mp_spent_ += mutation.paid;
  }
}

void FullGameBatch::reset_environments(ActionInput environments) {
  const auto indices = checked_environments(environments);
  for (const auto env : indices) {
    if (episodes_[env].epoch >= kMaximumCounter)
      throw std::invalid_argument("full-game episode epoch is exhausted");
  }
  for (const auto env : indices) {
    const auto first = env * player_count_;
    for (std::size_t player = 0; player < player_count_; ++player) {
      const auto index = first + player;
      statuses_.states_[index] = {statuses_.initial_hp_, 0, 0, 0};
      statuses_.transitions_[index] = {};
      resources_[index] = {initial_mp_, initial_cp_};
      inventory_.sizes_[index] = 0;
      std::fill_n(inventory_.items_.begin() +
                      static_cast<std::ptrdiff_t>(index * capacity_),
                  capacity_, DreamInventoryBatch::Item{});
    }
    episodes_[env] = fresh_episode(env, episodes_[env].epoch + 1);
  }
}

Int64_2D FullGameBatch::episode_snapshot() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 9);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto &episode = episodes_[env];
    const std::array<std::int64_t, 9> row{
        episode.epoch,  episode.decision, episode.actor,
        episode.phase,  episode.turns,    episode.outcome,
        episode.winner, episode.commands, episode.last_choice};
    std::copy(row.begin(), row.end(), buffer.get() + env * 9);
  }
  return owned_array<Int64_2D>(std::move(buffer), {batch_size_, 9});
}

CurseStateSnapshot FullGameBatch::diagnostic_players() const {
  auto buffer = std::make_unique<std::int64_t[]>(resources_.size() * 6);
  for (std::size_t index = 0; index < resources_.size(); ++index) {
    const auto &state = statuses_.states_[index];
    const std::array<std::int64_t, 6> row{state[0],
                                          resources_[index][0],
                                          resources_[index][1],
                                          state[1],
                                          state[2],
                                          state[3]};
    std::copy(row.begin(), row.end(), buffer.get() + index * 6);
  }
  return owned_array<CurseStateSnapshot>(std::move(buffer),
                                         {batch_size_, player_count_, 6});
}

ActorInventorySnapshot FullGameBatch::actor_hands() const {
  std::vector<std::int64_t> envs(batch_size_), actors(batch_size_);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    envs[env] = static_cast<std::int64_t>(env);
    actors[env] = episodes_[env].actor;
  }
  return inventory_.actor_hands(ActionInput(envs.data(), {batch_size_}),
                                ActionInput(actors.data(), {batch_size_}));
}

Bool2D FullGameBatch::choice_masks() const {
  auto buffer = std::make_unique<bool[]>(batch_size_ * (capacity_ + 1));
  for (std::size_t env = 0; env < batch_size_; ++env) {
    if (episodes_[env].phase != 1)
      continue;
    const auto owner =
        env * player_count_ + static_cast<std::size_t>(episodes_[env].actor);
    buffer[env * (capacity_ + 1)] = true;
    for (std::size_t slot = 0; slot < inventory_.sizes_[owner]; ++slot) {
      const auto &item = inventory_.items_[owner * capacity_ + slot];
      const auto found = effects_.find(item[2] == 0 ? item[1] : item[2]);
      if (found != effects_.end() &&
          visible_utility_eligible(owner, found->second)) {
        buffer[env * (capacity_ + 1) + slot + 1] = true;
      }
    }
  }
  return owned_array<Bool2D>(std::move(buffer), {batch_size_, capacity_ + 1});
}

CurseStateSnapshot FullGameBatch::player_observations() const {
  auto buffer = std::make_unique<std::int64_t[]>(batch_size_ * 9 * 8);
  for (std::size_t env = 0; env < batch_size_; ++env) {
    const auto actor = static_cast<std::size_t>(episodes_[env].actor);
    const auto actor_mask = static_cast<std::uint8_t>(
        statuses_.states_[env * player_count_ + actor][2]);
    for (std::size_t offset = 0; offset < 9; ++offset) {
      const auto output = (env * 9 + offset) * 8;
      if (offset >= player_count_) {
        buffer[output] = -1;
        continue;
      }
      const auto seat = (actor + offset) % player_count_;
      const auto owner = env * player_count_ + seat;
      buffer[output] = static_cast<std::int64_t>(seat);
      buffer[output + 1] = 1;
      if (fog_hides_other_player(actor_mask, offset == 0))
        continue;
      const auto &state = statuses_.states_[owner];
      buffer[output + 2] = 1;
      buffer[output + 3] = state[0];
      buffer[output + 4] = resources_[owner][0];
      buffer[output + 5] = resources_[owner][1];
      buffer[output + 6] = state[1];
      buffer[output + 7] = state[2];
    }
  }
  return owned_array<CurseStateSnapshot>(std::move(buffer),
                                         {batch_size_, 9, 8});
}

void bind_full_game(nb::module_ &module) {
  module.attr("FULL_GAME_KERNEL_SCHEMA_VERSION") = kFullGameKernelSchemaVersion;
  module.attr("FULL_GAME_COMMAND_SCHEMA_VERSION") =
      kFullGameKernelSchemaVersion;
  module.attr("FULL_GAME_OBSERVATION_SCHEMA_VERSION") =
      kFullGameKernelSchemaVersion;
  module.attr("FULL_GAME_RULESET_ID") = kFullGameRulesetId;
  nb::class_<FullGameBatch>(module, "FullGameBatch")
      .def(nb::init<std::size_t, std::size_t, InventoryProfileInput,
                    InventoryInput, std::size_t, std::uint64_t, std::uint64_t,
                    std::uint64_t, std::uint16_t, std::uint16_t,
                    std::uint16_t>(),
           nb::arg("batch_size"), nb::arg("player_count"),
           nb::arg("inventory_profiles").noconvert(),
           nb::arg("utility_profiles").noconvert(), nb::arg("capacity") = 512,
           nb::arg("seed") = 67, nb::arg("max_turns") = 1000,
           nb::arg("max_decisions") = 4000, nb::arg("initial_hp") = 40,
           nb::arg("initial_mp") = 10, nb::arg("initial_cp") = 0)
      .def("seed_players", &FullGameBatch::seed_players,
           nb::arg("environments").noconvert(), nb::arg("owners").noconvert(),
           nb::arg("hp_mp_cp_illness").noconvert(),
           nb::arg("curse_masks").noconvert())
      .def("seed_hand", &FullGameBatch::seed_hand, nb::arg("environment"),
           nb::arg("owner"), nb::arg("items").noconvert())
      .def("deal_cards", &FullGameBatch::deal_cards,
           nb::arg("environments").noconvert(), nb::arg("owners").noconvert(),
           nb::arg("instance_ids").noconvert(),
           nb::arg("model_ids").noconvert())
      .def("start_environments", &FullGameBatch::start_environments,
           nb::arg("environments").noconvert())
      .def("reset_environments", &FullGameBatch::reset_environments,
           nb::arg("environments").noconvert())
      .def("step", &FullGameBatch::step, nb::arg("commands").noconvert())
      .def("episode_snapshot", &FullGameBatch::episode_snapshot)
      .def("diagnostic_players", &FullGameBatch::diagnostic_players)
      .def("diagnostic_inventory", &FullGameBatch::diagnostic_inventory)
      .def("actor_hands", &FullGameBatch::actor_hands)
      .def("player_observations", &FullGameBatch::player_observations)
      .def("choice_masks", &FullGameBatch::choice_masks)
      .def_prop_ro("action_count", &FullGameBatch::action_count)
      .def_prop_ro("pass_count", &FullGameBatch::pass_count)
      .def_prop_ro("utility_count", &FullGameBatch::utility_count)
      .def_prop_ro("mp_spent", &FullGameBatch::mp_spent)
      .def_prop_ro("gift_count", &FullGameBatch::gift_count)
      .def_prop_ro("consumed_count", &FullGameBatch::consumed_count)
      .def_prop_ro("miracle_use_count", &FullGameBatch::miracle_use_count)
      .def_prop_ro("restored_count", &FullGameBatch::restored_count);
}

} // namespace godfield_sim
