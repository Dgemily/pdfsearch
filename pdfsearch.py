import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import zipfile
import tempfile
import PyPDF2
from typing import List, Tuple
import threading
import time
import shutil


class PDFSearchApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.temp_dir = None
        self.title("Recherche PDF")
        self.geometry("800x600")
        self.directory_path = ctk.StringVar()
        self.search_text = ctk.StringVar()
        self.is_processing = False
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        self.create_widgets()

    def create_widgets(self):
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(padx=20, pady=20, fill="both", expand=True)

        title = ctk.CTkLabel(main_frame, text="Recherche dans les PDFs", font=("Arial", 24))
        title.pack(pady=10)

        dir_frame = ctk.CTkFrame(main_frame)
        dir_frame.pack(fill="x", padx=10, pady=5)
        self.dir_entry = ctk.CTkEntry(dir_frame, textvariable=self.directory_path, width=500)
        self.dir_entry.pack(side="left", padx=5)
        dir_button = ctk.CTkButton(dir_frame, text="Parcourir", command=self.browse_directory, width=100)
        dir_button.pack(side="right", padx=5)

        search_frame = ctk.CTkFrame(main_frame)
        search_frame.pack(fill="x", padx=10, pady=5)
        search_label = ctk.CTkLabel(search_frame, text="Texte à rechercher:")
        search_label.pack(side="left", padx=5)
        search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_text, width=400)
        search_entry.pack(side="left", padx=5)

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
            self.directory_path.set(directory)

    def log(self, message: str):
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")

    def search_in_pdf(self, pdf_path: str, search_text: str) -> List[Tuple[int, str]]:
        matching_pages = []
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text = page.extract_text()
                    if text and search_text in text:
                        matching_pages.append((page_num, pdf_path))
        except Exception as e:
            self.log(f"Erreur lors de la lecture de {pdf_path}: {str(e)}")
        return matching_pages

    def process_directory(self, directory: str, search_text: str) -> List[Tuple[int, str]]:
        all_matching_pages = []
        pdf_files = []
        self.temp_dir = tempfile.mkdtemp()

        for root, _, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                if file.lower().endswith('.pdf'):
                    pdf_files.append(file_path)
                elif file.lower().endswith('.zip'):
                    try:
                        with zipfile.ZipFile(file_path, 'r') as zip_ref:
                            for zip_file in zip_ref.namelist():
                                if zip_file.lower().endswith('.pdf'):
                                    zip_ref.extract(zip_file, self.temp_dir)
                                    pdf_files.append(os.path.join(self.temp_dir, zip_file))
                    except Exception as e:
                        self.log(f"Erreur avec le fichier ZIP {file_path}: {str(e)}")

        total_files = len(pdf_files)
        for i, pdf_path in enumerate(pdf_files):
            if not self.is_processing:
                break

            self.log(f"Traitement de {pdf_path}")
            matching_pages = self.search_in_pdf(pdf_path, search_text)
            all_matching_pages.extend(matching_pages)

            progress = (i + 1) / total_files
            self.progress_bar.set(progress)

        return all_matching_pages

    def create_output_pdf(self, matching_pages: List[Tuple[int, str]], output_path: str):
        writer = PyPDF2.PdfWriter()

        for page_num, pdf_path in matching_pages:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                writer.add_page(reader.pages[page_num])

        with open(output_path, 'wb') as output_file:
            writer.write(output_file)

    def start_search(self):
        if not self.directory_path.get() or not self.search_text.get():
            messagebox.showerror("Erreur", "Veuillez remplir tous les champs")
            return

        if not os.path.exists(self.directory_path.get()):
            messagebox.showerror("Erreur", "Le répertoire spécifié n'existe pas")
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

            matching_pages = self.process_directory(
                self.directory_path.get(),
                self.search_text.get()
            )

            if not self.is_processing:
                self.log("Recherche annulée")
                return

            if not matching_pages:
                self.log("Aucune correspondance trouvée")
                return

            output_dir = os.path.join(self.directory_path.get(), "resultats")
            os.makedirs(output_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            output_path = os.path.join(output_dir, f"resultats_{timestamp}.pdf")

            self.log("Génération du PDF...")
            self.create_output_pdf(matching_pages, output_path)

            duration = time.time() - start_time
            self.log(f"""
            Recherche terminée !
            - Pages trouvées : {len(matching_pages)}
            - Temps d'exécution : {duration:.2f} secondes
            - PDF généré : {output_path}
            """)

        except Exception as e:
            self.log(f"Erreur : {str(e)}")
            messagebox.showerror("Erreur", str(e))

        finally:
            self.is_processing = False
            self.search_button.configure(state="normal")
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)


def main():
    app = PDFSearchApp()
    app.mainloop()


if __name__ == "__main__":
    main()