#pragma once

#include <algorithm>
#include <cstdint>

namespace godfield_sim {

// Source-pinned client display arithmetic. Scheduling, credit semantics and
// official payment validation belong to the caller, not this pure helper.
// Preconditions: nonnegative balances and amount, validated by the caller.
struct PaymentWallet {
  std::int64_t hp, mp, cp;
};

struct PaymentResult {
  PaymentWallet wallet;
  std::int64_t hp_debit, mp_debit, cp_debit, unpaid;
};

[[nodiscard]] inline constexpr PaymentResult
pay_cp_waterfall(PaymentWallet wallet, std::int64_t amount) noexcept {
  const auto cp = std::min(wallet.cp, amount);
  amount -= cp;
  const auto mp = std::min(wallet.mp, amount);
  amount -= mp;
  const auto hp = std::min(wallet.hp, amount);
  return {{wallet.hp - hp, wallet.mp - mp, wallet.cp - cp},
          hp,
          mp,
          cp,
          amount - hp};
}

// Local credit cap/timing remain provisional. Preconditions: amount and cap
// nonnegative, and 0 <= wallet.cp <= cap, validated by the caller.
struct CreditResult {
  PaymentWallet wallet;
  std::int64_t credited, capped;
};

[[nodiscard]] inline constexpr CreditResult
credit_cp_capped(PaymentWallet wallet, std::int64_t amount,
                 std::int64_t cap) noexcept {
  const auto credited = std::min(amount, cap - wallet.cp);
  wallet.cp += credited;
  return {wallet, credited, amount - credited};
}

} // namespace godfield_sim
