"""Écriture de fichiers Excel (.xlsx) en Python pur.

Un .xlsx est une archive ZIP contenant du XML : on la fabrique avec
`zipfile` (bibliothèque standard), sans aucune dépendance externe.
Suffisant pour les besoins comptables : titres, en-têtes, nombres,
dates, formats monétaires, largeurs de colonnes, totaux en gras.
"""

from __future__ import annotations

import datetime
import io
import zipfile
from xml.sax.saxutils import escape

# Styles (index dans la feuille de styles ci-dessous)
NORMAL = 0
GRAS = 1
TITRE = 2
ENTETE = 3
MONNAIE = 4
MONNAIE_GRAS = 5
DATE = 6
POURCENT = 7
ENTIER = 8
TOTAL_MONNAIE = 9

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2">
<numFmt numFmtId="164" formatCode="#,##0.00\\ &quot;DA&quot;"/>
<numFmt numFmtId="165" formatCode="0.00%"/>
</numFmts>
<fonts count="4">
<font><sz val="10"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><name val="Calibri"/></font>
<font><b/><sz val="14"/><name val="Calibri"/></font>
<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E5F"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left/><right/><top style="thin"><color rgb="FF808080"/></top><bottom style="double"><color rgb="FF404040"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="10">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="3" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="164" fontId="1" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"/>
<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="164" fontId="1" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyBorder="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

_EPOQUE = datetime.date(1899, 12, 30)


def _lettre_colonne(index: int) -> str:
    lettres = ""
    index += 1
    while index:
        index, reste = divmod(index - 1, 26)
        lettres = chr(65 + reste) + lettres
    return lettres


class Cellule:
    __slots__ = ("valeur", "style")

    def __init__(self, valeur, style=NORMAL):
        self.valeur = valeur
        self.style = style


def monnaie(centimes, gras=False, total=False):
    """Cellule monétaire à partir d'un montant en centimes."""
    style = TOTAL_MONNAIE if total else (MONNAIE_GRAS if gras else MONNAIE)
    return Cellule((centimes or 0) / 100.0, style)


def texte(valeur, style=NORMAL):
    return Cellule(valeur, style)


def date_cel(iso):
    if not iso:
        return Cellule("")
    try:
        return Cellule(datetime.date.fromisoformat(str(iso)[:10]), DATE)
    except ValueError:
        return Cellule(str(iso))


def nombre(valeur, style=ENTIER):
    return Cellule(valeur, style)


class Feuille:
    def __init__(self, nom: str):
        self.nom = nom[:31].replace("/", "-").replace("\\", "-").replace("?", "")
        self.rangs: list[list] = []
        self.largeurs: dict[int, int] = {}
        self.figer_lignes = 0

    def ajoute(self, *cellules):
        self.rangs.append(list(cellules))
        return self

    def vide(self, n=1):
        for _ in range(n):
            self.rangs.append([])
        return self

    def titre(self, libelle):
        self.rangs.append([Cellule(libelle, TITRE)])
        return self

    def entetes(self, *libelles):
        self.rangs.append([Cellule(x, ENTETE) for x in libelles])
        self.figer_lignes = len(self.rangs)
        return self

    def largeur(self, index, valeur):
        self.largeurs[index] = valeur
        return self

    def largeurs_auto(self, *valeurs):
        for i, v in enumerate(valeurs):
            self.largeurs[i] = v
        return self


class Classeur:
    def __init__(self):
        self.feuilles: list[Feuille] = []

    def feuille(self, nom) -> Feuille:
        f = Feuille(nom)
        self.feuilles.append(f)
        return f

    # -- génération --------------------------------------------------------
    def _xml_feuille(self, feuille: Feuille) -> str:
        morceaux = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
        if feuille.largeurs:
            morceaux.append("<cols>")
            for index, largeur in sorted(feuille.largeurs.items()):
                morceaux.append(
                    f'<col min="{index + 1}" max="{index + 1}" width="{largeur}" customWidth="1"/>'
                )
            morceaux.append("</cols>")
        morceaux.append("<sheetData>")
        for i_rang, rang in enumerate(feuille.rangs, start=1):
            if not rang:
                morceaux.append(f'<row r="{i_rang}"/>')
                continue
            morceaux.append(f'<row r="{i_rang}">')
            for i_col, cellule in enumerate(rang):
                if cellule is None:
                    continue
                if not isinstance(cellule, Cellule):
                    cellule = Cellule(cellule)
                ref = f"{_lettre_colonne(i_col)}{i_rang}"
                style = f' s="{cellule.style}"' if cellule.style else ""
                valeur = cellule.valeur
                if valeur is None or valeur == "":
                    morceaux.append(f'<c r="{ref}"{style}/>')
                elif isinstance(valeur, bool):
                    morceaux.append(
                        f'<c r="{ref}"{style} t="inlineStr"><is><t>'
                        f'{"Oui" if valeur else "Non"}</t></is></c>'
                    )
                elif isinstance(valeur, (int, float)):
                    morceaux.append(f'<c r="{ref}"{style}><v>{valeur}</v></c>')
                elif isinstance(valeur, datetime.date):
                    jours = (valeur - _EPOQUE).days
                    morceaux.append(f'<c r="{ref}"{style}><v>{jours}</v></c>')
                else:
                    contenu = escape(str(valeur))
                    morceaux.append(
                        f'<c r="{ref}"{style} t="inlineStr"><is><t xml:space="preserve">'
                        f"{contenu}</t></is></c>"
                    )
            morceaux.append("</row>")
        morceaux.append("</sheetData>")
        if feuille.figer_lignes:
            morceaux.insert(
                2,
                f'<sheetViews><sheetView workbookViewId="0"><pane ySplit="{feuille.figer_lignes}" '
                f'topLeftCell="A{feuille.figer_lignes + 1}" activePane="bottomLeft" state="frozen"/>'
                "</sheetView></sheetViews>",
            )
        morceaux.append("</worksheet>")
        return "".join(morceaux)

    def octets(self) -> bytes:
        if not self.feuilles:
            self.feuille("Feuille1")
        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                + "".join(
                    f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    for i in range(1, len(self.feuilles) + 1)
                )
                + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                "</Types>",
            )
            zf.writestr(
                "_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                "</Relationships>",
            )
            feuilles_xml = "".join(
                f'<sheet name="{escape(f.nom)}" sheetId="{i}" r:id="rId{i}"/>'
                for i, f in enumerate(self.feuilles, start=1)
            )
            zf.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f"<sheets>{feuilles_xml}</sheets></workbook>",
            )
            relations = "".join(
                f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(self.feuilles) + 1)
            )
            zf.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + relations
                + f'<Relationship Id="rId{len(self.feuilles) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                "</Relationships>",
            )
            zf.writestr("xl/styles.xml", _STYLES)
            for i, feuille in enumerate(self.feuilles, start=1):
                zf.writestr(f"xl/worksheets/sheet{i}.xml", self._xml_feuille(feuille))
        return tampon.getvalue()


def csv_octets(entetes: list[str], rangs: list[list]) -> bytes:
    """Export CSV compatible Excel francophone (séparateur ';', BOM UTF-8)."""
    import csv
    tampon = io.StringIO()
    graveur = csv.writer(tampon, delimiter=";", quoting=csv.QUOTE_MINIMAL,
                         lineterminator="\r\n")
    if entetes:
        graveur.writerow(entetes)
    for rang in rangs:
        graveur.writerow([
            str(c).replace(".", ",") if isinstance(c, float) else ("" if c is None else c)
            for c in rang
        ])
    return "﻿".encode("utf-8") + tampon.getvalue().encode("utf-8")
