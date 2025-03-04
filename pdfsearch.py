import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import zipfile
import tempfile
import PyPDF2
from typing import List, Tuple, Dict
import threading
import time
import shutil
import logging
import sys
import platform

# Configuration pour supprimer les messages de PyPDF2
logging.getLogger('PyPDF2').setLevel(logging.ERROR)


# Fonctions utilitaires pour la compatibilité multi-plateforme
def get_system_info():
    system = platform.system()
    is_macos = system == "Darwin"
    is_windows = system == "Windows"
    return {"system": system, "is_macos": is_macos, "is_windows": is_windows}


def get_default_output_dir():
    system_info = get_system_info()

    if getattr(sys, 'frozen', False):
        # Si c'est un exécutable créé par PyInstaller
        if system_info["is_macos"]:
            # Sur macOS, éviter d'utiliser le dossier de l'exécutable dans le bundle
            # Utiliser plutôt le dossier Documents dans le répertoire personnel de l'utilisateur
            return os.path.join(os.path.expanduser("~"), "Documents")
        else:
            # Sur Windows, utiliser le dossier où se trouve l'exécutable
            return os.path.dirname(sys.executable)
    else:
        # Si c'est un script Python normal
        return os.path.dirname(os.path.abspath(__file__))


def create_safe_temp_dir():
    # Créer un répertoire temporaire dans un emplacement accessible
    if get_system_info()["is_macos"]:
        # Sur macOS, utiliser un dossier temporaire dans le répertoire personnel
        temp_base = os.path.join(os.path.expanduser("~"), "Library", "Caches")
        os.makedirs(temp_base, exist_ok=True)
        return tempfile.mkdtemp(dir=temp_base)
    else:
        # Sur d'autres systèmes, utiliser le comportement par défaut
        return tempfile.mkdtemp()


def normalize_path(path):
    # Convertir les backslash en slash pour une meilleure compatibilité
    return os.path.normpath(path).replace("\\", "/")


def create_directory_with_permissions(directory_path):
    try:
        os.makedirs(directory_path, exist_ok=True)
        # Vérifier que le dossier est accessible en écriture
        test_file_path = os.path.join(directory_path, ".permission_test")
        with open(test_file_path, 'w') as f:
            f.write("test")
        os.remove(test_file_path)
        return True
    except (PermissionError, OSError) as e:
        print(f"Erreur de permission lors de la création du dossier {directory_path}: {str(e)}")
        return False


class PDFSearchApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.temp_dir = None
        self.title("Recherche pdf")
        self.geometry("800x600")
        self.directory_path = ctk.StringVar()
        self.output_directory_path = ctk.StringVar()
        self.search_text = ctk.StringVar()
        self.extract_option = ctk.StringVar(value="pages")  # Valeur par défaut: pages
        self.is_processing = False
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        # Utiliser la fonction améliorée pour obtenir le répertoire par défaut
        default_output_dir = get_default_output_dir()
        self.output_directory_path.set(default_output_dir)

        self.create_widgets()

    def create_widgets(self):
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        title = ctk.CTkLabel(main_frame, text="Recherche de documents pdf", font=("Arial", 22))
        title.pack(pady=10)

        dir_frame = ctk.CTkFrame(main_frame)
        dir_frame.pack(fill="x", padx=10, pady=5)
        dir_label = ctk.CTkLabel(dir_frame, text="Dossier de recherche:")
        dir_label.pack(side="left", padx=5)
        self.dir_entry = ctk.CTkEntry(dir_frame, textvariable=self.directory_path, width=400)
        self.dir_entry.pack(side="left", padx=5)
        dir_button = ctk.CTkButton(dir_frame, text="Parcourir", command=self.browse_directory, width=100)
        dir_button.pack(side="right", padx=5)

        # Ajout du cadre pour le dossier de sortie
        output_dir_frame = ctk.CTkFrame(main_frame)
        output_dir_frame.pack(fill="x", padx=10, pady=5)
        output_dir_label = ctk.CTkLabel(output_dir_frame, text="Dossier des résultats:")
        output_dir_label.pack(side="left", padx=5)
        self.output_dir_entry = ctk.CTkEntry(output_dir_frame, textvariable=self.output_directory_path, width=400)
        self.output_dir_entry.pack(side="left", padx=5)
        output_dir_button = ctk.CTkButton(output_dir_frame, text="Parcourir", command=self.browse_output_directory,
                                          width=100)
        output_dir_button.pack(side="right", padx=5)

        search_frame = ctk.CTkFrame(main_frame)
        search_frame.pack(fill="x", padx=10, pady=5)
        search_label = ctk.CTkLabel(search_frame, text="Texte à rechercher:")
        search_label.pack(side="left", padx=5)
        search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_text, width=400)
        search_entry.pack(side="left", padx=5)

        # Ajout des options d'extraction
        option_frame = ctk.CTkFrame(main_frame)
        option_frame.pack(fill="x", padx=10, pady=5)
        option_label = ctk.CTkLabel(option_frame, text="Mode d'extraction:")
        option_label.pack(side="left", padx=5)

        # Option pour extraire uniquement les pages contenant le texte
        pages_radio = ctk.CTkRadioButton(option_frame, text="Pages contenant le texte",
                                         variable=self.extract_option, value="pages")
        pages_radio.pack(side="left", padx=20)

        # Option pour extraire les documents entiers
        docs_radio = ctk.CTkRadioButton(option_frame, text="Documents entiers",
                                        variable=self.extract_option, value="documents")
        docs_radio.pack(side="left", padx=20)

        self.search_button = ctk.CTkButton(main_frame, text="Lancer la recherche", command=self.start_search)
        self.search_button.pack(pady=10)

        self.progress_bar = ctk.CTkProgressBar(main_frame)
        self.progress_bar.pack(fill="x", padx=10, pady=5)
        self.progress_bar.set(0)

        self.log_text = ctk.CTkTextbox(main_frame, height=200)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=5)

    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            # Normaliser le chemin pour une meilleure compatibilité
            self.directory_path.set(normalize_path(directory))

    def browse_output_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            # Normaliser le chemin pour une meilleure compatibilité
            self.output_directory_path.set(normalize_path(directory))

    def log(self, message: str):
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")

    def search_in_pdf(self, pdf_path: str, search_text: str) -> List[Tuple[int, str]]:
        matching_pages = []
        # Convertir le texte recherché en minuscules pour une recherche insensible à la casse
        search_text_lower = search_text.lower()

        try:
            # Utiliser normalize_path pour assurer la compatibilité des chemins
            pdf_path = normalize_path(pdf_path)
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text = page.extract_text()
                    # Convertir le texte de la page en minuscules pour comparaison
                    if text and search_text_lower in text.lower():
                        matching_pages.append((page_num, pdf_path))
        except Exception as e:
            self.log(f"Erreur lors de la lecture de {pdf_path}: {str(e)}")
        return matching_pages

    def process_directory(self, directory: str, search_text: str) -> Dict[str, List[int]]:
        all_matching_pages = []
        pdf_files = []
        matching_documents = {}  # Dictionnaire pour stocker les documents et leurs pages correspondantes

        # Utiliser create_safe_temp_dir pour éviter les problèmes de permissions
        self.temp_dir = create_safe_temp_dir()

        for root, _, files in os.walk(directory):
            for file in files:
                file_path = normalize_path(os.path.join(root, file))
                if file.lower().endswith('.pdf'):
                    pdf_files.append(file_path)
                elif file.lower().endswith('.zip'):
                    try:
                        with zipfile.ZipFile(file_path, 'r') as zip_ref:
                            for zip_file in zip_ref.namelist():
                                if zip_file.lower().endswith('.pdf'):
                                    extraction_path = normalize_path(os.path.join(self.temp_dir, zip_file))
                                    # Créer les dossiers parents si nécessaire pour les fichiers dans des sous-dossiers zip
                                    os.makedirs(os.path.dirname(extraction_path), exist_ok=True)
                                    zip_ref.extract(zip_file, self.temp_dir)
                                    pdf_files.append(extraction_path)
                    except Exception as e:
                        self.log(f"Erreur avec le fichier ZIP {file_path}: {str(e)}")

        total_files = len(pdf_files)
        for i, pdf_path in enumerate(pdf_files):
            if not self.is_processing:
                break

            self.log(f"Traitement de {pdf_path}")
            matching_pages = self.search_in_pdf(pdf_path, search_text)

            if matching_pages:
                # Ajouter ce document au dictionnaire des correspondances
                doc_pages = [page_num for page_num, _ in matching_pages]
                matching_documents[pdf_path] = doc_pages
                all_matching_pages.extend(matching_pages)

            progress = (i + 1) / total_files
            self.progress_bar.set(progress)

        return matching_documents, all_matching_pages

    def create_output_pdf(self, matching_info, output_path: str, mode: str):
        # Normaliser le chemin de sortie
        output_path = normalize_path(output_path)

        # En mode "pages", on crée un seul PDF avec les pages spécifiques
        if mode == "pages":
            writer = PyPDF2.PdfWriter()
            matching_pages = matching_info[1]  # all_matching_pages
            self.log(f"Mode 'pages': Extraction de {len(matching_pages)} pages spécifiques")

            for page_num, pdf_path in matching_pages:
                try:
                    with open(pdf_path, 'rb') as file:
                        reader = PyPDF2.PdfReader(file)
                        writer.add_page(reader.pages[page_num])
                except Exception as e:
                    self.log(f"Erreur lors de l'ajout de la page {page_num} de {pdf_path}: {str(e)}")
                    continue

            # S'assurer que le dossier parent existe
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Écrire le PDF résultat
            try:
                with open(output_path, 'wb') as output_file:
                    writer.write(output_file)
            except Exception as e:
                self.log(f"Erreur lors de l'écriture du PDF résultat: {str(e)}")
                return 0

            return 1  # Un seul fichier créé

        else:  # mode == "documents"
            # En mode "documents", on copie les fichiers PDF entiers
            # Le output_path est désormais un dossier
            output_dir = normalize_path(os.path.dirname(output_path))
            timestamp = time.strftime("%Y%m%d-%H%M%S")

            # Créer un sous-dossier spécifique pour cette recherche
            result_subdir = normalize_path(os.path.join(output_dir, f"resultats_{timestamp}"))

            # Vérifier les permissions avant de créer le dossier
            if not create_directory_with_permissions(result_subdir):
                self.log(f"Erreur: impossible de créer le dossier {result_subdir}. Vérifiez les permissions.")
                return 0

            matching_documents = matching_info[0]  # matching_documents dict
            self.log(f"Mode 'documents': Copie de {len(matching_documents)} documents entiers")

            # Dictionnaire pour éviter de traiter plusieurs fois le même document
            processed_documents = set()
            copied_files = 0

            for pdf_path in matching_documents:
                if pdf_path in processed_documents:
                    continue

                processed_documents.add(pdf_path)
                file_name = os.path.basename(pdf_path)
                dest_path = normalize_path(os.path.join(result_subdir, file_name))

                # Éviter les conflits de noms de fichiers
                if os.path.exists(dest_path):
                    base_name, ext = os.path.splitext(file_name)
                    dest_path = normalize_path(os.path.join(result_subdir, f"{base_name}_{copied_files}{ext}"))

                self.log(f"Copie du document: {file_name}")

                try:
                    # Copier le fichier entier
                    shutil.copy2(pdf_path, dest_path)
                    copied_files += 1
                except Exception as e:
                    self.log(f"Erreur lors de la copie du document {pdf_path}: {str(e)}")

            return copied_files  # Nombre de fichiers copiés

    def start_search(self):
        if not self.directory_path.get() or not self.search_text.get():
            messagebox.showerror("Erreur", "Veuillez remplir tous les champs")
            return

        if not os.path.exists(self.directory_path.get()):
            messagebox.showerror("Erreur", "Le répertoire spécifié n'existe pas")
            return

        # Vérifier les permissions sur le dossier de sortie
        if not create_directory_with_permissions(self.output_directory_path.get()):
            messagebox.showerror("Erreur",
                                 "Impossible d'écrire dans le dossier de résultats spécifié. Vérifiez les permissions.")
            return

        self.is_processing = True
        self.search_button.configure(state="disabled")
        self.progress_bar.set(0)
        self.log_text.delete("1.0", "end")

        thread = threading.Thread(target=self.search_process)
        thread.start()

    def search_process(self):
        try:
            start_time = time.time()
            self.log("Recherche en cours...")

            matching_info = self.process_directory(
                self.directory_path.get(),
                self.search_text.get()
            )

            if not self.is_processing:
                self.log("Recherche annulée")
                return

            matching_documents, all_matching_pages = matching_info

            if not all_matching_pages:
                self.log("Aucune correspondance trouvée")
                return

            # Utilisation du dossier de sortie spécifié par l'utilisateur
            output_dir = normalize_path(os.path.join(self.output_directory_path.get(), "resultats"))
            if not create_directory_with_permissions(output_dir):
                self.log("Erreur: impossible de créer le dossier des résultats. Vérifiez les permissions.")
                return

            timestamp = time.strftime("%Y%m%d-%H%M%S")

            # Mode d'extraction (pages ou documents)
            mode = self.extract_option.get()
            extraction_type = "pages contenant le texte" if mode == "pages" else "documents entiers"

            # En mode pages, on crée un seul fichier PDF
            # En mode documents, on utilise le même chemin pour le dossier parent
            if mode == "pages":
                output_path = normalize_path(os.path.join(output_dir, f"resultats_{timestamp}.pdf"))
                self.log(f"Génération du PDF avec {extraction_type}...")
            else:
                output_path = normalize_path(os.path.join(output_dir, f"resultats_{timestamp}.pdf"))
                self.log(f"Copie des documents contenant le texte recherché...")

            # Créer le résultat (PDF unique ou copie de fichiers)
            result_count = self.create_output_pdf(matching_info, output_path, mode)

            # Afficher la liste des documents trouvés
            self.log("\nDocuments contenant le texte recherché:")
            for idx, doc_path in enumerate(matching_documents.keys(), 1):
                pages = matching_documents[doc_path]
                self.log(f"{idx}. {os.path.basename(doc_path)} - {len(pages)} page(s) trouvée(s)")

            # Statistiques du nombre de pages et documents
            total_pages_found = sum(len(pages) for pages in matching_documents.values())
            total_docs = len(matching_documents)

            duration = time.time() - start_time

            if mode == "pages":
                # Dans ce mode, on génère un seul PDF
                self.log(f"""
Recherche terminée !
- Documents trouvés : {total_docs}
- Pages contenant le texte : {total_pages_found}
- Mode d'extraction : {extraction_type}
- Temps d'exécution : {duration:.2f} secondes
- PDF généré : {output_path}
                """)
            else:
                # Dans ce mode, on a copié des fichiers entiers
                result_folder = normalize_path(os.path.join(output_dir, f"resultats_{timestamp}"))
                self.log(f"""
Recherche terminée !
- Documents trouvés : {total_docs}
- Documents copiés : {result_count}
- Pages contenant le texte : {total_pages_found}
- Mode d'extraction : {extraction_type}
- Temps d'exécution : {duration:.2f} secondes
- Dossier des résultats : {result_folder}
                """)

        except Exception as e:
            self.log(f"Erreur : {str(e)}")
            messagebox.showerror("Erreur", str(e))

        finally:
            self.is_processing = False
            self.search_button.configure(state="normal")

            # Nettoyage sécurisé des fichiers temporaires
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                except Exception as e:
                    self.log(f"Avertissement: impossible de supprimer les fichiers temporaires: {str(e)}")


def main():
    app = PDFSearchApp()
    app.mainloop()


if __name__ == "__main__":
    main()