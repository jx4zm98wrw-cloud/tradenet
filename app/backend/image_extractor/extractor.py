r"""
================================================================================
PDF IMAGE EXTRACTOR - COMPREHENSIVE TRADEMARK IMAGE PROCESSING SYSTEM
================================================================================

Version: 2.2 (Three-Mode Processing)
Author: ASL Project Team
Last Updated: November 2025
Python: 3.7+
Platform: Cross-platform (Windows, macOS, Linux)
Optimized for: Apple Silicon (M1/M2/M3) MacBooks

================================================================================
DESCRIPTION
================================================================================

This script provides advanced PDF processing capabilities for extracting and
organizing trademark/logo images from large-scale PDF document collections.
It intelligently handles split logos, performs spatial clustering, and
maintains organized directory structures based on year and document type.

Key Capabilities:
- Processes 1000+ PDFs efficiently with parallel processing
- Automatically detects and merges split logo images
- Supports multiple PDF types (A-type, B-type) with different sector patterns
- Year-based folder organization (2015, 2016, ..., 2025)
- Real-time progress tracking and memory monitoring
- Generates CSV files mapping image names to file paths
- Quick Mode for batch processing with minimal user interaction

================================================================================
FEATURES
================================================================================

✓ INTELLIGENT IMAGE PROCESSING:
  • Spatial clustering to separate different sectors' logos
  • Automatic merging of split/fragmented logo images
  • Configurable thresholds for clustering and combining
  • High-quality image preservation (PNG format, minimal compression)
  • Duplicate image handling (same logo appearing multiple times)

✓ MULTI-TYPE PDF SUPPORT:
  • Type A PDFs: Contains only (210) patterns - Format: 4-2016-10220
  • Type B PDFs: Contains BOTH (210) and (116) patterns
    - (210) patterns: Format 4-2016-10220
    - (116) patterns: Format 1233953 or 0840351A
  
  • Three Processing Modes:
    1. Auto-Detect (default): Processes PDFs based on filename
       - A_T*.pdf → Extract (210) only
       - B_T*.pdf → Extract BOTH (210) and (116)
       - Best for: Normal mixed folder processing
    
    2. Force Type A: Process ALL PDFs using only (210)
       - Ignores (116) patterns completely
       - Faster (no type detection overhead)
       - Best for: When you only want A-type sectors
    
    3. Force Type B: Process ALL PDFs using only (116)
       - Ignores (210) patterns completely
       - A-type PDFs will have 0 sectors
       - Best for: When you only want B-type sectors from B PDFs

✓ SCALABLE PROCESSING:
  • Quick Mode: Process 1000+ PDFs with single prompt
  • Hybrid Batching: Processes folders sequentially with cooling breaks
  • Dynamic Worker Scaling: Adjusts workers based on total workload
    - Small batches (<50 PDFs): Aggressive (6+ workers)
    - Medium batches (50-150): Balanced (4 workers)
    - Large batches (>150): Conservative (3 workers)
  • Cooling breaks between folders (30-60s) prevent thermal throttling
  • Manual Mode: Granular control over year and PDF selection
  • Parallel processing with auto-calculated worker threads
  • Real-time progress bars with ETA and memory monitoring
  • Graceful error handling (one failure doesn't stop others)

✓ SYSTEM SAFETY (MacBook Pro M1 Optimized):
  • Auto-calculates optimal worker count based on CPU and RAM
  • Real-time memory monitoring with warnings at 80% usage
  • Auto garbage collection when memory is high
  • CPU throttling (75% cores) to prevent overheating
  • Worker cap at 8 for stability during sustained workloads

✓ ORGANIZED OUTPUT:
  • Year-based directory structure (mirrors input organization)
  • Separate folders for images, modified PDFs, and CSV files
  • CSV files mapping image names to relative file paths
  • Automatic blank page removal from modified PDFs
  • Comprehensive error logging (errors.json)

✓ USER EXPERIENCE:
  • Auto-confirm prompts (15-second timeout, default options)
  • Three-mode processing selection (Auto/Force A/Force B)
  • Progress bars showing completion %, RAM usage, elapsed time
  • Time estimation before processing starts
  • Detailed completion summary with statistics
  • Cross-platform compatible (Windows/Mac/Linux)
================================================================================
"""

import sys
import os

# ============================================================================
# CRITICAL: Suppress MuPDF C-level stderr BEFORE importing PyMuPDF
# ============================================================================
# MuPDF (C library) writes directly to file descriptor 2 (stderr), bypassing
# Python's sys.stderr. We must redirect at OS level before importing fitz.

# The fd2 dance is transient: save fd 2, redirect to /dev/null only for the
# duration of `import fitz`, then restore. No global state mutation leaks
# out, so this is safe to run on every import (worker or standalone).
_stderr_backup = os.dup(2)
_devnull_fd = os.open(os.devnull, os.O_WRONLY)
os.dup2(_devnull_fd, 2)
import fitz
os.dup2(_stderr_backup, 2)
os.close(_devnull_fd)
os.close(_stderr_backup)
# ============================================================================

# Continue with normal imports
import re
from PIL import Image
import io
from dataclasses import dataclass
from typing import List, Tuple, Optional, Any, Dict
from pathlib import Path
import logging
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import psutil
import gc
import json
import threading
import time
import csv
from tqdm import tqdm

# Set up logging (stderr is now restored)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress Python warnings
import warnings
warnings.filterwarnings("ignore", category=UserWarning)


# Redirect MuPDF error messages to reduce console spam
import sys
if hasattr(sys, 'stderr'):
    class MuPDFErrorFilter:
        def __init__(self, stream):
            self.stream = stream
            
        def write(self, text):
            if text and not text.startswith('MuPDF error:'):
                self.stream.write(text)
                
        def flush(self):
            self.stream.flush()
    
    # Install the filter only when running as a script. Globally wrapping
    # sys.stderr at import time would mutate the worker process's stderr for
    # the lifetime of the worker, with a small chance of swallowing
    # unrelated log lines that happen to start with "MuPDF error:".
    if __name__ == "__main__":
        sys.stderr = MuPDFErrorFilter(sys.stderr)

def auto_confirm_prompt(question: str, timeout: int = 15, default: bool = True) -> bool:
    """Ask yes/no question with auto-answer after timeout."""
    result = {'answered': False, 'value': default}
    
    def get_input():
        try:
            default_text = "Y/n" if default else "y/N"
            default_answer = "Yes" if default else "No"
            prompt = f"\n{question} ({default_text}, auto-{default_answer} in {timeout}s): "
            response = input(prompt).strip().lower()
            result['answered'] = True
            if not response:
                result['value'] = default
            else:
                result['value'] = response in ['y', 'yes']
        except:
            result['value'] = default
    
    input_thread = threading.Thread(target=get_input, daemon=True)
    input_thread.start()
    input_thread.join(timeout=timeout)
    
    if not result['answered']:
        default_answer = "Yes" if default else "No"
        print(f"\n⏱  No input received. Using default: {default_answer}")
        return default
    
    return result['value']

