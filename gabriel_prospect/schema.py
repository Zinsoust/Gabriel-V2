"""Shared schema constants for the prospect import preview."""

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1_000
MAX_COLUMNS = 100
MAX_HEADER_CHARS = 120
MAX_CELL_CHARS = 5_000

CANONICAL_FIELDS = (
    "company_name",
    "website",
    "domain",
    "agency_type",
    "services",
    "market_type",
    "employee_count",
    "country",
    "city",
    "contact_first_name",
    "contact_last_name",
    "contact_full_name",
    "job_title",
    "email",
    "phone",
    "linkedin_url",
)

FIELD_ALIASES = {
    "company_name": (
        "company_name", "company", "entreprise", "societe", "société",
        "organisation", "organization", "agence", "raison sociale",
    ),
    "website": ("website", "site", "site web", "url", "company website"),
    "domain": ("domain", "domaine", "nom de domaine"),
    "agency_type": (
        "agency_type", "type agence", "type d'agence", "type d’agence",
        "categorie", "catégorie", "activity", "activite", "activité",
    ),
    "services": (
        "services", "prestations", "offre", "offres", "expertises",
        "specialites", "spécialités",
    ),
    "market_type": ("market_type", "marche", "marché", "b2b b2c", "b2b/b2c"),
    "employee_count": (
        "employee_count", "employees", "effectif", "taille", "headcount",
        "nombre employes", "nombre employés",
    ),
    "country": ("country", "pays"),
    "city": ("city", "ville", "localite", "localité"),
    "contact_first_name": ("contact_first_name", "first_name", "firstname", "prenom", "prénom"),
    "contact_last_name": ("contact_last_name", "last_name", "lastname", "nom", "nom contact"),
    "contact_full_name": ("contact_full_name", "contact", "nom complet", "full_name", "full name"),
    "job_title": ("job_title", "title", "fonction", "poste", "role", "rôle"),
    "email": ("email", "e-mail", "mail", "email professionnel"),
    "phone": ("phone", "telephone", "téléphone", "tel", "mobile"),
    "linkedin_url": (
        "linkedin_url", "linkedin", "profil linkedin", "linkedin profile",
        "url linkedin",
    ),
}
