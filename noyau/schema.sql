-- ============================================================================
--  CABINET IMMO — Schéma de la base de données (SQLite)
--  Comptabilité SCF algérienne — Agence immobilière & Promotion immobilière
--
--  Conventions :
--   * Tous les montants sont stockés en CENTIMES (entiers) pour éviter
--     toute erreur d'arrondi sur les décimaux. 1 DA = 100 centimes.
--   * Toutes les dates sont au format ISO 'AAAA-MM-JJ' (tri naturel).
--   * Les taux sont stockés en CENTIÈMES DE POUR-CENT (19 % => 1900,
--     1,5 % => 150 ; 100 % => 10000), afin de rester en arithmétique entière.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- 0. Métadonnées & sécurité
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS meta (
    cle     TEXT PRIMARY KEY,
    valeur  TEXT
);

CREATE TABLE IF NOT EXISTS utilisateurs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    identifiant     TEXT NOT NULL UNIQUE,
    nom_complet     TEXT NOT NULL,
    mot_de_passe    TEXT NOT NULL,          -- pbkdf2_sha256$iterations$sel$hash
    role            TEXT NOT NULL DEFAULT 'comptable',  -- admin | comptable | lecture
    actif           INTEGER NOT NULL DEFAULT 1,
    derniere_visite TEXT,
    cree_le         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    jeton        TEXT PRIMARY KEY,
    utilisateur_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    cree_le      TEXT NOT NULL,
    expire_le    TEXT NOT NULL
);

-- Journal d'audit : toute écriture comptable / suppression est tracée.
CREATE TABLE IF NOT EXISTS audit (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    horodatage    TEXT NOT NULL,
    utilisateur   TEXT,
    action        TEXT NOT NULL,      -- creation | modification | suppression | validation ...
    entite        TEXT NOT NULL,      -- ecriture | facture | lot | ...
    entite_id     INTEGER,
    details       TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_date ON audit(horodatage);

-- ---------------------------------------------------------------------------
-- 1. Dossiers (sociétés) et exercices
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS societes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    code              TEXT NOT NULL UNIQUE,
    raison_sociale    TEXT NOT NULL,
    forme_juridique   TEXT,                     -- SARL, EURL, SPA, SNC, Personne physique
    -- 'agence' : agence immobilière (transaction + gestion locative)
    -- 'promotion' : promoteur immobilier (loi 11-04)
    -- 'mixte' : les deux activités dans la même entité
    activite          TEXT NOT NULL DEFAULT 'mixte',
    adresse           TEXT,
    commune           TEXT,
    wilaya            TEXT,
    telephone         TEXT,
    email             TEXT,
    site_web          TEXT,
    -- Identifiants fiscaux algériens obligatoires sur les factures
    nif               TEXT,                     -- Numéro d'Identification Fiscale (15 ch.)
    nis               TEXT,                     -- Numéro d'Identification Statistique
    rc                TEXT,                     -- Registre de Commerce
    article_imposition TEXT,                    -- Article d'imposition
    capital_cts       INTEGER NOT NULL DEFAULT 0,
    -- Régime & fiscalité
    regime_tva        TEXT NOT NULL DEFAULT 'reel',   -- reel | franchise | exonere
    assujetti_tva     INTEGER NOT NULL DEFAULT 1,
    taux_ibs          INTEGER,                  -- en centièmes de % (23 % => 2300)
    -- Spécifique promotion immobilière (loi n° 11-04)
    agrement_promoteur TEXT,                    -- n° d'agrément du promoteur
    num_fgcmpi        TEXT,                     -- n° d'adhésion au FGCMPI
    -- Coordonnées bancaires
    banque_nom        TEXT,
    banque_rib        TEXT,
    actif             INTEGER NOT NULL DEFAULT 1,
    cree_le           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exercices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id  INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    libelle     TEXT NOT NULL,          -- ex : "2026"
    date_debut  TEXT NOT NULL,
    date_fin    TEXT NOT NULL,
    cloture     INTEGER NOT NULL DEFAULT 0,
    date_cloture TEXT,
    UNIQUE(societe_id, libelle)
);
CREATE INDEX IF NOT EXISTS idx_exercices_soc ON exercices(societe_id);

-- ---------------------------------------------------------------------------
-- 2. Plan comptable (SCF — Système Comptable Financier algérien)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS comptes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id  INTEGER REFERENCES societes(id) ON DELETE CASCADE,
    numero      TEXT NOT NULL,
    intitule    TEXT NOT NULL,
    classe      INTEGER NOT NULL,
    -- nature : actif | passif | charge | produit | mixte
    nature      TEXT NOT NULL DEFAULT 'mixte',
    -- rattachement aux états financiers (rubrique du bilan / TCR)
    rubrique    TEXT,
    -- collectif de tiers : client | fournisseur | salarie | mandant | etat | associe
    collectif   TEXT,
    lettrable   INTEGER NOT NULL DEFAULT 0,
    -- compte de TVA : collectee | deductible_bs | deductible_immo | precompte | a_payer
    role_tva    TEXT,
    actif       INTEGER NOT NULL DEFAULT 1,
    UNIQUE(societe_id, numero)
);
CREATE INDEX IF NOT EXISTS idx_comptes_num ON comptes(societe_id, numero);

