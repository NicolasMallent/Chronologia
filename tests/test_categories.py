import json

import pytest

from chronologia.categories import (
    CategoryError,
    CategoryRegistry,
    default_registry,
    load_registry,
    save_registry,
)
from chronologia.csv_io import parse_events


def test_defauts_conformes_a_la_legende():
    registry = default_registry()
    assert len(registry) == 10
    assert registry.for_color("steelblue").name == "Législation internationale"
    assert registry.for_color("#FF0000").name == "Evènements historiques"  # = red
    assert registry.for_color("gray").name == "Syndicalisme agricole"


def test_categorie_implicite_pour_couleur_non_mappee():
    event = parse_events(b"start,end,title,color\n1900,1900,A,purple\n").events[0]
    assert default_registry().category_name(event) == "#800080"


def test_couleur_et_nom_uniques():
    registry = CategoryRegistry()
    registry.add("A", "red")
    with pytest.raises(CategoryError):
        registry.add("B", "#ff0000")  # même couleur résolue
    with pytest.raises(CategoryError):
        registry.add("a", "blue")  # même nom, casse ignorée
    with pytest.raises(CategoryError):
        registry.add("C", "yallow")
    with pytest.raises(CategoryError):
        registry.add("  ", "blue")


def test_ajout_modification_suppression():
    registry = default_registry()
    new = registry.add("Divers", "purple")
    assert registry.for_color("#800080") == new
    renamed = registry.update(new, "Autres", "purple")
    assert list(registry)[-1] == renamed
    registry.remove(renamed)
    assert registry.for_color("purple") is None


def test_persistance(tmp_path):
    path = tmp_path / "sub" / "categories.json"
    registry = default_registry()
    registry.add("Divers", "purple")
    save_registry(registry, path)
    loaded, warning = load_registry(path)
    assert warning is None
    assert list(loaded) == list(registry)
    assert not list(path.parent.glob("*.tmp"))


def test_fichier_absent_donne_les_defauts(tmp_path):
    registry, warning = load_registry(tmp_path / "absent.json")
    assert len(registry) == 10 and warning is None


@pytest.mark.parametrize(
    "content",
    [
        "pas du json",
        "{}",
        '{"categories": [{"name": "A"}]}',
        '{"categories": [{"name": "A", "color": "yallow"}]}',
    ],
)
def test_fichier_corrompu_garde_les_defauts_et_n_est_pas_ecrase(tmp_path, content):
    path = tmp_path / "categories.json"
    path.write_text(content, encoding="utf-8")
    registry, warning = load_registry(path)
    assert len(registry) == 10 and warning
    assert path.read_text(encoding="utf-8") == content


def test_json_est_stable():
    assert json.loads(default_registry().to_json())["version"] == 1


def test_deplacement_borne():
    registry = CategoryRegistry()
    a, b, c = (registry.add(n, col) for n, col in (("A", "red"), ("B", "blue"), ("C", "green")))
    registry.move(c, -1)
    assert [x.name for x in registry] == ["A", "C", "B"]
    registry.move(a, -5)
    registry.move(b, 5)
    assert [x.name for x in registry] == ["A", "C", "B"]


def test_erreurs_avec_code():
    registry = CategoryRegistry()
    registry.add("A", "red")
    for name, color, code in (
        ("", "blue", CategoryError.NAME_INVALID),
        ("B", "nope", CategoryError.COLOR_UNKNOWN),
        ("a", "blue", CategoryError.NAME_EXISTS),
        ("B", "#FF0000", CategoryError.COLOR_USED),
    ):
        with pytest.raises(CategoryError) as info:
            registry.check(name, color)
        assert info.value.code == code
