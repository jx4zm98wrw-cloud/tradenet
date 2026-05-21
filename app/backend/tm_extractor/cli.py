"""Interactive CLI — preserves the original `python TM_csv_builder.py` UX."""

from __future__ import annotations

import logging
from pathlib import Path

from colorama import Fore, Style

from .config import ExtractorConfig
from .processor import PDFProcessor


class UserInterface:
    @staticmethod
    def get_pdf_selection(pdf_files: list[Path]) -> list[Path]:
        if not pdf_files:
            logging.warning(f"{Fore.YELLOW}No PDF files found in the input directory.{Style.RESET_ALL}")
            return []
        print(f"\n{Fore.BLUE}Available PDFs:{Style.RESET_ALL}")
        for i, pdf in enumerate(pdf_files, 1):
            print(f"{Fore.BLUE}{i}. {pdf.name}{Style.RESET_ALL}")
        print(f"\n{Fore.BLUE}Options:{Style.RESET_ALL}")
        print(f"{Fore.BLUE}1. Process all PDFs{Style.RESET_ALL}")
        print(f"{Fore.BLUE}2. Select specific PDFs{Style.RESET_ALL}")
        while True:
            try:
                choice = input(f"\n{Fore.BLUE}Enter choice (1 or 2): {Style.RESET_ALL}").strip()
                if choice == "1":
                    return pdf_files
                elif choice == "2":
                    indices_input = input(
                        f"{Fore.BLUE}Enter PDF numbers (comma-separated, e.g., 1,2,3): {Style.RESET_ALL}"
                    ).strip()
                    if not indices_input:
                        print(f"{Fore.YELLOW}No input provided. Please try again.{Style.RESET_ALL}")
                        continue
                    selected_indices: set[int] = set()
                    for i in indices_input.split(","):
                        i = i.strip()
                        if not i.isdigit():
                            print(
                                f"{Fore.RED}Invalid input '{i}': Please enter valid numbers.{Style.RESET_ALL}"
                            )
                            break
                        index = int(i) - 1
                        if 0 <= index < len(pdf_files):
                            selected_indices.add(index)
                        else:
                            print(f"{Fore.RED}Index {i} is out of range. Please try again.{Style.RESET_ALL}")
                            break
                    else:
                        if not selected_indices:
                            print(
                                f"{Fore.YELLOW}No valid selections made. Please try again.{Style.RESET_ALL}"
                            )
                            continue
                        return [pdf_files[i] for i in sorted(selected_indices)]
                else:
                    print(f"{Fore.RED}Invalid choice. Please enter 1 or 2.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}Error: {e!s}. Please try again.{Style.RESET_ALL}")


def run(root: Path) -> None:
    """Interactive entry point — used by the project-root CLI wrapper."""
    cfg = ExtractorConfig.from_root(root)
    try:
        pdf_files = sorted(cfg.input_dir.glob("*.pdf"))
        if not pdf_files:
            logging.error(f"{Fore.RED}No PDF files found in the input directory.{Style.RESET_ALL}")
            return
        selected_files = UserInterface.get_pdf_selection(pdf_files)
        if not selected_files:
            logging.warning(f"{Fore.YELLOW}No files selected for processing.{Style.RESET_ALL}")
            return
        processor = PDFProcessor(cfg)
        processor.process_files_parallel(selected_files, max_workers=1)
        logging.info(f"{Fore.GREEN}Processing completed successfully.{Style.RESET_ALL}")
    except Exception as e:
        logging.error(f"{Fore.RED}Application error: {e!s}{Style.RESET_ALL}")
        raise