-- ---------------------------------------------------------------------------
-- 3. Journaux comptables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS journaux (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id          INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    code                TEXT NOT NULL,
    libelle             TEXT NOT NULL,
    -- VE=ventes AC=achats BQ=banque CA=caisse OD=opérations diverses
    -- PA=paie AN=à-nouveaux
    type                TEXT NOT NULL,
    compte_contrepartie TEXT,
    actif               INTEGER NOT NULL DEFAULT 1,
    UNIQUE(societe_id, code)
);

-- ---------------------------------------------------------------------------
-- 4. Tiers (clients, fournisseurs, salariés, propriétaires mandants…)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tiers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id      INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    code            TEXT NOT NULL,
    -- client | fournisseur | salarie | mandant | notaire | administration | autre
    type            TEXT NOT NULL,
    raison_sociale  TEXT NOT NULL,
    -- 'physique' ou 'morale' : conditionne les mentions et retenues
    forme           TEXT NOT NULL DEFAULT 'physique',
    civilite        TEXT,
    nom             TEXT,
    prenom          TEXT,
    date_naissance  TEXT,
    lieu_naissance  TEXT,
    piece_identite  TEXT,        -- type + n° CNI / passeport
    adresse         TEXT,
    commune         TEXT,
    wilaya          TEXT,
    telephone       TEXT,
    telephone2      TEXT,
    email           TEXT,
    nif             TEXT,
    nis             TEXT,
    rc              TEXT,
    article_imposition TEXT,
    banque_rib      TEXT,
    compte_comptable TEXT,       -- ex : 411, 401, 467
    plafond_credit_cts INTEGER NOT NULL DEFAULT 0,
    notes           TEXT,
    actif           INTEGER NOT NULL DEFAULT 1,
    cree_le         TEXT NOT NULL,
    UNIQUE(societe_id, code)
);
CREATE INDEX IF NOT EXISTS idx_tiers_soc_type ON tiers(societe_id, type);
CREATE INDEX IF NOT EXISTS idx_tiers_nom ON tiers(societe_id, raison_sociale);

-- ---------------------------------------------------------------------------
-- 5. Écritures comptables (partie double)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ecritures (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id   INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    exercice_id  INTEGER NOT NULL REFERENCES exercices(id) ON DELETE CASCADE,
    journal_id   INTEGER NOT NULL REFERENCES journaux(id),
    date         TEXT NOT NULL,
    numero       TEXT,                -- n° de séquence dans le journal
    piece        TEXT,                -- n° de pièce justificative
    libelle      TEXT NOT NULL,
    reference    TEXT,
    -- traçabilité de l'origine (généré automatiquement par un module métier)
    module       TEXT,                -- facturation | agence | promotion | paie | fiscalite | manuel
    source_type  TEXT,
    source_id    INTEGER,
    validee      INTEGER NOT NULL DEFAULT 0,   -- une écriture validée n'est plus modifiable
    cree_le      TEXT NOT NULL,
    cree_par     TEXT,
    modifie_le   TEXT
);
CREATE INDEX IF NOT EXISTS idx_ecr_ex_date ON ecritures(exercice_id, date);
CREATE INDEX IF NOT EXISTS idx_ecr_journal ON ecritures(journal_id, date);
CREATE INDEX IF NOT EXISTS idx_ecr_source ON ecritures(module, source_type, source_id);

CREATE TABLE IF NOT EXISTS lignes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ecriture_id  INTEGER NOT NULL REFERENCES ecritures(id) ON DELETE CASCADE,
    ordre        INTEGER NOT NULL DEFAULT 0,
    compte       TEXT NOT NULL,
    tiers_id     INTEGER REFERENCES tiers(id) ON DELETE SET NULL,
    libelle      TEXT,
    debit        INTEGER NOT NULL DEFAULT 0,   -- centimes
    credit       INTEGER NOT NULL DEFAULT 0,   -- centimes
    lettrage     TEXT,
    echeance     TEXT,
    -- Axes analytiques : suivi par programme / lot (promotion) ou par bien (agence)
    programme_id INTEGER,
    lot_id       INTEGER,
    bien_id      INTEGER,
    poste_budget TEXT,
    CHECK (debit >= 0 AND credit >= 0)
);
CREATE INDEX IF NOT EXISTS idx_lig_ecr ON lignes(ecriture_id);
CREATE INDEX IF NOT EXISTS idx_lig_compte ON lignes(compte);
CREATE INDEX IF NOT EXISTS idx_lig_tiers ON lignes(tiers_id);
CREATE INDEX IF NOT EXISTS idx_lig_prog ON lignes(programme_id);
CREATE INDEX IF NOT EXISTS idx_lig_lettrage ON lignes(lettrage);

-- ---------------------------------------------------------------------------
-- 6. Trésorerie
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS comptes_tresorerie (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id  INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    code        TEXT NOT NULL,
    libelle     TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'banque',   -- banque | caisse | ccp
    compte      TEXT NOT NULL,                    -- compte comptable 512x / 53x
    banque      TEXT,
    agence      TEXT,
    rib         TEXT,
    devise      TEXT NOT NULL DEFAULT 'DZD',
    -- Compte séquestre / spécial promotion immobilière (art. loi 11-04)
    est_sequestre INTEGER NOT NULL DEFAULT 0,
    programme_id  INTEGER,
    actif       INTEGER NOT NULL DEFAULT 1,
    UNIQUE(societe_id, code)
);

