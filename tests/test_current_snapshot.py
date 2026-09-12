import json
from pathlib import Path

from godfield_bot.domain.reference import BibleSnapshot
from godfield_bot.reference import (
    category_counts,
    plain_attack_booster_cards,
    plain_attack_weapon_cards,
    plain_attack_weapon_values,
    plain_chance_dual_role_weapon_cards,
    plain_chance_weapon_cards,
    plain_defense_armor_cards,
    plain_defense_armor_values,
    plain_dual_role_weapon_cards,
    plain_hp_utility_sundries,
    plain_mp_utility_sundries,
    verified_attack_booster_miracle_cards,
    verified_attack_miracle_cards,
    verified_attack_weapon_values,
    verified_browser_weapon_attacks,
    verified_chance_attack_miracle_cards,
    verified_cp_utility_miracle_cards,
    verified_effect_attack_miracle_cards,
    verified_hp_utility_miracle_cards,
    verified_reflection_armor_cards,
    verified_reflection_weapon_cards,
    verified_stochastic_hp_sundries,
)

SNAPSHOT_PATH = Path(__file__).parents[1] / "data" / "snapshots" / "2026-09-07" / "bible.json"


def test_committed_snapshot_matches_validated_live_catalog() -> None:
    snapshot = BibleSnapshot.model_validate(json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8")))

    assert snapshot.total_artifacts == 291
    assert snapshot.client.sha256 == (
        "764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd"
    )
    assert category_counts(snapshot) == {
        "weapons": 107,
        "armor": 78,
        "sundries": 19,
        "miracles": 30,
        "devils": 5,
        "guardians": 42,
        "phenomena": 10,
    }
    plain_attacks = plain_attack_weapon_values(snapshot)
    assert snapshot.schema_version == 2
    assert len(plain_attacks) == 18
    assert plain_attacks["bronze-club"] == 1
    assert plain_attacks["gravity-mace"] == 11
    plain_defenses = plain_defense_armor_values(snapshot)
    assert len(plain_defenses) == 15
    assert plain_defenses["iron-shield"] == 4
    assert plain_defenses["steel-shield"] == 8
    assert "flame-shield" not in plain_defenses
    elemental_attacks = plain_attack_weapon_cards(snapshot)
    assert len(elemental_attacks) == 39
    assert elemental_attacks["bronze-club"] == (1, "non-element")
    assert elemental_attacks["torch"] == (1, "fire")
    assert elemental_attacks["pri-pri-pricker"] == (1, "darkness")
    attack_boosters = plain_attack_booster_cards(snapshot)
    assert len(attack_boosters) == 17
    assert attack_boosters["blowgun"] == (1, "non-element")
    assert attack_boosters["piece-of-brightness"] == (1, "light")
    assert attack_boosters["abyss-dart"] == (5, "darkness")
    elemental_defenses = plain_defense_armor_cards(snapshot)
    assert len(elemental_defenses) == 47
    assert elemental_defenses["iron-shield"] == (4, "non-element")
    assert elemental_defenses["flame-shield"] == (5, "fire")
    assert elemental_defenses["shining-high-heels"] == (6, "light")
    verified_attacks = verified_attack_weapon_values(snapshot)
    assert len(verified_attacks) == 37
    assert verified_attacks["bouncing-sword"] == 5
    assert verified_attacks["reflection-sword"] == 10
    assert verified_attacks["moonlight-axe"] == 10
    assert verified_attacks["angel-sword"] == 13
    assert verified_attacks["legendary-scabbard"] == 13
    assert verified_attacks["saver-rod"] == 2
    assert verified_attacks["spiked-belt"] == 4
    assert verified_attacks["plate-of-strike"] == 5
    assert verified_attacks["elbow-sack"] == 6
    assert verified_attacks["sword-shield"] == 10
    assert verified_attacks["ghost-sword"] == 7
    assert verified_attacks["hell-scissors"] == 8
    assert verified_attacks["gale-sword"] == 9
    assert verified_attacks["bogus-spear"] == 10
    assert verified_attacks["hexagon-doom"] == 11
    assert verified_attacks["real-ghost-sword"] == 12
    assert verified_attacks["severe-gale-sword"] == 13
    assert "evil-broadsword" not in verified_attacks
    assert "saw-boom-boom" not in verified_attacks
    assert "spiritual-staff" not in verified_attacks
    assert "frozen-hammer" not in verified_attacks
    assert "flaming-roll" not in verified_attacks
    browser_attacks = verified_browser_weapon_attacks(snapshot)
    assert len(browser_attacks) == 107
    assert browser_attacks["torch"] == ("ATK1", 1.0)
    assert browser_attacks["sword-ware"] == ("ATK2", 2.0)
    assert browser_attacks["saw-boom-boom"] == ("ATK3", 6.0)
    assert browser_attacks["blowgun"] == ("ATK1", 1.0)
    assert browser_attacks["sky-harpoon"] == ("ATK9", 9.0)
    assert browser_attacks["shadow-hand"] == ("50%ATK2", 1.0)
    assert browser_attacks["spark-bag"] == ("75%ATK1", 0.75)
    assert browser_attacks["magical-stick"] == (
        "ATK{2\N{MULTIPLICATION SIGN}MP}",
        2.0,
    )
    assert browser_attacks["spiritual-staff"] == ("ATK12", 12.0)
    assert browser_attacks["evil-broadsword"] == ("ATK14", 14.0)
    assert browser_attacks["wand-of-ignition"] == ("ATK2", 2.0)
    assert browser_attacks["wand-of-mystic-water"] == ("ATK5", 5.0)
    assert browser_attacks["dangerous-pestle"] == ("ATK30", 30.0)
    assert browser_attacks["ascension-bow"] == (
        "25%ATK1",
        0.25,
        ("75%ATK30",),
    )
    frozen_hammer = next(
        artifact
        for artifact in snapshot.catalog["weapons"].items
        if artifact.asset == "frozen-hammer"
    )
    assert frozen_hammer.element_image_paths == ("/images/elements/water.webp",)
    verified_miracles = verified_attack_miracle_cards(snapshot)
    assert len(verified_miracles) == 6
    assert verified_miracles["ice"] == (4, 2, "water")
    assert verified_miracles["flame"] == (10, 5, "fire")
    assert verified_miracles["waterfall"] == (25, 12, "water")
    assert "absorption" not in verified_miracles
    assert "fireball" not in verified_miracles
    assert verified_attack_booster_miracle_cards(snapshot) == {
        "fireball": (2, 2, "fire"),
        "meteor": (10, 7, "light"),
    }
    assert verified_reflection_armor_cards(snapshot) == {"super-mirror"}
    assert verified_reflection_weapon_cards(snapshot) == {"reflection-sword": 10}
    assert plain_dual_role_weapon_cards(snapshot) == {
        "elbow-sack": (6, 3, "non-element"),
        "flaming-roll": (4, 4, "fire"),
        "legendary-scabbard": (13, 1, "non-element"),
        "plate-of-strike": (5, 7, "non-element"),
        "saver-rod": (2, 6, "non-element"),
        "spiked-belt": (4, 2, "non-element"),
        "sword-shield": (10, 10, "non-element"),
    }
    chance_weapons = plain_chance_weapon_cards(snapshot)
    assert len(chance_weapons) == 14
    assert chance_weapons["spark-bag"] == (75, 1, "fire")
    assert chance_weapons["shadow-hand"] == (50, 2, "darkness")
    assert chance_weapons["petit-saturn"] == (25, 20, "stone")
    assert "fog-fan" not in chance_weapons
    assert "vine-shoot" not in chance_weapons
    assert "ascension-bow" not in chance_weapons
    assert plain_chance_dual_role_weapon_cards(snapshot) == {
        "jinn-s-rocking-horse": (75, 8, 6, "wood")
    }
    assert verified_effect_attack_miracle_cards(snapshot) == {
        "absorption": (10, 10, "light", "absorbHP")
    }
    chance_miracles = verified_chance_attack_miracle_cards(snapshot)
    assert len(chance_miracles) == 6
    assert chance_miracles["smoke"] == (75, 5, 4, "fire")
    assert chance_miracles["thunder"] == (25, 10, 4, "light")
    assert "flash" not in chance_miracles
    assert verified_cp_utility_miracle_cards(snapshot) == {"treasure": (10, 5)}
    assert plain_hp_utility_sundries(snapshot) == {
        "smile-dew": 5,
        "heart-dew": 10,
        "romance-water": 15,
        "galaxy-geyser": 20,
    }
    assert plain_mp_utility_sundries(snapshot) == {
        "smile-flower": 5,
        "heart-flower": 10,
        "romance-fragrance": 15,
    }
    assert verified_hp_utility_miracle_cards(snapshot) == {"spring": (10, 7)}
    assert verified_stochastic_hp_sundries(snapshot) == {"thump-thump-tear": (10, 10)}
