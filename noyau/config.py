"""Configuration de l'application et emplacement du dossier de données.

Le dossier de données est **local** et entièrement sous le contrôle du
comptable. Par défaut il s'agit du sous-dossier `donnees/` situé à côté de
l'application, mais on peut le déplacer (clé USB, disque réseau, dossier
sauvegardé automatiquement…) via :

  * la variable d'environnement ``CABINET_IMMO_DONNEES`` ;
  * l'option en ligne de commande ``--donnees /chemin/vers/dossier`` ;
  * le fichier ``configuration.json`` placé à côté de l'application.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

APPLICATION = "Cabinet Immo"
VERSION = "1.8.2"

DEFAUTS = {
    "dossier_donnees": "donnees",
    "hote": "127.0.0.1",
    "port": 8781,
    "ouvrir_navigateur": True,
    "devise": "DZD",
    "symbole_devise": "DA",
    "duree_session_heures": 12,
    "sauvegarde_auto": True,
    "sauvegardes_a_conserver": 30,
    # Adresse d'un petit fichier JSON annonçant la dernière version publiée.
    # Vide par défaut : aucun appel réseau n'est alors effectué. Renseignée,
    # l'application prévient qu'une mise à jour existe.
    "url_versions": "",
}


class Configuration:
    def __init__(self, surcharges: dict | None = None):
        valeurs = dict(DEFAUTS)

        fichier = RACINE / "configuration.json"
        if fichier.exists():
            try:
                valeurs.update(json.loads(fichier.read_text(encoding="utf-8")))
            except (ValueError, OSError) as err:
                print(f"[config] Fichier configuration.json ignoré : {err}")

        env = os.environ.get("CABINET_IMMO_DONNEES")
        if env:
            valeurs["dossier_donnees"] = env
        if os.environ.get("CABINET_IMMO_PORT"):
            valeurs["port"] = int(os.environ["CABINET_IMMO_PORT"])
        if os.environ.get("CABINET_IMMO_HOTE"):
            valeurs["hote"] = os.environ["CABINET_IMMO_HOTE"]

        if surcharges:
            valeurs.update({c: v for c, v in surcharges.items() if v is not None})

        self._valeurs = valeurs

        chemin = Path(valeurs["dossier_donnees"]).expanduser()
        if not chemin.is_absolute():
            chemin = RACINE / chemin
        self.dossier_donnees = chemin.resolve()

    # -- accès --------------------------------------------------------------
    def __getitem__(self, cle):
        return self._valeurs[cle]

    def get(self, cle, defaut=None):
        return self._valeurs.get(cle, defaut)

    @property
    def base_de_donnees(self) -> Path:
        return self.dossier_donnees / "comptabilite.db"

    @property
    def dossier_pieces(self) -> Path:
        return self.dossier_donnees / "pieces_justificatives"

    @property
    def dossier_exports(self) -> Path:
        return self.dossier_donnees / "exports"

    @property
    def dossier_sauvegardes(self) -> Path:
        return self.dossier_donnees / "sauvegardes"

    @property
    def dossier_modeles(self) -> Path:
        return self.dossier_donnees / "modeles_documents"

    @property
    def journal_incidents(self) -> Path:
        return self.dossier_donnees / "journal.log"

    @property
    def dossier_web(self) -> Path:
        return RACINE / "web"

    @property
    def dossier_reference(self) -> Path:
        return RACINE / "reference"

    def prepare_dossiers(self) -> None:
        """Crée l'arborescence locale au premier lancement."""
        for dossier in (
            self.dossier_donnees,
            self.dossier_pieces,
            self.dossier_exports,
            self.dossier_sauvegardes,
            self.dossier_modeles,
        ):
            dossier.mkdir(parents=True, exist_ok=True)

        lisez_moi = self.dossier_donnees / "LISEZ-MOI.txt"
        if not lisez_moi.exists():
            lisez_moi.write_text(
                "DOSSIER DE DONNÉES — CABINET IMMO\n"
                "=================================\n\n"
                "Ce dossier contient l'intégralité de votre comptabilité.\n"
                "Il ne quitte jamais votre poste : aucune donnée n'est envoyée sur Internet.\n\n"
                "  comptabilite.db          la base de données (à sauvegarder en priorité)\n"
                "  pieces_justificatives/   les factures et documents scannés rattachés aux écritures\n"
                "  exports/                 les fichiers Excel/CSV produits par l'application\n"
                "  sauvegardes/             les copies de sécurité horodatées\n"
                "  modeles_documents/       vos modèles personnalisés\n\n"
                "SAUVEGARDE : copiez ce dossier entier sur un disque externe régulièrement,\n"
                "ou utilisez le menu « Sauvegarde » de l'application.\n"
                "Ne modifiez jamais comptabilite.db en dehors de l'application.\n",
                encoding="utf-8",
            )

    def resume(self) -> dict:
        return {
            "application": APPLICATION,
            "version": VERSION,
            "dossier_donnees": str(self.dossier_donnees),
            "base_de_donnees": str(self.base_de_donnees),
            "devise": self._valeurs["devise"],
            "symbole_devise": self._valeurs["symbole_devise"],
        }


config = Configuration()


#: Taille au-delà de laquelle le journal est reparti à zéro (1 Mio).
TAILLE_MAX_JOURNAL = 1024 * 1024


def journalise(categorie: str, message: str, trace: str | None = None) -> None:
    """Consigne un incident dans « donnees/journal.log ».

    Lancée par un raccourci Windows, l'application n'a pas de console : sans
    ce fichier, une erreur survenue chez l'utilisateur ne laisse aucune trace
    et devient impossible à diagnostiquer à distance.
    """
    import datetime
    try:
        config.prepare_dossiers()
        fichier = config.journal_incidents
        if fichier.exists() and fichier.stat().st_size > TAILLE_MAX_JOURNAL:
            fichier.replace(fichier.with_suffix(".log.1"))
        horodatage = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
        with fichier.open("a", encoding="utf-8") as flux:
            flux.write(f"[{horodatage}] {categorie} : {message}\n")
            if trace:
                flux.write("".join(f"    {l}\n" for l in trace.rstrip().splitlines()))
    except OSError:
        pass        # journaliser ne doit jamais faire échouer une opération