CREATE TABLE IF NOT EXISTS rapprochements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tresorerie_id INTEGER NOT NULL REFERENCES comptes_tresorerie(id) ON DELETE CASCADE,
    date_arrete   TEXT NOT NULL,
    solde_releve  INTEGER NOT NULL DEFAULT 0,
    cloture       INTEGER NOT NULL DEFAULT 0,
    cree_le       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rapprochement_lignes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    rapprochement_id  INTEGER NOT NULL REFERENCES rapprochements(id) ON DELETE CASCADE,
    ligne_id          INTEGER NOT NULL REFERENCES lignes(id) ON DELETE CASCADE,
    pointee           INTEGER NOT NULL DEFAULT 1,
    UNIQUE(rapprochement_id, ligne_id)
);

-- ---------------------------------------------------------------------------
-- 7. Facturation (conforme aux mentions obligatoires algériennes)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS factures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id      INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    exercice_id     INTEGER NOT NULL REFERENCES exercices(id) ON DELETE CASCADE,
    -- vente | achat | avoir_vente | avoir_achat | proforma
    sens            TEXT NOT NULL DEFAULT 'vente',
    numero          TEXT NOT NULL,
    date            TEXT NOT NULL,
    date_echeance   TEXT,
    tiers_id        INTEGER REFERENCES tiers(id),
    objet           TEXT,
    reference       TEXT,
    -- origine métier : commission_vente | honoraires_location | gestion_locative |
    --                  vsp_tranche | travaux | achat_divers | autre
    origine         TEXT,
    programme_id    INTEGER,
    lot_id          INTEGER,
    bien_id         INTEGER,
    bail_id         INTEGER,
    contrat_vsp_id  INTEGER,
    montant_ht      INTEGER NOT NULL DEFAULT 0,
    montant_tva     INTEGER NOT NULL DEFAULT 0,
    montant_ttc     INTEGER NOT NULL DEFAULT 0,
    timbre          INTEGER NOT NULL DEFAULT 0,   -- droit de timbre (paiement espèces)
    net_a_payer     INTEGER NOT NULL DEFAULT 0,
    montant_regle   INTEGER NOT NULL DEFAULT 0,
    mode_reglement  TEXT,                         -- espece | cheque | virement | traite
    -- brouillon | validee | payee | partielle | annulee
    statut          TEXT NOT NULL DEFAULT 'brouillon',
    ecriture_id     INTEGER REFERENCES ecritures(id) ON DELETE SET NULL,
    notes           TEXT,
    conditions      TEXT,
    cree_le         TEXT NOT NULL,
    cree_par        TEXT,
    UNIQUE(societe_id, sens, numero)
);
CREATE INDEX IF NOT EXISTS idx_fact_soc_date ON factures(societe_id, date);
CREATE INDEX IF NOT EXISTS idx_fact_tiers ON factures(tiers_id);

CREATE TABLE IF NOT EXISTS facture_lignes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    facture_id  INTEGER NOT NULL REFERENCES factures(id) ON DELETE CASCADE,
    ordre       INTEGER NOT NULL DEFAULT 0,
    designation TEXT NOT NULL,
    quantite    INTEGER NOT NULL DEFAULT 1000,    -- millièmes (1 => 1000)
    unite       TEXT,
    prix_unitaire INTEGER NOT NULL DEFAULT 0,     -- centimes
    remise_taux INTEGER NOT NULL DEFAULT 0,       -- centièmes de %
    taux_tva    INTEGER NOT NULL DEFAULT 1900,    -- 19 % => 1900
    montant_ht  INTEGER NOT NULL DEFAULT 0,
    montant_tva INTEGER NOT NULL DEFAULT 0,
    compte      TEXT                              -- compte de produit / charge
);
CREATE INDEX IF NOT EXISTS idx_fl_fact ON facture_lignes(facture_id);

-- Règlements (encaissements clients / décaissements fournisseurs)
CREATE TABLE IF NOT EXISTS reglements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id    INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    exercice_id   INTEGER NOT NULL REFERENCES exercices(id) ON DELETE CASCADE,
    sens          TEXT NOT NULL,               -- encaissement | decaissement
    date          TEXT NOT NULL,
    tiers_id      INTEGER REFERENCES tiers(id),
    tresorerie_id INTEGER REFERENCES comptes_tresorerie(id),
    montant       INTEGER NOT NULL DEFAULT 0,
    mode          TEXT NOT NULL DEFAULT 'virement',
    reference     TEXT,                        -- n° chèque / virement
    libelle       TEXT,
    facture_id    INTEGER REFERENCES factures(id) ON DELETE SET NULL,
    echeance_id   INTEGER,                     -- échéance VSP réglée
    quittance_id  INTEGER,
    ecriture_id   INTEGER REFERENCES ecritures(id) ON DELETE SET NULL,
    cree_le       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_regl_date ON reglements(societe_id, date);

