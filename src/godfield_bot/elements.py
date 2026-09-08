from typing import Literal

CombatElement = Literal[
    "non-element",
    "fire",
    "water",
    "wood",
    "stone",
    "light",
    "darkness",
]

COMBAT_ELEMENTS: tuple[CombatElement, ...] = (
    "non-element",
    "fire",
    "water",
    "wood",
    "stone",
    "light",
    "darkness",
)
COMBAT_ELEMENT_IDS: dict[CombatElement, int] = {
    element: index for index, element in enumerate(COMBAT_ELEMENTS)
}
ELEMENT_IMAGE_PATHS: dict[str, CombatElement] = {
    f"/images/elements/{element}.webp": element
    for element in COMBAT_ELEMENTS
    if element != "non-element"
}
