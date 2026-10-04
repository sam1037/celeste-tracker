import zipfile
from pathlib import Path

import pytest

from celeste_tracker.mods import scan_mods

SLOTS = Path(__file__).parent / "fixtures" / "slots"


def write_zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)


@pytest.fixture
def mods_dir(tmp_path):
    """A small Mods folder, built per test so no binary files live in the repo. Map .bin files are empty:
    the tracker only reads their names."""
    d = tmp_path / "Mods"
    d.mkdir()
    write_zip(d / "Sides.zip", {
        # Name isn't on the first line, and dependencies have their own (deeper) Name entries.
        "everest.yaml": "- DLL: Code/x.dll\n  Name: Sides Mod\n  Version: 1.0.0\n  Dependencies:\n    - Name: Everest\n",
        "Maps/Test/Sides/Forest.bin": b"",
        "Maps/Test/Sides/Forest-B.bin": b"",
        "Maps/Test/Sides/Forest-C.bin": b"",
        "Dialog/English.txt": "# titles\nTest_Sides= Side Set\nTest_Sides_Forest= The {#ff0000}Forest\n"
                              "Test_Sides_Forest_c_01= Deep Woods\n",
    })
    write_zip(d / "Collab.zip", {  # no everest.yaml: named after the zip
        "Maps/Test/Collab/Lobby.bin": b"",
        "Maps/Test/Collab/M1.bin": b"",
        "Maps/Test/Collab/M2.bin": b"",
        "Maps/Test/Collab/M3-D.bin": b"",  # a D side is a map of its own
    })
    write_zip(d / "AddOn.zip", {  # a second mod adding one map to the same set
        "everest.yaml": "- Name: Collab D Side\n",
        "Maps/Test/Collab/Extra-D.bin": b"",
    })
    blizzard = d / "BlizzardDir"  # an unzipped mod folder
    (blizzard / "Maps/Test/Blizzard").mkdir(parents=True)
    (blizzard / "Maps/Test/Blizzard/1-blizzard-B.bin").write_bytes(b"")
    (blizzard / "Maps/Test/Blizzard/1-blizzard-C.bin").write_bytes(b"")
    (blizzard / "everest.yaml").write_text("- Name: Blizzard\n")
    (d / "broken.zip").write_bytes(b"not a zip")
    (d / "blacklist.txt").write_text("")
    return d


@pytest.fixture
def mods(mods_dir):
    return scan_mods(mods_dir)