-- ---------------------------------------------------------------------------
-- 8. AGENCE IMMOBILIÈRE — biens, mandats, transactions, gestion locative
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS biens (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id     INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    reference      TEXT NOT NULL,
    -- appartement | villa | local_commercial | bureau | terrain | hangar | garage | immeuble
    type_bien      TEXT NOT NULL DEFAULT 'appartement',
    designation    TEXT NOT NULL,
    adresse        TEXT,
    commune        TEXT,
    wilaya         TEXT,
    surface        INTEGER,                    -- m² × 100
    nb_pieces      TEXT,                       -- F2, F3, F4…
    etage          TEXT,
    -- Situation juridique du bien (important en Algérie)
    nature_juridique TEXT,                     -- acte_notarie | livret_foncier | acte_admin | indivision
    num_acte       TEXT,
    proprietaire_id INTEGER REFERENCES tiers(id) ON DELETE SET NULL,
    prix_demande   INTEGER NOT NULL DEFAULT 0,
    loyer_mensuel  INTEGER NOT NULL DEFAULT 0,
    -- disponible | sous_compromis | vendu | loue | retire
    statut         TEXT NOT NULL DEFAULT 'disponible',
    description    TEXT,
    cree_le        TEXT NOT NULL,
    UNIQUE(societe_id, reference)
);
CREATE INDEX IF NOT EXISTS idx_biens_soc ON biens(societe_id, statut);

CREATE TABLE IF NOT EXISTS mandats (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id     INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    numero         TEXT NOT NULL,
    bien_id        INTEGER NOT NULL REFERENCES biens(id) ON DELETE CASCADE,
    mandant_id     INTEGER REFERENCES tiers(id),
    type_mandat    TEXT NOT NULL DEFAULT 'vente',   -- vente | location | gestion
    exclusif       INTEGER NOT NULL DEFAULT 0,
    date_debut     TEXT NOT NULL,
    date_fin       TEXT,
    prix_mandat    INTEGER NOT NULL DEFAULT 0,
    -- Commission : taux en centièmes de % OU forfait en centimes
    taux_commission INTEGER NOT NULL DEFAULT 0,
    commission_forfait INTEGER NOT NULL DEFAULT 0,
    -- qui paye : vendeur | acquereur | partage
    charge_commission TEXT NOT NULL DEFAULT 'vendeur',
    statut         TEXT NOT NULL DEFAULT 'actif',   -- actif | realise | expire | resilie
    notes          TEXT,
    cree_le        TEXT NOT NULL,
    UNIQUE(societe_id, numero)
);

-- Transaction : vente d'un bien via l'agence, génère la commission
CREATE TABLE IF NOT EXISTS transactions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id     INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    numero         TEXT NOT NULL,
    bien_id        INTEGER REFERENCES biens(id),
    mandat_id      INTEGER REFERENCES mandats(id),
    vendeur_id     INTEGER REFERENCES tiers(id),
    acquereur_id   INTEGER REFERENCES tiers(id),
    date_compromis TEXT,
    date_acte      TEXT,
    notaire_id     INTEGER REFERENCES tiers(id),
    prix_vente     INTEGER NOT NULL DEFAULT 0,
    commission_ht  INTEGER NOT NULL DEFAULT 0,
    taux_tva       INTEGER NOT NULL DEFAULT 1900,
    commission_ttc INTEGER NOT NULL DEFAULT 0,
    statut         TEXT NOT NULL DEFAULT 'en_cours',  -- en_cours | signee | annulee
    facture_id     INTEGER REFERENCES factures(id) ON DELETE SET NULL,
    notes          TEXT,
    cree_le        TEXT NOT NULL,
    UNIQUE(societe_id, numero)
);

-- Bail : contrat de location géré par l'agence
CREATE TABLE IF NOT EXISTS baux (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id        INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    numero            TEXT NOT NULL,
    bien_id           INTEGER NOT NULL REFERENCES biens(id),
    proprietaire_id   INTEGER REFERENCES tiers(id),
    locataire_id      INTEGER REFERENCES tiers(id),
    -- habitation | commercial | professionnel
    usage             TEXT NOT NULL DEFAULT 'habitation',
    date_debut        TEXT NOT NULL,
    date_fin          TEXT,
    duree_mois        INTEGER NOT NULL DEFAULT 12,
    loyer_mensuel     INTEGER NOT NULL DEFAULT 0,
    charges_mensuelles INTEGER NOT NULL DEFAULT 0,
    caution           INTEGER NOT NULL DEFAULT 0,
    -- jour du mois d'échéance du loyer
    jour_echeance     INTEGER NOT NULL DEFAULT 5,
    periodicite_mois  INTEGER NOT NULL DEFAULT 1,
    -- Honoraires de gestion prélevés sur le loyer (centièmes de %)
    taux_gestion      INTEGER NOT NULL DEFAULT 0,
    -- Honoraires d'entremise perçus à la signature (centimes)
    honoraires_entremise INTEGER NOT NULL DEFAULT 0,
    -- Le bail est-il enregistré aux impôts ? (obligation algérienne)
    enregistre        INTEGER NOT NULL DEFAULT 0,
    date_enregistrement TEXT,
    -- L'agence encaisse-t-elle le loyer pour le compte du propriétaire ?
    encaisse_par_agence INTEGER NOT NULL DEFAULT 1,
    statut            TEXT NOT NULL DEFAULT 'actif',   -- actif | resilie | echu
    notes             TEXT,
    cree_le           TEXT NOT NULL,
    UNIQUE(societe_id, numero)
);
CREATE INDEX IF NOT EXISTS idx_baux_soc ON baux(societe_id, statut);