def select_processing_mode(timeout: int = 15) -> str:
    """Ask user to select PDF processing mode with three options."""
    print("\n" + "="*60)
    print("SELECT PROCESSING MODE")
    print("="*60)
    print("\n[1] Auto-Detect (default):")
    print("    • A-type PDFs → Extract (210) only")
    print("    • B-type PDFs → Extract BOTH (210) and (116)")
    print("    • Best for: Normal processing of mixed folders")
    print("\n[2] Force Type A - Extract only (210):")
    print("    • ALL PDFs → Extract (210) only")
    print("    • B-type PDFs will ignore (116) sectors")
    print("    • Best for: Only want A-type sectors")
    print("\n[3] Force Type B - Extract only (116):")
    print("    • ALL PDFs → Extract (116) only")
    print("    • A-type PDFs will have 0 sectors")
    print("    • Best for: Only want B-type sectors from B PDFs")
    
    result = {'answered': False, 'value': 'auto'}
    
    def get_input():
        try:
            prompt = f"\nPress Enter or wait {timeout}s for [1], or type 1/2/3: "
            response = input(prompt).strip()
            result['answered'] = True
            
            if not response or response == '1':
                result['value'] = 'auto'
            elif response == '2':
                result['value'] = 'force_a'
            elif response == '3':
                result['value'] = 'force_b'
            else:
                print("Invalid choice. Using default: Auto-Detect")
                result['value'] = 'auto'
        except:
            result['value'] = 'auto'
    
    input_thread = threading.Thread(target=get_input, daemon=True)
    input_thread.start()
    input_thread.join(timeout=timeout)
    
    if not result['answered']:
        print(f"\n⏱  No input received. Using default: Auto-Detect")
    
    return result['value']

@dataclass
class ProcessingStats:
    """Tracks processing statistics for PDFs."""
    total_sectors: int = 0
    total_images: int = 0

@dataclass
class ProcessingPaths:
    """Handles directory path operations and validations."""
    working_dir: Path
    input_dir: Path
    image_dir: Path
    modified_dir: Path
    image_link_dir: Path

    @classmethod
    def create_default(cls, base_dir: str) -> 'ProcessingPaths':
        """Create default ProcessingPaths instance."""
        working_dir = Path(base_dir)
        return cls(
            working_dir=working_dir,
            input_dir=working_dir / "input",
            image_dir=working_dir / "image",
            modified_dir=working_dir / "modified",
            image_link_dir=working_dir / "image_link"
        )

    def ensure_directories_exist(self) -> None:
        """Create all necessary directories if they don't exist."""
        for directory in [self.input_dir, self.image_dir, self.modified_dir, self.image_link_dir]:
            directory.mkdir(parents=True, exist_ok=True)

class MemoryProfiler:
    """Logs memory usage for monitoring resource consumption."""
    def __init__(self):
        self.process = psutil.Process(os.getpid())

    def log_memory_usage(self, label: str) -> None:
        """Log current memory usage with an optional label."""
        mem_info = self.process.memory_info()
        logger.info(f"[MemoryProfiler] {label}: "
                    f"RSS={mem_info.rss / 1024 ** 2:.2f} MB, "
                    f"VMS={mem_info.vms / 1024 ** 2:.2f} MB")

memory_profiler = MemoryProfiler()

class ImageProcessor:
    """Handles image processing and combination operations."""
    
    @staticmethod
    def process_image_safely(image_bytes: bytes, max_size: Optional[Tuple[int, int]] = None, preserve_quality: bool = True) -> Optional[Image.Image]:
        """Safely process image bytes and return PIL Image."""
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                if img.mode not in ('RGB', 'RGBA', 'L', 'P'):
                    img = img.convert('RGB')

                if max_size and not preserve_quality:
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)

                return img.copy()
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            return None

    @staticmethod
    def cluster_images_by_position(images: List[Tuple[fitz.Rect, bytes]], cluster_threshold: int = 50) -> List[List[Tuple[fitz.Rect, bytes]]]:
        """Cluster images by spatial position to separate different sectors' logos."""
        if not images:
            return []
        
        clusters: List[List[Tuple[fitz.Rect, bytes]]] = []
        
        for rect, img_bytes in images:
            center_x = (rect.x0 + rect.x1) / 2
            center_y = (rect.y0 + rect.y1) / 2
            
            assigned = False
            for cluster in clusters:
                for cluster_rect, _ in cluster:
                    cluster_center_x = (cluster_rect.x0 + cluster_rect.x1) / 2
                    cluster_center_y = (cluster_rect.y0 + cluster_rect.y1) / 2
                    
                    distance = math.sqrt(
                        (center_x - cluster_center_x) ** 2 + 
                        (center_y - cluster_center_y) ** 2
                    )
                    
                    if distance < cluster_threshold:
                        cluster.append((rect, img_bytes))
                        assigned = True
                        logger.debug(f"Image at ({center_x:.0f}, {center_y:.0f}) added to existing cluster (distance: {distance:.0f}px)")
                        break
                
                if assigned:
                    break
            
            if not assigned:
                clusters.append([(rect, img_bytes)])
                logger.debug(f"New cluster created for image at ({center_x:.0f}, {center_y:.0f})")
        
        logger.debug(f"Clustered {len(images)} images into {len(clusters)} groups")
        return clusters
    
    @staticmethod
    def combine_images(images: List[Tuple[fitz.Rect, bytes]], threshold: int = 10, max_size: Optional[Tuple[int, int]] = None, preserve_quality: bool = True) -> List[Tuple[fitz.Rect, Image.Image]]:
        """Combines overlapping or nearby images using multi-pass algorithm."""
        if not images:
            return []
        
        processed_images = []
        for rect, img_bytes in images:
            img = ImageProcessor.process_image_safely(img_bytes, max_size, preserve_quality)
            if img:
                processed_images.append((rect, img))
        
        if not processed_images:
            return []
        
        result = processed_images
        max_passes = 10
        pass_count = 0
        
        while pass_count < max_passes:
            pass_count += 1
            merged_any = False
            new_result = []
            used = [False] * len(result)
            
            logger.debug(f"Combining pass {pass_count}: {len(result)} images")
            
            for i in range(len(result)):
                if used[i]:
                    continue
                
                current_rect, current_image = result[i]
                used[i] = True
                
                changed = True
                while changed:
                    changed = False
                    for j in range(i + 1, len(result)):
                        if used[j]:
                            continue
                        
                        other_rect, other_image = result[j]
                        
                        if ImageProcessor._are_rectangles_close_or_overlapping(current_rect, other_rect, threshold):
                            try:
                                current_image, current_rect = ImageProcessor._merge_images(
                                    current_image, current_rect, other_image, other_rect
                                )
                                used[j] = True
                                merged_any = True
                                changed = True
                                logger.debug(f"  Merged image {j} into image {i}")
                            except Exception as e:
                                logger.error(f"Error merging images {i} and {j}: {e}")
                
                new_result.append((current_rect, current_image))
            
            result = new_result
            logger.debug(f"  After pass {pass_count}: {len(result)} images")
            
            if not merged_any:
                logger.debug(f"No more merges possible after {pass_count} passes")
                break
        
        if pass_count >= max_passes:
            logger.warning(f"Reached maximum passes ({max_passes}), stopping merge attempts")

        return result

    @staticmethod
    def _are_rectangles_close_or_overlapping(rect1: fitz.Rect, rect2: fitz.Rect, threshold: int) -> bool:
        """Check if two rectangles are close or overlapping."""
        return rect1.intersects(rect2) or ImageProcessor._rect_distance(rect1, rect2) < threshold

    @staticmethod
    def _rect_distance(rect1: fitz.Rect, rect2: fitz.Rect) -> float:
        """Calculate distance between two rectangles."""
        dx = max(rect1.x0 - rect2.x1, rect2.x0 - rect1.x1, 0)
        dy = max(rect1.y0 - rect2.y1, rect2.y0 - rect1.y1, 0)
        return math.hypot(dx, dy)

    @staticmethod
    def _merge_images(image1: Image.Image, rect1: fitz.Rect, image2: Image.Image, rect2: fitz.Rect) -> Tuple[Image.Image, fitz.Rect]:
        """Merge two images based on their actual spatial positions."""
        try:
            combined_rect = rect1 | rect2
            # Use rounding + min-1 so sub-pixel scanlines (PDF rasters split
            # into 0.8px-tall slices) don't truncate to zero-height canvas
            # rows. Without this, stacking 111 scanlines into one logo
            # produced a 1×N degenerate canvas and combine_images silently
            # dropped 110 of the slices.
            canvas_width = max(1, round(combined_rect.x1 - combined_rect.x0))
            canvas_height = max(1, round(combined_rect.y1 - combined_rect.y0))
            mode = 'RGBA' if image1.mode == 'RGBA' or image2.mode == 'RGBA' else 'RGB'
            img1 = image1.convert(mode) if image1.mode != mode else image1
            img2 = image2.convert(mode) if image2.mode != mode else image2
            combined_image = Image.new(mode, (canvas_width, canvas_height), (255, 255, 255, 0) if mode == 'RGBA' else (255, 255, 255))
            img1_x = max(0, round(rect1.x0 - combined_rect.x0))
            img1_y = max(0, round(rect1.y0 - combined_rect.y0))
            img2_x = max(0, round(rect2.x0 - combined_rect.x0))
            img2_y = max(0, round(rect2.y0 - combined_rect.y0))
            img1_width = max(1, round(rect1.x1 - rect1.x0))
            img1_height = max(1, round(rect1.y1 - rect1.y0))
            img2_width = max(1, round(rect2.x1 - rect2.x0))
            img2_height = max(1, round(rect2.y1 - rect2.y0))

            # No degenerate guard here — max(1, …) above ensures every
            # dimension is at least 1 px. The prior `min(...) < 1` short-
            # circuit returned image1 alone while combine_images still
            # marked image2 as merged, silently dropping it.

            if img1.size != (img1_width, img1_height):
                img1 = img1.resize((img1_width, img1_height), Image.Resampling.LANCZOS)
            if img2.size != (img2_width, img2_height):
                img2 = img2.resize((img2_width, img2_height), Image.Resampling.LANCZOS)
            
            combined_image.paste(img1, (img1_x, img1_y))
            combined_image.paste(img2, (img2_x, img2_y))
            
            logger.debug(f"Merged images: canvas={canvas_width}x{canvas_height}, "
                        f"img1 at ({img1_x},{img1_y}), img2 at ({img2_x},{img2_y})")
            
            return combined_image, combined_rect
            
        except Exception as e:
            logger.error(f"Error merging images: {e}")
            return image1, rect1

