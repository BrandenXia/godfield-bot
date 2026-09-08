#pragma once

#include <cstddef>
#include <cstdint>

#include <nanobind/ndarray.h>

namespace godfield_sim {

namespace nb = nanobind;

inline constexpr std::size_t kPlayerCount = 2;
inline constexpr std::size_t kHandSlots = 9;
inline constexpr std::size_t kActionCount = 21;
inline constexpr std::size_t kForgiveActionIndex = 19;
inline constexpr std::size_t kGlobalFeatureCount = 6;
inline constexpr std::size_t kElementCount = 7;
inline constexpr std::size_t kElementalGlobalFeatureCount =
    kGlobalFeatureCount + kElementCount;
inline constexpr std::size_t kPlayerFeatureCount = 4;

using TokenInput = nb::ndarray<const std::uint32_t, nb::numpy, nb::shape<-1>,
                               nb::c_contig, nb::device::cpu>;
using ValueInput = nb::ndarray<const std::uint16_t, nb::numpy, nb::shape<-1>,
                               nb::c_contig, nb::device::cpu>;
using ElementInput = nb::ndarray<const std::uint8_t, nb::numpy, nb::shape<-1>,
                                 nb::c_contig, nb::device::cpu>;
using AttackInput = ValueInput;
using ActionInput = nb::ndarray<const std::int64_t, nb::numpy, nb::shape<-1>,
                                nb::c_contig, nb::device::cpu>;

using Float2D = nb::ndarray<const float, nb::numpy, nb::ndim<2>, nb::c_contig>;
using Float3D = nb::ndarray<const float, nb::numpy, nb::ndim<3>, nb::c_contig>;
using Bool1D = nb::ndarray<const bool, nb::numpy, nb::ndim<1>, nb::c_contig>;
using Bool2D = nb::ndarray<const bool, nb::numpy, nb::ndim<2>, nb::c_contig>;
using Int64_2D =
    nb::ndarray<const std::int64_t, nb::numpy, nb::ndim<2>, nb::c_contig>;
using UInt8_1D =
    nb::ndarray<const std::uint8_t, nb::numpy, nb::ndim<1>, nb::c_contig>;
using UInt8_2D =
    nb::ndarray<const std::uint8_t, nb::numpy, nb::ndim<2>, nb::c_contig>;
using UInt16_1D =
    nb::ndarray<const std::uint16_t, nb::numpy, nb::ndim<1>, nb::c_contig>;
using UInt64_1D =
    nb::ndarray<const std::uint64_t, nb::numpy, nb::ndim<1>, nb::c_contig>;

} // namespace godfield_sim