-- Quittance de loyer : une ligne par période
CREATE TABLE IF NOT EXISTS quittances (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id      INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    bail_id         INTEGER NOT NULL REFERENCES baux(id) ON DELETE CASCADE,
    numero          TEXT NOT NULL,
    periode         TEXT NOT NULL,          -- 'AAAA-MM'
    date_echeance   TEXT NOT NULL,
    loyer           INTEGER NOT NULL DEFAULT 0,
    charges         INTEGER NOT NULL DEFAULT 0,
    total           INTEGER NOT NULL DEFAULT 0,
    honoraires_gestion_ht INTEGER NOT NULL DEFAULT 0,
    tva_honoraires  INTEGER NOT NULL DEFAULT 0,
    net_proprietaire INTEGER NOT NULL DEFAULT 0,
    montant_encaisse INTEGER NOT NULL DEFAULT 0,
    date_encaissement TEXT,
    montant_reverse INTEGER NOT NULL DEFAULT 0,
    date_reversement TEXT,
    -- a_encaisser | encaissee | reversee | impayee | annulee
    statut          TEXT NOT NULL DEFAULT 'a_encaisser',
    ecriture_id     INTEGER REFERENCES ecritures(id) ON DELETE SET NULL,
    notes           TEXT,
    cree_le         TEXT NOT NULL,
    UNIQUE(societe_id, bail_id, periode)
);
CREATE INDEX IF NOT EXISTS idx_quit_periode ON quittances(societe_id, periode);
CREATE INDEX IF NOT EXISTS idx_quit_statut ON quittances(societe_id, statut);

-- ---------------------------------------------------------------------------
-- 9. PROMOTION IMMOBILIÈRE — loi n° 11-04, VSP, programmes, lots
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS programmes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id        INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    code              TEXT NOT NULL,
    intitule          TEXT NOT NULL,
    adresse           TEXT,
    commune           TEXT,
    wilaya            TEXT,
    -- Assiette foncière
    surface_terrain   INTEGER NOT NULL DEFAULT 0,   -- m² × 100
    surface_batie     INTEGER NOT NULL DEFAULT 0,
    nb_logements      INTEGER NOT NULL DEFAULT 0,
    nb_locaux         INTEGER NOT NULL DEFAULT 0,
    -- Autorisations administratives
    num_permis_construire TEXT,
    date_permis       TEXT,
    num_acte_terrain  TEXT,
    date_acte_terrain TEXT,
    num_certificat_conformite TEXT,
    date_conformite   TEXT,
    -- Dates clés
    date_debut_travaux TEXT,
    date_fin_prevue   TEXT,
    date_livraison    TEXT,
    -- Budget prévisionnel (centimes)
    budget_terrain    INTEGER NOT NULL DEFAULT 0,
    budget_etudes     INTEGER NOT NULL DEFAULT 0,
    budget_travaux    INTEGER NOT NULL DEFAULT 0,
    budget_vrd        INTEGER NOT NULL DEFAULT 0,
    budget_frais_divers INTEGER NOT NULL DEFAULT 0,
    budget_frais_financiers INTEGER NOT NULL DEFAULT 0,
    chiffre_affaires_prevu INTEGER NOT NULL DEFAULT 0,
    -- Régime de reconnaissance du produit : achevement | avancement
    methode_produit   TEXT NOT NULL DEFAULT 'achevement',
    -- Fait générateur de la TVA : encaissement | livraison
    fait_generateur_tva TEXT NOT NULL DEFAULT 'livraison',
    taux_tva          INTEGER NOT NULL DEFAULT 1900,
    -- Avancement physique déclaré (centièmes de %) — sert au produit à l'avancement
    avancement        INTEGER NOT NULL DEFAULT 0,
    -- etude | lancement | en_cours | acheve | livre | cloture
    statut            TEXT NOT NULL DEFAULT 'etude',
    -- Garantie FGCMPI (obligatoire pour la VSP)
    fgcmpi_police     TEXT,
    fgcmpi_taux       INTEGER NOT NULL DEFAULT 0,   -- centièmes de %
    notes             TEXT,
    cree_le           TEXT NOT NULL,
    UNIQUE(societe_id, code)
);

CREATE TABLE IF NOT EXISTS tranches (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    programme_id  INTEGER NOT NULL REFERENCES programmes(id) ON DELETE CASCADE,
    code          TEXT NOT NULL,
    intitule      TEXT NOT NULL,
    nb_lots       INTEGER NOT NULL DEFAULT 0,
    date_debut    TEXT,
    date_livraison_prevue TEXT,
    avancement    INTEGER NOT NULL DEFAULT 0,
    statut        TEXT NOT NULL DEFAULT 'en_cours',
    UNIQUE(programme_id, code)
);

