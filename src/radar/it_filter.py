import re
import unicodedata

NORMALIZED_TERMS = (
    "tecnologia da informacao",
    "informatica",
    "software",
    "hardware",
    "sistema de informacao",
    "sistemas de informacao",
    "desenvolvimento de sistema",
    "sistema web",
    "aplicativo",
    "aplicacao web",
    "plataforma digital",
    "banco de dados",
    "data center",
    "datacenter",
    "nuvem",
    "cloud",
    "hospedagem",
    "computador",
    "microcomputador",
    "notebook",
    "desktop",
    "tablet",
    "impressora",
    "scanner",
    "servidor de rede",
    "storage",
    "switch",
    "roteador",
    "firewall",
    "antivirus",
    "seguranca da informacao",
    "ciberseguranca",
    "inteligencia artificial",
    "internet",
    "conectividade",
    "cabeamento estruturado",
    "rede logica",
    "rede de dados",
    "backup",
    "nobreak",
    "wifi",
    "wi-fi",
    "voip",
    "videoconferencia",
    "certificado digital",
    "assinatura digital",
    "erp",
)

CASE_SENSITIVE_PATTERNS = {
    "TI": re.compile(r"\bTI\b"),
    "TIC": re.compile(r"\bTICs?\b"),
}


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return without_accents.lower()


def build_pattern(term: str) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(word) for word in term.split())
    return re.compile(rf"(?<![a-z0-9]){body}(?:s|es)?(?![a-z0-9])")


TERM_PATTERNS = {term: build_pattern(term) for term in NORMALIZED_TERMS}


def find_it_terms(text: str | None) -> list[str]:
    if not text:
        return []
    normalized = normalize(text)
    found = [term for term, pattern in TERM_PATTERNS.items() if pattern.search(normalized)]
    found.extend(name for name, pattern in CASE_SENSITIVE_PATTERNS.items() if pattern.search(text))
    return found
