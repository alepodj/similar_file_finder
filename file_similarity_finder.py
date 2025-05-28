import os
import hashlib
import difflib
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import defaultdict
from fuzzywuzzy import fuzz
import threading
import time
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import itertools
from functools import partial
import json
import csv
from datetime import datetime

# Try to import xxhash for faster hashing, fallback to hashlib
try:
    import xxhash
    XXHASH_AVAILABLE = True
    print("✅ xxHash available - using fast xxh64 hashing")
except ImportError:
    XXHASH_AVAILABLE = False
    print("⚠️ xxHash not available - using SHA-256 (install with: pip install xxhash)")

# Global functions for multiprocessing (must be at module level)
def calculate_file_hash_worker(file_path: str, chunk_size: int = 8192) -> Tuple[str, str]:
    """Calculate file hash using xxHash (fast) or SHA-256 (fallback)"""
    try:
        if XXHASH_AVAILABLE:
            # Use xxHash for much faster hashing (10x+ speedup)
            hasher = xxhash.xxh64()
        else:
            # Fallback to SHA-256
            hasher = hashlib.sha256()
            
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        
        if XXHASH_AVAILABLE:
            # xxHash returns integer, convert to hex string
            file_hash = hasher.hexdigest()
        else:
            # SHA-256 already returns hex string
            file_hash = hasher.hexdigest()
            
        return file_path, file_hash
    except Exception as e:
        return file_path, f"ERROR: {str(e)}"

def calculate_name_similarity_worker(args: Tuple[str, str, str]) -> Tuple[str, str, float]:
    """Worker function for name similarity calculation"""
    file1, file2, method = args
    
    name1 = os.path.basename(file1)
    name2 = os.path.basename(file2)
    
    # Remove extensions for comparison
    name1_base = os.path.splitext(name1)[0]
    name2_base = os.path.splitext(name2)[0]
    
    if method == 'ratio':
        similarity = fuzz.ratio(name1_base.lower(), name2_base.lower())
    elif method == 'partial_ratio':
        similarity = fuzz.partial_ratio(name1_base.lower(), name2_base.lower())
    elif method == 'token_sort_ratio':
        similarity = fuzz.token_sort_ratio(name1_base.lower(), name2_base.lower())
    elif method == 'token_set_ratio':
        similarity = fuzz.token_set_ratio(name1_base.lower(), name2_base.lower())
    elif method == 'sequence_matcher':
        similarity = difflib.SequenceMatcher(None, name1_base.lower(), name2_base.lower()).ratio() * 100
    else:
        similarity = fuzz.ratio(name1_base.lower(), name2_base.lower())
    
    return (file1, file2, similarity)

def process_similarity_chunk(args: Tuple[List[Tuple[str, str]], str, float]) -> List[Tuple[str, str, float]]:
    """Process a chunk of file pairs for similarity comparison"""
    file_pairs, method, threshold = args
    results = []
    
    for file1, file2 in file_pairs:
        name1 = os.path.basename(file1)
        name2 = os.path.basename(file2)
        
        # Skip if same name
        if name1 == name2:
            continue
            
        # Remove extensions for comparison
        name1_base = os.path.splitext(name1)[0]
        name2_base = os.path.splitext(name2)[0]
        
        if method == 'ratio':
            similarity = fuzz.ratio(name1_base.lower(), name2_base.lower())
        elif method == 'partial_ratio':
            similarity = fuzz.partial_ratio(name1_base.lower(), name2_base.lower())
        elif method == 'token_sort_ratio':
            similarity = fuzz.token_sort_ratio(name1_base.lower(), name2_base.lower())
        elif method == 'token_set_ratio':
            similarity = fuzz.token_set_ratio(name1_base.lower(), name2_base.lower())
        elif method == 'sequence_matcher':
            similarity = difflib.SequenceMatcher(None, name1_base.lower(), name2_base.lower()).ratio() * 100
        else:
            similarity = fuzz.ratio(name1_base.lower(), name2_base.lower())
        
        if similarity >= threshold:
            results.append((file1, file2, similarity))
    
    return results