CREATE TABLE IF NOT EXISTS lots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id     INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    programme_id   INTEGER NOT NULL REFERENCES programmes(id) ON DELETE CASCADE,
    tranche_id     INTEGER REFERENCES tranches(id) ON DELETE SET NULL,
    numero         TEXT NOT NULL,
    -- logement | local_commercial | bureau | parking | cave | terrain
    type_lot       TEXT NOT NULL DEFAULT 'logement',
    typologie      TEXT,                       -- F2, F3, F4…
    batiment       TEXT,
    etage          TEXT,
    surface_habitable INTEGER NOT NULL DEFAULT 0,   -- m² × 100
    surface_utile  INTEGER NOT NULL DEFAULT 0,
    quote_part_terrain INTEGER NOT NULL DEFAULT 0,  -- millièmes de copropriété
    prix_m2        INTEGER NOT NULL DEFAULT 0,
    prix_vente     INTEGER NOT NULL DEFAULT 0,      -- prix TTC de commercialisation
    cout_revient   INTEGER NOT NULL DEFAULT 0,      -- calculé par répartition
    -- disponible | reserve | vendu | livre | bloque
    statut         TEXT NOT NULL DEFAULT 'disponible',
    notes          TEXT,
    UNIQUE(programme_id, numero)
);
CREATE INDEX IF NOT EXISTS idx_lots_prog ON lots(programme_id, statut);

-- Postes budgétaires détaillés d'un programme (suivi budget / réalisé)
CREATE TABLE IF NOT EXISTS budget_lignes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    programme_id INTEGER NOT NULL REFERENCES programmes(id) ON DELETE CASCADE,
    poste        TEXT NOT NULL,        -- terrain | etudes | gros_oeuvre | second_oeuvre | vrd | ...
    libelle      TEXT NOT NULL,
    montant_prevu INTEGER NOT NULL DEFAULT 0,
    comptes      TEXT,                 -- comptes de charges rattachés, séparés par ';'
    ordre        INTEGER NOT NULL DEFAULT 0
);

-- Contrat de Vente sur Plan (VSP) — loi 11-04 / décret exécutif 13-431
CREATE TABLE IF NOT EXISTS contrats_vsp (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id        INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    numero            TEXT NOT NULL,
    programme_id      INTEGER NOT NULL REFERENCES programmes(id),
    lot_id            INTEGER NOT NULL REFERENCES lots(id),
    acquereur_id      INTEGER NOT NULL REFERENCES tiers(id),
    -- reservation | vsp | vente_definitive
    type_contrat      TEXT NOT NULL DEFAULT 'vsp',
    date_reservation  TEXT,
    date_contrat      TEXT,
    -- Le contrat VSP doit être notarié et publié à la conservation foncière
    notaire_id        INTEGER REFERENCES tiers(id),
    num_acte_notarie  TEXT,
    date_publication  TEXT,
    prix_total        INTEGER NOT NULL DEFAULT 0,   -- TTC
    prix_ht           INTEGER NOT NULL DEFAULT 0,
    tva               INTEGER NOT NULL DEFAULT 0,
    taux_tva          INTEGER NOT NULL DEFAULT 1900,
    -- Financement
    mode_financement  TEXT,                          -- fonds_propres | credit_bancaire | cnl_aide | mixte
    banque            TEXT,
    montant_credit    INTEGER NOT NULL DEFAULT 0,
    aide_etat         INTEGER NOT NULL DEFAULT 0,    -- aide CNL / FNPOS
    -- Garantie FGCMPI
    fgcmpi_atteste    INTEGER NOT NULL DEFAULT 0,
    fgcmpi_numero     TEXT,
    fgcmpi_prime      INTEGER NOT NULL DEFAULT 0,
    montant_encaisse  INTEGER NOT NULL DEFAULT 0,
    -- en_cours | solde | livre | resilie
    statut            TEXT NOT NULL DEFAULT 'en_cours',
    date_livraison    TEXT,
    date_pv_reception TEXT,
    notes             TEXT,
    cree_le           TEXT NOT NULL,
    UNIQUE(societe_id, numero)
);
CREATE INDEX IF NOT EXISTS idx_vsp_prog ON contrats_vsp(programme_id, statut);

