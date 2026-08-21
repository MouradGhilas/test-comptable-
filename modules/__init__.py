"""Modules métier. L'import de ce paquet enregistre toutes les routes de l'API."""

from . import systeme          # noqa: F401  installation, connexion, dossiers, exercices
from . import comptabilite     # noqa: F401  plan comptable, écritures, balance, clôture
from . import tiers            # noqa: F401  clients, fournisseurs, mandants, salariés
from . import facturation      # noqa: F401  factures, avoirs, règlements
from . import tresorerie       # noqa: F401  caisses, banques, rapprochement
from . import agence           # noqa: F401  biens, mandats, baux, gestion locative
from . import promotion        # noqa: F401  programmes, lots, VSP, coût de revient
from . import fiscalite        # noqa: F401  G50, TVA, IBS, obligations
from . import paie             # noqa: F401  salariés, bulletins, CNAS, IRG
from . import immobilisations  # noqa: F401  amortissements
from . import etats            # noqa: F401  bilan, TCR, flux de trésorerie
from . import documents        # noqa: F401  éditions imprimables
from . import fichiers         # noqa: F401  pièces jointes, sauvegardes
from . import rapports         # noqa: F401  résumés Telegram / courriel
from . import imports          # noqa: F401  reprise de données depuis Excel
from . import maj              # noqa: F401  mise à jour depuis l'application
from . import incidents        # noqa: F401  signalement d'un problème
from . import recherche        # noqa: F401  recherche globale, un seul champ
from . import sante            # noqa: F401  contrôles de santé du dossier
from . import annuelles        # noqa: F401  DAS et état des clients

__all__ = [
    "systeme", "comptabilite", "tiers", "facturation", "tresorerie", "agence",
    "promotion", "fiscalite", "paie", "immobilisations", "etats", "documents",
    "fichiers", "rapports", "recherche", "sante", "annuelles",
]
