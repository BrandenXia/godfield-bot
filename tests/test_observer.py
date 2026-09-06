from godfield_bot.domain.observation import Bounds, ScreenKind, VisibleImage
from godfield_bot.observer import classify_screen


def image(path: str) -> VisibleImage:
    return VisibleImage(path=path, bounds=Bounds(x=0, y=0, width=80, height=80))


def test_menu_takes_priority_over_hidden_home_labels() -> None:
    text = (
        "Prophet Name",
        "Genesis",
        "Training",
        "Hidden Melee",
        "Royal Duel",
    )

    assert classify_screen(text, ()) is ScreenKind.MENU


def test_bible_is_classified_from_reference_tabs() -> None:
    text = ("Elements", "Curses", "Trade", "Weapons")

    assert classify_screen(text, ()) is ScreenKind.BIBLE


def test_training_room_is_classified_from_screen_asset() -> None:
    text = ("Training", "Bible", "ロキ-67")

    assert classify_screen(text, (image("/images/screens/room.webp"),)) is ScreenKind.TRAINING_SETUP


def test_unknown_screen_fails_to_guess() -> None:
    assert (
        classify_screen(("Surprising new UI",), (image("/images/new.webp"),)) is ScreenKind.UNKNOWN
    )