-- Échéancier de paiement adossé à l'avancement des travaux
CREATE TABLE IF NOT EXISTS echeances_vsp (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contrat_id      INTEGER NOT NULL REFERENCES contrats_vsp(id) ON DELETE CASCADE,
    ordre           INTEGER NOT NULL DEFAULT 0,
    libelle         TEXT NOT NULL,       -- "Signature du contrat", "Achèvement fondations"…
    -- déclencheur : date | avancement | livraison
    declencheur     TEXT NOT NULL DEFAULT 'date',
    seuil_avancement INTEGER NOT NULL DEFAULT 0,   -- centièmes de %
    date_prevue     TEXT,
    pourcentage     INTEGER NOT NULL DEFAULT 0,    -- centièmes de % du prix total
    montant         INTEGER NOT NULL DEFAULT 0,
    montant_regle   INTEGER NOT NULL DEFAULT 0,
    date_reglement  TEXT,
    -- a_venir | exigible | reglee | partielle | retard
    statut          TEXT NOT NULL DEFAULT 'a_venir',
    appelee         INTEGER NOT NULL DEFAULT 0,    -- appel de fonds émis
    date_appel      TEXT,
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_ech_contrat ON echeances_vsp(contrat_id, ordre);

-- Modèles d'échéancier réutilisables
CREATE TABLE IF NOT EXISTS modeles_echeancier (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id INTEGER REFERENCES societes(id) ON DELETE CASCADE,
    code       TEXT NOT NULL,
    libelle    TEXT NOT NULL,
    lignes     TEXT NOT NULL,     -- JSON : [{libelle, pourcentage, declencheur, seuil}]
    UNIQUE(societe_id, code)
);

-- Situations de travaux des entreprises (sous-traitants du promoteur)
CREATE TABLE IF NOT EXISTS situations_travaux (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id     INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    programme_id   INTEGER NOT NULL REFERENCES programmes(id) ON DELETE CASCADE,
    entreprise_id  INTEGER REFERENCES tiers(id),
    numero         TEXT NOT NULL,
    date           TEXT NOT NULL,
    lot_travaux    TEXT,                     -- gros œuvre, étanchéité, menuiserie…
    montant_marche INTEGER NOT NULL DEFAULT 0,
    avancement     INTEGER NOT NULL DEFAULT 0,   -- centièmes de %
    montant_ht     INTEGER NOT NULL DEFAULT 0,
    taux_tva       INTEGER NOT NULL DEFAULT 1900,
    montant_ttc    INTEGER NOT NULL DEFAULT 0,
    retenue_garantie INTEGER NOT NULL DEFAULT 0,
    net_a_payer    INTEGER NOT NULL DEFAULT 0,
    statut         TEXT NOT NULL DEFAULT 'brouillon',
    facture_id     INTEGER REFERENCES factures(id) ON DELETE SET NULL,
    cree_le        TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- 10. PAIE (CNAS / IRG salaires)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS salaries (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id        INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    matricule         TEXT NOT NULL,
    nom               TEXT NOT NULL,
    prenom            TEXT NOT NULL,
    date_naissance    TEXT,
    num_secu          TEXT,               -- n° de sécurité sociale CNAS
    poste             TEXT,
    categorie         TEXT,
    date_embauche     TEXT,
    date_sortie       TEXT,
    type_contrat      TEXT DEFAULT 'CDI',
    salaire_base      INTEGER NOT NULL DEFAULT 0,
    -- primes récurrentes stockées en JSON [{libelle, montant, soumis_cnas, soumis_irg}]
    primes            TEXT,
    situation_familiale TEXT,
    nb_enfants        INTEGER NOT NULL DEFAULT 0,
    rib               TEXT,
    actif             INTEGER NOT NULL DEFAULT 1,
    UNIQUE(societe_id, matricule)
);

CREATE TABLE IF NOT EXISTS bulletins (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id     INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    salarie_id     INTEGER NOT NULL REFERENCES salaries(id) ON DELETE CASCADE,
    periode        TEXT NOT NULL,          -- 'AAAA-MM'
    jours_travailles INTEGER NOT NULL DEFAULT 3000,   -- millièmes (30 j => 30000)
    salaire_base   INTEGER NOT NULL DEFAULT 0,
    primes_soumises INTEGER NOT NULL DEFAULT 0,
    primes_non_soumises INTEGER NOT NULL DEFAULT 0,
    salaire_brut   INTEGER NOT NULL DEFAULT 0,
    base_cnas      INTEGER NOT NULL DEFAULT 0,
    cnas_salarie   INTEGER NOT NULL DEFAULT 0,   -- 9 %
    cnas_patronale INTEGER NOT NULL DEFAULT 0,   -- 26 %
    base_irg       INTEGER NOT NULL DEFAULT 0,
    irg            INTEGER NOT NULL DEFAULT 0,
    abattement_irg INTEGER NOT NULL DEFAULT 0,
    autres_retenues INTEGER NOT NULL DEFAULT 0,
    net_a_payer    INTEGER NOT NULL DEFAULT 0,
    cout_employeur INTEGER NOT NULL DEFAULT 0,
    detail         TEXT,                   -- JSON du détail de calcul
    statut         TEXT NOT NULL DEFAULT 'brouillon',
    ecriture_id    INTEGER REFERENCES ecritures(id) ON DELETE SET NULL,
    cree_le        TEXT NOT NULL,
    UNIQUE(societe_id, salarie_id, periode)
);
CREATE INDEX IF NOT EXISTS idx_bul_periode ON bulletins(societe_id, periode);

-- ---------------------------------------------------------------------------
-- 11. IMMOBILISATIONS & amortissements
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS immobilisations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id     INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    code           TEXT NOT NULL,
    designation    TEXT NOT NULL,
    compte         TEXT NOT NULL,             -- 213, 2182, 2183…
    compte_amort   TEXT NOT NULL,             -- 281x
    compte_dotation TEXT NOT NULL DEFAULT '68112',
    date_acquisition TEXT NOT NULL,
    date_mise_service TEXT,
    valeur_acquisition INTEGER NOT NULL DEFAULT 0,
    valeur_residuelle  INTEGER NOT NULL DEFAULT 0,
    duree_mois     INTEGER NOT NULL DEFAULT 60,
    mode           TEXT NOT NULL DEFAULT 'lineaire',   -- lineaire | degressif
    coefficient    INTEGER NOT NULL DEFAULT 1000,      -- millièmes
    date_cession   TEXT,
    valeur_cession INTEGER NOT NULL DEFAULT 0,
    statut         TEXT NOT NULL DEFAULT 'en_service', -- en_service | cede | rebute | amorti
    programme_id   INTEGER,
    UNIQUE(societe_id, code)
);

CREATE TABLE IF NOT EXISTS amortissements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    immo_id       INTEGER NOT NULL REFERENCES immobilisations(id) ON DELETE CASCADE,
    exercice_id   INTEGER REFERENCES exercices(id) ON DELETE CASCADE,
    annee         INTEGER NOT NULL,
    base          INTEGER NOT NULL DEFAULT 0,
    dotation      INTEGER NOT NULL DEFAULT 0,
    cumul         INTEGER NOT NULL DEFAULT 0,
    vnc           INTEGER NOT NULL DEFAULT 0,
    comptabilise  INTEGER NOT NULL DEFAULT 0,
    ecriture_id   INTEGER REFERENCES ecritures(id) ON DELETE SET NULL,
    UNIQUE(immo_id, annee)
);

