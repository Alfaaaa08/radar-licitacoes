import pytest

from radar.it_filter import find_it_terms, normalize


def test_normalize_removes_accents_and_case():
    assert normalize("Aquisição de LICENÇAS") == "aquisicao de licencas"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Aquisição de notebooks para a secretaria", ["notebook"]),
        ("CONTRATAÇÃO DE LICENÇAS DE SOFTWARE", ["software"]),
        ("Material de informática", ["informatica"]),
        ("Serviço de tecnologia da informação e comunicação", ["tecnologia da informacao"]),
        ("Aquisição de equipamentos de TI", ["TI"]),
        ("Solução de TIC para a prefeitura", ["TIC"]),
        ("Cabeamento   estruturado em prédios", ["cabeamento estruturado"]),
    ],
)
def test_finds_it_terms(text, expected):
    assert find_it_terms(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Aquisição de gêneros alimentícios para merenda escolar",
        "Contratação de servidor público temporário",
        "Serviços de limpeza e conservação",
        "Pregão para compra de pneus",
        "Aquisição de mobiliário e material de expediente",
        "Manutenção de ar condicionado e de itens do ti-ti",
        "",
        None,
    ],
)
def test_ignores_unrelated_objects(text):
    assert find_it_terms(text) == []


def test_terms_do_not_match_inside_other_words():
    assert find_it_terms("Fornecimento de softwarezinho") == []
    assert find_it_terms("Conserto de ferro de passar, internetwork") == []


def test_plural_forms_match():
    assert find_it_terms("Compra de computadores e impressoras") == ["computador", "impressora"]


def test_returns_every_distinct_term_once():
    terms = find_it_terms("Software de gestão com banco de dados e software de backup")
    assert terms == ["software", "banco de dados", "backup"]
