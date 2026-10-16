"""
Génère locale/fr/LC_MESSAGES/django.po et .mo : traduction française des textes
de django-unfold (le thème n'est pas traduit en français).

`python manage.py compile_backoffice_locale`
Pur Python : aucune dépendance à gettext/msgfmt (absents sous Windows).
"""
import array
import pathlib

from django.conf import settings
from django.core.management.base import BaseCommand

UNFOLD_FR = {
    "%(class_name)s %(instance)s": "%(class_name)s %(instance)s",
    "Action": "Action",
    "Add new item": "Ajouter un élément",
    "Add row": "Ajouter une ligne",
    "After you've created a user, you’ll be able to edit more user options.":
        "Une fois l’utilisateur créé, vous pourrez modifier ses autres options.",
    "All applications": "Toutes les applications",
    "Apply Filters": "Appliquer les filtres",
    "Bold": "Gras",
    "Choose file to upload": "Choisir un fichier",
    "Click to cancel": "Cliquer pour annuler",
    "Click to download": "Cliquer pour télécharger",
    "Code": "Code",
    "Dark": "Sombre",
    "Dataset not found. No action performed.": "Données introuvables. Aucune action effectuée.",
    "Date": "Date",
    "Date from": "Du",
    "Date to": "Au",
    "Enter an URL": "Saisir une URL",
    "Expand row": "Déplier la ligne",
    "False": "Non",
    "From": "De",
    "General": "Général",
    "Go back": "Retour",
    "Heading": "Titre",
    "Hide counts": "Masquer les compteurs",
    "Image preview": "Aperçu de l’image",
    "Indent decrease": "Réduire le retrait",
    "Indent increase": "Augmenter le retrait",
    "Italic": "Italique",
    "Light": "Clair",
    "Link": "Lien",
    "Loading more results...": "Chargement de résultats…",
    "More actions": "Plus d’actions",
    "Next": "Suivant",
    "No data": "Aucune donnée",
    "No recent searches": "Aucune recherche récente",
    "No results found": "Aucun résultat",
    "No results matching your query": "Aucun résultat pour cette recherche",
    "Not enough data.": "Pas assez de données.",
    "Ordered list": "Liste numérotée",
    "Paragraph": "Paragraphe",
    "Previous": "Précédent",
    "Quote": "Citation",
    "Recent searches": "Recherches récentes",
    "Record picture": "Photo",
    "Redo": "Rétablir",
    "Reset filters": "Réinitialiser les filtres",
    "Return to site": "Retour au site",
    "Run": "Exécuter",
    "Search apps and models...": "Rechercher dans le menu…",
    "Select action": "Choisir une action",
    "Select action to run": "Choisir l’action à exécuter",
    "Select all objects on this page for an action": "Sélectionner tous les éléments de la page",
    "Select all rows": "Tout sélectionner",
    "Select currency": "Choisir la devise",
    "Select record": "Choisir un élément",
    "Select value": "Choisir une valeur",
    "Show counts": "Afficher les compteurs",
    "Strike": "Barré",
    "System": "Système",
    "This item will be deleted.": "Cet élément sera supprimé.",
    "This page yielded into no results. Create a new item or reset your filters.":
        "Aucun résultat. Modifiez vos filtres ou votre recherche.",
    "To": "À",
    "Toggle password visibility": "Afficher ou masquer le mot de passe",
    "True": "Oui",
    "Type to search": "Rechercher…",
    "Underlined": "Souligné",
    "Undo": "Annuler",
    "Unlink": "Retirer le lien",
    "Unordered list": "Liste à puces",
    "Value": "Valeur",
    "Welcome": "Bienvenue",
    "Welcome back to": "Bon retour sur",
    "You can not create nested object without parent": "Impossible de créer un élément imbriqué sans parent",
    "You have been successfully logged out from the administration": "Vous êtes déconnecté du back-office",
}


def _po_escape(text):
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def write_po(path, catalog):
    lines = [
        'msgid ""', 'msgstr ""',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Language: fr\\n"', "",
        "# Traductions de django-unfold — générées par compile_backoffice_locale", "",
    ]
    for msgid, msgstr in sorted(catalog.items()):
        lines += [f'msgid "{_po_escape(msgid)}"', f'msgstr "{_po_escape(msgstr)}"', ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_mo(path, catalog):
    """Format binaire GNU gettext (même algorithme que Tools/i18n/msgfmt.py)."""
    entries = {"": "Content-Type: text/plain; charset=UTF-8\nLanguage: fr\n", **catalog}
    keys = sorted(entries)
    ids = strs = b""
    offsets = []
    for k in keys:
        kb, vb = k.encode("utf-8"), entries[k].encode("utf-8")
        offsets.append((len(ids), len(kb), len(strs), len(vb)))
        ids += kb + b"\0"
        strs += vb + b"\0"
    keystart = 7 * 4 + 16 * len(keys)
    valuestart = keystart + len(ids)
    koffsets, voffsets = [], []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]
    header = array.array("I", [0x950412DE, 0, len(keys), 7 * 4, 7 * 4 + len(keys) * 8, 0, 0])
    path.write_bytes(
        header.tobytes() + array.array("I", koffsets + voffsets).tobytes() + ids + strs
    )


class Command(BaseCommand):
    help = "Génère la traduction française de django-unfold (locale/fr)."

    def handle(self, *args, **options):
        out = pathlib.Path(settings.BASE_DIR) / "locale" / "fr" / "LC_MESSAGES"
        out.mkdir(parents=True, exist_ok=True)
        write_po(out / "django.po", UNFOLD_FR)
        write_mo(out / "django.mo", UNFOLD_FR)
        self.stdout.write(self.style.SUCCESS(f"{len(UNFOLD_FR)} traductions écrites dans {out}"))
