from app.integrations.fsp_registry import RegistryParticipant
from app.seed.demo_fsp import spread


def test_seed_spread_covers_weak_and_strong() -> None:
    """Сид берёт участников равномерно по силе истории: и пустые, и призёров."""
    items = [RegistryParticipant(id=f"fsp-{index}", events=index) for index in range(10)]
    picked = spread(items, 4)
    assert [item.id for item in picked] == ["fsp-0", "fsp-3", "fsp-6", "fsp-9"]
    assert spread(items, 0) == []
    assert spread(items[:2], 5) == items[:2]
