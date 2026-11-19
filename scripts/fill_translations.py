"""Remplit les traductions EN/ES des fichiers .ts (texte source : français).

Usage : python scripts/fill_translations.py   puis   scripts/update_translations.sh
Seules les traductions encore « unfinished » sont remplies.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

TS_DIR = Path(__file__).resolve().parent.parent / "src" / "chronologia" / "translations"

# français : (anglais, espagnol)
T: dict[str, tuple[str, str]] = {
    "Ajouter un événement": ("Add an event", "Añadir un evento"),
    "Modifier un événement": ("Edit an event", "Modificar un evento"),
    "Supprimer un événement": ("Delete an event", "Eliminar un evento"),
    "Modifier l'événement": ("Edit event", "Modificar el evento"),
    "Nouvel événement": ("New event", "Nuevo evento"),
    "aaaa, aaaamm, aaaammjj ou jj/mm/aaaa": (
        "yyyy, yyyymm, yyyymmdd or dd/mm/yyyy",
        "aaaa, aaaamm, aaaammdd o dd/mm/aaaa",
    ),
    "vide = événement ponctuel": ("empty = single-date event", "vacío = evento puntual"),
    "Commentaire ou source (affiché au survol)": (
        "Comment or source (shown on hover)",
        "Comentario o fuente (se muestra al pasar el ratón)",
    ),
    "Couleur personnalisée": ("Custom colour", "Color personalizado"),
    "red ou #FF0000": ("red or #FF0000", "red o #FF0000"),
    "Choisir…": ("Choose…", "Elegir…"),
    "Titre": ("Title", "Título"),
    "Début": ("Start", "Inicio"),
    "Fin": ("End", "Fin"),
    "Catégorie": ("Category", "Categoría"),
    "Couleur": ("Colour", "Color"),
    "Source": ("Source", "Fuente"),
    "Le titre est obligatoire.": ("The title is required.", "El título es obligatorio."),
    "Le titre est trop long.": ("The title is too long.", "El título es demasiado largo."),
    "Date de début invalide (aaaa, aaaamm, aaaammjj, mm/aaaa ou jj/mm/aaaa).": (
        "Invalid start date (yyyy, yyyymm, yyyymmdd, mm/yyyy or dd/mm/yyyy).",
        "Fecha de inicio no válida (aaaa, aaaamm, aaaammdd, mm/aaaa o dd/mm/aaaa).",
    ),
    "Date de fin invalide.": ("Invalid end date.", "Fecha de fin no válida."),
    "La fin ne peut pas précéder le début.": (
        "The end cannot be before the start.",
        "El fin no puede ser anterior al inicio.",
    ),
    "Couleur inconnue (nom comme « red » ou code #FF0000).": (
        "Unknown colour (a name such as “red” or a code like #FF0000).",
        "Color desconocido (un nombre como «red» o un código como #FF0000).",
    ),
    "La source est trop longue.": ("The source is too long.", "La fuente es demasiado larga."),
    "Exporter en PDF": ("Export to PDF", "Exportar a PDF"),
    "Personnalisé": ("Custom", "Personalizado"),
    "Paysage": ("Landscape", "Horizontal"),
    "Portrait": ("Portrait", "Vertical"),
    "Titre affiché en haut de la frise (facultatif)": (
        "Title shown at the top of the timeline (optional)",
        "Título mostrado en la parte superior de la cronología (opcional)",
    ),
    "Limiter à la période": ("Limit to period", "Limitar al período"),
    "Format": ("Format", "Formato"),
    "Orientation": ("Orientation", "Orientación"),
    "Dimensions": ("Dimensions", "Dimensiones"),
    "Période": ("Period", "Período"),
    "Exporter…": ("Export…", "Exportar…"),
    "Aucun événement à exporter avec les filtres actuels.": (
        "No events to export with the current filters.",
        "No hay eventos que exportar con los filtros actuales.",
    ),
    "%1 événements, %2 catégories. Taille du texte sur la page : %3 pt.": (
        "%1 events, %2 categories. Text size on the page: %3 pt.",
        "%1 eventos, %2 categorías. Tamaño del texto en la página: %3 pt.",
    ),
    "Texte très petit : choisissez un format plus grand ou une période plus courte.": (
        "Very small text: choose a larger format or a shorter period.",
        "Texto muy pequeño: elija un formato mayor o un período más corto.",
    ),
    "Au-delà de 5 m, certains lecteurs PDF refusent la page. Le PDF est vectoriel : exportez à la moitié ou au dixième de la taille, puis agrandissez à l'impression.": (
        "Above 5 m, some PDF readers reject the page. The PDF is vector-based: export at half or one tenth of the size, then enlarge when printing.",
        "Por encima de 5 m, algunos lectores de PDF rechazan la página. El PDF es vectorial: exporte a la mitad o a la décima parte del tamaño y amplíe al imprimir.",
    ),
    "Tout": ("All", "Todo"),
    "Aucun": ("None", "Ninguno"),
    "Catégories": ("Categories", "Categorías"),
    "Catégories personnalisées illisibles, valeurs par défaut utilisées : %1": (
        "Custom categories unreadable, defaults used: %1",
        "Categorías personalizadas ilegibles, se usan los valores por defecto: %1",
    ),
    "&Ouvrir un CSV…": ("&Open CSV…", "&Abrir CSV…"),
    "&Enregistrer": ("&Save", "&Guardar"),
    "Enregistrer &sous…": ("Save &as…", "Guardar &como…"),
    "E&xporter en PDF…": ("E&xport to PDF…", "E&xportar a PDF…"),
    "&Quitter": ("&Quit", "&Salir"),
    "&Fichier": ("&File", "&Archivo"),
    "&Nouvel événement…": ("&New event…", "&Nuevo evento…"),
    "Annuler": ("Undo", "Deshacer"),
    "Rétablir": ("Redo", "Rehacer"),
    "&Édition": ("&Edit", "&Edición"),
    "Zoom +": ("Zoom in", "Acercar"),
    "Zoom −": ("Zoom out", "Alejar"),
    "Ajuster": ("Fit", "Ajustar"),
    "Rechercher un événement…": ("Search for an event…", "Buscar un evento…"),
    "Outils": ("Tools", "Herramientas"),
    "&Affichage": ("&View", "&Ver"),
    "&Langue": ("&Language", "&Idioma"),
    "Langue": ("Language", "Idioma"),
    "La nouvelle langue sera appliquée au prochain démarrage de Chronologia.": (
        "The new language will be applied the next time Chronologia starts.",
        "El nuevo idioma se aplicará la próxima vez que se inicie Chronologia.",
    ),
    "Supprimer l'événement": ("Delete event", "Eliminar el evento"),
    "Supprimer « %1 » ? (Annulable avec Ctrl+Z)": (
        "Delete “%1”? (Can be undone with Ctrl+Z)",
        "¿Eliminar «%1»? (Se puede deshacer con Ctrl+Z)",
    ),
    "Ouvrir un CSV": ("Open a CSV", "Abrir un CSV"),
    "Fichiers CSV (*.csv);;Tous les fichiers (*)": (
        "CSV files (*.csv);;All files (*)",
        "Archivos CSV (*.csv);;Todos los archivos (*)",
    ),
    "Import impossible": ("Import failed", "No se puede importar"),
    "Enregistrer sous": ("Save as", "Guardar como"),
    "Fichiers CSV (*.csv)": ("CSV files (*.csv)", "Archivos CSV (*.csv)"),
    "Enregistrement impossible": ("Save failed", "No se puede guardar"),
    "Enregistré : %1": ("Saved: %1", "Guardado: %1"),
    "Fichiers PDF (*.pdf)": ("PDF files (*.pdf)", "Archivos PDF (*.pdf)"),
    "Export impossible": ("Export failed", "No se puede exportar"),
    "PDF exporté : %1": ("PDF exported: %1", "PDF exportado: %1"),
    "Modifications non enregistrées": ("Unsaved changes", "Cambios sin guardar"),
    "Enregistrer les modifications avant de continuer ?": (
        "Save changes before continuing?",
        "¿Guardar los cambios antes de continuar?",
    ),
    "Sans titre": ("Untitled", "Sin título"),
    "Import terminé avec des anomalies": (
        "Import completed with issues",
        "Importación terminada con incidencias",
    ),
    "%1 événements importés, %2 lignes ignorées, %3 corrigées.": (
        "%1 events imported, %2 rows skipped, %3 corrected.",
        "%1 eventos importados, %2 filas omitidas, %3 corregidas.",
    ),
    "ligne": ("row", "fila"),
    "%1 événements affichés / %2": ("%1 events shown / %2", "%1 eventos mostrados / %2"),
    "%1 correspondances": ("%1 matches", "%1 coincidencias"),
    "titre vide": ("empty title", "título vacío"),
    "date de début invalide : %1": ("invalid start date: %1", "fecha de inicio no válida: %1"),
    "date de fin invalide : %1": ("invalid end date: %1", "fecha de fin no válida: %1"),
    "fin avant début : dates remises dans l'ordre": (
        "end before start: dates put back in order",
        "fin anterior al inicio: fechas reordenadas",
    ),
    "couleur inconnue %1 : gris utilisé": (
        "unknown colour %1: grey used",
        "color desconocido %1: se usa gris",
    ),
    "Le fichier est vide.": ("The file is empty.", "El archivo está vacío."),
    "Colonnes obligatoires absentes : %1": (
        "Required columns missing: %1",
        "Faltan columnas obligatorias: %1",
    ),
    "Le fichier est trop volumineux.": (
        "The file is too large.",
        "El archivo es demasiado grande.",
    ),
    "titre trop long : tronqué": ("title too long: truncated", "título demasiado largo: recortado"),
    "source trop longue : tronquée": (
        "source too long: truncated",
        "fuente demasiado larga: recortada",
    ),
    "plus de %1 événements : import arrêté": (
        "more than %1 events: import stopped",
        "más de %1 eventos: importación detenida",
    ),
    "Le fichier est mal formé (autour de la ligne %1).": (
        "The file is malformed (around row %1).",
        "El archivo está mal formado (cerca de la fila %1).",
    ),
    "Modifier…": ("Edit…", "Modificar…"),
    "Supprimer": ("Delete", "Eliminar"),
    "Nouvel événement ici…": ("New event here…", "Nuevo evento aquí…"),
    "Ouvrez un fichier CSV (Ctrl+O)": ("Open a CSV file (Ctrl+O)", "Abra un archivo CSV (Ctrl+O)"),
}


def fill(path: Path, index: int) -> tuple[int, list[str]]:
    text = path.read_text(encoding="utf-8")
    missing: list[str] = []
    done = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal done
        block = match.group(0)
        source = html.unescape(re.search(r"<source>(.*?)</source>", block, re.DOTALL).group(1))
        if source not in T:
            missing.append(source)
            return block
        done += 1
        value = html.escape(T[source][index], quote=False)
        return re.sub(
            r'<translation type="unfinished">.*?</translation>',
            lambda _m: f"<translation>{value}</translation>",
            block,
            flags=re.DOTALL,
        )

    text = re.sub(r"<message>.*?</message>", repl, text, flags=re.DOTALL)
    path.write_text(text, encoding="utf-8")
    return done, missing


if __name__ == "__main__":
    for i, lang in enumerate(("en", "es")):
        done, missing = fill(TS_DIR / f"chronologia_{lang}.ts", i)
        print(lang, done, "traduits ; manquants :", missing)
