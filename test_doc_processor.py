from document_processor import DocumentReader

def main():
    # specify your files
    file_paths = [
        "contextual-docs/grant_application_examples/README.md",
        # add more files as needed
        # "path/to/other/file.pdf",
    ]

    reader = DocumentReader(file_paths=file_paths)

    documents = reader.load_all()


    print("\n" + "=" * 60)
    print("DOCUMENT CONTENTS")
    print("=" * 60)

    for file_path, content in documents.items():
        print(f"\n{'=' * 60}")
        print(f"File: {file_path}")
        print(f"{'=' * 60}")
        print(content)
        print(f"\n[End of {file_path}]")


    all_content = reader.get_all_content()
    print(f"\n{'=' * 60}")
    print(f"TOTAL: {len(all_content)} characters across {len(documents)} documents")
    print("=" * 60)


if __name__ == "__main__":
    main()