class PDFProcessor:
    """Processes PDF files to filter text, combine images, and extract images from modified PDFs."""
    def __init__(self, paths: ProcessingPaths, config: dict, processing_mode: str = 'auto'):
        """Initialize with paths and configuration."""
        self.paths = paths
        self.paths.ensure_directories_exist()
        self.config = config
        self.stats = ProcessingStats()
        self.processing_mode = processing_mode

    def _get_pdf_config(self, pdf_type: str) -> dict:
        """Get PDF configuration with pattern overrides based on processing mode."""
        pdf_config = dict(self.config['pdf_types'][pdf_type])
        
        if self.processing_mode == 'force_b' and pdf_type == 'B':
            pdf_config['text_pattern'] = r'\(116\)\s*([^\s]+)'
            pdf_config['image_name_pattern'] = r'\(116\)\s*([A-Za-z0-9-]+)'
            logger.debug("Force Type B: Using (116) pattern only")
        
        return pdf_config

    def count_sectors_in_pdf(self, pdf_path: Path, pdf_type: str) -> int:
        """Count the number of sectors in a PDF without processing."""
        try:
            with fitz.open(pdf_path) as doc:
                pdf_config = self._get_pdf_config(pdf_type)
                pattern = str(pdf_config.get('image_name_pattern', ''))
                sector_count = 0
                
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    text: str = page.get_text()  # type: ignore
                    matches = list(re.finditer(pattern, str(text)))
                    sector_count += len(matches)
                
                return sector_count
        except Exception as e:
            logger.error(f"Error counting sectors in {pdf_path}: {e}")
            return 0

    def process_pdfs(self, pdf_list: List[Tuple[str, str]]) -> ProcessingStats:
        """Process multiple PDF files with hybrid batching strategy."""
        self.stats = ProcessingStats()
        errors = []
        
        folder_batches = {}
        for pdf_file, year_folder in pdf_list:
            if year_folder not in folder_batches:
                folder_batches[year_folder] = []
            folder_batches[year_folder].append((pdf_file, year_folder))
        
        total_folders = len(folder_batches)
        total_pdfs = len(pdf_list)
        max_workers = self._get_optimal_workers(total_pdfs)
        
        print(f"\n⚙️  Processing Strategy: Hybrid Batching")
        print(f"📁 Total folders: {total_folders}")
        print(f"📄 Total PDFs: {total_pdfs}")
        print(f"👷 Workers per batch: {max_workers}")
        print(f"💾 Available RAM: {psutil.virtual_memory().available / (1024**3):.1f}GB / {psutil.virtual_memory().total / (1024**3):.1f}GB")
        
        memory_warning_threshold = psutil.virtual_memory().total * 0.8
        
        folder_index = 0
        for year_folder in sorted(folder_batches.keys()):
            folder_index += 1
            batch_pdfs = folder_batches[year_folder]
            
            print(f"\n{'='*60}")
            print(f"📂 PROCESSING FOLDER {folder_index}/{total_folders}: {year_folder}")
            print(f"{'='*60}")
            print(f"PDFs in this folder: {len(batch_pdfs)}")
            
            batch_start_time = time.time()
            last_warning_time = 0
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(self._process_single_pdf, pdf_file, year): (pdf_file, year) 
                          for pdf_file, year in batch_pdfs}
                
                with tqdm(total=len(batch_pdfs), desc=f"  {year_folder}", unit="pdf") as pbar:
                    for future in futures:
                        try:
                            future.result()
                            pbar.update(1)
                            
                            current_memory = psutil.virtual_memory().used
                            memory_percent = psutil.virtual_memory().percent
                            
                            pbar.set_postfix({
                                'RAM': f'{memory_percent:.0f}%',
                                'Used': f'{current_memory / (1024**3):.1f}GB'
                            })
                            
                            current_time = time.time()
                            if current_memory > memory_warning_threshold and (current_time - last_warning_time) > 30:
                                logger.warning(f"⚠️  HIGH MEMORY USAGE: {memory_percent:.1f}% ({current_memory / (1024**3):.1f}GB / {psutil.virtual_memory().total / (1024**3):.1f}GB)")
                                last_warning_time = current_time
                                gc.collect()
                                
                        except Exception as e:
                            pdf_file, year = futures[future]
                            error_name = f"{year}/{pdf_file}"
                            errors.append({'pdf': error_name, 'error': str(e)})
                            logger.error(f"Error processing PDF {error_name}: {e}")
                            pbar.update(1)
            
            batch_end_time = time.time()
            batch_elapsed = batch_end_time - batch_start_time
            batch_mins = int(batch_elapsed // 60)
            batch_secs = int(batch_elapsed % 60)
            
            print(f"  ✅ Folder {year_folder} completed in {batch_mins}m {batch_secs}s")
            
            if folder_index < total_folders:
                cooling_seconds = 30 if total_folders <= 5 else 60
                print(f"  ❄️  Cooling break: {cooling_seconds}s (preventing thermal throttling)...")
                gc.collect()
                
                for remaining in range(cooling_seconds, 0, -5):
                    mem_percent = psutil.virtual_memory().percent
                    print(f"     {remaining}s remaining... RAM: {mem_percent:.0f}%", end='\r')
                    time.sleep(5)
                print(f"     Ready for next folder! RAM: {psutil.virtual_memory().percent:.0f}%          ")
        
        if errors:
            with open(self.paths.working_dir / 'errors.json', 'w') as f:
                json.dump(errors, f, indent=2)
            logger.info(f"⚠️  {len(errors)} errors occurred. Details saved to {self.paths.working_dir / 'errors.json'}")
        
        logger.info(f"✅ All folders processed. Total sectors: {self.stats.total_sectors}, "
                    f"Total images: {self.stats.total_images}")
        return self.stats

    def _get_optimal_workers(self, total_pdfs: int = 24) -> int:
        """Determine optimal number of workers based on system resources and workload."""
        cpu_count = psutil.cpu_count(logical=False) or 4
        mem_available = psutil.virtual_memory().available / (1024 ** 3)
        memory_based_workers = max(1, int(mem_available // 2))
        
        if total_pdfs < 50:
            cpu_multiplier = 0.75
            strategy = "Aggressive"
        elif total_pdfs < 150:
            cpu_multiplier = 0.50
            strategy = "Balanced"
        else:
            cpu_multiplier = 0.375
            strategy = "Conservative"
        
        cpu_based_workers = max(2, int(cpu_count * cpu_multiplier))
        optimal_workers = min(memory_based_workers, cpu_based_workers, 8)
        config_max = self.config.get('max_workers', optimal_workers)
        final_workers = min(optimal_workers, config_max)
        
        logger.info(f"Worker calculation ({strategy} strategy for {total_pdfs} PDFs): "
                   f"CPU cores={cpu_count}, Available RAM={mem_available:.1f}GB, "
                   f"Memory-based={memory_based_workers}, CPU-based={cpu_based_workers}, "
                   f"Final={final_workers} workers")
        
        return final_workers

    def _process_single_pdf(self, pdf_file: str, year_folder: Optional[str] = None) -> None:
        """Process a single PDF file."""
        if year_folder:
            input_path = self.paths.input_dir / year_folder / pdf_file
            pdf_name = Path(pdf_file).stem
            modified_output_dir = self.paths.modified_dir / year_folder / pdf_name
            image_output_dir = self.paths.image_dir / year_folder / pdf_name
            csv_output_dir = self.paths.image_link_dir / year_folder
        else:
            input_path = self.paths.input_dir / pdf_file
            pdf_name = Path(pdf_file).stem
            modified_output_dir = self.paths.modified_dir / pdf_name
            image_output_dir = self.paths.image_dir / pdf_name
            csv_output_dir = self.paths.image_link_dir
        
        modified_output_dir.mkdir(parents=True, exist_ok=True)
        image_output_dir.mkdir(parents=True, exist_ok=True)
        csv_output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Processing {year_folder + '/' if year_folder else ''}{pdf_file}...")
        try:
            pdf_type = self._determine_pdf_type(input_path)
            modified_pdf_path = self._modify_pdf(input_path, modified_output_dir, pdf_type)
            self._extract_images(modified_pdf_path, image_output_dir, pdf_type)
            self._create_image_link_csv(pdf_name, image_output_dir, csv_output_dir, year_folder)
        except Exception as e:
            logger.error(f"Error processing {pdf_file}: {e}")
            raise

    def _determine_pdf_type(self, pdf_path: Path) -> str:
        """Determine PDF type based on filename or processing mode."""
        try:
            if self.processing_mode == 'force_a':
                logger.debug(f"FORCE TYPE A MODE: Processing {pdf_path.name} as Type A")
                return 'A'
            
            if self.processing_mode == 'force_b':
                logger.debug(f"FORCE TYPE B MODE: Processing {pdf_path.name} as Type B")
                return 'B'
            
            filename = pdf_path.stem.upper()
            
            for pdf_type in self.config['pdf_types'].keys():
                if filename.startswith(pdf_type.upper()):
                    logger.debug(f"Auto-detected type {pdf_type} for: {pdf_path.name}")
                    return pdf_type
            
            default_type = list(self.config['pdf_types'].keys())[0]
            logger.warning(f"Could not determine PDF type from filename '{pdf_path.name}', defaulting to '{default_type}'")
            return default_type
            
        except Exception as e:
            logger.error(f"Error determining PDF type for {pdf_path}: {e}")
            return list(self.config['pdf_types'].keys())[0]

    def _modify_pdf(self, pdf_path: Path, output_dir: Path, pdf_type: str) -> Path:
        """Modify a PDF using the specified type's configuration."""
        pdf_config = self._get_pdf_config(pdf_type)
        text_pattern = str(pdf_config.get('text_pattern', ''))
        output_path = output_dir / pdf_path.name
        try:
            with fitz.open(pdf_path) as doc:
                new_doc = fitz.open()
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    new_page = new_doc.new_page(width=page.rect.width, height=page.rect.height)  # type: ignore
                    self._process_text(page, new_page, text_pattern)
                    self._process_images(page, new_page)
                new_doc.save(output_path)
                new_doc.close()
            logger.info(f"Modified PDF saved: {output_path}")
            cleaned_path = self._remove_blank_pages(output_path)
            return cleaned_path
        except Exception as e:
            logger.error(f"Error modifying PDF {pdf_path}: {e}")
            raise
    
    def _remove_blank_pages(self, pdf_path: Path) -> Path:
        """Remove blank pages from a PDF. Writes to a temp file then renames,
        rather than saving over the still-open source doc (which is fragile
        across PyMuPDF versions)."""
        try:
            pages_to_keep: List[int] = []
            blank_pages: List[int] = []
            tmp_path = pdf_path.with_suffix(pdf_path.suffix + ".tmp")

            with fitz.open(pdf_path) as doc:
                logger.info(f"Scanning for blank pages in {pdf_path.name}...")

                for page_num in range(len(doc)):
                    page = doc[page_num]
                    text = page.get_text().strip()  # type: ignore
                    images = page.get_images(full=True)

                    if not text and not images:
                        blank_pages.append(page_num)
                        logger.debug(f"Page {page_num + 1} is blank")
                    else:
                        pages_to_keep.append(page_num)

                if blank_pages:
                    logger.info(f"Found {len(blank_pages)} blank pages out of {len(doc)} total pages")
                    new_doc = fitz.open()
                    for page_num in pages_to_keep:
                        new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                    new_doc.save(str(tmp_path), garbage=4, deflate=True)
                    new_doc.close()
                else:
                    logger.info(f"No blank pages found. PDF has {len(doc)} pages.")

            if blank_pages:
                os.replace(tmp_path, pdf_path)
                logger.info(f"Removed {len(blank_pages)} blank pages. PDF now has {len(pages_to_keep)} pages.")

            return pdf_path

        except Exception as e:
            logger.error(f"Error removing blank pages from {pdf_path}: {e}")
            return pdf_path

    def _process_text(self, page: fitz.Page, new_page: fitz.Page, pattern: str) -> None:
        """Process text for a page using the provided regex pattern.

        The old implementation inserted every match at the block's bbox top,
        which placed markers far above their real position when a block
        spanned many lines (e.g., (732) applicant text from y=194 down to
        y=400 with the next sector's (111) at line y=337 — the marker
        ended up at y=194). That broke the y-binding in _save_page_images.

        Naively switching to per-line matching breaks the regex when fitz
        splits "(111) 1746424" across two "line" objects at the same y
        (one for "(111)", one for "1746424") — neither line alone matches
        the pattern.

        Hybrid approach: join the block's line texts (preserving line
        boundaries via an offset table), run the regex on the joined text,
        and for each match place the inserted marker at the LINE the
        match's start position lies in.
        """
        text_dict: Dict[str, Any] = page.get_text("dict")  # type: ignore
        text_instances: List[Any] = text_dict.get("blocks", [])
        keep_pattern = re.compile(pattern)

        for block in text_instances:
            if not isinstance(block, dict):
                continue
            if block.get('type') != 0:
                continue

            # Collect line texts + bbox; build joined block text with an
            # offset table mapping each position in the joined string back
            # to its source line.
            line_meta: List[Tuple[int, int, float, float]] = []  # (start, end, y, x)
            joined_parts: List[str] = []
            pos = 0
            for line in block.get('lines', []):
                if not isinstance(line, dict):
                    continue
                lt = " ".join(
                    str(s.get('text', ''))
                    for s in line.get('spans', [])
                    if isinstance(s, dict) and s.get('text')
                )
                bbox = line.get('bbox', [0, 0, 0, 0])
                if not isinstance(bbox, (list, tuple)) or len(bbox) < 2:
                    continue
                line_meta.append((pos, pos + len(lt), float(bbox[1]), float(bbox[0])))
                joined_parts.append(lt)
                pos += len(lt) + 1  # +1 for the separating space in " ".join

            if not line_meta:
                continue

            joined = " ".join(joined_parts)

            for match in keep_pattern.finditer(joined):
                if not any(g for g in match.groups()):
                    continue
                # Find which source line this match's first char lies in.
                start = match.start()
                line_y = line_meta[0][2]
                line_x = line_meta[0][3]
                for s, e, y, x in line_meta:
                    if s <= start <= e:
                        line_y = y
                        line_x = x
                        break
                new_page.insert_text((line_x, line_y),  # type: ignore
                                     match.group(0).strip(), fontsize=12)  # type: ignore

    def _process_images(self, page: fitz.Page, new_page: fitz.Page) -> None:
        """Process and combine images on the page using spatial clustering."""
        try:
            images = page.get_images(full=True)
            image_data = []
            
            preserve_quality = self.config.get('image_settings', {}).get('preserve_quality', True)
            max_size = tuple(self.config.get('image_settings', {}).get('max_size', None)) if not preserve_quality else None
            clustering_enabled = self.config.get('clustering', {}).get('enabled', True)
            cluster_threshold = self.config.get('clustering', {}).get('cluster_threshold', 50)
            combine_threshold = self.config.get('clustering', {}).get('combine_threshold', 50)
            
            for xref in (img[0] for img in images):
                if page.parent is None:
                    logger.warning(f"Parent document is None for image {xref}")
                    continue
                
                img = page.parent.extract_image(xref)
                if not img:
                    continue
                
                try:
                    rects = page.get_image_rects(xref)  # type: ignore
                    
                    if not rects:
                        logger.warning(f"No rectangles found for image {xref}")
                        continue
                    
                    processed_img = ImageProcessor.process_image_safely(img["image"], max_size, preserve_quality)
                    if not processed_img:
                        continue
                    
                    img_bytes = io.BytesIO()
                    processed_img.save(img_bytes, format='PNG', compress_level=1)
                    img_bytes_data = img_bytes.getvalue()
                    processed_img.close()
                    
                    page_w = page.rect.width
                    for rect in rects:
                        w = rect.x1 - rect.x0
                        h = rect.y1 - rect.y0
                        # Skip true point rects (both dims sub-pixel).
                        if w < 0.5 and h < 0.5:
                            logger.debug(f"Skipping degenerate rect for xref {xref}: {rect}")
                            continue
                        # Skip page-wide thin strips — these are the horizontal-rule
                        # decorations between sectors. Width > 50% of page is the
                        # distinguishing feature: real logos (even scanline-encoded
                        # rasters) span only the logo's width, never the gutter.
                        if h < 1.0 and w > 0.5 * page_w:
                            logger.debug(f"Skipping page-wide divider for xref {xref}: {rect}")
                            continue
                        image_data.append((rect, img_bytes_data))
                        logger.debug(f"Image {xref} found at position ({rect.x0:.0f}, {rect.y0:.0f})")

                    if len(rects) > 1:
                        logger.debug(f"Image {xref} appears {len(rects)} times on page (identical logos for different sectors)")

                except Exception as e:
                    logger.warning(f"Error processing image {xref}: {e}")

            if not image_data:
                return

            logger.debug(f"Page has {len(image_data)} image instances from {len(images)} unique images")

            if logger.isEnabledFor(logging.DEBUG) and len(image_data) > 1:
                logger.debug("=== DISTANCE ANALYSIS ===")
                for i in range(len(image_data)):
                    for j in range(i + 1, len(image_data)):
                        rect1, rect2 = image_data[i][0], image_data[j][0]
                        distance = ImageProcessor._rect_distance(rect1, rect2)
                        center1 = ((rect1.x0 + rect1.x1)/2, (rect1.y0 + rect1.y1)/2)
                        center2 = ((rect2.x0 + rect2.x1)/2, (rect2.y0 + rect2.y1)/2)
                        logger.debug(f"Image {i} at ({center1[0]:.0f},{center1[1]:.0f}) <-> "
                                  f"Image {j} at ({center2[0]:.0f},{center2[1]:.0f}): "
                                  f"distance = {distance:.1f}px "
                                  f"{'[SAME CLUSTER]' if distance < cluster_threshold else '[DIFFERENT CLUSTER]'}")

            if clustering_enabled and len(image_data) > 1:
                image_clusters = ImageProcessor.cluster_images_by_position(image_data, cluster_threshold)
                logger.debug(f"Grouped into {len(image_clusters)} clusters (sectors)")
            else:
                image_clusters = [[(rect, img_bytes)] for rect, img_bytes in image_data]

            for cluster_idx, cluster in enumerate(image_clusters):
                logger.debug(f"Cluster {cluster_idx + 1} has {len(cluster)} images")

                for img_idx, (rect, _) in enumerate(cluster):
                    logger.debug(f"  Image {img_idx}: position=({rect.x0:.1f}, {rect.y0:.1f}), "
                               f"size=({rect.width:.1f}x{rect.height:.1f})")

                if logger.isEnabledFor(logging.DEBUG) and len(cluster) > 1:
                    for i in range(len(cluster) - 1):
                        rect1 = cluster[i][0]
                        rect2 = cluster[i+1][0]
                        distance = ImageProcessor._rect_distance(rect1, rect2)
                        logger.debug(f"  Distance between image {i} and {i+1}: {distance:.1f}px")

                combined_images = ImageProcessor.combine_images(
                    cluster,
                    threshold=combine_threshold,
                    max_size=max_size,
                    preserve_quality=preserve_quality
                )

                logger.debug(f"  After combining: {len(combined_images)} image(s)")

                for img_idx, (rect, image) in enumerate(combined_images):
                    try:
                        output_stream = io.BytesIO()
                        image.save(output_stream, format='PNG', compress_level=1)
                        output_stream.seek(0)

                        logger.debug(f"  Inserting combined image {img_idx + 1}: "
                                  f"position=({rect.x0:.1f}, {rect.y0:.1f}), "
                                  f"size=({rect.width:.1f}x{rect.height:.1f}), "
                                  f"image_size={image.size}")
                        
                        new_page.insert_image(rect, stream=output_stream, keep_proportion=False)  # type: ignore
                        logger.debug(f"  Successfully inserted image for cluster {cluster_idx + 1}")
                    except Exception as e:
                        logger.error(f"Error inserting combined image: {e}")
        except Exception as e:
            logger.error(f"Error processing images: {e}")
            raise

    def _extract_images(self, pdf_path: Path, output_dir: Path, pdf_type: str) -> None:
        """Extract images from modified PDF."""
        try:
            with fitz.open(pdf_path) as doc:
                pdf_config = self._get_pdf_config(pdf_type)
                pattern = str(pdf_config.get('image_name_pattern', ''))
                image_format = self.config.get('image_settings', {}).get('format', 'PNG')
                preserve_quality = self.config.get('image_settings', {}).get('preserve_quality', True)
                max_size = tuple(self.config.get('image_settings', {}).get('max_size', None)) if not preserve_quality else None
                
                page_sectors = []
                label_pat = re.compile(pattern)
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    text_dict: Dict[str, Any] = page.get_text("dict")  # type: ignore
                    labels: List[Tuple[float, str]] = []
                    for block in text_dict.get("blocks", []):
                        if not isinstance(block, dict) or block.get("type") != 0:
                            continue
                        for line in block.get("lines", []):
                            if not isinstance(line, dict):
                                continue
                            line_text = " ".join(
                                str(s.get("text", "")) for s in line.get("spans", []) if isinstance(s, dict)
                            )
                            for m in label_pat.finditer(line_text):
                                ident = next((g for g in m.groups() if g), None) or m.group(0)
                                y0 = line.get("bbox", [0, 0, 0, 0])[1]
                                labels.append((float(y0), str(ident)))
                    labels.sort(key=lambda t: t[0])
                    # Dedupe by Y-proximity for stats: B sectors have (111) + (210) at
                    # similar Y, so counting both inflates total_sectors. Keep the full
                    # list for the saver — its Y-based mapping still picks the right id.
                    last_y = float("-inf")
                    for y, ident in labels:
                        if y - last_y >= 80.0:
                            page_sectors.append(ident)
                        last_y = y
                    self._save_page_images(page, labels, output_dir, page_num, image_format, max_size)
                self.stats.total_sectors += len(page_sectors)
        except Exception as e:
            logger.error(f"Error extracting images from {pdf_path}: {e}")
            raise

    def _save_page_images(self, page: fitz.Page, labels: List[Tuple[float, str]],
                         output_dir: Path, page_num: int, image_format: str, max_size: Optional[Tuple[int, int]]) -> None:
        """Save images from a page, mapping each placement to the (210)/(116)
        identifier whose Y is at or above the image's Y (closest from above).

        Iterates per-placement (not per-xref) so a single image used on multiple
        sectors gets one save per sector. Multiple distinct images falling under
        the same identifier are suffixed _2, _3, … so unclustered logo fragments
        are preserved rather than silently dropped.
        """
        try:
            images = page.get_images(full=True)
            preserve_quality = self.config.get('image_settings', {}).get('preserve_quality', True)
            saved_keys: set = set()  # (identifier, xref) — dedupe same xref under same sector
            count_per_id: Dict[str, int] = {}

            for img_index, img in enumerate(images):
                try:
                    xref = img[0]
                    if page.parent is None:
                        logger.warning(f"Parent document is None for image {img_index} on page {page_num}")
                        continue
                    try:
                        rects = page.get_image_rects(xref)  # type: ignore
                    except Exception as e:
                        logger.warning(f"get_image_rects failed for xref {xref} page {page_num}: {e}")
                        continue
                    if not rects:
                        continue
                    base_image = page.parent.extract_image(xref)
                    if not base_image:
                        logger.warning(f"Could not extract image xref {xref} from page {page_num}")
                        continue

                    for rect_idx, rect in enumerate(rects):
                        # Nearest label whose y <= rect.y0 + tolerance.
                        # Standard gazette layout puts the marker line 10-15
                        # px ABOVE its logo, but the marker's baseline y can
                        # land slightly below the rect top depending on font
                        # metrics. +20 gives slack without bleeding into the
                        # NEXT sector's marker (sector spacing is typically
                        # 80+ px, gated by the cluster_threshold in YAML).
                        best: Optional[str] = None
                        for y_lbl, ident in labels:
                            if y_lbl <= rect.y0 + 20:
                                best = ident
                            else:
                                break

                        # Interior labels: marker y-positions that fall
                        # STRICTLY inside the rect, past the best-tolerance
                        # band. Their presence means _modify_pdf's clustering
                        # merged image rects across sector boundaries
                        # (adjacent sectors' logos within cluster_threshold
                        # of each other). To recover per-sector logos we
                        # split the merged image at each interior label's
                        # y-position rather than dropping all-but-one sector.
                        interior_labels = [
                            (y_lbl, ident)
                            for y_lbl, ident in labels
                            if rect.y0 + 20 < y_lbl < rect.y1
                        ]

                        # Build the (identifier, page_y0, page_y1) slices.
                        # Single-sector rects produce one slice covering the
                        # whole rect — flow is unchanged from the original.
                        # Multi-sector rects produce one slice per covered
                        # label. If `best` exists, it owns the top portion
                        # from rect.y0 to the first interior label; if not,
                        # the area above the first interior label has no
                        # owning sector and is dropped.
                        if interior_labels:
                            ordered: List[Tuple[float, str]] = []
                            if best is not None:
                                ordered.append((rect.y0, best))
                            ordered.extend(interior_labels)
                            slices: List[Tuple[str, float, float]] = []
                            for i, (y_label, ident) in enumerate(ordered):
                                sy0 = y_label
                                sy1 = ordered[i + 1][0] if i + 1 < len(ordered) else rect.y1
                                slices.append((ident, sy0, sy1))
                        else:
                            ident_single = (
                                best
                                if best is not None
                                else f"unknown_{page_num}_{img_index}_{rect_idx}"
                            )
                            slices = [(ident_single, rect.y0, rect.y1)]

                        # Decode the source image once. For single-slice
                        # rects we save it directly; for multi-slice rects
                        # we crop each slice's pixel sub-region.
                        processed_img = ImageProcessor.process_image_safely(
                            base_image["image"],
                            max_size if not preserve_quality else None,
                            preserve_quality,
                        )
                        if processed_img is None:
                            logger.warning(f"Could not process image xref {xref} on page {page_num}")
                            continue

                        try:
                            img_w, img_h = processed_img.size
                            rect_h_pts = rect.y1 - rect.y0
                            # Sub-images thinner than this are rendering
                            # artifacts when SPLITTING a multi-section image
                            # (a label sitting one or two px above the rect
                            # bottom) — drop them rather than emit a useless
                            # sliver. Single-slice cases (no interior labels,
                            # rect maps to exactly one section) must NEVER be
                            # filtered here: that would drop legitimate small
                            # logos (e.g., gazette mark rasters as small as
                            # 68x18) and create false NEITHER cases.
                            MIN_SLICE_PX = 20
                            is_single_slice = len(slices) == 1

                            for slice_idx, (identifier_raw, sy0, sy1) in enumerate(slices):
                                if identifier_raw.startswith("unknown_"):
                                    logger.warning(
                                        f"Skipping image with no matching identifier: {identifier_raw}"
                                    )
                                    continue

                                px_y0 = max(0, int((sy0 - rect.y0) / rect_h_pts * img_h))
                                px_y1 = min(img_h, int((sy1 - rect.y0) / rect_h_pts * img_h))
                                if not is_single_slice and (px_y1 - px_y0) < MIN_SLICE_PX:
                                    continue

                                key = (identifier_raw, xref, slice_idx)
                                if key in saved_keys:
                                    continue
                                saved_keys.add(key)
                                count_per_id[identifier_raw] = count_per_id.get(identifier_raw, 0) + 1
                                identifier = (
                                    identifier_raw
                                    if count_per_id[identifier_raw] == 1
                                    else f"{identifier_raw}_{count_per_id[identifier_raw]}"
                                )

                                img_to_save = (
                                    processed_img.crop((0, px_y0, img_w, px_y1))
                                    if len(slices) > 1
                                    else processed_img
                                )
                                image_path = output_dir / f"{identifier}.{image_format.lower()}"
                                try:
                                    if image_format.upper() == 'PNG':
                                        img_to_save.save(image_path, image_format, compress_level=1)
                                    elif image_format.upper() in ['JPEG', 'JPG']:
                                        img_to_save.save(image_path, 'JPEG', quality=95, subsampling=0)
                                    else:
                                        img_to_save.save(image_path, image_format)
                                    self.stats.total_images += 1
                                    logger.info(f"Extracted and saved image: {image_path}")
                                except Exception as save_error:
                                    logger.error(f"Error saving image {identifier}: {save_error}")
                                finally:
                                    if len(slices) > 1:
                                        img_to_save.close()
                        finally:
                            processed_img.close()
                except Exception as e:
                    logger.error(f"Error processing image {img_index} from page {page_num}: {e}")
        except Exception as e:
            logger.error(f"Error accessing images on page {page_num}: {e}")

    def _create_image_link_csv(self, pdf_name: str, image_output_dir: Path, csv_output_dir: Path, year_folder: Optional[str] = None) -> None:
        """Create a CSV file with image names and their file paths."""
        try:
            csv_path = csv_output_dir / f"{pdf_name}.csv"
            image_files = sorted([f for f in image_output_dir.iterdir() if f.is_file() and f.suffix.lower() in ['.png', '.jpg', '.jpeg']])
            
            if not image_files:
                logger.warning(f"No images found in {image_output_dir} for CSV creation")
                return
            
            with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['image name', 'image link'])
                
                for image_file in image_files:
                    relative_path = image_file.relative_to(self.paths.working_dir)
                    writer.writerow([image_file.name, str(relative_path)])
            
            logger.info(f"Created image link CSV: {csv_path} ({len(image_files)} images)")
            
        except Exception as e:
            logger.error(f"Error creating image link CSV for {pdf_name}: {e}")

def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_path, 'r') as config_file:
            config = yaml.safe_load(config_file)
            required_fields = ['base_directory', 'pdf_types']
            for field in required_fields:
                if field not in config:
                    raise ValueError(f"Missing required config field: {field}")
            
            if 'pdf_types' in config:
                for pdf_type, pdf_config in config['pdf_types'].items():
                    if not isinstance(pdf_config, dict):
                        raise ValueError(f"Invalid configuration for PDF type '{pdf_type}'")
                    required_pdf_fields = ['identifier', 'text_pattern', 'image_name_pattern']
                    for field in required_pdf_fields:
                        if field not in pdf_config:
                            logger.warning(f"PDF type '{pdf_type}' missing field '{field}'")
            
            return config
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        return {}

def validate_pdf(pdf_path: Path) -> bool:
    """Validate if a PDF file is readable."""
    try:
        with fitz.open(pdf_path) as doc:
            if len(doc) > 0:
                try:
                    page = doc[0]
                    _ = page.get_text()
                except:
                    logger.warning(f"PDF may be corrupted but readable: {pdf_path.name}")
            return True
    except Exception as e:
        logger.error(f"Invalid/unreadable PDF: {pdf_path.name} - {e}")
        return False

def main():
    """Main entry point for the PDF processing script."""
    try:
        config = load_config('config_image_extractor.yaml')
        if not config:
            logger.error("Failed to load configuration, exiting.")
            return
        
        print("\n" + "="*60)
        print("PDF IMAGE EXTRACTOR")
        print("="*60)
        
        paths = ProcessingPaths.create_default(config['base_directory'])
        
        year_folders = sorted([d.name for d in paths.input_dir.iterdir() if d.is_dir()])
        
        if not year_folders:
            logger.error("No year folders found in input directory")
            return
        
        year_pdf_counts = {}
        total_pdfs = 0
        for year in year_folders:
            year_path = paths.input_dir / year
            pdf_files = [f for f in year_path.iterdir() if f.is_file() and f.suffix.lower() == '.pdf' and validate_pdf(f)]
            year_pdf_counts[year] = len(pdf_files)
            total_pdfs += len(pdf_files)
        
        year_folders = [year for year in year_folders if year_pdf_counts.get(year, 0) > 0]
        
        if not year_folders:
            logger.error("No valid PDF files found in any year folder")
            return
        
        print(f"\n📊 Found {len(year_folders)} year(s) with {total_pdfs} total PDFs")
        print(f"   Years: {', '.join(year_folders)}")
        
        quick_mode = auto_confirm_prompt(
            f"🚀 Quick Mode: Process ALL {total_pdfs} PDFs from ALL years?",
            timeout=15,
            default=True
        )
        
        if quick_mode:
            print(f"\n✅ QUICK MODE: Processing all {total_pdfs} PDFs from all years")
            
            all_pdfs = []
            for year in year_folders:
                year_path = paths.input_dir / year
                pdf_files = sorted([f.name for f in year_path.iterdir() if f.is_file() and f.suffix.lower() == '.pdf' and validate_pdf(year_path / f.name)])
                for pdf_file in pdf_files:
                    all_pdfs.append((pdf_file, year, f"{year}/{pdf_file}"))
            
            selected_pdfs = [(pdf_file, year) for pdf_file, year, _ in all_pdfs]
            
        else:
            print("\n" + "="*60)
            print("STEP 1: SELECT YEAR(S) TO PROCESS")
            print("="*60)
            print("\nAvailable years:")
            for i, year in enumerate(year_folders, 1):
                pdf_count = year_pdf_counts[year]
                print(f"  {i}. {year} ({pdf_count} PDFs)")
            
            while True:
                choice = input("\nEnter year numbers (comma-separated), or 'all' for all years: ").strip().lower()
                if choice == 'all':
                    selected_years = year_folders
                    break
                try:
                    indices = [int(x.strip()) - 1 for x in choice.split(',')]
                    selected_years = [year_folders[i] for i in indices if 0 <= i < len(year_folders)]
                    if selected_years:
                        break
                    print("No valid selections. Please try again.")
                except ValueError:
                    print("Invalid input. Please enter numbers only.")
            
            print(f"\nSelected years: {', '.join(selected_years)}")
            
            all_pdfs = []
            for year in selected_years:
                year_path = paths.input_dir / year
                pdf_files = sorted([f.name for f in year_path.iterdir() if f.is_file() and f.suffix.lower() == '.pdf' and validate_pdf(year_path / f.name)])
                for pdf_file in pdf_files:
                    all_pdfs.append((pdf_file, year, f"{year}/{pdf_file}"))
            
            if not all_pdfs:
                logger.error("No valid PDF files found in selected years")
                return
            
            print("\n" + "="*60)
            print("STEP 2: SELECT PDF(S) TO PROCESS")
            print("="*60)
            print(f"\nAvailable PDFs ({len(all_pdfs)} total):")
            
            for i, (pdf_file, year, display_name) in enumerate(all_pdfs, 1):
                print(f"  {i}. {display_name}")
            
            while True:
                choice = input("\nEnter PDF numbers (comma-separated), or 'all' for all PDFs: ").strip().lower()
                if choice == 'all':
                    selected_pdf_indices = list(range(len(all_pdfs)))
                    break
                try:
                    indices = [int(x.strip()) - 1 for x in choice.split(',')]
                    selected_pdf_indices = [i for i in indices if 0 <= i < len(all_pdfs)]
                    if selected_pdf_indices:
                        break
                    print("No valid selections. Please try again.")
                except ValueError:
                    print("Invalid input. Please enter numbers only.")
            
            selected_pdfs = [(all_pdfs[i][0], all_pdfs[i][1]) for i in selected_pdf_indices]
            
            print(f"\nSelected {len(selected_pdfs)} PDF(s) for processing")
        
        processing_mode = select_processing_mode(timeout=15)
        
        print("\n" + "="*60)
        if processing_mode == 'auto':
            print("✓ AUTO-DETECT MODE")
            print("  → A-type PDFs: Extract (210) patterns only")
            print("  → B-type PDFs: Extract BOTH (210) and (116) patterns")
        elif processing_mode == 'force_a':
            print("✓ FORCE TYPE A MODE")
            print("  → ALL PDFs: Extract (210) patterns only")
            print("  → B-type PDFs will ignore (116) sectors")
        elif processing_mode == 'force_b':
            print("✓ FORCE TYPE B MODE")
            print("  → ALL PDFs: Extract (116) patterns only")
            print("  → A-type PDFs will have 0 sectors (no 116 patterns)")
            print("  ⚠️  Warning: A-type PDFs may produce 0 sectors")
        print("="*60)
        
        processor = PDFProcessor(paths, config, processing_mode=processing_mode)
        
        print("\n" + "="*60)
        print("SECTOR COUNT ANALYSIS")
        print("="*60)
        
        folder_groups = {}
        for pdf_file, year in selected_pdfs:
            if year not in folder_groups:
                folder_groups[year] = []
            folder_groups[year].append((pdf_file, year))
        
        total_sectors = 0
        print(f"\n⏳ Counting sectors in {len(selected_pdfs)} PDFs across {len(folder_groups)} folder(s)...")
        
        if processing_mode == 'force_a':
            print("   [Force Type A: Using (210) pattern only]")
        elif processing_mode == 'force_b':
            print("   [Force Type B: Using (116) pattern only]")
        else:
            print("   [Auto-Detect: A=(210), B=(210)+(116)]")
        
        for year_folder in sorted(folder_groups.keys()):
            pdfs_in_folder = folder_groups[year_folder]
            folder_sectors = 0
            
            print(f"\n📁 {year_folder}:")
            with tqdm(total=len(pdfs_in_folder), desc=f"  Counting", unit="pdf", leave=False) as pbar:
                for pdf_file, year in pdfs_in_folder:
                    pdf_path = paths.input_dir / year / pdf_file
                    
                    if processing_mode == 'force_a':
                        pdf_type = 'A'
                    elif processing_mode == 'force_b':
                        pdf_type = 'B'
                    else:
                        pdf_type = processor._determine_pdf_type(pdf_path)
                    
                    sector_count = processor.count_sectors_in_pdf(pdf_path, pdf_type)
                    folder_sectors += sector_count
                    total_sectors += sector_count
                    pbar.update(1)
            
            print(f"  ✓ {len(pdfs_in_folder)} PDFs → {folder_sectors} sectors")
        
        print(f"\n{'='*60}")
        print(f"✅ Total: {total_sectors} sectors across all folders")
        print("="*60)
        
        workers_for_estimate = processor._get_optimal_workers(len(selected_pdfs))
        avg_time_per_pdf = 3
        processing_time = (len(selected_pdfs) * avg_time_per_pdf) / workers_for_estimate
        num_folders = len(folder_groups)
        cooling_time = (num_folders - 1) * (30 if num_folders <= 5 else 60)
        estimated_time_seconds = processing_time + cooling_time
        estimated_hours = int(estimated_time_seconds // 3600)
        estimated_minutes = int((estimated_time_seconds % 3600) // 60)
        
        print(f"\n⏱️  Processing strategy: {num_folders} folder(s) × {workers_for_estimate} workers")
        if estimated_hours > 0:
            print(f"⏱️  Estimated time: ~{estimated_hours}h {estimated_minutes}m (includes cooling breaks)")
        else:
            print(f"⏱️  Estimated time: ~{estimated_minutes}m (includes cooling breaks)")
        
        proceed = auto_confirm_prompt(
            "Proceed with extraction?",
            timeout=15,
            default=True
        )
        
        if not proceed:
            print("Extraction cancelled.")
            return
        
        print("\n" + "="*60)
        print("STARTING EXTRACTION")
        print("="*60 + "\n")
        
        start_time = time.time()
        stats = processor.process_pdfs(selected_pdfs)
        end_time = time.time()
        
        elapsed_time = end_time - start_time
        elapsed_hours = int(elapsed_time // 3600)
        elapsed_minutes = int((elapsed_time % 3600) // 60)
        elapsed_seconds = int(elapsed_time % 60)
        
        print("\n" + "="*60)
        print("PROCESSING COMPLETE")
        print("="*60)
        print(f"✅ Folders processed: {len(folder_groups)}")
        print(f"✅ Total PDFs processed: {len(selected_pdfs)}")
        print(f"✅ Total sectors found: {stats.total_sectors}")
        print(f"✅ Total images extracted: {stats.total_images}")
        print(f"✅ Average images per sector: {stats.total_images/stats.total_sectors:.2f}" if stats.total_sectors > 0 else "No sectors found")
        
        if elapsed_hours > 0:
            print(f"⏱️  Total time: {elapsed_hours}h {elapsed_minutes}m {elapsed_seconds}s")
        else:
            print(f"⏱️  Total time: {elapsed_minutes}m {elapsed_seconds}s")
        
        avg_time_per_folder = elapsed_time / len(folder_groups) if folder_groups else 0
        avg_folder_mins = int(avg_time_per_folder // 60)
        avg_folder_secs = int(avg_time_per_folder % 60)
        print(f"📊 Average per folder: {avg_folder_mins}m {avg_folder_secs}s")
        
        print(f"\n📁 Images saved to: {paths.image_dir}")
        print(f"📄 Image link CSVs saved to: {paths.image_link_dir}")
        print(f"📝 Modified PDFs saved to: {paths.modified_dir}")
        print("="*60 + "\n")
        
    except Exception as e:
        logger.error(f"An error occurred in the main process: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()