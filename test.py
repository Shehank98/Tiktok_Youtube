import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import scrolledtext
import os
import threading
from pathlib import Path
from datetime import datetime, timedelta
import cv2
import numpy as np
import json
import subprocess
import shutil
import re
from queue import Queue
import time

try:
    from PIL import Image, ImageDraw, ImageFont
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ImportError as e:
    print(f"Required module: {e}")
    print("pip install pillow opencv-python google-auth-oauthlib google-api-python-client")
    exit(1)


class TikTokShortsConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("TikTok to YouTube Shorts Converter - Pro Edition")
        self.root.geometry("1400x1600")
        self.root.resizable(True, True)
        
        # Variables
        self.tiktok_input = tk.StringVar()
        self.download_count = tk.IntVar(value=5)
        self.download_folder = tk.StringVar()
        self.video_folder = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.processing = False
        self.downloading = False
        self.process_queue = Queue()
        
        # Download options
        self.remove_watermark = tk.BooleanVar(value=True)
        self.auto_convert = tk.BooleanVar(value=True)
        self.remove_source_after_convert = tk.BooleanVar(value=True)
        
        # YouTube settings
        self.youtube_enabled = tk.BooleanVar(value=False)
        self.youtube_title = tk.StringVar(value="Amazing Viral Shorts")
        self.youtube_description = tk.StringVar(value="")
        self.youtube_tags = tk.StringVar(value="shorts,viral,trending,entertainment,viralvideos,foryou,awesome,trending2024")
        self.youtube_visibility = tk.StringVar(value="public")
        self.upload_limit = tk.IntVar(value=3)
        self.upload_times = tk.StringVar(value="08:00,14:00,20:00")
        self.youtube_authenticated = False
        self.youtube_service = None
        
        # Background text/emoji
        self.top_text = tk.StringVar(value="Trending Now")
        self.bottom_text = tk.StringVar(value="Subscribe for More")
        self.top_bg_color = tk.StringVar(value="#000000")
        self.bottom_bg_color = tk.StringVar(value="#000000")
        
        # Video effects
        self.flip_horizontal = tk.BooleanVar(value=False)
        self.flip_vertical = tk.BooleanVar(value=False)
        self.quality_preset = tk.StringVar(value="standard")
        self.compress_video = tk.BooleanVar(value=True)
        self.generate_thumbnail = tk.BooleanVar(value=True)
        self.add_captions = tk.BooleanVar(value=False)
        
        # Output resolution
        self.OUTPUT_WIDTH = 1080
        self.OUTPUT_HEIGHT = 1920
        self.TOP_SECTION_HEIGHT = 384
        self.MIDDLE_SECTION_HEIGHT = 1152
        self.BOTTOM_SECTION_HEIGHT = 384
        
        self.load_settings()
        self.setup_ui()
    
    def load_settings(self):
        """Load saved settings"""
        settings_file = "converter_settings.json"
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r') as f:
                    s = json.load(f)
                    self.download_folder.set(s.get('download_folder', ''))
                    self.video_folder.set(s.get('video_folder', ''))
                    self.output_folder.set(s.get('output_folder', ''))
                    self.youtube_title.set(s.get('youtube_title', 'Amazing Viral Shorts'))
                    self.youtube_description.set(s.get('youtube_description', ''))
                    self.youtube_tags.set(s.get('youtube_tags', 'shorts,viral,trending,entertainment,viralvideos,foryou,awesome,trending2024'))
                    self.top_text.set(s.get('top_text', 'Trending Now'))
                    self.bottom_text.set(s.get('bottom_text', 'Subscribe for More'))
                    self.top_bg_color.set(s.get('top_bg_color', '#000000'))
                    self.bottom_bg_color.set(s.get('bottom_bg_color', '#000000'))
                    self.upload_limit.set(int(s.get('upload_limit', 3)))
                    self.upload_times.set(s.get('upload_times', '08:00,14:00,20:00'))
            except:
                pass
    
    def save_settings(self):
        """Save all settings"""
        settings = {
            'download_folder': self.download_folder.get(),
            'video_folder': self.video_folder.get(),
            'output_folder': self.output_folder.get(),
            'youtube_title': self.youtube_title.get(),
            'youtube_description': self.youtube_description.get(),
            'youtube_tags': self.youtube_tags.get(),
            'top_text': self.top_text.get(),
            'bottom_text': self.bottom_text.get(),
            'top_bg_color': self.top_bg_color.get(),
            'bottom_bg_color': self.bottom_bg_color.get(),
            'upload_limit': str(self.upload_limit.get()),
            'upload_times': self.upload_times.get()
        }
        with open('converter_settings.json', 'w') as f:
            json.dump(settings, f, indent=2)
        self.log("Settings saved")
    
    def setup_ui(self):
        """Setup UI"""
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Tab 1: Download
        dl_tab = ttk.Frame(notebook, padding="10")
        notebook.add(dl_tab, text="Download & Convert")
        self.setup_download_tab(dl_tab)
        
        # Tab 2: Background
        bg_tab = ttk.Frame(notebook)
        notebook.add(bg_tab, text="Backgrounds & Text")
        self.setup_background_tab(bg_tab)
        
        # Tab 3: YouTube
        yt_tab = ttk.Frame(notebook)
        notebook.add(yt_tab, text="YouTube Settings")
        self.setup_youtube_tab(yt_tab)
        
        # Tab 4: Log
        log_tab = ttk.Frame(notebook, padding="10")
        notebook.add(log_tab, text="Processing Log")
        self.setup_log_tab(log_tab)
    
    def setup_download_tab(self, parent):
        """Download tab"""
        title = ttk.Label(parent, text="Download & Convert Videos", font=("Arial", 14, "bold"))
        title.pack(pady=10)
        
        input_frame = ttk.LabelFrame(parent, text="TikTok Input", padding="10")
        input_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(input_frame, text="URL or @username:").pack(anchor=tk.W)
        ttk.Entry(input_frame, textvariable=self.tiktok_input, width=60).pack(fill=tk.X, pady=5)
        
        ttk.Label(input_frame, text="Number of videos (for @username):").pack(anchor=tk.W, pady=(10, 0))
        ttk.Spinbox(input_frame, from_=1, to=100, textvariable=self.download_count, width=10).pack(anchor=tk.W, pady=5)
        
        folder_frame = ttk.LabelFrame(parent, text="Folders", padding="10")
        folder_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(folder_frame, text="Download:").pack(anchor=tk.W)
        f1 = ttk.Frame(folder_frame)
        f1.pack(fill=tk.X, pady=3)
        ttk.Entry(f1, textvariable=self.download_folder, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(f1, text="Browse", command=self.browse_download_folder).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(folder_frame, text="Output:").pack(anchor=tk.W, pady=(10, 0))
        f2 = ttk.Frame(folder_frame)
        f2.pack(fill=tk.X, pady=3)
        ttk.Entry(f2, textvariable=self.output_folder, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(f2, text="Browse", command=self.browse_output_folder).pack(side=tk.LEFT, padx=5)
        
        opt_frame = ttk.LabelFrame(parent, text="Options", padding="10")
        opt_frame.pack(fill=tk.X, pady=10)
        
        ttk.Checkbutton(opt_frame, text="Remove watermark", variable=self.remove_watermark).pack(anchor=tk.W)
        ttk.Checkbutton(opt_frame, text="Auto-convert to Shorts", variable=self.auto_convert).pack(anchor=tk.W)
        ttk.Checkbutton(opt_frame, text="Delete source after convert", variable=self.remove_source_after_convert).pack(anchor=tk.W)
        ttk.Checkbutton(opt_frame, text="Compress video", variable=self.compress_video).pack(anchor=tk.W)
        ttk.Checkbutton(opt_frame, text="Generate thumbnail", variable=self.generate_thumbnail).pack(anchor=tk.W)
        
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=15)
        
        self.download_button = ttk.Button(btn_frame, text="DOWNLOAD FROM TIKTOK", command=self.start_download)
        self.download_button.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        self.dl_progress_var = tk.IntVar()
        self.dl_progress_bar = ttk.Progressbar(parent, variable=self.dl_progress_var, maximum=100)
        self.dl_progress_bar.pack(fill=tk.X, pady=10)
        
        self.dl_status = ttk.Label(parent, text="Ready", foreground="green", font=("Arial", 10, "bold"))
        self.dl_status.pack(fill=tk.X)
    
    def setup_background_tab(self, parent):
        """Background & Text tab"""
        canvas = tk.Canvas(parent, highlightthickness=0, bg='white')
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        title = ttk.Label(scrollable, text="Top & Bottom Backgrounds", font=("Arial", 14, "bold"))
        title.pack(pady=10)
        
        top_frame = ttk.LabelFrame(scrollable, text="Top Section", padding="10")
        top_frame.pack(fill=tk.X, pady=10, padx=10)
        
        ttk.Label(top_frame, text="Text:").pack(anchor=tk.W)
        ttk.Entry(top_frame, textvariable=self.top_text, width=40).pack(fill=tk.X, pady=5)
        ttk.Label(top_frame, text="Background Color:").pack(anchor=tk.W, pady=(10, 0))
        c1 = ttk.Frame(top_frame)
        c1.pack(fill=tk.X, pady=3)
        ttk.Entry(c1, textvariable=self.top_bg_color, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(c1, text="Pick Color", command=self.pick_top_color).pack(side=tk.LEFT, padx=5)
        
        bot_frame = ttk.LabelFrame(scrollable, text="Bottom Section", padding="10")
        bot_frame.pack(fill=tk.X, pady=10, padx=10)
        
        ttk.Label(bot_frame, text="Text:").pack(anchor=tk.W)
        ttk.Entry(bot_frame, textvariable=self.bottom_text, width=40).pack(fill=tk.X, pady=5)
        ttk.Label(bot_frame, text="Background Color:").pack(anchor=tk.W, pady=(10, 0))
        c2 = ttk.Frame(bot_frame)
        c2.pack(fill=tk.X, pady=3)
        ttk.Entry(c2, textvariable=self.bottom_bg_color, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(c2, text="Pick Color", command=self.pick_bottom_color).pack(side=tk.LEFT, padx=5)
        
        eff_frame = ttk.LabelFrame(scrollable, text="Video Effects", padding="10")
        eff_frame.pack(fill=tk.X, pady=10, padx=10)
        
        ttk.Checkbutton(eff_frame, text="Flip Horizontally", variable=self.flip_horizontal).pack(anchor=tk.W)
        ttk.Checkbutton(eff_frame, text="Flip Vertically", variable=self.flip_vertical).pack(anchor=tk.W)
        
        ttk.Label(eff_frame, text="Quality:").pack(anchor=tk.W, pady=(10, 0))
        for text, val in [("Draft", "draft"), ("Standard", "standard"), ("High", "high")]:
            ttk.Radiobutton(eff_frame, text=text, variable=self.quality_preset, value=val).pack(anchor=tk.W)
        
        process_frame = ttk.LabelFrame(scrollable, text="Process", padding="10")
        process_frame.pack(fill=tk.X, pady=10, padx=10)
        
        btn_frame = ttk.Frame(process_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.process_btn = ttk.Button(btn_frame, text="PROCESS ALL VIDEOS", command=self.process_videos)
        self.process_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        ttk.Button(btn_frame, text="Save Settings", command=self.save_settings).pack(side=tk.LEFT, padx=5)
        
        self.progress_var = tk.IntVar()
        self.progress_bar = ttk.Progressbar(process_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=10)
        
        self.status_label = ttk.Label(process_frame, text="Ready", foreground="green", font=("Arial", 10, "bold"))
        self.status_label.pack(fill=tk.X)
    
    def setup_youtube_tab(self, parent):
        """YouTube settings tab"""
        canvas = tk.Canvas(parent, highlightthickness=0, bg='white')
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        auth = ttk.LabelFrame(scrollable, text="YouTube Authentication", padding="10")
        auth.pack(fill=tk.X, pady=10, padx=10)
        
        self.auth_label = ttk.Label(auth, text="Not authenticated", foreground="red", font=("Arial", 10, "bold"))
        self.auth_label.pack(anchor=tk.W, pady=5)
        
        self.auth_btn = ttk.Button(auth, text="Login to YouTube", command=self.authenticate_youtube)
        self.auth_btn.pack(anchor=tk.W, pady=5)
        
        upload = ttk.LabelFrame(scrollable, text="Upload Settings", padding="10")
        upload.pack(fill=tk.X, pady=10, padx=10)
        
        ttk.Checkbutton(upload, text="Auto-upload to YouTube", variable=self.youtube_enabled).pack(anchor=tk.W)
        
        ttk.Label(upload, text="Title:").pack(anchor=tk.W, pady=(10, 0))
        ttk.Entry(upload, textvariable=self.youtube_title, width=60).pack(fill=tk.X, pady=5)
        
        ttk.Label(upload, text="Description:").pack(anchor=tk.W, pady=(10, 0))
        desc = tk.Text(upload, height=8, width=60)
        desc.pack(fill=tk.X, pady=5)
        self.desc_widget = desc
        default_desc = """Watch this amazing viral short that's trending everywhere!

This incredible content will keep you entertained and engaged. Don't forget to:
- LIKE the video
- SUBSCRIBE for more viral content
- COMMENT your thoughts below
- SHARE with your friends

Keywords: viral videos, trending shorts, entertainment, awesome content, viral TikTok, YouTube Shorts, trending videos 2024, must watch, entertainment videos, viral moments

Follow us for daily viral content and trending videos. Join our community of millions of viewers enjoying the best viral shorts on YouTube!

#Shorts #Viral #Trending #Entertainment #ViralVideos"""
        desc.insert("1.0", default_desc)
        
        ttk.Label(upload, text="Tags (comma separated):").pack(anchor=tk.W, pady=(10, 0))
        ttk.Entry(upload, textvariable=self.youtube_tags, width=60).pack(fill=tk.X, pady=5)
        
        sched = ttk.LabelFrame(scrollable, text="Upload Schedule", padding="10")
        sched.pack(fill=tk.X, pady=10, padx=10)
        
        ttk.Label(sched, text="Daily upload limit:").pack(anchor=tk.W)
        ttk.Spinbox(sched, from_=1, to=20, textvariable=self.upload_limit, width=5).pack(anchor=tk.W, pady=5)
        
        ttk.Label(sched, text="Upload times (HH:MM, comma separated):").pack(anchor=tk.W, pady=(10, 0))
        ttk.Entry(sched, textvariable=self.upload_times, width=60).pack(fill=tk.X, pady=5)
        ttk.Label(sched, text="Example: 08:00,14:00,20:00 (UTC)", foreground="gray", font=("Arial", 9)).pack(anchor=tk.W)
        
        ttk.Label(sched, text="Visibility:").pack(anchor=tk.W, pady=(10, 0))
        for text, val in [("Public", "public"), ("Unlisted", "unlisted"), ("Private", "private")]:
            ttk.Radiobutton(sched, text=text, variable=self.youtube_visibility, value=val).pack(anchor=tk.W)
    
    def setup_log_tab(self, parent):
        """Log tab"""
        log_frame = ttk.LabelFrame(parent, text="Processing Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=40, wrap=tk.WORD, font=("Courier", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
    
    def log(self, msg):
        """Log message"""
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def browse_download_folder(self):
        folder = filedialog.askdirectory(title="Select Download Folder")
        if folder:
            self.download_folder.set(folder)
            self.log(f"Download folder: {folder}")
    
    def browse_output_folder(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_folder.set(folder)
            self.log(f"Output folder: {folder}")
    
    def pick_top_color(self):
        from tkinter import colorchooser
        color = colorchooser.askcolor(color=self.top_bg_color.get(), title="Top Color")
        if color[1]:
            self.top_bg_color.set(color[1])
    
    def pick_bottom_color(self):
        from tkinter import colorchooser
        color = colorchooser.askcolor(color=self.bottom_bg_color.get(), title="Bottom Color")
        if color[1]:
            self.bottom_bg_color.set(color[1])
    
    def start_download(self):
        """Start download"""
        if self.downloading or self.processing:
            messagebox.showwarning("Busy", "Already processing")
            return
        
        if not self.tiktok_input.get():
            messagebox.showerror("Error", "Enter TikTok URL or @username")
            return
        
        if not self.download_folder.get():
            messagebox.showerror("Error", "Select download folder")
            return
        
        self.downloading = True
        self.download_button.config(state=tk.DISABLED)
        thread = threading.Thread(target=self.download_thread, daemon=True)
        thread.start()
    
    def download_thread(self):
        """Download thread"""
        try:
            self.log("\nStarting TikTok download...")
            self.dl_status.config(text="Downloading", foreground="orange")
            
            tiktok_input = self.tiktok_input.get().strip()
            
            try:
                subprocess.run(['yt-dlp', '--version'], capture_output=True, timeout=5)
            except FileNotFoundError:
                raise Exception("yt-dlp not installed. Install with: pip install yt-dlp")
            
            url = f"https://www.tiktok.com/{tiktok_input}" if tiktok_input.startswith('@') else tiktok_input
            
            output_template = os.path.join(self.download_folder.get(), "%(title)s.%(ext)s")
            
            cmd = ['yt-dlp', '-f', 'best[ext=mp4]', '-o', output_template, '--no-warnings', '-q']
            
            if tiktok_input.startswith('@'):
                count = self.download_count.get()
                cmd.extend(['-I', f'1:{count}'])
            
            cmd.append(url)
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                self.log(f"Download error: {result.stderr}")
                raise Exception("Download failed")
            
            self.log("Download complete")
            
            downloaded = []
            for f in os.listdir(self.download_folder.get()):
                if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                    path = os.path.join(self.download_folder.get(), f)
                    if time.time() - os.path.getmtime(path) < 3600:
                        downloaded.append(path)
            
            if not downloaded:
                raise Exception("No videos downloaded")
            
            self.log(f"Downloaded {len(downloaded)} video(s)")
            
            # Rename videos to simple names (video_1.mp4, video_2.mp4, etc)
            self.log("Renaming videos to simple format...")
            renamed_videos = []
            for idx, video_path in enumerate(sorted(downloaded), 1):
                new_name = os.path.join(self.download_folder.get(), f"video_{idx}.mp4")
                try:
                    if os.path.exists(new_name):
                        os.remove(new_name)
                    os.rename(video_path, new_name)
                    renamed_videos.append(new_name)
                    self.log(f"  Renamed to: video_{idx}.mp4")
                except Exception as e:
                    self.log(f"  Rename error: {str(e)}")
                    renamed_videos.append(video_path)
            
            if self.remove_watermark.get():
                self.log("Removing watermarks...")
                for v in renamed_videos:
                    self.remove_tiktok_watermark(v)
            
            if self.auto_convert.get():
                self.log("Converting to Shorts...")
                self.video_folder.set(self.download_folder.get())
                
                if not self.output_folder.get():
                    out_dir = os.path.join(self.download_folder.get(), "output_shorts")
                    os.makedirs(out_dir, exist_ok=True)
                    self.output_folder.set(out_dir)
                
                videos = [os.path.join(self.download_folder.get(), f) 
                         for f in os.listdir(self.download_folder.get())
                         if f.lower().startswith('video_') and f.lower().endswith('.mp4')]
                
                if videos:
                    self.process_thread(sorted(videos))
            
            self.dl_status.config(text="Ready", foreground="green")
            messagebox.showinfo("Success", "Download complete!")
        
        except Exception as e:
            self.log(f"Error: {str(e)}")
            self.dl_status.config(text="Error", foreground="red")
            messagebox.showerror("Error", str(e))
        
        finally:
            self.downloading = False
            self.download_button.config(state=tk.NORMAL)
    
    def remove_tiktok_watermark(self, video_path):
        """Remove watermark"""
        try:
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                return
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            crop_height = int(height * 0.92)
            out_path = video_path + "_no_wm.mp4"
            
            fourcc = cv2.VideoWriter_fourcc(*'avc1')
            out = cv2.VideoWriter(out_path, fourcc, fps, (width, crop_height))
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                out.write(frame[:crop_height, :])
            
            cap.release()
            out.release()
            
            os.remove(video_path)
            os.rename(out_path, video_path)
            
            self.log("  Watermark removed")
        
        except Exception as e:
            self.log(f"  Watermark removal skipped: {str(e)}")
    
    def process_videos(self):
        """Process videos"""
        if self.processing or self.downloading:
            messagebox.showwarning("Busy", "Already processing")
            return
        
        if not self.output_folder.get() or not os.path.exists(self.output_folder.get()):
            messagebox.showerror("Error", "Select valid output folder")
            return
        
        if not self.video_folder.get() or not os.path.exists(self.video_folder.get()):
            messagebox.showerror("Error", "Select valid video folder")
            return
        
        videos = [os.path.join(self.video_folder.get(), f) 
                 for f in os.listdir(self.video_folder.get())
                 if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))]
        
        if not videos:
            messagebox.showerror("Error", "No videos found")
            return
        
        self.log(f"\nProcessing {len(videos)} video(s)...")
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        thread = threading.Thread(target=self.process_thread, args=(sorted(videos),), daemon=True)
        thread.start()
    
    def process_thread(self, videos):
        """Process videos"""
        try:
            total = len(videos)
            
            for idx, video in enumerate(videos):
                if not self.processing:
                    break
                
                self.status_label.config(text=f"Processing {idx+1}/{total}", foreground="orange")
                self.log(f"\n[{idx+1}/{total}] {os.path.basename(video)}")
                
                try:
                    self.convert_video(video)
                    self.log("Conversion complete")
                    
                    if self.youtube_enabled.get() and self.youtube_authenticated:
                        out_file = os.path.join(self.output_folder.get(), 
                                               f"shorts_{os.path.splitext(os.path.basename(video))[0]}.mp4")
                        if os.path.exists(out_file):
                            self.upload_to_youtube(out_file)
                    
                    if self.remove_source_after_convert.get():
                        try:
                            os.remove(video)
                            self.log("Source removed")
                        except:
                            pass
                
                except Exception as e:
                    self.log(f"Error: {str(e)}")
                
                self.progress_var.set(int((idx + 1) / total * 100))
            
            self.status_label.config(text="Complete!", foreground="green")
            self.log(f"\nAll done! {total} video(s) processed")
            messagebox.showinfo("Success", f"Processed {total} video(s)!")
        
        except Exception as e:
            self.status_label.config(text="Error", foreground="red")
            self.log(f"Fatal: {str(e)}")
            messagebox.showerror("Error", str(e))
        
        finally:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            self.progress_var.set(0)
    
    def create_bg_with_text(self, hex_color, size, text):
        """Create background with text (with emoji support)"""
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        rgb = (r, g, b)
        
        # Create image using PIL for emoji support
        img_pil = Image.new('RGB', size, rgb)
        draw = ImageDraw.Draw(img_pil)
        
        if text:
            try:
                # Try to use a system font that supports emoji
                font = ImageFont.truetype("arial.ttf", 80)
            except:
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
                except:
                    try:
                        font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 80)
                    except:
                        font = ImageFont.load_default()
            
            # Get text size for centering
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            x = (size[0] - text_width) // 2
            y = (size[1] - text_height) // 2
            
            # Draw text in white
            draw.text((x, y), text, fill=(255, 255, 255), font=font)
        
        # Convert PIL image back to numpy array (BGR for OpenCV)
        img_array = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        return img_array
    
    def extract_audio(self, video_path):
        """Extract audio with better error handling"""
        try:
            audio_path = video_path.replace('.mp4', '_audio.aac')
            
            # Check if input video exists
            if not os.path.exists(video_path):
                self.log(f"  Error: Video file not found: {video_path}")
                return None
            
            # Extract audio using ffmpeg with proper path quoting
            cmd = f'ffmpeg -i "{video_path}" -vn -acodec aac -q:a 9 "{audio_path}" -y'
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, shell=True)
            
            if result.returncode != 0:
                self.log(f"  Audio extraction error: {result.stderr[:150]}")
                return None
            
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                self.log(f"  Audio extracted ({os.path.getsize(audio_path) / 1024:.1f}KB)")
                return audio_path
            else:
                self.log(f"  Audio extraction failed (no audio in video)")
                return None
                
        except subprocess.TimeoutExpired:
            self.log(f"  Audio extraction timeout")
            return None
        except Exception as e:
            self.log(f"  Audio extraction error: {str(e)}")
            return None
    
    def add_audio_to_video(self, video_path, audio_path):
        try:
            final_path = video_path.replace(".mp4", "_final.mp4")

            cmd = (
                f'ffmpeg -y '
                f'-i "{video_path}" '
                f'-i "{audio_path}" '
                f'-map 0:v:0 -map 1:a:0 '
                f'-c:v libx264 -preset fast -pix_fmt yuv420p '
                f'-c:a aac -b:a 128k '
                f'-shortest '
                f'"{final_path}"'
            )

            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                self.log(f"  FFmpeg error: {result.stderr[:200]}")
                return False

            os.remove(video_path)
            os.rename(final_path, video_path)

            self.log("  Audio merged successfully (FFmpeg)")
            return True

        except Exception as e:
            self.log(f"  Audio merge failed: {e}")
        return False
    
    def convert_video(self, video_path):
        """Convert video"""
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise Exception("Cannot open video")
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        if fps <= 0:
            fps = 30
        
        self.log(f"  {width}x{height} @ {fps:.1f}fps")
        
        audio_path = self.extract_audio(video_path)
        
        top_img = self.create_bg_with_text(self.top_bg_color.get(), (self.OUTPUT_WIDTH, self.TOP_SECTION_HEIGHT), self.top_text.get())
        bot_img = self.create_bg_with_text(self.bottom_bg_color.get(), (self.OUTPUT_WIDTH, self.BOTTOM_SECTION_HEIGHT), self.bottom_text.get())
        
        aspect = width / height
        target_aspect = self.OUTPUT_WIDTH / self.MIDDLE_SECTION_HEIGHT
        
        if aspect > target_aspect:
            new_w = self.OUTPUT_WIDTH
            new_h = int(new_w / aspect)
        else:
            new_h = self.MIDDLE_SECTION_HEIGHT
            new_w = int(new_h * aspect)
        
        new_w = new_w if new_w % 2 == 0 else new_w - 1
        new_h = new_h if new_h % 2 == 0 else new_h - 1
        
        x_off = (self.OUTPUT_WIDTH - new_w) // 2
        y_off = (self.MIDDLE_SECTION_HEIGHT - new_h) // 2
        
        base = os.path.splitext(os.path.basename(video_path))[0]
        out_path = os.path.join(self.output_folder.get(), f"shorts_{base}.mp4")
        
        if os.path.exists(out_path):
            os.remove(out_path)
        
        crf = 28 if self.quality_preset.get() == "draft" else (24 if self.quality_preset.get() == "standard" else 20)
        
        fourcc = cv2.VideoWriter_fourcc(*'avc1')
        out = cv2.VideoWriter(out_path, fourcc, fps, (self.OUTPUT_WIDTH, self.OUTPUT_HEIGHT))
        
        if not out.isOpened():
            raise Exception("Cannot create output video")
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            if self.flip_horizontal.get():
                frame = cv2.flip(frame, 1)
            if self.flip_vertical.get():
                frame = cv2.flip(frame, 0)
            
            resized = cv2.resize(frame, (new_w, new_h))
            
            mid = np.zeros((self.MIDDLE_SECTION_HEIGHT, self.OUTPUT_WIDTH, 3), dtype=np.uint8)
            mid[y_off:y_off+new_h, x_off:x_off+new_w] = resized
            
            final = np.vstack([top_img, mid, bot_img])
            out.write(final)
        
        cap.release()
        out.release()
        
        if audio_path and os.path.exists(audio_path):
            self.log("  Adding audio...")
            self.add_audio_to_video(out_path, audio_path)
            try:
                os.remove(audio_path)
            except:
                pass
        
        if not os.path.exists(out_path):
            raise Exception("Output not created")
        
        size = os.path.getsize(out_path) / 1024 / 1024
        self.log(f"  Saved {size:.1f}MB")
    
    def authenticate_youtube(self):
        """Authenticate YouTube"""
        try:
            self.log("\nAuthenticating YouTube...")
            
            SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
            
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=8080)
            
            self.youtube_service = build('youtube', 'v3', credentials=creds)
            self.youtube_authenticated = True
            
            self.auth_label.config(text="Authenticated", foreground="green")
            self.auth_btn.config(state=tk.DISABLED)
            self.log("YouTube authenticated!")
            messagebox.showinfo("Success", "YouTube authenticated!")
        
        except FileNotFoundError:
            messagebox.showerror("Error", "client_secrets.json not found")
        except Exception as e:
            self.log(f"Auth failed: {str(e)}")
            messagebox.showerror("Error", str(e))
    
    def upload_to_youtube(self, video_path):
        """Upload to YouTube"""
        if not self.youtube_authenticated:
            self.log("  Upload skipped (not authenticated)")
            return
        
        try:
            self.log("  Uploading to YouTube...")
            
            base = os.path.splitext(os.path.basename(video_path))[0]
            title = self.youtube_title.get() or base
            desc = self.desc_widget.get("1.0", tk.END).strip() or "Viral Shorts"
            tags = [t.strip() for t in self.youtube_tags.get().split(',') if t.strip()][:30]
            
            body = {
                'snippet': {
                    'title': title[:100],
                    'description': desc,
                    'tags': tags,
                    'categoryId': '24'
                },
                'status': {
                    'privacyStatus': self.youtube_visibility.get(),
                    'selfDeclaredMadeForKids': False
                }
            }
            
            media = MediaFileUpload(video_path, chunksize=5*1024*1024, resumable=True, mimetype='video/mp4')
            
            request = self.youtube_service.videos().insert(part='snippet,status', body=body, media_body=media)
            
            response = None
            while response is None:
                status, response = request.next_chunk()
            
            vid_id = response['id']
            self.log(f"  Uploaded: youtube.com/watch?v={vid_id}")
            
            uploaded_dir = os.path.join(self.output_folder.get(), "uploaded")
            os.makedirs(uploaded_dir, exist_ok=True)
            shutil.move(video_path, os.path.join(uploaded_dir, os.path.basename(video_path)))
            self.log(f"  Moved to uploaded folder")
        
        except Exception as e:
            self.log(f"  Upload failed: {str(e)}")


def main():
    root = tk.Tk()
    app = TikTokShortsConverter(root)
    root.mainloop()


if __name__ == "__main__":
    main()