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
ORDER_HINT = (
    "L'ordre ci-dessous est celui des lignes de la frise. "
    "Les événements d'une couleur sans catégorie restent affichés."
)
ORDER_HINT_EN = (
    "The order below is the order of the timeline lanes. "
    "Events whose color has no category remain displayed."
)
ORDER_HINT_ES = (
    "El orden de abajo es el de las filas de la cronología. "
    "Los eventos de un color sin categoría siguen mostrándose."
)
LINES_FR = (
    "Un titre trop long pour la place disponible passe sur plusieurs lignes "
    "(jusqu'à ce nombre) : plus de titres s'affichent en entier, "
    "mais les lignes de la frise deviennent plus hautes."
)
LINES_EN = (
    "A title too long for the available space wraps onto several lines "
    "(up to this number): more titles are shown in full, "
    "but the timeline rows become taller."
)
LINES_ES = (
    "Un título demasiado largo para el espacio disponible pasa a varias líneas "
    "(hasta este número): se muestran más títulos completos, "
    "pero las filas de la cronología son más altas."
)
UNSEEN_FR = (
    "%1 titres tronqués ou masqués : choisissez une page plus grande "
    "ou réduisez la taille du texte pour en afficher davantage."
)
UNSEEN_EN = (
    "%1 titles truncated or hidden: choose a larger page "
    "or reduce the text size to show more of them."
)
UNSEEN_ES = (
    "%1 títulos recortados u ocultos: elija una página mayor "
    "o reduzca el tamaño del texto para mostrar más."
)
FIXED_FR = (
    "Touches fixes : Suppr supprime l'événement sélectionné, Échap le désélectionne, "
    "molette = zoom, Maj + molette = défilement vertical."
)
FIXED_EN = (
    "Fixed keys: Del deletes the selected event, Esc deselects it, "
    "wheel = zoom, Shift + wheel = vertical scroll."
)
FIXED_ES = (
    "Teclas fijas: Supr elimina el evento seleccionado, Esc lo deselecciona, "
    "rueda = zoom, Mayús + rueda = desplazamiento vertical."
)
SIZE_FR = (
    "Taille du texte sur la feuille. La frise s'élargit quand le texte est plus petit : "
    "plus de titres s'affichent en entier."
)
SIZE_EN = (
    "Text size on the sheet. The timeline gets wider when the text is smaller: "
    "more titles are shown in full."
)
SIZE_ES = (
    "Tamaño del texto en la hoja. La cronología se ensancha cuando el texto es más pequeño: "
    "se muestran más títulos completos."
)
REDUCED_FR = (
    "Texte réduit à %1 pt (au lieu de %2 pt) pour que la frise tienne dans la "
    "hauteur de la page : choisissez une page plus haute ou un texte plus petit."
)
REDUCED_EN = (
    "Text reduced to %1 pt (instead of %2 pt) so that the timeline fits the "
    "page height: choose a taller page or smaller text."
)
REDUCED_ES = (
    "Texto reducido a %1 pt (en lugar de %2 pt) para que la cronología quepa en la "
    "altura de la página: elija una página más alta o un texto más pequeño."
)
LIMIT_FR = (
    "Au-delà de 5 m, certains lecteurs PDF refusent la page : le PDF sera exporté "
    "à l'échelle 1/%1 (vectoriel, sans perte). Imprimez-le à %2 %."
)
LIMIT_EN = (
    "Beyond 5 m, some PDF readers refuse the page: the PDF will be exported "
    "at 1/%1 scale (vector, lossless). Print it at %2 %."
)
LIMIT_ES = (
    "Por encima de 5 m, algunos lectores PDF rechazan la página: el PDF se exportará "
    "a escala 1/%1 (vectorial, sin pérdida). Imprímalo al %2 %."
)
SETUP_FR = "Réglez la feuille (format, titre…), puis exportez-la en PDF."
SETUP_EN = "Set up the sheet (format, title…), then export it as PDF."
SETUP_ES = "Configure la hoja (formato, título…) y expórtela a PDF."
T: dict[str, tuple[str, str]] = {
    "Ajouter un événement": ("Add an event", "Añadir un evento"),
    "Modifier un événement": ("Edit an event", "Modificar un evento"),
    "Changer la couleur d'une catégorie": (
        "Change a category color",
        "Cambiar el color de una categoría",
    ),
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
    "Ouvrez un fichier CSV (Ctrl+O) ou glissez-le ici": (
        "Open a CSV file (Ctrl+O) or drag it here",
        "Abra un archivo CSV (Ctrl+O) o arrástrelo aquí",
    ),
    "Déposez un fichier CSV pour l'ouvrir": (
        "Drop a CSV file to open it",
        "Suelte un archivo CSV para abrirlo",
    ),
    "Seuls les fichiers CSV peuvent être déposés.": (
        "Only CSV files can be dropped.",
        "Solo se pueden soltar archivos CSV.",
    ),
    "%1 fichiers déposés : « %2 » est ouvert, les autres sont ignorés.": (
        "%1 files dropped: “%2” is opened, the others are ignored.",
        "%1 archivos soltados: se abre «%2», los demás se ignoran.",
    ),
    "Nom": ("Name", "Nombre"),
    "Modifier la catégorie": ("Edit category", "Modificar la categoría"),
    "Modifier la catégorie…": ("Edit category…", "Modificar la categoría…"),
    "Nouvelle catégorie": ("New category", "Nueva categoría"),
    "Gérer les catégories": ("Manage categories", "Gestionar categorías"),
    "&Gérer les catégories…": ("&Manage categories…", "&Gestionar categorías…"),
    "Ajouter…": ("Add…", "Añadir…"),
    "Monter": ("Move up", "Subir"),
    "Descendre": ("Move down", "Bajar"),
    "Valeurs par défaut": ("Defaults", "Valores predeterminados"),
    ORDER_HINT: (ORDER_HINT_EN, ORDER_HINT_ES),
    "Supprimer la catégorie « %1 » ?": (
        "Delete category “%1”?",
        "¿Eliminar la categoría «%1»?",
    ),
    "Remplacer toutes les catégories par celles livrées avec l'application ?": (
        "Replace all categories with those shipped with the application?",
        "¿Reemplazar todas las categorías por las incluidas con la aplicación?",
    ),
    "Catégories appliquées mais non enregistrées : %1": (
        "Categories applied but not saved: %1",
        "Categorías aplicadas pero no guardadas: %1",
    ),
    "Le nom de la catégorie est vide ou trop long.": (
        "The category name is empty or too long.",
        "El nombre de la categoría está vacío o es demasiado largo.",
    ),
    "Une catégorie porte déjà ce nom.": (
        "A category already has this name.",
        "Ya existe una categoría con este nombre.",
    ),
    "Cette couleur est déjà utilisée par « %1 ».": (
        "This color is already used by “%1”.",
        "Este color ya lo usa «%1».",
    ),
    "Trop de catégories.": ("Too many categories.", "Demasiadas categorías."),
    "%1 titres masqués (zoomez pour les voir)": (
        "%1 titles hidden (zoom in to see them)",
        "%1 títulos ocultos (acerque para verlos)",
    ),
    "Taille du texte": ("Text size", "Tamaño del texto"),
    SIZE_FR: (SIZE_EN, SIZE_ES),
    REDUCED_FR: (REDUCED_EN, REDUCED_ES),
    "&Préférences…": ("&Preferences…", "&Preferencias…"),
    "Préférences": ("Preferences", "Preferencias"),
    "Général": ("General", "General"),
    "Raccourcis": ("Shortcuts", "Atajos"),
    "Action": ("Action", "Acción"),
    "Raccourci": ("Shortcut", "Atajo"),
    "Appuyer sur un raccourci": ("Press a shortcut", "Pulse un atajo"),
    "Réinitialiser": ("Reset", "Restablecer"),
    "Tout réinitialiser": ("Reset all", "Restablecer todo"),
    "Ce raccourci est déjà utilisé par « %1 ».": (
        "This shortcut is already used by “%1”.",
        "Este atajo ya lo usa «%1».",
    ),
    "La nouvelle langue est appliquée au prochain démarrage.": (
        "The new language is applied the next time the application starts.",
        "El nuevo idioma se aplica en el próximo inicio de la aplicación.",
    ),
    FIXED_FR: (FIXED_EN, FIXED_ES),
    "Le nom du format est vide ou trop long.": (
        "The format name is empty or too long.",
        "El nombre del formato está vacío o es demasiado largo.",
    ),
    "Un format porte déjà ce nom.": (
        "A format already has this name.",
        "Ya existe un formato con este nombre.",
    ),
    "Les dimensions doivent être comprises entre 5 cm et 20 m.": (
        "Dimensions must be between 5 cm and 20 m.",
        "Las dimensiones deben estar entre 5 cm y 20 m.",
    ),
    "Trop de formats enregistrés.": ("Too many saved formats.", "Demasiados formatos guardados."),
    "Feuille": ("Sheet", "Hoja"),
    "Libre": ("Free", "Libre"),
    "Frise libre : le zoom dévoile les titres": (
        "Free timeline: zooming reveals the titles",
        "Cronología libre: el zoom revela los títulos",
    ),
    "Feuille : la frise au format d'impression": (
        "Sheet: the timeline at print size",
        "Hoja: la cronología al tamaño de impresión",
    ),
    "Mode Libre": ("Free mode", "Modo libre"),
    "Mode Feuille": ("Sheet mode", "Modo hoja"),
    "Largeur de la feuille": ("Sheet width", "Ancho de la hoja"),
    "Hauteur de la feuille": ("Sheet height", "Alto de la hoja"),
    "Taille réelle (100 %)": ("Actual size (100 %)", "Tamaño real (100 %)"),
    "Règles": ("Rulers", "Reglas"),
    "Mini-carte": ("Mini-map", "Minimapa"),
    "Formats": ("Formats", "Formatos"),
    "Formats personnalisés illisibles, ignorés : %1": (
        "Unreadable custom formats, ignored: %1",
        "Formatos personalizados ilegibles, ignorados: %1",
    ),
    "Format appliqué mais non enregistré : %1": (
        "Format applied but not saved: %1",
        "Formato aplicado pero no guardado: %1",
    ),
    SETUP_FR: (SETUP_EN, SETUP_ES),
    "à imprimer à %1 %": ("print at %1 %", "imprimir al %1 %"),
    "texte %1 pt": ("text %1 pt", "texto %1 pt"),
    "%1 titres complets, %2 tronqués, %3 masqués": (
        "%1 titles complete, %2 truncated, %3 hidden",
        "%1 títulos completos, %2 recortados, %3 ocultos",
    ),
    "Enregistrer ce format…": ("Save this format…", "Guardar este formato…"),
    "Supprimer ce format": ("Delete this format", "Eliminar este formato"),
    "Exporter en PDF…": ("Export to PDF…", "Exportar a PDF…"),
    "Enregistrer ce format": ("Save this format", "Guardar este formato"),
    "Nom du format :": ("Format name:", "Nombre del formato:"),
    "Supprimer le format « %1 » ?": ("Delete format “%1”?", "¿Eliminar el formato «%1»?"),
    "Aucun événement à afficher avec les filtres actuels.": (
        "No events to display with the current filters.",
        "Ningún evento que mostrar con los filtros actuales.",
    ),
    "Aucun événement à afficher": ("No events to display", "Ningún evento que mostrar"),
    LIMIT_FR: (LIMIT_EN, LIMIT_ES),
    "Lignes maximum par titre": ("Maximum lines per title", "Líneas máximas por título"),
    LINES_FR: (LINES_EN, LINES_ES),
    UNSEEN_FR: (UNSEEN_EN, UNSEEN_ES),
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