class FileSimilarityFinder:
    """
    A comprehensive file similarity finder that identifies:
    1. Files with identical content but different names
    2. Files with identical names but different content
    3. Files with similar names based on user-defined similarity threshold
    
    Optimized with multiprocessing for better performance.
    """
    
    def __init__(self, max_workers: int = None):
        self.file_hashes = {}  # hash -> list of file paths
        self.file_names = defaultdict(list)  # filename -> list of file paths
        self.all_files = []  # all discovered files
        self.progress_callback = None
        self.max_workers = max_workers or min(32, (os.cpu_count() or 1) + 4)
        self.cancel_event = threading.Event()  # Add cancellation support
        self.current_executor = None  # Track current executor for cleanup
        
    def set_progress_callback(self, callback):
        """Set callback function for progress updates"""
        self.progress_callback = callback
        
    def cancel_operation(self):
        """Cancel the current operation"""
        self.cancel_event.set()
        if self.current_executor:
            self.current_executor.shutdown(wait=False)
            
    def reset_cancellation(self):
        """Reset cancellation state for new operations"""
        self.cancel_event.clear()
        self.current_executor = None
        
    def is_cancelled(self):
        """Check if operation has been cancelled"""
        return self.cancel_event.is_set()
        
    def _update_progress(self, message, percentage=None):
        """Update progress if callback is set"""
        if self.progress_callback:
            self.progress_callback(message, percentage)
        
        # Check for cancellation during progress updates
        if self.is_cancelled():
            raise InterruptedError("Operation was cancelled by user")
    
    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate hash of a single file using xxHash (fast) or SHA-256 (fallback)"""
        try:
            if XXHASH_AVAILABLE:
                # Use xxHash for much faster hashing (10x+ speedup)
                hasher = xxhash.xxh64()
            else:
                # Fallback to SHA-256
                hasher = hashlib.sha256()
                
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    hasher.update(chunk)
            
            if XXHASH_AVAILABLE:
                # xxHash returns integer, convert to hex string
                return hasher.hexdigest()
            else:
                # SHA-256 already returns hex string
                return hasher.hexdigest()
                
        except Exception as e:
            print(f"Error calculating hash for {file_path}: {e}")
            return f"ERROR: {str(e)}"

    def calculate_hashes_parallel(self, file_paths: List[str]) -> Dict[str, str]:
        """Calculate file hashes in parallel using xxHash (fast) or SHA-256 (fallback)"""
        file_hashes = {}
        total_files = len(file_paths)
        
        if total_files < 100:  # Use sequential for small datasets
            for i, file_path in enumerate(file_paths):
                if self.is_cancelled():
                    raise InterruptedError("Operation was cancelled by user")
                    
                file_hash = self.calculate_file_hash(file_path)
                if not file_hash.startswith("ERROR:"):
                    file_hashes[file_path] = file_hash
                else:
                    print(f"Skipping file with error: {file_path}")
                    
                if self.progress_callback:
                    progress = (i + 1) / total_files * 100
                    hash_type = "xxHash" if XXHASH_AVAILABLE else "SHA-256"
                    self._update_progress(f"Calculating {hash_type} hashes: {i + 1}/{total_files} files", progress)
            return file_hashes
        
        # Use parallel processing for larger datasets
        completed = 0
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_file = {executor.submit(calculate_file_hash_worker, file_path): file_path 
                            for file_path in file_paths}
            
            # Process completed tasks
            for future in as_completed(future_to_file):
                if self.is_cancelled():
                    # Cancel remaining futures
                    for f in future_to_file:
                        f.cancel()
                    raise InterruptedError("Operation was cancelled by user")
                
                file_path, file_hash = future.result()
                if not file_hash.startswith("ERROR:"):
                    file_hashes[file_path] = file_hash
                else:
                    print(f"Skipping file with error: {file_path}")
                
                completed += 1
                if self.progress_callback:
                    progress = completed / total_files * 100
                    hash_type = "xxHash" if XXHASH_AVAILABLE else "SHA-256"
                    self._update_progress(f"Calculating {hash_type} hashes: {completed}/{total_files} files", progress)
        
        return file_hashes
    
    def scan_directory(self, directory_path: str, recursive: bool = True) -> None:
        """Scan directory for files and build hash and name mappings"""
        self._update_progress("Scanning directories...")
        
        path = Path(directory_path)
        if not path.exists():
            raise ValueError(f"Directory does not exist: {directory_path}")
        
        # Collect all files
        if recursive:
            files = list(path.rglob('*'))
        else:
            files = list(path.glob('*'))
        
        # Check for cancellation after file discovery
        if self.is_cancelled():
            raise InterruptedError("Directory scan was cancelled")
        
        files = [f for f in files if f.is_file()]
        self.all_files = [str(f) for f in files]
        
        total_files = len(self.all_files)
        self._update_progress(f"Found {total_files} files. Calculating hashes...")
        
        # Calculate hashes in parallel
        if total_files > 0:
            hash_results = self.calculate_hashes_parallel(self.all_files)
            
            # Check for cancellation before building mappings
            if self.is_cancelled():
                raise InterruptedError("Directory scan was cancelled")
            
            # Build hash and name mappings
            for file_path in self.all_files:
                if file_path in hash_results:
                    file_hash = hash_results[file_path]
                    if file_hash not in self.file_hashes:
                        self.file_hashes[file_hash] = []
                    self.file_hashes[file_hash].append(file_path)
                
                # Track by filename
                filename = os.path.basename(file_path)
                self.file_names[filename].append(file_path)
    
    def find_identical_content_different_names(self) -> List[List[str]]:
        """Find files with identical content but different names"""
        identical_groups = []
        
        for file_hash, file_paths in self.file_hashes.items():
            if len(file_paths) > 1:
                # Check if files have different names
                filenames = [os.path.basename(path) for path in file_paths]
                if len(set(filenames)) > 1:  # Different names exist
                    identical_groups.append(file_paths)
        
        return identical_groups
    
    def find_all_duplicates(self) -> List[List[str]]:
        """Find ALL files with identical content (regardless of name)"""
        duplicate_groups = []
        
        for file_hash, file_paths in self.file_hashes.items():
            if len(file_paths) > 1:  # Multiple files with same hash = duplicates
                duplicate_groups.append(file_paths)
        
        return duplicate_groups
    
    def find_duplicates_same_name(self) -> List[List[str]]:
        """Find files with identical content AND identical names"""
        same_name_duplicates = []
        
        for file_hash, file_paths in self.file_hashes.items():
            if len(file_paths) > 1:
                # Check if files have the same names
                filenames = [os.path.basename(path) for path in file_paths]
                if len(set(filenames)) == 1:  # All files have the same name
                    same_name_duplicates.append(file_paths)
        
        return same_name_duplicates
    
    def find_same_names_different_content(self) -> List[List[str]]:
        """Find files with identical names but different content (includes same base name with different extensions)"""
        same_name_groups = []
        processed_groups = set()
        
        # First, check for exact filename matches (original functionality)
        for filename, file_paths in self.file_names.items():
            if len(file_paths) > 1:
                # Check if files have different hashes
                hashes = set()
                for path in file_paths:
                    # Use cached hash if available
                    file_hash = None
                    for h, paths in self.file_hashes.items():
                        if path in paths:
                            file_hash = h
                            break
                    
                    if not file_hash:
                        file_hash = self.calculate_file_hash(path)
                    
                    if file_hash:
                        hashes.add(file_hash)
                
                if len(hashes) > 1:  # Different content
                    same_name_groups.append(file_paths)
                    # Mark these files as processed to avoid duplicates
                    for path in file_paths:
                        processed_groups.add(path)
        
        # Second, check for same base name with different extensions
        base_name_groups = defaultdict(list)
        
        # Group files by base name (without extension)
        for file_path in self.all_files:
            if file_path not in processed_groups:  # Skip already processed files
                filename = os.path.basename(file_path)
                base_name = os.path.splitext(filename)[0]
                base_name_groups[base_name].append(file_path)
        
        # Check groups with same base name but different extensions
        for base_name, file_paths in base_name_groups.items():
            if len(file_paths) > 1:
                # Check if they have different extensions
                extensions = set()
                for path in file_paths:
                    filename = os.path.basename(path)
                    ext = os.path.splitext(filename)[1]
                    extensions.add(ext)
                
                # Only proceed if there are different extensions
                if len(extensions) > 1:
                    # Check if files have different hashes
                    hashes = set()
                    for path in file_paths:
                        # Use cached hash if available
                        file_hash = None
                        for h, paths in self.file_hashes.items():
                            if path in paths:
                                file_hash = h
                                break
                        
                        if not file_hash:
                            file_hash = self.calculate_file_hash(path)
                        
                        if file_hash:
                            hashes.add(file_hash)
                    
                    if len(hashes) > 1:  # Different content
                        same_name_groups.append(file_paths)
        
        return same_name_groups
    
    def calculate_name_similarity(self, name1: str, name2: str, method: str = 'ratio') -> float:
        """Calculate similarity between two filenames using various methods"""
        # Remove extensions for comparison
        name1_base = os.path.splitext(name1)[0]
        name2_base = os.path.splitext(name2)[0]
        
        if method == 'ratio':
            return fuzz.ratio(name1_base.lower(), name2_base.lower())
        elif method == 'partial_ratio':
            return fuzz.partial_ratio(name1_base.lower(), name2_base.lower())
        elif method == 'token_sort_ratio':
            return fuzz.token_sort_ratio(name1_base.lower(), name2_base.lower())
        elif method == 'token_set_ratio':
            return fuzz.token_set_ratio(name1_base.lower(), name2_base.lower())
        elif method == 'sequence_matcher':
            return difflib.SequenceMatcher(None, name1_base.lower(), name2_base.lower()).ratio() * 100
        else:
            return fuzz.ratio(name1_base.lower(), name2_base.lower())

    def find_similar_names_parallel(self, similarity_threshold: float = 50.0, 
                                  method: str = 'ratio', chunk_size: int = 1000) -> List[Tuple[str, str, float]]:
        """Find files with similar names using parallel processing"""
        if len(self.all_files) < 2:
            return []
        
        self._update_progress("Generating file pairs for comparison...")
        
        # Generate all unique pairs
        file_pairs = list(itertools.combinations(self.all_files, 2))
        total_pairs = len(file_pairs)
        
        # Check for cancellation after pair generation
        if self.is_cancelled():
            raise InterruptedError("Similar names search was cancelled")
        
        self._update_progress(f"Comparing {total_pairs} file pairs...")
        
        # Split pairs into chunks for parallel processing
        chunks = [file_pairs[i:i + chunk_size] for i in range(0, len(file_pairs), chunk_size)]
        
        similar_pairs = []
        processed_chunks = 0
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            self.current_executor = executor  # Track executor for cancellation
            
            # Submit chunks for processing
            chunk_args = [(chunk, method, similarity_threshold) for chunk in chunks]
            future_to_chunk = {executor.submit(process_similarity_chunk, args): i 
                             for i, args in enumerate(chunk_args)}
            
            try:
                for future in as_completed(future_to_chunk):
                    # Check for cancellation
                    if self.is_cancelled():
                        # Cancel remaining futures
                        for f in future_to_chunk:
                            f.cancel()
                        raise InterruptedError("Similar names search was cancelled")
                    
                    chunk_results = future.result()
                    similar_pairs.extend(chunk_results)
                    
                    processed_chunks += 1
                    percentage = processed_chunks / len(chunks) * 100
                    self._update_progress(f"Processing chunks: {processed_chunks}/{len(chunks)}", percentage)
            finally:
                self.current_executor = None
        
        # Sort by similarity (highest first)
        similar_pairs.sort(key=lambda x: x[2], reverse=True)
        return similar_pairs
    
    def find_similar_names(self, similarity_threshold: float = 50.0, 
                          method: str = 'ratio') -> List[Tuple[str, str, float]]:
        """Find files with similar names based on similarity threshold"""
        # Use parallel version for large datasets, sequential for small ones
        if len(self.all_files) > 100:
            return self.find_similar_names_parallel(similarity_threshold, method)
        
        # Original sequential implementation for small datasets
        similar_pairs = []
        processed_pairs = set()
        
        total_comparisons = len(self.all_files) * (len(self.all_files) - 1) // 2
        comparison_count = 0
        
        self._update_progress("Finding similar names...")
        
        for i, file1 in enumerate(self.all_files):
            for j, file2 in enumerate(self.all_files[i+1:], i+1):
                comparison_count += 1
                
                name1 = os.path.basename(file1)
                name2 = os.path.basename(file2)
                
                # Skip if same file or already processed
                pair_key = tuple(sorted([file1, file2]))
                if pair_key in processed_pairs or name1 == name2:
                    continue
                
                processed_pairs.add(pair_key)
                
                similarity = self.calculate_name_similarity(name1, name2, method)
                
                if similarity >= similarity_threshold:
                    similar_pairs.append((file1, file2, similarity))
                
                # Update progress every 100 comparisons
                if comparison_count % 100 == 0:
                    percentage = comparison_count / total_comparisons * 100
                    self._update_progress(f"Comparing names: {comparison_count}/{total_comparisons}", percentage)
        
        # Sort by similarity (highest first)
        similar_pairs.sort(key=lambda x: x[2], reverse=True)
        return similar_pairs
    
    def get_file_info(self, file_path: str) -> Dict:
        """Get detailed information about a file"""
        try:
            stat = os.stat(file_path)
            file_hash = None
            
            # Try to get cached hash first
            for h, paths in self.file_hashes.items():
                if file_path in paths:
                    file_hash = h
                    break
            
            # Calculate hash if not cached
            if not file_hash:
                file_hash = self.calculate_file_hash(file_path)
            
            return {
                'path': file_path,
                'name': os.path.basename(file_path),
                'directory': os.path.dirname(file_path),
                'extension': os.path.splitext(file_path)[1].lower(),
                'size': stat.st_size,
                'size_mb': round(stat.st_size / (1024 * 1024), 2),
                'modified': time.ctime(stat.st_mtime),
                'modified_timestamp': stat.st_mtime,
                'created': time.ctime(stat.st_ctime),
                'created_timestamp': stat.st_ctime,
                'hash': file_hash,
                'hash_short': file_hash[:16] if file_hash else None
            }
        except (OSError, IOError) as e:
            return {
                'path': file_path,
                'name': os.path.basename(file_path),
                'directory': os.path.dirname(file_path),
                'error': str(e)
            }
    
    def generate_report(self, output_file: str = None) -> str:
        """Generate a comprehensive report of findings"""
        report = []
        report.append("=" * 60)
        report.append("FILE SIMILARITY ANALYSIS REPORT")
        report.append("=" * 60)
        report.append(f"Total files scanned: {len(self.all_files)}")
        report.append("")
        
        # ALL duplicates
        all_duplicates = self.find_all_duplicates()
        report.append(f"ALL DUPLICATE FILES (regardless of name): {len(all_duplicates)} groups")
        report.append("-" * 40)
        for i, group in enumerate(all_duplicates, 1):
            report.append(f"Group {i}:")
            for file_path in group:
                info = self.get_file_info(file_path)
                report.append(f"  - {info['name']} ({info['size']} bytes) - {file_path}")
            report.append("")
        
        # Identical content, different names
        identical_groups = self.find_identical_content_different_names()
        report.append(f"Files with identical content but different names: {len(identical_groups)} groups")
        report.append("-" * 40)
        for i, group in enumerate(identical_groups, 1):
            report.append(f"Group {i}:")
            for file_path in group:
                info = self.get_file_info(file_path)
                report.append(f"  - {info['name']} ({info['size']} bytes) - {file_path}")
            report.append("")
        
        # Same names, different content
        same_name_groups = self.find_same_names_different_content()
        report.append(f"Files with same names but different content: {len(same_name_groups)} groups")
        report.append("-" * 40)
        for i, group in enumerate(same_name_groups, 1):
            report.append(f"Group {i}:")
            for file_path in group:
                info = self.get_file_info(file_path)
                report.append(f"  - {info['name']} ({info['size']} bytes) - {file_path}")
            report.append("")
        
        report_text = "\n".join(report)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
        
        return report_text

    def get_scan_metadata(self) -> Dict:
        """Get comprehensive metadata about the scan"""
        if not self.all_files:
            return {}
        
        # Calculate file statistics
        total_size = 0
        extensions = defaultdict(int)
        size_by_ext = defaultdict(int)
        
        for file_path in self.all_files:
            try:
                stat = os.stat(file_path)
                total_size += stat.st_size
                ext = os.path.splitext(file_path)[1].lower()
                extensions[ext] += 1
                size_by_ext[ext] += stat.st_size
            except (OSError, IOError):
                continue
        
        # Get duplicate statistics
        all_duplicates = self.find_all_duplicates()
        same_name_groups = self.find_same_names_different_content()
        
        # Calculate potential space savings
        space_savings = 0
        for group in all_duplicates:
            if len(group) > 1:
                try:
                    file_size = os.path.getsize(group[0])
                    space_savings += file_size * (len(group) - 1)  # Keep one, delete rest
                except (OSError, IOError):
                    continue
        
        return {
            'scan_timestamp': datetime.now().isoformat(),
            'total_files': len(self.all_files),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'total_size_gb': round(total_size / (1024 * 1024 * 1024), 2),
            'max_workers_used': self.max_workers,
            'duplicate_groups': len(all_duplicates),
            'name_conflict_groups': len(same_name_groups),
            'potential_space_savings_bytes': space_savings,
            'potential_space_savings_mb': round(space_savings / (1024 * 1024), 2),
            'potential_space_savings_gb': round(space_savings / (1024 * 1024 * 1024), 2),
            'file_extensions': dict(extensions),
            'size_by_extension_mb': {ext: round(size / (1024 * 1024), 2) for ext, size in size_by_ext.items()}
        }
    
    def export_to_csv(self, output_file: str, similarity_threshold: float = 70.0, similarity_method: str = 'ratio') -> str:
        """Export comprehensive data to CSV format"""
        # Get all data
        all_duplicates = self.find_all_duplicates()
        same_name_groups = self.find_same_names_different_content()
        similar_pairs = self.find_similar_names(similarity_threshold, similarity_method)
        metadata = self.get_scan_metadata()
        
        # Create CSV with multiple sheets (files)
        base_name = os.path.splitext(output_file)[0]
        
        # 1. Summary CSV
        summary_file = f"{base_name}_summary.csv"
        with open(summary_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Metric', 'Value'])
            writer.writerow(['Scan Date', metadata.get('scan_timestamp', 'Unknown')])
            writer.writerow(['Total Files', metadata.get('total_files', 0)])
            writer.writerow(['Total Size (MB)', metadata.get('total_size_mb', 0)])
            writer.writerow(['Total Size (GB)', metadata.get('total_size_gb', 0)])
            writer.writerow(['Workers Used', metadata.get('max_workers_used', 1)])
            writer.writerow(['Duplicate Groups', metadata.get('duplicate_groups', 0)])
            writer.writerow(['Name Conflict Groups', metadata.get('name_conflict_groups', 0)])
            writer.writerow(['Similar Name Pairs', len(similar_pairs)])
            writer.writerow(['Potential Space Savings (MB)', metadata.get('potential_space_savings_mb', 0)])
            writer.writerow(['Potential Space Savings (GB)', metadata.get('potential_space_savings_gb', 0)])
        
        # 2. Content Duplicates CSV
        duplicates_file = f"{base_name}_content_duplicates.csv"
        with open(duplicates_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Group_ID', 'File_Name', 'File_Path', 'Directory', 'Extension', 
                           'Size_Bytes', 'Size_MB', 'Modified_Date', 'Created_Date', 'Hash'])
            
            for group_id, group in enumerate(all_duplicates, 1):
                for file_path in group:
                    info = self.get_file_info(file_path)
                    if 'error' not in info:
                        writer.writerow([
                            group_id, info['name'], info['path'], info['directory'],
                            info['extension'], info['size'], info['size_mb'],
                            info['modified'], info['created'], info['hash']
                        ])
        
        # 3. Name Conflicts CSV
        conflicts_file = f"{base_name}_name_conflicts.csv"
        with open(conflicts_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Group_ID', 'File_Name', 'File_Path', 'Directory', 'Extension',
                           'Size_Bytes', 'Size_MB', 'Modified_Date', 'Created_Date', 'Hash'])
            
            for group_id, group in enumerate(same_name_groups, 1):
                for file_path in group:
                    info = self.get_file_info(file_path)
                    if 'error' not in info:
                        writer.writerow([
                            group_id, info['name'], info['path'], info['directory'],
                            info['extension'], info['size'], info['size_mb'],
                            info['modified'], info['created'], info['hash']
                        ])
        
        # 4. Similar Names CSV
        similar_file = f"{base_name}_similar_names.csv"
        with open(similar_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['File1_Name', 'File1_Path', 'File1_Size_MB', 'File2_Name', 
                           'File2_Path', 'File2_Size_MB', 'Similarity_Percent', 'Method_Used'])
            
            for file1, file2, similarity in similar_pairs:
                info1 = self.get_file_info(file1)
                info2 = self.get_file_info(file2)
                if 'error' not in info1 and 'error' not in info2:
                    writer.writerow([
                        info1['name'], info1['path'], info1['size_mb'],
                        info2['name'], info2['path'], info2['size_mb'],
                        f"{similarity:.1f}", similarity_method
                    ])
        
        # 5. File Extensions CSV
        extensions_file = f"{base_name}_file_extensions.csv"
        with open(extensions_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Extension', 'File_Count', 'Total_Size_MB'])
            
            for ext, count in metadata.get('file_extensions', {}).items():
                size_mb = metadata.get('size_by_extension_mb', {}).get(ext, 0)
                writer.writerow([ext or '(no extension)', count, size_mb])
        
        return f"CSV export completed: {summary_file}, {duplicates_file}, {conflicts_file}, {similar_file}, {extensions_file}"
    
    def export_to_json(self, output_file: str, similarity_threshold: float = 70.0, similarity_method: str = 'ratio') -> str:
        """Export comprehensive data to JSON format"""
        # Get all data
        all_duplicates = self.find_all_duplicates()
        same_name_groups = self.find_same_names_different_content()
        similar_pairs = self.find_similar_names(similarity_threshold, similarity_method)
        metadata = self.get_scan_metadata()
        
        # Build comprehensive JSON structure
        export_data = {
            'metadata': metadata,
            'scan_parameters': {
                'similarity_threshold': similarity_threshold,
                'similarity_method': similarity_method,
                'recursive_scan': True  # Assuming recursive, could be parameterized
            },
            'content_duplicates': [],
            'name_conflicts': [],
            'similar_names': [],
            'file_statistics': {
                'by_extension': metadata.get('file_extensions', {}),
                'size_by_extension_mb': metadata.get('size_by_extension_mb', {})
            }
        }
        
        # Add content duplicates
        for group_id, group in enumerate(all_duplicates, 1):
            group_data = {
                'group_id': group_id,
                'files': []
            }
            for file_path in group:
                info = self.get_file_info(file_path)
                if 'error' not in info:
                    group_data['files'].append(info)
            export_data['content_duplicates'].append(group_data)
        
        # Add name conflicts
        for group_id, group in enumerate(same_name_groups, 1):
            group_data = {
                'group_id': group_id,
                'files': []
            }
            for file_path in group:
                info = self.get_file_info(file_path)
                if 'error' not in info:
                    group_data['files'].append(info)
            export_data['name_conflicts'].append(group_data)
        
        # Add similar names
        for file1, file2, similarity in similar_pairs:
            info1 = self.get_file_info(file1)
            info2 = self.get_file_info(file2)
            if 'error' not in info1 and 'error' not in info2:
                export_data['similar_names'].append({
                    'file1': info1,
                    'file2': info2,
                    'similarity_percent': round(similarity, 1),
                    'method_used': similarity_method
                })
        
        # Write JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        return f"JSON export completed: {output_file}"
    
    def export_to_html(self, output_file: str, similarity_threshold: float = 70.0, similarity_method: str = 'ratio') -> str:
        """Export comprehensive data to HTML format with interactive features"""
        # Get all data
        all_duplicates = self.find_all_duplicates()
        same_name_groups = self.find_same_names_different_content()
        similar_pairs = self.find_similar_names(similarity_threshold, similarity_method)
        metadata = self.get_scan_metadata()
        
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Similarity Analysis Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; text-align: center; margin-bottom: 30px; }}
        h2 {{ color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        h3 {{ color: #2980b9; }}
        .summary {{ background: #ecf0f1; padding: 20px; border-radius: 8px; margin-bottom: 30px; }}
        .metric {{ display: inline-block; margin: 10px 20px; text-align: center; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #e74c3c; }}
        .metric-label {{ font-size: 14px; color: #7f8c8d; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #3498db; color: white; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        tr:hover {{ background-color: #e8f4f8; }}
        .group {{ background: #fff3cd; padding: 10px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #ffc107; }}
        .file-path {{ font-family: monospace; font-size: 12px; color: #6c757d; }}
        .similarity {{ font-weight: bold; color: #28a745; }}
        .warning {{ color: #e74c3c; font-weight: bold; }}
        .info {{ color: #17a2b8; }}
        .toggle {{ cursor: pointer; color: #007bff; text-decoration: underline; }}
        .hidden {{ display: none; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; }}
    </style>
    <script>
        function toggleSection(id) {{
            var element = document.getElementById(id);
            element.classList.toggle('hidden');
        }}
        function sortTable(tableId, column) {{
            var table = document.getElementById(tableId);
            var rows = Array.from(table.rows).slice(1);
            var isNumeric = !isNaN(rows[0].cells[column].textContent);
            
            rows.sort(function(a, b) {{
                var aVal = a.cells[column].textContent;
                var bVal = b.cells[column].textContent;
                if (isNumeric) {{
                    return parseFloat(aVal) - parseFloat(bVal);
                }}
                return aVal.localeCompare(bVal);
            }});
            
            rows.forEach(function(row) {{
                table.appendChild(row);
            }});
        }}
    </script>
</head>
<body>
    <div class="container">
        <h1>📁 File Similarity Analysis Report</h1>
        
        <div class="summary">
            <h2>📊 Scan Summary</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="metric-value">{metadata.get('total_files', 0)}</div>
                    <div class="metric-label">Total Files</div>
                </div>
                <div class="stat-card">
                    <div class="metric-value">{metadata.get('total_size_gb', 0):.1f} GB</div>
                    <div class="metric-label">Total Size</div>
                </div>
                <div class="stat-card">
                    <div class="metric-value">{len(all_duplicates)}</div>
                    <div class="metric-label">Duplicate Groups</div>
                </div>
                <div class="stat-card">
                    <div class="metric-value">{len(same_name_groups)}</div>
                    <div class="metric-label">Name Conflicts</div>
                </div>
                <div class="stat-card">
                    <div class="metric-value">{len(similar_pairs)}</div>
                    <div class="metric-label">Similar Names</div>
                </div>
                <div class="stat-card">
                    <div class="metric-value">{metadata.get('potential_space_savings_gb', 0):.1f} GB</div>
                    <div class="metric-label">Potential Savings</div>
                </div>
            </div>
            <p><strong>Scan Date:</strong> {metadata.get('scan_timestamp', 'Unknown')}</p>
            <p><strong>Workers Used:</strong> {metadata.get('max_workers_used', 1)}</p>
            <p><strong>Similarity Method:</strong> {similarity_method} (threshold: {similarity_threshold}%)</p>
        </div>
"""
        
        # Add Content Duplicates section
        if all_duplicates:
            html_content += f"""
        <h2>🔄 Content Duplicates ({len(all_duplicates)} groups)</h2>
        <p class="info">Files with identical content - safe to delete extras to save space.</p>
        <span class="toggle" onclick="toggleSection('duplicates-section')">Show/Hide Details</span>
        <div id="duplicates-section">
"""
            for i, group in enumerate(all_duplicates, 1):
                html_content += f'<div class="group"><h4>Group {i} ({len(group)} files)</h4>'
                for file_path in group:
                    info = self.get_file_info(file_path)
                    if 'error' not in info:
                        html_content += f"""
                        <p><strong>{info['name']}</strong> ({info['size_mb']} MB)<br>
                        <span class="file-path">{info['path']}</span><br>
                        <small>Modified: {info['modified']} | Hash: {info['hash_short']}...</small></p>
"""
                html_content += '</div>'
            html_content += '</div>'
        
        # Add Name Conflicts section
        if same_name_groups:
            html_content += f"""
        <h2>⚠️ Name Conflicts ({len(same_name_groups)} groups)</h2>
        <p class="warning">Files with same names but different content - review for version conflicts.</p>
        <span class="toggle" onclick="toggleSection('conflicts-section')">Show/Hide Details</span>
        <div id="conflicts-section">
"""
            for i, group in enumerate(same_name_groups, 1):
                html_content += f'<div class="group"><h4>Group {i} ({len(group)} files)</h4>'
                for file_path in group:
                    info = self.get_file_info(file_path)
                    if 'error' not in info:
                        html_content += f"""
                        <p><strong>{info['name']}</strong> ({info['size_mb']} MB)<br>
                        <span class="file-path">{info['path']}</span><br>
                        <small>Modified: {info['modified']} | Hash: {info['hash_short']}...</small></p>
"""
                html_content += '</div>'
            html_content += '</div>'
        
        # Add Similar Names section
        if similar_pairs:
            html_content += f"""
        <h2>🔍 Similar Names ({len(similar_pairs)} pairs)</h2>
        <p class="info">Files with similar names - may indicate related files or typos.</p>
        <span class="toggle" onclick="toggleSection('similar-section')">Show/Hide Details</span>
        <div id="similar-section">
            <table id="similar-table">
                <thead>
                    <tr>
                        <th onclick="sortTable('similar-table', 0)">File 1</th>
                        <th onclick="sortTable('similar-table', 1)">File 2</th>
                        <th onclick="sortTable('similar-table', 2)">Similarity</th>
                        <th onclick="sortTable('similar-table', 3)">Size 1 (MB)</th>
                        <th onclick="sortTable('similar-table', 4)">Size 2 (MB)</th>
                    </tr>
                </thead>
                <tbody>
"""
            for file1, file2, similarity in similar_pairs[:50]:  # Limit to first 50 for performance
                info1 = self.get_file_info(file1)
                info2 = self.get_file_info(file2)
                if 'error' not in info1 and 'error' not in info2:
                    html_content += f"""
                    <tr>
                        <td>{info1['name']}<br><small class="file-path">{info1['directory']}</small></td>
                        <td>{info2['name']}<br><small class="file-path">{info2['directory']}</small></td>
                        <td class="similarity">{similarity:.1f}%</td>
                        <td>{info1['size_mb']}</td>
                        <td>{info2['size_mb']}</td>
                    </tr>
"""
            html_content += """
                </tbody>
            </table>
        </div>
"""
        
        # Add File Extensions section
        extensions = metadata.get('file_extensions', {})
        if extensions:
            html_content += f"""
        <h2>📄 File Extensions Analysis</h2>
        <span class="toggle" onclick="toggleSection('extensions-section')">Show/Hide Details</span>
        <div id="extensions-section">
            <table id="extensions-table">
                <thead>
                    <tr>
                        <th onclick="sortTable('extensions-table', 0)">Extension</th>
                        <th onclick="sortTable('extensions-table', 1)">File Count</th>
                        <th onclick="sortTable('extensions-table', 2)">Total Size (MB)</th>
                    </tr>
                </thead>
                <tbody>
"""
            size_by_ext = metadata.get('size_by_extension_mb', {})
            for ext, count in sorted(extensions.items(), key=lambda x: x[1], reverse=True):
                size_mb = size_by_ext.get(ext, 0)
                ext_display = ext if ext else '(no extension)'
                html_content += f"""
                    <tr>
                        <td>{ext_display}</td>
                        <td>{count}</td>
                        <td>{size_mb:.1f}</td>
                    </tr>
"""
            html_content += """
                </tbody>
            </table>
        </div>
"""
        
        html_content += """
        <footer style="margin-top: 50px; text-align: center; color: #7f8c8d; border-top: 1px solid #ddd; padding-top: 20px;">
            <p>Generated by File Similarity Finder v2.0</p>
        </footer>
    </div>
</body>
</html>
"""
        
        # Write HTML file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return f"HTML export completed: {output_file}"

# Example usage
if __name__ == "__main__":
    finder = FileSimilarityFinder()
    
    # Example directory scan
    directory = input("Enter directory path to scan: ")
    
    try:
        finder.scan_directory(directory)
        
        print("\n=== IDENTICAL CONTENT, DIFFERENT NAMES ===")
        identical = finder.find_identical_content_different_names()
        for i, group in enumerate(identical, 1):
            print(f"Group {i}:")
            for file_path in group:
                print(f"  - {os.path.basename(file_path)} -> {file_path}")
            print()
        
        print("\n=== SAME NAMES, DIFFERENT CONTENT ===")
        same_names = finder.find_same_names_different_content()
        for i, group in enumerate(same_names, 1):
            print(f"Group {i}:")
            for file_path in group:
                print(f"  - {os.path.basename(file_path)} -> {file_path}")
            print()
        
        print("\n=== SIMILAR NAMES (70% threshold) ===")
        similar = finder.find_similar_names(70.0)
        for file1, file2, similarity in similar[:10]:  # Show top 10
            print(f"{similarity:.1f}% - {os.path.basename(file1)} <-> {os.path.basename(file2)}")
        
    except Exception as e:
        print(f"Error: {e}") 