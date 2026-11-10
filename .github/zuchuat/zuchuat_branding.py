# -*- coding: utf-8 -*-
"""
Zuchuat IT & Cyber – personnalisation du client RustDesk au moment de la compilation.

Ce script est lancé par le workflow .github/workflows/zuchuat-build.yml, juste après
le « checkout » du code source (sous-module libs/hbb_common compris). Il modifie les
fichiers dans la machine de compilation GitHub uniquement.

Serveurs : par défaut, le client utilise les serveurs PUBLICS de RustDesk (valeurs
d'origine de libs/hbb_common/src/config.rs, rien n'est modifié). Si un jour un serveur
auto-hébergé est mis en place, il suffit de créer les secrets GitHub RENDEZVOUS_SERVER
et RS_PUB_KEY : le script les écrira alors en dur dans config.rs et les imposera.

Le script est idempotent : il peut être relancé sur un dépôt déjà personnalisé.

Variables lues (voir le workflow) :
  ZR_RENDEZVOUS_SERVER  (facultatif) ex. monserveur.example.ch   ← secret RENDEZVOUS_SERVER
  ZR_RS_PUB_KEY         (facultatif, obligatoire si le serveur est fourni) ← secret RS_PUB_KEY
  ZR_APP_NAME           nom technique, sans espace ni « & » (défaut : ZuchuatRemote)
  ZR_DISPLAY_NAME       nom affiché dans les propriétés du fichier (défaut : Zuchuat IT & Cyber)
  ZR_CONN_TYPE          vide (défaut) = client complet, sert dans les deux sens (proches ET mon poste) ;
                        « incoming » = variante « proche » qui ne peut que recevoir
  ZR_APPROVE_MODE       « click » (validation manuelle obligatoire) ou « password »
  ZR_ICONES             dossier des icônes (défaut : .github/zuchuat/icones-rustdesk)
"""
import os
import re
import shutil
import sys

RACINE = os.getcwd()


def erreur(message):
    print(f"::error::{message}")
    sys.exit(1)


def lire(rel):
    chemin = os.path.join(RACINE, rel)
    if not os.path.isfile(chemin):
        erreur(f"Fichier introuvable : {rel} (le dépôt RustDesk a peut-être changé de structure)")
    with open(chemin, encoding="utf-8", newline="") as f:
        return f.read()


def ecrire(rel, contenu):
    with open(os.path.join(RACINE, rel), "w", encoding="utf-8", newline="") as f:
        f.write(contenu)


def remplacer(texte, motif, remplacement, rel, attendu=1, deja=None):
    """Remplace `motif` exactement `attendu` fois.
    Si le motif est absent mais que `deja` (regex) est présent, le fichier est
    considéré comme déjà personnalisé et laissé tel quel."""
    nouveau, n = re.subn(motif, remplacement, texte, flags=re.MULTILINE)
    if n == 0 and deja is not None and re.search(deja, texte, flags=re.MULTILINE):
        return texte
    if n != attendu:
        erreur(f"{rel} : motif « {motif} » trouvé {n} fois au lieu de {attendu}. "
               "Le code amont a changé : adapte zuchuat_branding.py.")
    return nouveau


def rust_str(valeur):
    return '"' + valeur.replace("\\", "\\\\").replace('"', '\\"') + '"'


def rust_map(paires):
    if not paires:
        return "Default::default()"
    elements = ", ".join(f"({rust_str(k)}.to_owned(), {rust_str(v)}.to_owned())" for k, v in paires)
    return f"RwLock::new(HashMap::from([{elements}]))"


