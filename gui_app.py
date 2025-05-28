import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import multiprocessing as mp
import sv_ttk
from PIL import Image, ImageTk
from file_similarity_finder import FileSimilarityFinder

class FileSimilarityGUI:
    def __init__(self, root):
        self.root = root
        
        # Remove default title bar to create custom one
        self.root.overrideredirect(True)
        
        # Center the window on screen
        self.window_width = 1200
        self.window_height = 1000
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Calculate position for center
        self.center_x = (screen_width - self.window_width) // 2
        self.center_y = (screen_height - self.window_height) // 2
        
        self.root.geometry(f"{self.window_width}x{self.window_height}+{self.center_x}+{self.center_y}")  # Centered on screen
        
        # Apply Sun Valley theme
        sv_ttk.set_theme("light")  # You can change to "dark" for dark mode
        
        # Set application icon (before UI setup)
        self.set_application_icon()
        
        # Variables for window dragging
        self.drag_start_x = 0
        self.drag_start_y = 0
        
        # Variables for window resizing
        self.resize_start_x = 0
        self.resize_start_y = 0
        self.resize_start_width = 0
        self.resize_start_height = 0
        self.resize_border_width = 10  # Width of resize border in pixels
        
        # Variables
        self.selected_directory = tk.StringVar()
        self.similarity_threshold = tk.DoubleVar(value=70.0)
        self.similarity_method = tk.StringVar(value='Basic Similarity (Fastest)')
        self.recursive_scan = tk.BooleanVar(value=True)
        self.max_workers = tk.IntVar(value=min(32, (mp.cpu_count() or 1) + 4))
        self.current_theme = tk.StringVar(value="light")
        
        # Initialize finder
        self.finder = None
        
        # Add cancellation support
        self.scan_thread = None
        self.is_scanning = False
        
        self.setup_ui()
        
        # Set initial method explanation
        self.update_method_explanation()
        
        # Initialize hover styles
        self.refresh_hover_styles()
        
        # Add resize functionality
        self.setup_resize_functionality()
        
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(7, weight=1)  # Results notebook should expand (row 7)
        
        # Custom title bar
        self.create_custom_title_bar(main_frame)
        
        # Subtitle (moved up to replace header)
        subtitle_label = ttk.Label(main_frame, text="High-performance duplicate detection with multiprocessing", 
                                  font=('Arial', 12))
        subtitle_label.grid(row=1, column=0, columnspan=3, pady=(10, 20))
        
        # Directory selection
        ttk.Label(main_frame, text="Directory:").grid(row=2, column=0, sticky=tk.W, pady=5)
        
        dir_frame = ttk.Frame(main_frame)
        dir_frame.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        dir_frame.columnconfigure(0, weight=1)
        
        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.selected_directory, width=50)
        self.dir_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        browse_button = ttk.Button(dir_frame, text="Browse", command=self.browse_directory)
        browse_button.grid(row=0, column=1)
        self.add_regular_button_hover(browse_button, "button")
        
        # Options frame
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="10")
        options_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        options_frame.columnconfigure(1, weight=1)
        
        # Recursive scan
        ttk.Checkbutton(options_frame, text="Recursive scan (include subdirectories)", 
                       variable=self.recursive_scan).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Max workers
        ttk.Label(options_frame, text="Worker processes:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        workers_frame = ttk.Frame(options_frame)
        workers_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5)
        
        workers_spinbox = ttk.Spinbox(workers_frame, from_=1, to=64, 
                                     textvariable=self.max_workers, width=10)
        workers_spinbox.grid(row=0, column=0, sticky=tk.W)
        
        cpu_count = mp.cpu_count() or 1
        ttk.Label(workers_frame, text=f"(CPU cores: {cpu_count}, recommended: {min(32, cpu_count + 4)})").grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        # Similarity threshold
        ttk.Label(options_frame, text="Name similarity threshold (%):").grid(row=2, column=0, sticky=tk.W, pady=5)
        
        threshold_frame = ttk.Frame(options_frame)
        threshold_frame.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5)
        
        self.threshold_scale = ttk.Scale(threshold_frame, from_=0, to=100, 
                                        variable=self.similarity_threshold, orient=tk.HORIZONTAL)
        self.threshold_scale.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 10))
        threshold_frame.columnconfigure(0, weight=1)
        
        self.threshold_label = ttk.Label(threshold_frame, text="70.0%")
        self.threshold_label.grid(row=0, column=1)
        
        self.threshold_scale.configure(command=self.update_threshold_label)
        
        # Similarity method
        ttk.Label(options_frame, text="Similarity method:").grid(row=3, column=0, sticky=tk.W, pady=5)
        
        method_frame = ttk.Frame(options_frame)
        method_frame.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=5)
        method_frame.columnconfigure(1, weight=1)
        
        # Create mapping for user-friendly names
        self.method_display_names = {
            'Basic Similarity (Fastest)': 'ratio',
            'Partial Match': 'partial_ratio', 
            'Word Order Independent': 'token_sort_ratio',
            'Advanced Word Matching': 'token_set_ratio',
            'Precise Character Match': 'sequence_matcher'
        }
        
        # Reverse mapping for getting display name from method
        self.method_names_reverse = {v: k for k, v in self.method_display_names.items()}
        
        method_combo = ttk.Combobox(method_frame, textvariable=self.similarity_method,
                                   values=list(self.method_display_names.keys()), 
                                   state='readonly', width=25)
        method_combo.grid(row=0, column=0, sticky=tk.W)
        method_combo.bind('<<ComboboxSelected>>', self.on_method_selected)
        
        # Store reference for focus management
        self.method_combo = method_combo
        
        # Method explanation label (spans across remaining columns)
        self.method_explanation = ttk.Label(method_frame, text="Basic string similarity (fastest, good for most cases)", 
                                          font=('Arial', 8), wraplength=500)
        self.method_explanation.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        # Actions frame (like Options frame)
        actions_frame = ttk.LabelFrame(main_frame, text="Actions", padding="15")
        actions_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        # Create a centered frame for buttons
        button_container = ttk.Frame(actions_frame)
        button_container.pack(anchor=tk.CENTER, pady=5)
        
        self.scan_button = ttk.Button(button_container, text="Start Scan", command=self.start_scan, width=15)
        self.scan_button.pack(side=tk.LEFT, padx=5)
        self.add_regular_button_hover(self.scan_button, "action")
        
        self.export_button = ttk.Button(button_container, text="Export Report", 
                                       command=self.export_report, state='disabled', width=15)
        self.export_button.pack(side=tk.LEFT, padx=5)
        self.add_regular_button_hover(self.export_button, "export")
        
        clear_button = ttk.Button(button_container, text="Clear Results", command=self.clear_results, width=15)
        clear_button.pack(side=tk.LEFT, padx=5)
        self.add_regular_button_hover(clear_button, "clear")
        
        help_button = ttk.Button(button_container, text="Help Guide", command=self.show_method_help, width=15)
        help_button.pack(side=tk.LEFT, padx=5)
        self.add_regular_button_hover(help_button, "help")
        
        theme_button = ttk.Button(button_container, text="Toggle Theme", command=self.toggle_theme, width=15)
        theme_button.pack(side=tk.LEFT, padx=5)
        self.add_regular_button_hover(theme_button, "theme")
        
        # Output frame (like Options and Actions frames)
        output_frame = ttk.LabelFrame(main_frame, text="Output", padding="15")
        output_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        output_frame.columnconfigure(0, weight=1)
        
        # Progress label
        self.progress_var = tk.StringVar(value="Ready - Select a directory to begin scanning")
        progress_label = ttk.Label(output_frame, textvariable=self.progress_var, font=('Arial', 10))
        progress_label.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Progress bar
        self.progress_bar = ttk.Progressbar(output_frame, mode='determinate', length=400)
        self.progress_bar.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 5), ipady=1)  # Reduced from 8 to 3
        self.progress_bar['maximum'] = 100
        self.progress_bar['value'] = 0  # Start at 0
        
        # Separator line
        separator = ttk.Separator(main_frame, orient='horizontal')
        separator.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        # Results notebook (larger and resizable)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        
        # Tab 1: Content Duplicates (ALL identical content files)
        self.all_duplicates_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.all_duplicates_frame, text="Content Duplicates")
        
        # Add explanation for Content Duplicates tab
        all_dup_info = ttk.Label(self.all_duplicates_frame, 
                                text="📁 Shows ALL files with identical content (true duplicates) - same data, regardless of filename. Safe to delete extras.",
                                font=('Arial', 9))
        all_dup_info.pack(fill=tk.X, padx=5, pady=5)
        
        # Create container frame for treeview and scrollbar
        all_dup_container = ttk.Frame(self.all_duplicates_frame)
        all_dup_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        
        self.all_duplicates_tree = ttk.Treeview(all_dup_container, columns=('Name', 'Size', 'Path'), show='tree headings', height=18)
        self.all_duplicates_tree.heading('#0', text='Group')
        self.all_duplicates_tree.heading('Name', text='File Name')
        self.all_duplicates_tree.heading('Size', text='Size (bytes)')
        self.all_duplicates_tree.heading('Path', text='Full Path')
        
        # Configure column widths for better display
        self.all_duplicates_tree.column('#0', width=80, minwidth=80, anchor='center')
        self.all_duplicates_tree.column('Name', width=200, minwidth=150, anchor='center')
        self.all_duplicates_tree.column('Size', width=100, minwidth=80, anchor='center')
        self.all_duplicates_tree.column('Path', width=400, minwidth=200, anchor='center')
        
        all_duplicates_scroll = ttk.Scrollbar(all_dup_container, orient=tk.VERTICAL, command=self.all_duplicates_tree.yview)
        self.all_duplicates_tree.configure(yscrollcommand=all_duplicates_scroll.set)
        
        self.all_duplicates_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        all_duplicates_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tab 2: Name Conflicts (same/similar names, different content)
        self.same_names_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.same_names_frame, text="Name Conflicts")
        
        # Add explanation for Same Names tab
        same_names_info = ttk.Label(self.same_names_frame, 
                                   text="⚠️ Shows files with identical names OR same base name with different extensions but different content - potential naming conflicts or version issues",
                                   font=('Arial', 9))
        same_names_info.pack(fill=tk.X, padx=5, pady=5)
        
        # Create container frame for treeview and scrollbar
        same_names_container = ttk.Frame(self.same_names_frame)
        same_names_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        
        self.same_names_tree = ttk.Treeview(same_names_container, columns=('Name', 'Size', 'Path'), show='tree headings', height=18)
        self.same_names_tree.heading('#0', text='Group')
        self.same_names_tree.heading('Name', text='File Name')
        self.same_names_tree.heading('Size', text='Size (bytes)')
        self.same_names_tree.heading('Path', text='Full Path')
        
        # Configure column widths
        self.same_names_tree.column('#0', width=80, minwidth=80, anchor='center')
        self.same_names_tree.column('Name', width=200, minwidth=150, anchor='center')
        self.same_names_tree.column('Size', width=100, minwidth=80, anchor='center')
        self.same_names_tree.column('Path', width=400, minwidth=200, anchor='center')
        
        same_names_scroll = ttk.Scrollbar(same_names_container, orient=tk.VERTICAL, command=self.same_names_tree.yview)
        self.same_names_tree.configure(yscrollcommand=same_names_scroll.set)
        
        self.same_names_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        same_names_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Tab 3: Similar names
        self.similar_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.similar_frame, text="Similar Names")
        
        # Add explanation for Similar Names tab
        similar_names_info = ttk.Label(self.similar_frame, 
                                      text="🔍 Shows files with similar (but not identical) names",
                                      font=('Arial', 9))
        similar_names_info.pack(fill=tk.X, padx=5, pady=5)
        
        # Create container frame for treeview and scrollbar
        similar_container = ttk.Frame(self.similar_frame)
        similar_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        
        self.similar_tree = ttk.Treeview(similar_container, columns=('File1', 'File2', 'Similarity'), show='headings', height=18)
        self.similar_tree.heading('File1', text='File 1')
        self.similar_tree.heading('File2', text='File 2')
        self.similar_tree.heading('Similarity', text='Similarity %')
        
        # Configure column widths
        self.similar_tree.column('File1', width=300, minwidth=200, anchor='center')
        self.similar_tree.column('File2', width=300, minwidth=200, anchor='center')
        self.similar_tree.column('Similarity', width=100, minwidth=80, anchor='center')
        
        similar_scroll = ttk.Scrollbar(similar_container, orient=tk.VERTICAL, command=self.similar_tree.yview)
        self.similar_tree.configure(yscrollcommand=similar_scroll.set)
        
        self.similar_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        similar_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Status bar at the bottom - REMOVED (duplicate display)
        # Only keep version info
        version_frame = ttk.Frame(main_frame)
        version_frame.grid(row=8, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Version info on the right
        version_label = ttk.Label(version_frame, text="v2.0 - Sun Valley Theme", 
                                 font=('Arial', 8))
        version_label.pack(side=tk.RIGHT)
        
    def update_threshold_label(self, value):
        """Update the threshold label when scale changes"""
        self.threshold_label.config(text=f"{float(value):.1f}%")
        
    def update_method_explanation(self, event=None):
        """Update the method explanation when similarity method changes"""
        display_name = self.similarity_method.get()
        # Convert display name to internal method name
        method = self.method_display_names.get(display_name, 'ratio')
        
        explanations = {
            'ratio': "Basic Levenshtein distance - fastest method. Good for: simple typos, character differences. Example: 'document.txt' vs 'documnet.txt'",
            'partial_ratio': "Best substring match - finds common parts. Good for: version numbers, prefixes/suffixes. Example: 'report_v1.pdf' vs 'final_report_v1_backup.pdf'",
            'token_sort_ratio': "Sorts words before comparing - ignores word order. Good for: rearranged words. Example: 'final report.doc' vs 'report final.doc'",
            'token_set_ratio': "Set-based word comparison - handles duplicates and different word counts. Good for: complex variations. Example: 'data analysis report.xlsx' vs 'report data analysis final.xlsx'",
            'sequence_matcher': "Python's difflib algorithm - most precise character-level matching. Good for: complex cases, highest accuracy (slower)"
        }
        
        explanation = explanations.get(method, "Select a similarity method")
        self.method_explanation.config(text=explanation)
        
    def on_method_selected(self, event=None):
        """Handle method selection and remove focus from combobox"""
        # Update the explanation
        self.update_method_explanation(event)
        
        # Remove focus from the combobox to clear the blue highlight
        self.method_combo.selection_clear()
        self.root.focus()  # Move focus to the main window
        
    def show_method_help(self):
        """Show detailed help about similarity methods"""
        help_text = """
══════════════════════════════════════════════════════
                                                                                    FILE SIMILARITY FINDER
                                                                                        COMPLETE GUIDE
══════════════════════════════════════════════════════

📊 OVERVIEW
──────────────────────────────────────────────────────
This application helps you find and manage duplicate files, naming conflicts, 
and similar files across your directories using advanced algorithms and 
multiprocessing for optimal performance.

🗂️ RESULTS TABS EXPLAINED
──────────────────────────────────────────────────────

📁 CONTENT DUPLICATES
• Shows ALL files with identical content (true duplicates)
• Includes files with same OR different names
• These are safe to delete (keep one copy, delete the rest)
• Best for: Complete cleanup, finding all redundant files
• Example: 'photo.jpg' and 'vacation_pic.jpg' with identical content

⚠️ NAME CONFLICTS
• Shows files with identical names OR same base name with different extensions 
  but different content
• These are NOT duplicates - they have different content
• Indicates naming conflicts or version issues
• Best for: Finding version conflicts, naming problems, format duplicates
• Examples:
  - 'config.txt' in different folders with different settings
  - 'document.pdf' vs 'document.docx' with different content
  - 'archive.zip' vs 'archive.7z' with different files inside

🔍 SIMILAR NAMES
• Shows files with similar (but not identical) names
• Uses fuzzy matching based on your similarity threshold
• Best for: Finding potentially related files, typos in names
• Example: 'report_final.doc' vs 'report_finale.doc' (95% similar)

⚙️ SIMILARITY METHODS GUIDE
──────────────────────────────────────────────────────

⚡ BASIC SIMILARITY (FASTEST) - Recommended for most cases
Algorithm: Levenshtein distance
Speed: ★★★★★ (Fastest)
Accuracy: ★★★☆☆
Best for: Simple typos, character differences
Example: 'document.txt' ↔ 'documnet.txt' (90% match)

🎯 PARTIAL MATCH
Algorithm: Best substring matching
Speed: ★★★★☆
Accuracy: ★★★★☆
Best for: Files with version numbers, prefixes/suffixes
Example: 'report_v1.pdf' ↔ 'final_report_v1_backup.pdf' (85% match)

🔄 WORD ORDER INDEPENDENT
Algorithm: Token sort ratio (alphabetical word sorting)
Speed: ★★★☆☆
Accuracy: ★★★★☆
Best for: Rearranged words, different word order
Example: 'final report.doc' ↔ 'report final.doc' (100% match)

🧠 ADVANCED WORD MATCHING
Algorithm: Set-based word comparison
Speed: ★★☆☆☆
Accuracy: ★★★★★
Best for: Complex filename variations, different word counts
Example: 'data analysis report.xlsx' ↔ 'report data analysis final.xlsx' (90% match)

🎯 PRECISE CHARACTER MATCH
Algorithm: Python's difflib (sequence matcher)
Speed: ★☆☆☆☆ (Slowest)
Accuracy: ★★★★★ (Highest)
Best for: Complex cases requiring maximum precision
Example: Most accurate character-level matching for edge cases

🚀 PERFORMANCE TIPS
──────────────────────────────────────────────────────
• Use "Basic Similarity" for most cases - it's fast and effective
• Increase worker processes for large directories (more CPU cores = faster)
• xxHash provides 4x faster file hashing than SHA-256 (install: pip install xxhash)
• Lower similarity thresholds find more matches but may include false positives
• Higher thresholds are more precise but may miss some similar files
• Recursive scanning includes subdirectories but takes longer

💡 WORKFLOW RECOMMENDATIONS
──────────────────────────────────────────────────────
1. Start with "Content Duplicates" tab - these are safe to delete
2. Review "Name Conflicts" tab for potential issues to resolve
3. Use "Similar Names" tab to find related files or typos
4. Export reports for documentation and future reference

🔧 TECHNICAL DETAILS
──────────────────────────────────────────────────────
• File comparison uses xxHash (fast) or SHA-256 (fallback) for content verification
• xxHash provides 4.1x average speedup over SHA-256 with zero collision risk
• Multiprocessing provides 2-8x performance improvement on multi-core systems
• All similarity methods ignore file extensions for name comparison
• Progress tracking shows real-time file processing status with hash type indicator
        """
        
        # Create help window with modern styling
        help_window = tk.Toplevel(self.root)
        help_window.title("File Similarity Finder - Complete Guide")
        help_window.geometry("900x700")
        help_window.configure(bg='#f0f0f0')
        
        # Set icon for help window
        try:
            if hasattr(self, 'medium_icon_photo'):
                help_window.iconphoto(True, self.medium_icon_photo)
        except:
            pass
        
        # Make window modal and center it
        help_window.transient(self.root)
        help_window.grab_set()
        help_window.geometry("+%d+%d" % (self.root.winfo_rootx() + 50, self.root.winfo_rooty() + 50))
        
        # Create main container with padding
        main_container = ttk.Frame(help_window, padding="20")
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Create scrolled text widget with modern styling
        text_widget = scrolledtext.ScrolledText(
            main_container, 
            wrap=tk.WORD, 
            width=85, 
            height=35,
            font=('Segoe UI', 11),  # Changed from Consolas to Segoe UI for better readability
            bg='#ffffff',
            fg='#333333',
            selectbackground='#0078d4',
            selectforeground='white',
            relief='flat',
            borderwidth=1
        )
        text_widget.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        text_widget.insert(tk.END, help_text)
        text_widget.config(state=tk.DISABLED)  # Make read-only
        
        # Create button frame with modern styling
        button_frame = ttk.Frame(main_container)
        button_frame.pack(fill=tk.X)
        
        # Close button with modern styling
        close_button = ttk.Button(
            button_frame, 
            text="✕ Close", 
            command=help_window.destroy,
            width=12
        )
        close_button.pack(side=tk.RIGHT)
        self.add_regular_button_hover(close_button, "button")
        
    def create_custom_title_bar(self, parent):
        """Create a custom title bar with icon, title, and window controls"""
        title_bar = ttk.Frame(parent, style='TitleBar.TFrame')
        title_bar.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=0)
        title_bar.columnconfigure(1, weight=1)  # Middle section expands
        
        # Left section: Icon and title
        left_section = ttk.Frame(title_bar)
        left_section.grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        
        # Add icon if available
        if hasattr(self, 'medium_icon_photo'):
            icon_label = ttk.Label(left_section, image=self.medium_icon_photo)
            icon_label.pack(side=tk.LEFT, padx=(0, 8))
        
        # Title text (larger)
        title_label = ttk.Label(left_section, text="File Similarity Finder", 
                               font=('Arial', 14, 'bold'))
        title_label.pack(side=tk.LEFT)
        
        # Make title bar draggable
        title_bar.bind('<Button-1>', self.start_drag)
        title_bar.bind('<B1-Motion>', self.drag_window)
        left_section.bind('<Button-1>', self.start_drag)
        left_section.bind('<B1-Motion>', self.drag_window)
        title_label.bind('<Button-1>', self.start_drag)
        title_label.bind('<B1-Motion>', self.drag_window)
        if hasattr(self, 'medium_icon_photo'):
            icon_label.bind('<Button-1>', self.start_drag)
            icon_label.bind('<B1-Motion>', self.drag_window)
        
        # Right section: Window controls
        controls_frame = ttk.Frame(title_bar)
        controls_frame.grid(row=0, column=2, sticky=tk.E, padx=5, pady=2)
        
        # Minimize button
        minimize_btn = ttk.Button(controls_frame, text="−", width=4, 
                                 command=self.minimize_window)
        minimize_btn.pack(side=tk.LEFT, padx=2, pady=2)
        self.add_button_hover_effect(minimize_btn, "minimize")
        
        # Maximize/Restore button
        self.maximize_btn = ttk.Button(controls_frame, text="□", width=4, 
                                      command=self.toggle_maximize)
        self.maximize_btn.pack(side=tk.LEFT, padx=2, pady=2)
        self.add_button_hover_effect(self.maximize_btn, "maximize")
        
        # Close button
        close_btn = ttk.Button(controls_frame, text="✕", width=4, 
                              command=self.close_window)
        close_btn.pack(side=tk.LEFT, padx=2, pady=2)
        self.add_button_hover_effect(close_btn, "close")
        
        # Store window state
        self.is_maximized = False
        self.normal_geometry = f"{self.window_width}x{self.window_height}+{self.center_x}+{self.center_y}"  # Store centered geometry
        
    def add_button_hover_effect(self, button, button_type):
        """Add hover effects to window control buttons"""
        def on_enter(event):
            if button_type == "close":
                # Red hover for close button
                button.configure(style='CloseHover.TButton')
            elif button_type == "minimize":
                # Dark gray hover for minimize
                button.configure(style='MinimizeHover.TButton')
            else:  # maximize
                # Dark gray hover for maximize
                button.configure(style='MaximizeHover.TButton')
                
        def on_leave(event):
            # Return to normal style
            button.configure(style='TButton')
            
        # Bind hover events
        button.bind('<Enter>', on_enter)
        button.bind('<Leave>', on_leave)
        
        # Configure custom styles with high visibility
        style = ttk.Style()
        
        # Get current theme colors
        current_theme = sv_ttk.get_theme()
        if current_theme == "dark":
            # Dark mode - much more visible colors
            minimize_hover_bg = "#606060"  # Much lighter gray
            maximize_hover_bg = "#606060"  # Much lighter gray
            close_hover_bg = "#e74c3c"     # Bright red
            text_color = "white"
        else:
            # Light mode - high contrast colors (darker for better visibility)
            minimize_hover_bg = "#909090"  # Even darker gray for better contrast
            maximize_hover_bg = "#909090"  # Even darker gray for better contrast  
            close_hover_bg = "#c82333"     # Even darker red for better visibility
            text_color = "white"
            button_hover_bg = "#0078d4"    # Windows blue
            button_hover_fg = "white"
            
        # Configure hover styles with enhanced visibility
        style.configure('CloseHover.TButton', 
                       background=close_hover_bg, 
                       foreground="white",
                       relief="flat",
                       borderwidth=0,
                       focuscolor="none")
        style.configure('MinimizeHover.TButton', 
                       background=minimize_hover_bg, 
                       foreground=text_color,
                       relief="flat",
                       borderwidth=0,
                       focuscolor="none")
        style.configure('MaximizeHover.TButton', 
                       background=maximize_hover_bg, 
                       foreground=text_color,
                       relief="flat",
                       borderwidth=0,
                       focuscolor="none")
        
    def add_regular_button_hover(self, button, button_type):
        """Add hover effects to regular buttons throughout the app"""
        def on_enter(event):
            if button_type == "action":
                button.configure(style='ActionHover.TButton')
            elif button_type == "export":
                button.configure(style='ExportHover.TButton')
            elif button_type == "clear":
                button.configure(style='ClearHover.TButton')
            elif button_type == "help":
                button.configure(style='HelpHover.TButton')
            elif button_type == "theme":
                button.configure(style='ThemeHover.TButton')
            else:  # default button
                button.configure(style='ButtonHover.TButton')
                
        def on_leave(event):
            # Return to normal style
            button.configure(style='TButton')
            
        # Bind hover events
        button.bind('<Enter>', on_enter)
        button.bind('<Leave>', on_leave)
        
    def start_drag(self, event):
        """Start dragging the window"""
        if not hasattr(self, 'resizing') or not self.resizing:
            self.drag_start_x = event.x_root
            self.drag_start_y = event.y_root
        
    def drag_window(self, event):
        """Drag the window"""
        if not self.is_maximized and (not hasattr(self, 'resizing') or not self.resizing):  # Don't drag when maximized or resizing
            x = self.root.winfo_x() + (event.x_root - self.drag_start_x)
            y = self.root.winfo_y() + (event.y_root - self.drag_start_y)
            self.root.geometry(f"+{x}+{y}")
            self.drag_start_x = event.x_root
            self.drag_start_y = event.y_root
            
    def minimize_window(self):
        """Minimize the window"""
        # For overrideredirect windows, we need to hide the window
        self.root.withdraw()
        # Create a temporary window to show in taskbar
        self.create_taskbar_window()
        
    def create_taskbar_window(self):
        """Create a minimal window that appears in taskbar when minimized"""
        self.taskbar_window = tk.Toplevel()
        self.taskbar_window.title("File Similarity Finder")
        self.taskbar_window.geometry("1x1+0+0")  # Tiny window
        self.taskbar_window.attributes('-topmost', False)
        
        # Set icon for taskbar window
        if hasattr(self, 'medium_icon_photo'):
            self.taskbar_window.iconphoto(True, self.medium_icon_photo)
            
        # When taskbar window is clicked, restore main window
        self.taskbar_window.bind('<FocusIn>', self.restore_from_minimize)
        self.taskbar_window.bind('<Button-1>', self.restore_from_minimize)
        
    def restore_from_minimize(self, event=None):
        """Restore window from minimized state"""
        if hasattr(self, 'taskbar_window'):
            self.taskbar_window.destroy()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        
    def toggle_maximize(self):
        """Toggle between maximized and normal window state"""
        if self.is_maximized:
            # Restore to normal size
            self.root.geometry(self.normal_geometry)
            self.maximize_btn.config(text="□")
            self.is_maximized = False
        else:
            # Store current geometry and maximize
            self.normal_geometry = self.root.geometry()
            # Get screen dimensions
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.root.geometry(f"{screen_width}x{screen_height}+0+0")
            self.maximize_btn.config(text="❐")
            self.is_maximized = True
            
    def close_window(self):
        """Close the application"""
        self.root.quit()
        
    def setup_resize_functionality(self):
        """Set up window resize functionality"""
        # Bind mouse events for resize detection
        self.root.bind('<Motion>', self.on_mouse_motion)
        self.root.bind('<Button-1>', self.on_mouse_click)
        self.root.bind('<B1-Motion>', self.on_mouse_drag)
        self.root.bind('<ButtonRelease-1>', self.on_mouse_release)
        
    def get_resize_cursor(self, x, y):
        """Determine which resize cursor to show based on mouse position"""
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        border = self.resize_border_width
        
        # Check if mouse is near edges
        near_left = x <= border
        near_right = x >= width - border
        near_top = y <= border
        near_bottom = y >= height - border
        
        # Determine cursor type
        if near_top and near_left:
            return "top_left_corner"
        elif near_top and near_right:
            return "top_right_corner"
        elif near_bottom and near_left:
            return "bottom_left_corner"
        elif near_bottom and near_right:
            return "bottom_right_corner"
        elif near_top:
            return "top_side"
        elif near_bottom:
            return "bottom_side"
        elif near_left:
            return "left_side"
        elif near_right:
            return "right_side"
        else:
            return "arrow"
            
    def on_mouse_motion(self, event):
        """Handle mouse motion for cursor changes"""
        if not self.is_maximized:  # Don't resize when maximized
            # Don't show resize cursors in title bar area
            if event.y <= 40:
                self.root.config(cursor="arrow")
                return
                
            cursor_type = self.get_resize_cursor(event.x, event.y)
            
            # Set appropriate cursor
            cursor_map = {
                "top_left_corner": "size_nw_se",
                "top_right_corner": "size_ne_sw", 
                "bottom_left_corner": "size_ne_sw",
                "bottom_right_corner": "size_nw_se",
                "top_side": "size_ns",
                "bottom_side": "size_ns",
                "left_side": "size_we",
                "right_side": "size_we",
                "arrow": "arrow"
            }
            
            self.root.config(cursor=cursor_map.get(cursor_type, "arrow"))
            
    def on_mouse_click(self, event):
        """Handle mouse click for resize start"""
        if not self.is_maximized:
            # Check if click is in title bar area (first ~40 pixels)
            if event.y <= 40:
                self.resizing = False
                return
                
            self.resize_cursor = self.get_resize_cursor(event.x, event.y)
            if self.resize_cursor != "arrow":
                # Start resize
                self.resize_start_x = event.x_root
                self.resize_start_y = event.y_root
                self.resize_start_width = self.root.winfo_width()
                self.resize_start_height = self.root.winfo_height()
                self.resizing = True
            else:
                self.resizing = False
        else:
            self.resizing = False
            
    def on_mouse_drag(self, event):
        """Handle mouse drag for resizing"""
        if hasattr(self, 'resizing') and self.resizing and not self.is_maximized:
            dx = event.x_root - self.resize_start_x
            dy = event.y_root - self.resize_start_y
            
            new_width = self.resize_start_width
            new_height = self.resize_start_height
            new_x = self.root.winfo_x()
            new_y = self.root.winfo_y()
            
            # Calculate new dimensions based on resize direction
            if "right" in self.resize_cursor:
                new_width = max(400, self.resize_start_width + dx)
            elif "left" in self.resize_cursor:
                new_width = max(400, self.resize_start_width - dx)
                new_x = self.root.winfo_x() + dx
                
            if "bottom" in self.resize_cursor:
                new_height = max(300, self.resize_start_height + dy)
            elif "top" in self.resize_cursor:
                new_height = max(300, self.resize_start_height - dy)
                new_y = self.root.winfo_y() + dy
                
            # Apply new geometry
            self.root.geometry(f"{new_width}x{new_height}+{new_x}+{new_y}")
            
    def on_mouse_release(self, event):
        """Handle mouse release to end resize"""
        if hasattr(self, 'resizing'):
            self.resizing = False
        self.root.config(cursor="arrow")
        
    def set_application_icon(self):
        """Set the application icon for title bar and taskbar"""
        try:
            # Get the directory where the script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(script_dir, "icon.png")
            
            if os.path.exists(icon_path):
                # Load and resize the icon for different uses
                icon_image = Image.open(icon_path)
                
                # Create different sizes for different purposes
                # Small icon for title bar (16x16)
                small_icon = icon_image.resize((16, 16), Image.Resampling.LANCZOS)
                self.small_icon_photo = ImageTk.PhotoImage(small_icon)
                
                # Medium icon for taskbar (32x32)
                medium_icon = icon_image.resize((32, 32), Image.Resampling.LANCZOS)
                self.medium_icon_photo = ImageTk.PhotoImage(medium_icon)
                
                # Large icon for alt-tab (48x48)
                large_icon = icon_image.resize((48, 48), Image.Resampling.LANCZOS)
                self.large_icon_photo = ImageTk.PhotoImage(large_icon)
                
                # Set the window icon (this sets both title bar and taskbar icon)
                self.root.iconphoto(True, self.large_icon_photo, self.medium_icon_photo, self.small_icon_photo)
                
                print(f"✅ Icon loaded successfully from: {icon_path}")
            else:
                print(f"⚠️ Icon file not found: {icon_path}")
                
        except ImportError:
            print("⚠️ PIL (Pillow) not installed. Install with: pip install Pillow")
        except Exception as e:
            print(f"⚠️ Error loading icon: {e}")
        
    def toggle_theme(self):
        """Toggle between light and dark themes"""
        current = self.current_theme.get()
        if current == "light":
            sv_ttk.set_theme("dark")
            self.current_theme.set("dark")
        else:
            sv_ttk.set_theme("light")
            self.current_theme.set("light")
        
        # Refresh hover styles for new theme
        self.refresh_hover_styles()
        
    def refresh_hover_styles(self):
        """Refresh hover styles when theme changes"""
        style = ttk.Style()
        
        # Get current theme colors
        current_theme = sv_ttk.get_theme()
        if current_theme == "dark":
            # Dark mode - much more visible colors
            minimize_hover_bg = "#606060"  # Much lighter gray
            maximize_hover_bg = "#606060"  # Much lighter gray
            close_hover_bg = "#e74c3c"     # Bright red
            text_color = "white"
            button_hover_bg = "#505050"
            button_hover_fg = "white"
        else:
            # Light mode - high contrast colors (darker for better visibility)
            minimize_hover_bg = "#909090"  # Even darker gray for better contrast
            maximize_hover_bg = "#909090"  # Even darker gray for better contrast  
            close_hover_bg = "#c82333"     # Even darker red for better visibility
            text_color = "white"           # White text on dark backgrounds
            button_hover_bg = "#0078d4"    # Windows blue
            button_hover_fg = "white"
            
        # Update hover styles for title bar buttons with high visibility
        style.configure('CloseHover.TButton', 
                       background=close_hover_bg, 
                       foreground="white",
                       relief="flat",
                       borderwidth=0,
                       focuscolor="none")
        style.configure('MinimizeHover.TButton', 
                       background=minimize_hover_bg, 
                       foreground=text_color,
                       relief="flat",
                       borderwidth=0,
                       focuscolor="none")
        style.configure('MaximizeHover.TButton', 
                       background=maximize_hover_bg, 
                       foreground=text_color,
                       relief="flat",
                       borderwidth=0,
                       focuscolor="none")
                       
        # Add hover styles for regular buttons
        style.configure('ButtonHover.TButton',
                       background=button_hover_bg,
                       foreground=button_hover_fg,
                       relief="flat")
        style.configure('ActionHover.TButton',
                       background="#28a745",  # Green for action buttons
                       foreground="white",
                       relief="flat")
        style.configure('ExportHover.TButton',
                       background="#17a2b8",  # Teal for export
                       foreground="white",
                       relief="flat")
        style.configure('ClearHover.TButton',
                       background="#ffc107",  # Yellow for clear
                       foreground="white",
                       relief="flat")
        style.configure('HelpHover.TButton',
                       background="#6f42c1",  # Purple for help
                       foreground="white",
                       relief="flat")
        style.configure('ThemeHover.TButton',
                       background="#fd7e14",  # Orange for theme toggle
                       foreground="white",
                       relief="flat")
        
        # Add cancel scan button style
        style.configure('CancelScan.TButton',
                       background="#dc3545",  # Red background for cancel
                       foreground="white",
                       relief="flat")
        
        # Configure progress bar style for better visibility
        current_theme = sv_ttk.get_theme()
        if current_theme == "dark":
            progress_bg = '#0078d4'  # Blue progress
            trough_bg = '#404040'    # Dark gray background
        else:
            progress_bg = '#0078d4'  # Blue progress  
            trough_bg = '#e0e0e0'    # Light gray background
            
        style.configure('Custom.TProgressbar', 
                       background=progress_bg,
                       troughcolor=trough_bg,
                       borderwidth=0,  # Remove border
                       relief='flat',  # Flat appearance
                       lightcolor=progress_bg,
                       darkcolor=progress_bg)
        
        # Configure the progress bar layout to remove extra elements
        style.layout('Custom.TProgressbar', [
            ('Progressbar.trough', {
                'children': [('Progressbar.pbar', {'side': 'left', 'sticky': 'ns'})],
                'sticky': 'nswe'
            })
        ])
        
        # Apply the custom style to the existing progress bar if it exists
        if hasattr(self, 'progress_bar'):
            self.progress_bar.configure(style='Custom.TProgressbar')
        
    def browse_directory(self):
        """Open directory browser dialog"""
        directory = filedialog.askdirectory()
        if directory:
            self.selected_directory.set(directory)
            
    def update_progress(self, message, percentage=None):
        """Update progress bar and message"""
        self.progress_var.set(message)
        if percentage is not None:
            self.progress_bar['value'] = percentage
        self.root.update_idletasks()
        
    def start_scan(self):
        """Start the file scanning process in a separate thread"""
        if self.is_scanning:
            # If already scanning, this becomes a cancel button
            self.cancel_scan()
            return
            
        directory = self.selected_directory.get()
        if not directory:
            messagebox.showerror("Error", "Please select a directory to scan.")
            return
            
        if not os.path.exists(directory):
            messagebox.showerror("Error", "Selected directory does not exist.")
            return
            
        # Initialize finder with selected worker count
        self.finder = FileSimilarityFinder(max_workers=self.max_workers.get())
        self.finder.set_progress_callback(self.update_progress)
        self.finder.reset_cancellation()  # Reset any previous cancellation state
            
        # Update UI for scanning state
        self.is_scanning = True
        self.scan_button.config(text="❌ Cancel Scan", style='CancelScan.TButton')
        self.export_button.config(state='disabled')
        self.progress_bar['value'] = 0
        self.clear_results()
        
        # Start scanning in separate thread
        self.scan_thread = threading.Thread(target=self.perform_scan, args=(directory,))
        self.scan_thread.daemon = True
        self.scan_thread.start()
        
    def cancel_scan(self):
        """Cancel the current scan operation"""
        if self.finder and self.is_scanning:
            self.update_progress("Cancelling scan... Please wait for cleanup to complete.")
            self.finder.cancel_operation()
            
    def perform_scan(self, directory):
        """Perform the actual scanning (runs in separate thread)"""
        try:
            # Scan directory
            self.finder.scan_directory(directory, self.recursive_scan.get())
            
            # Find ALL duplicates
            self.root.after(0, self.update_progress, "Finding all duplicate files...")
            all_duplicates = self.finder.find_all_duplicates()
            
            # Find same names, different content
            self.root.after(0, self.update_progress, "Finding same names with different content...")
            same_name_groups = self.finder.find_same_names_different_content()
            
            # Find similar names
            self.root.after(0, self.update_progress, "Finding similar names...")
            # Convert display name to internal method name
            display_name = self.similarity_method.get()
            internal_method = self.method_display_names.get(display_name, 'ratio')
            similar_pairs = self.finder.find_similar_names(
                self.similarity_threshold.get(), 
                internal_method
            )
            
            # Update UI with results
            self.root.after(0, self.display_results, all_duplicates, same_name_groups, similar_pairs)
            
        except InterruptedError as e:
            # Handle cancellation gracefully
            self.root.after(0, self.update_progress, "Scan cancelled by user.")
            self.root.after(0, self.clear_results)
        except Exception as e:
            self.root.after(0, messagebox.showerror, "Error", f"An error occurred during scanning: {str(e)}")
        finally:
            self.root.after(0, self.scan_complete)
            
    def display_results(self, all_duplicates, same_name_groups, similar_pairs):
        """Display results in the GUI"""
        # Clear previous results
        self.clear_results()
        
        # Display ALL duplicates
        for i, group in enumerate(all_duplicates, 1):
            group_id = self.all_duplicates_tree.insert('', 'end', text=f'Group {i}', open=True)
            for file_path in group:
                info = self.finder.get_file_info(file_path)
                self.all_duplicates_tree.insert(group_id, 'end', text='', 
                                               values=(info['name'], info['size'], file_path))
        
        # Display same names, different content
        for i, group in enumerate(same_name_groups, 1):
            group_id = self.same_names_tree.insert('', 'end', text=f'Group {i}', open=True)
            for file_path in group:
                info = self.finder.get_file_info(file_path)
                self.same_names_tree.insert(group_id, 'end', text='', 
                                          values=(info['name'], info['size'], file_path))
        
        # Display similar names
        for file1, file2, similarity in similar_pairs:
            name1 = os.path.basename(file1)
            name2 = os.path.basename(file2)
            self.similar_tree.insert('', 'end', values=(name1, name2, f"{similarity:.1f}%"))
        
        # Update progress
        total_files = len(self.finder.all_files)
        workers_used = self.finder.max_workers
        self.update_progress(f"Scan complete! Found {total_files} files using {workers_used} workers. "
                           f"All duplicates: {len(all_duplicates)} groups, "
                           f"Same names diff content: {len(same_name_groups)} groups, "
                           f"Similar: {len(similar_pairs)} pairs")
        
    def scan_complete(self):
        """Re-enable controls after scan completion"""
        self.is_scanning = False
        self.scan_button.config(text="Start Scan", style='TButton')
        self.export_button.config(state='normal')
        self.progress_bar['value'] = 100
        self.scan_thread = None
        
    def export_report(self):
        """Export results with format selection dialog"""
        if not self.finder or not self.finder.all_files:
            messagebox.showwarning("Warning", "No scan results to export.")
            return
        
        # Create format selection dialog
        format_window = tk.Toplevel(self.root)
        format_window.title("Export Format Selection")
        format_window.geometry("500x750")  # Increased from 500x400 to accommodate all content
        format_window.transient(self.root)
        format_window.grab_set()
        
        # Center the dialog
        format_window.geometry("+%d+%d" % (self.root.winfo_rootx() + 75, self.root.winfo_rooty() + 50))  # Adjusted positioning
        
        # Set icon for format window
        try:
            if hasattr(self, 'medium_icon_photo'):
                format_window.iconphoto(True, self.medium_icon_photo)
        except:
            pass
        
        main_frame = ttk.Frame(format_window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="📊 Export File Similarity Report", 
                               font=('Arial', 14, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # Format selection
        format_frame = ttk.LabelFrame(main_frame, text="Export Format", padding="15")
        format_frame.pack(fill=tk.X, pady=(0, 15))
        
        export_format = tk.StringVar(value="html")
        
        formats = [
            ("html", "📄 HTML Report", "Interactive web page with sortable tables, collapsible sections, and modern styling"),
            ("json", "📋 JSON Data", "Structured data format perfect for programmatic analysis and integration"),
            ("csv", "📊 CSV Files", "Multiple CSV files for spreadsheet analysis (5 separate files created)"),
            ("txt", "📝 Text Report", "Simple text format for basic viewing and documentation")
        ]
        
        for value, label, description in formats:
            frame = ttk.Frame(format_frame)
            frame.pack(fill=tk.X, pady=8)  # Increased padding from 5 to 8
            
            radio = ttk.Radiobutton(frame, text=label, variable=export_format, value=value)
            radio.pack(anchor=tk.W)
            
            desc_label = ttk.Label(frame, text=description, font=('Arial', 9), 
                                  foreground='gray', wraplength=550)  # Increased from 400 to 550
            desc_label.pack(anchor=tk.W, padx=(20, 0), pady=(2, 0))  # Added vertical padding
        
        # Export parameters
        params_frame = ttk.LabelFrame(main_frame, text="Export Parameters", padding="15")
        params_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Include current similarity settings
        current_threshold = self.similarity_threshold.get()
        current_method_display = self.similarity_method.get()
        current_method = self.method_display_names.get(current_method_display, 'ratio')
        
        ttk.Label(params_frame, text=f"Similarity Threshold: {current_threshold:.1f}%").pack(anchor=tk.W, pady=2)
        ttk.Label(params_frame, text=f"Similarity Method: {current_method_display}").pack(anchor=tk.W, pady=2)
        ttk.Label(params_frame, text=f"Worker Processes: {self.max_workers.get()}").pack(anchor=tk.W, pady=2)
        
        # File statistics preview
        stats_frame = ttk.LabelFrame(main_frame, text="Export Preview", padding="15")
        stats_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Get quick stats
        all_duplicates = self.finder.find_all_duplicates()
        same_name_groups = self.finder.find_same_names_different_content()
        
        stats_text = f"""📁 Total Files: {len(self.finder.all_files)}
🔄 Content Duplicate Groups: {len(all_duplicates)}
⚠️ Name Conflict Groups: {len(same_name_groups)}
🔍 Similar Name Pairs: Will be calculated during export
📊 File Extensions: Will be analyzed during export
💾 Potential Space Savings: Will be calculated during export"""
        
        ttk.Label(stats_frame, text=stats_text, font=('Arial', 9)).pack(anchor=tk.W)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        def do_export():
            selected_format = export_format.get()
            
            # File dialog with appropriate extension
            extensions = {
                'html': [("HTML files", "*.html"), ("All files", "*.*")],
                'json': [("JSON files", "*.json"), ("All files", "*.*")],
                'csv': [("CSV files", "*.csv"), ("All files", "*.*")],
                'txt': [("Text files", "*.txt"), ("All files", "*.*")]
            }
            
            default_extensions = {
                'html': '.html',
                'json': '.json', 
                'csv': '.csv',
                'txt': '.txt'
            }
            
            file_path = filedialog.asksaveasfilename(
                defaultextension=default_extensions[selected_format],
                filetypes=extensions[selected_format],
                title=f"Save {selected_format.upper()} Report"
            )
            
            if file_path:
                format_window.destroy()
                
                # Show progress dialog
                progress_window = tk.Toplevel(self.root)
                progress_window.title("Exporting Report")
                progress_window.geometry("450x180")  # Increased height for cancel button
                progress_window.transient(self.root)
                progress_window.grab_set()
                progress_window.geometry("+%d+%d" % (self.root.winfo_rootx() + 150, self.root.winfo_rooty() + 150))
                
                progress_frame = ttk.Frame(progress_window, padding="20")
                progress_frame.pack(fill=tk.BOTH, expand=True)
                
                ttk.Label(progress_frame, text="Generating comprehensive report...", 
                         font=('Arial', 12)).pack(pady=(0, 10))
                
                export_progress = ttk.Progressbar(progress_frame, mode='indeterminate')
                export_progress.pack(fill=tk.X, pady=(0, 10))
                export_progress.start()
                
                status_label = ttk.Label(progress_frame, text="Analyzing files and calculating statistics...")
                status_label.pack(pady=(0, 10))
                
                # Add cancel button for export
                export_cancelled = threading.Event()
                
                def cancel_export():
                    export_cancelled.set()
                    if hasattr(self, 'finder') and self.finder:
                        self.finder.cancel_operation()
                    progress_window.destroy()
                
                cancel_export_btn = ttk.Button(progress_frame, text="❌ Cancel Export", 
                                             command=cancel_export, width=20)
                cancel_export_btn.pack()
                self.add_regular_button_hover(cancel_export_btn, "clear")
                
                def export_thread():
                    try:
                        # Check for cancellation before starting
                        if export_cancelled.is_set():
                            return
                        
                        # Update status
                        self.root.after(0, lambda: status_label.config(text="Calculating file statistics..."))
                        
                        # Reset finder cancellation state for export
                        if hasattr(self, 'finder') and self.finder:
                            self.finder.reset_cancellation()
                        
                        if selected_format == 'html':
                            result = self.finder.export_to_html(file_path, current_threshold, current_method)
                        elif selected_format == 'json':
                            result = self.finder.export_to_json(file_path, current_threshold, current_method)
                        elif selected_format == 'csv':
                            result = self.finder.export_to_csv(file_path, current_threshold, current_method)
                        else:  # txt
                            result = self.finder.generate_report(file_path)
                        
                        # Check for cancellation after export
                        if export_cancelled.is_set():
                            return
                        
                        # Close progress window and show success
                        self.root.after(0, lambda: progress_window.destroy())
                        self.root.after(0, lambda: messagebox.showinfo("Export Complete", 
                                                                      f"Report exported successfully!\n\n{result}"))
                        
                    except InterruptedError:
                        # Handle export cancellation
                        self.root.after(0, lambda: progress_window.destroy())
                        self.root.after(0, lambda: messagebox.showinfo("Export Cancelled", 
                                                                      "Export operation was cancelled by user."))
                    except Exception as e:
                        self.root.after(0, lambda: progress_window.destroy())
                        self.root.after(0, lambda: messagebox.showerror("Export Error", 
                                                                        f"Failed to export report:\n{str(e)}"))
                
                # Start export in separate thread
                export_thread_obj = threading.Thread(target=export_thread)
                export_thread_obj.daemon = True
                export_thread_obj.start()
        
        def cancel_export():
            format_window.destroy()
        
        export_btn = ttk.Button(button_frame, text="📤 Export Report", command=do_export, width=20)
        export_btn.pack(side=tk.RIGHT, padx=(5, 0))
        self.add_regular_button_hover(export_btn, "export")
        
        cancel_btn = ttk.Button(button_frame, text="❌ Cancel", command=cancel_export, width=15)
        cancel_btn.pack(side=tk.RIGHT)
        self.add_regular_button_hover(cancel_btn, "button")

    def clear_results(self):
        """Clear all result trees and reset output status"""
        for tree in [self.all_duplicates_tree, self.same_names_tree, self.similar_tree]:
            for item in tree.get_children():
                tree.delete(item)
        
        # Reset progress text and progress bar
        self.progress_var.set("Ready - Select a directory to begin scanning")
        self.progress_bar['value'] = 0

def main():
    root = tk.Tk()
    app = FileSimilarityGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main() 