# Accetta esclusivamente avvisi che identificano un esito o un bollettino
# di nomina GPS. Non basta che una pagina contenga genericamente la parola GPS.
TITLE_RE = re.compile(
    r"\bbollettin\w*\b|"
    r"\besito\s+(?:del\s+)?(?:turno|nomine)\b|"
    r"\bnomine\s+(?:a\s+tempo\s+determinato|da\s+gps|gps)\b|"
    r"\bturno\s+\d+\b",
    re.I
)

GPS_RE = re.compile(
    r"\bgps\b|"
    r"graduatori\w*\s+provincial\w*|"
    r"supplenz\w*",
    re.I
)

# Esclusioni tassative: questi documenti non devono essere scaricati.
SKIP_RE = re.compile(
    r"\bata\b|\bdsga\b|personale\s+ata|"
    r"collaborator\w*|assistent\w*|"
    r"ga[eè]\b|ad\s+esaurimento|"
    r"immission\w*|\bin\s+ruolo|"
    r"concors\w*|interpell\w*|\bmad\b|"
    r"rettific\w*|errat\w*|"
    r"disponibilit\w*|"
    r"convocazion\w*|"
    r"revoc\w*|"
    r"integrazion\w*|"
    r"annullament\w*|"
    r"sostituzion\w*|"
    r"scorriment\w*|"
    r"graduatori\w*\s+definitiv\w*|"
    r"mobilit\w*|"
    r"assunzion\w*|"
    r"tempo\s+indeterminato|"
    r"posti\s+residu\w*|"
    r"cattedre\s+disponibil\w*",
    re.I
)

RETTIFICA_RE = re.compile(
    r"rettific\w*|errat\w*|revoc\w*|"
    r"integrazion\w*|annullament\w*|"
    r"modific\w*|sostituzion\w*",
    re.I
)

ESTERNI_NO = (
    "facebook.", "twitter.", "x.com", "whatsapp.",
    "t.me", "telegram.", "google.", "linkedin.",
    "instagram.", "youtube.", "orizzontescuola.",
    "mailto:", "tecnicadellascuola.", "wa.me"
)