def main():
    serveur = os.environ.get("ZR_RENDEZVOUS_SERVER", "").strip()
    cle = os.environ.get("ZR_RS_PUB_KEY", "").strip()
    nom = os.environ.get("ZR_APP_NAME", "").strip() or "ZuchuatRemote"
    nom_affiche = os.environ.get("ZR_DISPLAY_NAME", "").strip() or "Zuchuat IT & Cyber"
    conn_type = os.environ.get("ZR_CONN_TYPE", "").strip()
    approve = os.environ.get("ZR_APPROVE_MODE", "").strip() or "click"
    icones = os.environ.get("ZR_ICONES", "").strip() or ".github/zuchuat/icones-rustdesk"

    serveur_perso = bool(serveur)
    if serveur_perso:
        if not re.fullmatch(r"[A-Za-z0-9.\-]+(:[0-9]{2,5})?", serveur):
            erreur("RENDEZVOUS_SERVER doit être un nom d'hôte seul, sans http:// ni espace.")
        if not re.fullmatch(r"[A-Za-z0-9+/]{43}=", cle):
            erreur("RS_PUB_KEY absent ou invalide alors que RENDEZVOUS_SERVER est fourni "
                   "(44 caractères base64, finit par « = »).")
    elif cle:
        erreur("RS_PUB_KEY est fourni sans RENDEZVOUS_SERVER : supprime le secret RS_PUB_KEY "
               "ou ajoute aussi RENDEZVOUS_SERVER.")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{2,30}", nom):
        erreur("ZR_APP_NAME : lettres et chiffres uniquement (pas d'espace, pas de « & »).")
    if conn_type not in ("", "incoming", "outgoing"):
        erreur("ZR_CONN_TYPE doit valoir incoming, outgoing ou rester vide.")
    if approve not in ("click", "password"):
        erreur("ZR_APPROVE_MODE doit valoir click ou password.")

    # ------------------------------------------------------------------ config.rs
    rel = "libs/hbb_common/src/config.rs"
    c = lire(rel)
    if serveur_perso:
        c = remplacer(c, r'^pub const RENDEZVOUS_SERVERS: &\[&str\] = &\[[^\]]*\];',
                      f"pub const RENDEZVOUS_SERVERS: &[&str] = &[{rust_str(serveur)}];", rel)
        c = remplacer(c, r'^pub const RS_PUB_KEY: &str = "[^"]*";',
                      f"pub const RS_PUB_KEY: &str = {rust_str(cle)};", rel)
    c = remplacer(c, r'(pub static ref APP_NAME: RwLock<String> = RwLock::new\()"[^"]*"(\.to_owned\(\)\);)',
                  rf'\g<1>{rust_str(nom)}\g<2>', rel)

    # Réglages imposés (« override ») : le proche ne peut pas les modifier.
    imposes = []
    if serveur_perso:
        imposes += [
            ("custom-rendezvous-server", serveur),   # serveur auto-hébergé uniquement
            ("key", cle),                            # clé publique correspondante
        ]
    # Sans serveur personnalisé, rien n'est imposé côté serveur : le client utilise
    # les serveurs publics RustDesk (RENDEZVOUS_SERVERS et RS_PUB_KEY d'origine).
    imposes += [
        ("approve-mode", approve),               # click = « Accepter / Refuser » obligatoire
        ("verification-method", "use-temporary-password"),  # jamais de mot de passe permanent
        ("temporary-password-length", "8"),
        ("allow-remote-config-modification", "N"),  # pas de modification des réglages à distance
        ("enable-lan-discovery", "N"),
        ("direct-server", "N"),
        ("enable-tunnel", "N"),                  # pas de tunnel TCP
        ("enable-terminal", "N"),                # pas de terminal distant
        ("enable-camera", "N"),
        ("enable-file-transfer", "Y"),           # transfert de fichiers autorisé
        ("allow-auto-disconnect", "Y"),          # déconnexion après inactivité
        ("auto-disconnect-timeout", "15"),       # en minutes
    ]
    # Réglages « intégrés » : ce qui est caché dans l'interface (affichage uniquement,
    # sans effet sur le choix du serveur).
    integres = [
        ("hide-server-settings", "Y"),
        ("hide-network-settings", "Y"),
        ("hide-proxy-settings", "Y"),
        ("hide-websocket-settings", "Y"),
        ("hide-security-settings", "Y"),
        ("hide-help-cards", "Y"),
        ("disable-change-id", "Y"),
        ("disable-change-permanent-password", "Y"),
    ]
    # Réglages « durs » : type de client ; pour le client « proche » (incoming),
    # la page Réglages est entièrement désactivée.
    durs = []
    if conn_type:
        durs.append(("conn-type", conn_type))
    if conn_type == "incoming":
        durs += [("disable-settings", "Y"), ("disable-ab", "Y"), ("disable-account", "Y")]

    for nom_map, paires in (("OVERWRITE_SETTINGS", imposes), ("BUILTIN_SETTINGS", integres),
                            ("HARD_SETTINGS", durs)):
        c = remplacer(c, rf'(pub static ref {nom_map}: RwLock<HashMap<String, String>> = )'
                         r'(?:Default::default\(\)|RwLock::new\(HashMap::from\(\[.*?\]\)\));',
                      lambda m, p=paires: m.group(1) + rust_map(p) + ";", rel)
    ecrire(rel, c)
    origine = f"serveur « {serveur} »" if serveur_perso else "serveurs publics RustDesk (inchangés)"
    print(f"OK {rel} : {origine}, nom « {nom} » et réglages imposés")

    # ------------------------------------------------------------------ Windows
    rel = "flutter/windows/runner/Runner.rc"
    r = lire(rel)
    r = remplacer(r, r'VALUE "CompanyName", "[^"]*"', f'VALUE "CompanyName", "{nom_affiche}"', rel)
    r = remplacer(r, r'VALUE "FileDescription", "[^"]*"',
                  f'VALUE "FileDescription", "{nom_affiche} – assistance à distance"', rel)
    r = remplacer(r, r'VALUE "ProductName", "[^"]*"', f'VALUE "ProductName", "{nom_affiche}"', rel)
    r = remplacer(r, r'VALUE "LegalCopyright", "[^"]*"',
                  'VALUE "LegalCopyright", "Basé sur RustDesk (AGPL-3.0), © Purslane Tech Pte. Ltd. '
                  f'Personnalisation © {nom_affiche}"', rel)
    ecrire(rel, r)
    print(f"OK {rel}")

    # ------------------------------------------------------------------ macOS
    rel = "flutter/macos/Runner/Configs/AppInfo.xcconfig"
    x = lire(rel)
    x = remplacer(x, r'^PRODUCT_NAME = .*$', f"PRODUCT_NAME = {nom}", rel)
    x = remplacer(x, r'^PRODUCT_COPYRIGHT = .*$',
                  f"PRODUCT_COPYRIGHT = Basé sur RustDesk (AGPL-3.0). Personnalisation {nom_affiche}", rel)
    ecrire(rel, x)
    print(f"OK {rel}")

    rel = "build.py"
    b = lire(rel)
    b = remplacer(b, r'\./build/macos/Build/Products/Release/RustDesk\.app',
                  f"./build/macos/Build/Products/Release/{nom}.app", rel, attendu=2,
                  deja=rf'\./build/macos/Build/Products/Release/{nom}\.app')
    b = remplacer(b, r'--icon RustDesk\.app 200 190 --hide-extension RustDesk\.app',
                  f"--icon {nom}.app 200 190 --hide-extension {nom}.app", rel,
                  deja=rf'--icon {nom}\.app 200 190')
    ecrire(rel, b)
    print(f"OK {rel}")

    # ------------------------------------------------------------------ icônes
    source = os.path.join(RACINE, icones)
    if not os.path.isdir(source):
        erreur(f"Dossier d'icônes introuvable : {icones}")
    n = 0
    for dossier, _, fichiers in os.walk(source):
        for f in fichiers:
            src = os.path.join(dossier, f)
            dst = os.path.join(RACINE, os.path.relpath(src, source))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            n += 1
    if n < 15:
        erreur(f"Seulement {n} icônes copiées : le dossier {icones} est incomplet.")
    print(f"OK {n} icônes copiées depuis {icones}")

    # Nom du bundle macOS pour les étapes suivantes du workflow
    env_github = os.environ.get("GITHUB_ENV")
    if env_github:
        with open(env_github, "a", encoding="utf-8") as f:
            f.write(f"ZR_APP_NAME={nom}\nZR_MAC_APP={nom}.app\n")
    print("Personnalisation terminée.")


if __name__ == "__main__":
    main()
