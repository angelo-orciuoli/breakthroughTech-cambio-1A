import os
from pypdf import PdfReader
import docx2txt


class DocumentReader:
    """ document reader - extracts text from files"""
    
    def __init__(self, file_paths=None):
        """
        Args:
            file_paths: list of file paths to read
        """
        self.file_paths = file_paths or []
        self.documents = {}  # file_path -> content
    
    def read_file(self, file_path):
        """
        read a single file and return its text content
        
        Args:
            file_path: Path to the file
            
        Returns:
            extracted text content as either a pdf, word, or plain text file
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.pdf':
            return self._read_pdf(file_path)
        elif ext in ['.docx', '.doc']:
            return self._read_docx(file_path)
        elif ext in ['.txt', '.md', '.rst']:
            return self._read_text(file_path)
        else:
            raise ValueError(f"Unsupported file type: {ext}")
    
    def _read_pdf(self, file_path):
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    
    def _read_docx(self, file_path):
        return docx2txt.process(file_path)
    
    def _read_text(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def load_all(self):
        """
        load all files and store their content
        """
        print(f"Loading {len(self.file_paths)} file(s)...\n")
        
        for file_path in self.file_paths:
            try:
                content = self.read_file(file_path)
                self.documents[file_path] = content
                print(f"✓ {file_path}")
                print(f"  Length: {len(content)} characters")
            except Exception as e:
                print(f"✗ {file_path}")
                print(f"  Error: {e}")
        
        print(f"\n✓ Loaded {len(self.documents)}/{len(self.file_paths)} documents successfully")
        return self.documents
    
    def get_content(self, file_path):
        return self.documents.get(file_path)
    
    def get_all_content(self):
        return "\n\n=== NEW DOCUMENT ===\n\n".join(self.documents.values())