-- ---------------------------------------------------------------------------
-- 12. FISCALITÉ — paramètres et déclarations
-- ---------------------------------------------------------------------------

-- Paramètres fiscaux versionnés par année (loi de finances)
CREATE TABLE IF NOT EXISTS parametres_fiscaux (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    annee    INTEGER NOT NULL,
    cle      TEXT NOT NULL,
    valeur   TEXT NOT NULL,
    libelle  TEXT,
    unite    TEXT,          -- pourcentage | montant | texte | bareme
    source   TEXT,          -- référence légale
    UNIQUE(annee, cle)
);

-- Déclaration mensuelle G n° 50
CREATE TABLE IF NOT EXISTS declarations_g50 (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id    INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    periode       TEXT NOT NULL,         -- 'AAAA-MM'
    date_limite   TEXT,
    -- Chiffre d'affaires
    ca_taxable    INTEGER NOT NULL DEFAULT 0,
    ca_exonere    INTEGER NOT NULL DEFAULT 0,
    -- TVA
    tva_collectee INTEGER NOT NULL DEFAULT 0,
    tva_deductible_bs INTEGER NOT NULL DEFAULT 0,
    tva_deductible_immo INTEGER NOT NULL DEFAULT 0,
    precompte_anterieur INTEGER NOT NULL DEFAULT 0,
    tva_a_payer   INTEGER NOT NULL DEFAULT 0,
    precompte_reporte INTEGER NOT NULL DEFAULT 0,
    -- TAP (si applicable selon la loi de finances de l'année)
    base_tap      INTEGER NOT NULL DEFAULT 0,
    taux_tap      INTEGER NOT NULL DEFAULT 0,
    tap           INTEGER NOT NULL DEFAULT 0,
    -- Retenues à la source
    irg_salaires  INTEGER NOT NULL DEFAULT 0,
    irg_ras_autres INTEGER NOT NULL DEFAULT 0,
    -- Acompte IBS
    acompte_ibs   INTEGER NOT NULL DEFAULT 0,
    -- Droit de timbre
    droit_timbre  INTEGER NOT NULL DEFAULT 0,
    autres        INTEGER NOT NULL DEFAULT 0,
    total_a_payer INTEGER NOT NULL DEFAULT 0,
    detail        TEXT,                  -- JSON du détail calculé
    -- brouillon | calculee | deposee | payee
    statut        TEXT NOT NULL DEFAULT 'brouillon',
    date_depot    TEXT,
    reference_depot TEXT,
    ecriture_id   INTEGER REFERENCES ecritures(id) ON DELETE SET NULL,
    cree_le       TEXT NOT NULL,
    UNIQUE(societe_id, periode)
);

-- ---------------------------------------------------------------------------
-- 13. Pièces justificatives (fichiers stockés dans le dossier local)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS pieces_jointes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id  INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    entite      TEXT NOT NULL,      -- ecriture | facture | contrat_vsp | bail | lot | programme
    entite_id   INTEGER NOT NULL,
    nom_fichier TEXT NOT NULL,
    chemin      TEXT NOT NULL,      -- relatif au dossier données
    taille      INTEGER NOT NULL DEFAULT 0,
    type_mime   TEXT,
    description TEXT,
    cree_le     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pj_entite ON pieces_jointes(entite, entite_id);

-- ---------------------------------------------------------------------------
-- 14. Compteurs de numérotation (séquences par société / type / année)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS compteurs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    cle        TEXT NOT NULL,       -- facture_vente | facture_achat | ecriture_VE | ...
    annee      INTEGER NOT NULL,
    valeur     INTEGER NOT NULL DEFAULT 0,
    format     TEXT,                -- ex : "FV{annee}-{numero:05d}"
    UNIQUE(societe_id, cle, annee)
);

-- ---------------------------------------------------------------------------
-- 15. Rappels / échéancier de travail du comptable
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS obligations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    societe_id   INTEGER NOT NULL REFERENCES societes(id) ON DELETE CASCADE,
    code         TEXT NOT NULL,       -- g50 | cnas_dsm | ibs_acompte | bilan | das
    libelle      TEXT NOT NULL,
    periode      TEXT,
    date_limite  TEXT NOT NULL,
    -- a_faire | fait | en_retard | sans_objet
    statut       TEXT NOT NULL DEFAULT 'a_faire',
    date_execution TEXT,
    reference    TEXT,
    notes        TEXT,
    UNIQUE(societe_id, code, periode)
);
CREATE INDEX IF NOT EXISTS idx_oblig_date ON obligations(societe_id, date_limite);
