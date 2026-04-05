import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
import time
import json
import subprocess
import shutil
import cv2
import numpy as np
from datetime import datetime
from queue import Queue

try:
    from PIL import Image, ImageDraw, ImageFont
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ImportError as e:
    print(f"Required module missing: {e}")
    print("pip install pillow opencv-python google-auth-oauthlib google-api-python-client")
    exit(1)

APP_WIDTH = 1280
APP_HEIGHT = 800

class TikTokShortsConverter(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("TikTok → YouTube Shorts (Auto) - Pro")
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        # Track active subprocesses (yt-dlp/ffmpeg) and cancel flag
        self.active_procs = []
        self.cancel_download = False
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Core variables
        self.tiktok_input = ctk.StringVar()
        self.download_count = ctk.IntVar(value=5)
        self.download_folder = ctk.StringVar()
        self.output_folder = ctk.StringVar()
        self.processing = False
        self.downloading = False
        self.youtube_enabled = ctk.BooleanVar(value=False)
        self.youtube_title = ctk.StringVar(value="Amazing Viral Shorts")
        self.youtube_tags = ctk.StringVar(value="shorts,viral,trending,entertainment,viralvideos,foryou,awesome,trending2024")
        self.youtube_visibility = ctk.StringVar(value="public")
        self.youtube_authenticated = False
        self.youtube_service = None

        # Text layers
        self.top_text = ctk.StringVar(value="Trending Now 🔥")
        self.bottom_text = ctk.StringVar(value="Subscribe for More ❤️")
        self.top_bg_color = ctk.StringVar(value="#000000")
        self.bottom_bg_color = ctk.StringVar(value="#000000")
        self.top_text_color = ctk.StringVar(value="#FFFFFF")
        self.bottom_text_color = ctk.StringVar(value="#FFFFFF")
        self.top_font_size = ctk.IntVar(value=80)
        self.bottom_font_size = ctk.IntVar(value=80)

        # Effects
        self.flip_horizontal = ctk.BooleanVar(value=False)
        self.flip_vertical = ctk.BooleanVar(value=False)
        self.quality_preset = ctk.StringVar(value="standard")

        # Resolution constants (Shorts)
        self.OUTPUT_WIDTH = 1080
        self.OUTPUT_HEIGHT = 1920
        self.TOP_SECTION_HEIGHT = 384
        self.MIDDLE_SECTION_HEIGHT = 1152
        self.BOTTOM_SECTION_HEIGHT = 384

        self.process_queue = Queue()

        self.load_settings()
        self.build_ui()

    # -------- Settings --------
    def load_settings(self):
        if os.path.exists("converter_settings.json"):
            try:
                with open("converter_settings.json", "r") as f:
                    s = json.load(f)
                    self.download_folder.set(s.get("download_folder", ""))
                    self.output_folder.set(s.get("output_folder", ""))
                    self.youtube_title.set(s.get("youtube_title", "Amazing Viral Shorts"))
                    self.youtube_tags.set(s.get("youtube_tags", "shorts,viral,trending"))
                    self.top_text.set(s.get("top_text", "Trending Now 🔥"))
                    self.bottom_text.set(s.get("bottom_text", "Subscribe for More ❤️"))
                    self.top_bg_color.set(s.get("top_bg_color", "#000000"))
                    self.bottom_bg_color.set(s.get("bottom_bg_color", "#000000"))
                    self.top_text_color.set(s.get("top_text_color", "#FFFFFF"))
                    self.bottom_text_color.set(s.get("bottom_text_color", "#FFFFFF"))
                    self.top_font_size.set(int(s.get("top_font_size", 80)))
                    self.bottom_font_size.set(int(s.get("bottom_font_size", 80)))
            except:
                pass

    def save_settings(self):
        s = {
            "download_folder": self.download_folder.get(),
            "output_folder": self.output_folder.get(),
            "youtube_title": self.youtube_title.get(),
            "youtube_tags": self.youtube_tags.get(),
            "top_text": self.top_text.get(),
            "bottom_text": self.bottom_text.get(),
            "top_bg_color": self.top_bg_color.get(),
            "bottom_bg_color": self.bottom_bg_color.get(),
            "top_text_color": self.top_text_color.get(),
            "bottom_text_color": self.bottom_text_color.get(),
            "top_font_size": self.top_font_size.get(),
            "bottom_font_size": self.bottom_font_size.get(),
        }
        with open("converter_settings.json", "w") as f:
            json.dump(s, f, indent=2)
        self.log("Settings saved.")

    # -------- UI --------
    def build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        tabs = ctk.CTkTabview(self)
        tabs.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        tabs.add("Pipeline")
        tabs.add("Text & Style")
        tabs.add("YouTube")
        tabs.add("Log")

        self.build_pipeline_tab(tabs.tab("Pipeline"))
        self.build_style_tab(tabs.tab("Text & Style"))
        self.build_youtube_tab(tabs.tab("YouTube"))
        self.build_log_tab(tabs.tab("Log"))

    def build_pipeline_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)

        # Left panel
        left = ctk.CTkFrame(parent, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="TikTok URL or @username", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w", pady=(0,4))
        ctk.CTkEntry(left, textvariable=self.tiktok_input, placeholder_text="https://www.tiktok.com/...", height=36).grid(row=1, column=0, sticky="ew", pady=4)
        ctk.CTkLabel(left, text="If @username, how many recent videos?").grid(row=2, column=0, sticky="w", pady=(6,0))
        ctk.CTkSlider(left, from_=1, to=50, number_of_steps=49, variable=self.download_count).grid(row=3, column=0, sticky="ew", pady=4)
        self.dl_count_label = ctk.CTkLabel(left, text="Count: 5")
        self.dl_count_label.grid(row=4, column=0, sticky="w")
        self.download_count.trace_add("write", lambda *_: self.dl_count_label.configure(text=f"Count: {self.download_count.get()}"))

        folder_frame = ctk.CTkFrame(left)
        folder_frame.grid(row=5, column=0, sticky="ew", pady=10)
        folder_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(folder_frame, text="Download Folder").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(folder_frame, textvariable=self.download_folder, height=32).grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkButton(folder_frame, text="Browse", command=self.pick_download_folder, width=80).grid(row=0, column=2, padx=4)
        ctk.CTkLabel(folder_frame, text="Output Folder").grid(row=1, column=0, sticky="w", pady=(6,0))
        ctk.CTkEntry(folder_frame, textvariable=self.output_folder, height=32).grid(row=1, column=1, sticky="ew", padx=4, pady=(6,0))
        ctk.CTkButton(folder_frame, text="Browse", command=self.pick_output_folder, width=80).grid(row=1, column=2, padx=4, pady=(6,0))

        btn_frame = ctk.CTkFrame(left, fg_color="transparent")
        btn_frame.grid(row=6, column=0, sticky="ew", pady=8)
        btn_frame.grid_columnconfigure((0,1,2,3), weight=1)
        ctk.CTkButton(btn_frame, text="Download Only", command=self.start_download, height=40).grid(row=0, column=0, padx=4)
        ctk.CTkButton(btn_frame, text="Stop Download", fg_color="#d9534f", command=self.stop_download, height=40).grid(row=0, column=1, padx=4)
        ctk.CTkButton(btn_frame, text="Process Only", command=self.process_videos, height=40).grid(row=0, column=2, padx=4)
        ctk.CTkButton(btn_frame, text="Auto Run (Download → Process → Upload)", fg_color="#1f6aa5", command=self.auto_run_pipeline, height=40).grid(row=0, column=3, padx=4)

        # Right panel
        right = ctk.CTkFrame(parent, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="Download Progress").grid(row=0, column=0, sticky="w")
        self.dl_progress = ctk.CTkProgressBar(right)
        self.dl_progress.set(0)
        self.dl_progress.grid(row=1, column=0, sticky="ew", pady=(0,6))
        self.dl_status = ctk.CTkLabel(right, text="Idle", text_color="green")
        self.dl_status.grid(row=2, column=0, sticky="w", pady=(0,10))

        ctk.CTkLabel(right, text="Process Progress").grid(row=3, column=0, sticky="w")
        self.proc_progress = ctk.CTkProgressBar(right)
        self.proc_progress.set(0)
        self.proc_progress.grid(row=4, column=0, sticky="ew", pady=(0,6))
        self.proc_status = ctk.CTkLabel(right, text="Idle", text_color="green")
        self.proc_status.grid(row=5, column=0, sticky="w", pady=(0,10))

        ctk.CTkButton(right, text="Save Settings", command=self.save_settings).grid(row=6, column=0, sticky="ew", pady=6)

    def build_style_tab(self, parent):
        parent.grid_columnconfigure((0,1), weight=1)

        top = ctk.CTkFrame(parent)
        top.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text="Top Section Text").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(top, textvariable=self.top_text).grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkLabel(top, text="Top BG").grid(row=1, column=0, sticky="w", pady=4)
        ctk.CTkEntry(top, textvariable=self.top_bg_color, width=100).grid(row=1, column=1, sticky="w", padx=4, pady=4)
        ctk.CTkButton(top, text="Pick", command=lambda:self.pick_color(self.top_bg_color)).grid(row=1, column=2, padx=4)
        ctk.CTkLabel(top, text="Top Text Color").grid(row=2, column=0, sticky="w", pady=4)
        ctk.CTkEntry(top, textvariable=self.top_text_color, width=100).grid(row=2, column=1, sticky="w", padx=4, pady=4)
        ctk.CTkButton(top, text="Pick", command=lambda:self.pick_color(self.top_text_color)).grid(row=2, column=2, padx=4)
        ctk.CTkLabel(top, text="Top Font Size").grid(row=3, column=0, sticky="w", pady=4)
        ctk.CTkSlider(top, from_=30, to=150, variable=self.top_font_size).grid(row=3, column=1, sticky="ew", padx=4, pady=4)

        bottom = ctk.CTkFrame(parent)
        bottom.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        bottom.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bottom, text="Bottom Section Text").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(bottom, textvariable=self.bottom_text).grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkLabel(bottom, text="Bottom BG").grid(row=1, column=0, sticky="w", pady=4)
        ctk.CTkEntry(bottom, textvariable=self.bottom_bg_color, width=100).grid(row=1, column=1, sticky="w", padx=4, pady=4)
        ctk.CTkButton(bottom, text="Pick", command=lambda:self.pick_color(self.bottom_bg_color)).grid(row=1, column=2, padx=4)
        ctk.CTkLabel(bottom, text="Bottom Text Color").grid(row=2, column=0, sticky="w", pady=4)
        ctk.CTkEntry(bottom, textvariable=self.bottom_text_color, width=100).grid(row=2, column=1, sticky="w", padx=4, pady=4)
        ctk.CTkButton(bottom, text="Pick", command=lambda:self.pick_color(self.bottom_text_color)).grid(row=2, column=2, padx=4)
        ctk.CTkLabel(bottom, text="Bottom Font Size").grid(row=3, column=0, sticky="w", pady=4)
        ctk.CTkSlider(bottom, from_=30, to=150, variable=self.bottom_font_size).grid(row=3, column=1, sticky="ew", padx=4, pady=4)

        # Process button in Text & Style tab
        process_style_frame = ctk.CTkFrame(parent, fg_color="transparent")
        process_style_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=6)
        process_style_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(process_style_frame, text="Process (apply styles to downloaded videos)", fg_color="#1f6aa5",
                    command=self.process_videos, height=36).grid(row=0, column=0, sticky="ew", padx=4, pady=4)

        fx = ctk.CTkFrame(parent, fg_color="transparent")
        fx.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        ctk.CTkLabel(fx, text="Effects").grid(row=0, column=0, sticky="w")
        ctk.CTkCheckBox(fx, text="Flip Horizontal", variable=self.flip_horizontal).grid(row=1, column=0, sticky="w", padx=4)
        ctk.CTkCheckBox(fx, text="Flip Vertical", variable=self.flip_vertical).grid(row=1, column=1, sticky="w", padx=4)
        ctk.CTkLabel(fx, text="Quality (CRF presets)").grid(row=2, column=0, sticky="w", pady=(6,2))
        ctk.CTkSegmentedButton(fx, values=["draft","standard","high"], variable=self.quality_preset).grid(row=3, column=0, columnspan=2, sticky="w")

    def build_youtube_tab(self, parent):
        parent.grid_columnconfigure((0,1), weight=1)

        auth = ctk.CTkFrame(parent)
        auth.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.auth_label = ctk.CTkLabel(auth, text="Not authenticated", text_color="red")
        self.auth_label.grid(row=0, column=0, sticky="w", pady=4)
        ctk.CTkButton(auth, text="Login to YouTube", command=self.authenticate_youtube).grid(row=1, column=0, pady=4, sticky="w")

        up = ctk.CTkFrame(parent)
        up.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        up.grid_columnconfigure(0, weight=1)
        ctk.CTkCheckBox(up, text="Auto-upload to YouTube", variable=self.youtube_enabled).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(up, text="Title").grid(row=1, column=0, sticky="w", pady=(4,0))
        ctk.CTkEntry(up, textvariable=self.youtube_title, height=36).grid(row=2, column=0, sticky="ew", pady=4)
        ctk.CTkLabel(up, text="Tags (comma separated)").grid(row=3, column=0, sticky="w")
        ctk.CTkEntry(up, textvariable=self.youtube_tags, height=36).grid(row=4, column=0, sticky="ew", pady=4)
        ctk.CTkLabel(up, text="Visibility").grid(row=5, column=0, sticky="w", pady=(6,2))
        ctk.CTkSegmentedButton(up, values=["public","unlisted","private"], variable=self.youtube_visibility).grid(row=6, column=0, sticky="w", pady=(0,6))

        desc_frame = ctk.CTkFrame(parent)
        desc_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        desc_frame.grid_rowconfigure(1, weight=1)
        desc_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(desc_frame, text="Description").grid(row=0, column=0, sticky="w")
        self.desc_text = ctk.CTkTextbox(desc_frame, height=180)
        self.desc_text.grid(row=1, column=0, sticky="nsew")
        default_desc = """Watch this amazing viral short that's trending everywhere!

    LIKE ❤️  SUBSCRIBE 🔔  COMMENT 💬  SHARE 🔁

    Keywords: viral videos, trending shorts, entertainment, awesome content, viral TikTok, YouTube Shorts, trending videos, must watch, entertainment videos, viral moments

    #Shorts #Viral #Trending #Entertainment #ViralVideos"""
        self.desc_text.insert("1.0", default_desc)

        ctk.CTkButton(parent, text="Upload videos from Output Folder", fg_color="#1f6aa5",
                    command=self.upload_existing_from_output).grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=6)

    def build_log_tab(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        self.log_box = ctk.CTkTextbox(parent, wrap="word")
        self.log_box.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    # -------- Utility --------
    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.update_idletasks()

    def pick_color(self, var):
        import tkinter.colorchooser as cc
        color = cc.askcolor(color=var.get())
        if color and color[1]:
            var.set(color[1])

    def pick_download_folder(self):
        folder = filedialog.askdirectory(title="Select Download Folder")
        if folder:
            self.download_folder.set(folder)

    def pick_output_folder(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_folder.set(folder)

    def on_close(self):
        # terminate any running subprocesses (yt-dlp/ffmpeg)
        for p in list(self.active_procs):
            try:
                p.terminate()
            except:
                pass
        self.destroy()

    # -------- Pipeline Buttons --------
    def auto_run_pipeline(self):
        if not self.tiktok_input.get():
            messagebox.showerror("Error", "Enter TikTok URL or @username")
            return
        if not self.download_folder.get():
            messagebox.showerror("Error", "Select download folder")
            return
        if not self.output_folder.get():
            messagebox.showerror("Error", "Select output folder")
            return
        def run():
            ok = self.download_thread(auto=True)
            if not ok:
                return
            self.process_thread(auto=True)
        threading.Thread(target=run, daemon=True).start()

    def start_download(self):
        if self.downloading or self.processing:
            messagebox.showwarning("Busy", "Already processing")
            return
        if not self.tiktok_input.get():
            messagebox.showerror("Error", "Enter TikTok URL or @username")
            return
        if not self.download_folder.get():
            messagebox.showerror("Error", "Select download folder")
            return
        threading.Thread(target=self.download_thread, daemon=True).start()

    def stop_download(self):
        self.cancel_download = True
        for p in list(self.active_procs):
            try:
                p.terminate()
            except:
                pass
        self.log("Download stopped by user.")
        self.dl_status.configure(text="Stopped", text_color="red")

    def process_videos(self):
        if self.processing or self.downloading:
            messagebox.showwarning("Busy", "Already processing")
            return
        threading.Thread(target=self.process_thread, daemon=True).start()

    # -------- Download logic --------
    def download_thread(self, auto=False):
        try:
            self.downloading = True
            self.cancel_download = False
            self.dl_status.configure(text="Downloading...", text_color="orange")
            self.dl_progress.set(0)

            tiktok_input = self.tiktok_input.get().strip()
            try:
                subprocess.run(['yt-dlp', '--version'], capture_output=True, timeout=5)
            except FileNotFoundError:
                raise Exception("yt-dlp not installed. pip install yt-dlp")

            url = f"https://www.tiktok.com/{tiktok_input}" if tiktok_input.startswith('@') else tiktok_input
            output_template = os.path.join(self.download_folder.get(), "%(title)s.%(ext)s")
            cmd = ['yt-dlp', '-f', 'best[ext=mp4]', '-o', output_template, '--no-warnings', '-q']

            if tiktok_input.startswith('@'):
                count = self.download_count.get()
                cmd.extend([
                    '--playlist-start', '1',
                    '--playlist-end', str(count),
                    '--max-downloads', str(count),
                    '--break-on-existing'
                ])
            cmd.append(url)

            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.active_procs.append(proc)
            stdout, stderr = proc.communicate(timeout=900)
            self.active_procs.remove(proc)

            if self.cancel_download:
                raise Exception("Download canceled")
            if proc.returncode != 0:
                self.log(f"Download error: {stderr[:200]}")
                raise Exception("Download failed")

            self.log("Download complete.")
            downloaded = []
            for f in os.listdir(self.download_folder.get()):
                if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                    path = os.path.join(self.download_folder.get(), f)
                    if time.time() - os.path.getmtime(path) < 3600:
                        downloaded.append(path)
            if not downloaded:
                raise Exception("No videos downloaded")

            self.log(f"Downloaded {len(downloaded)} video(s)")
            self.dl_progress.set(1.0)
            self.dl_status.configure(text="Download done", text_color="green")

            # Rename
            self.log("Renaming videos...")
            for idx, video_path in enumerate(sorted(downloaded), 1):
                new_name = os.path.join(self.download_folder.get(), f"video_{idx}.mp4")
                try:
                    if os.path.exists(new_name):
                        os.remove(new_name)
                    os.rename(video_path, new_name)
                except Exception as e:
                    self.log(f"  Rename error: {e}")
            self.log("Rename complete.")
            return True
        except Exception as e:
            self.log(f"Error: {e}")
            self.dl_status.configure(text="Error", text_color="red")
            if not auto and not self.cancel_download:
                messagebox.showerror("Error", str(e))
            return False
        finally:
            self.downloading = False
            self.cancel_download = False

    # -------- Processing --------
    def process_thread(self, auto=False):
        try:
            if not self.output_folder.get() or not os.path.exists(self.output_folder.get()):
                raise Exception("Select valid output folder")
            video_folder = self.download_folder.get()
            videos = [os.path.join(video_folder, f) for f in os.listdir(video_folder)
                    if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')) and f.lower().startswith("video_")]
            if not videos:
                raise Exception("No videos found")

            self.processing = True
            self.proc_progress.set(0)
            total = len(videos)
            for idx, video in enumerate(sorted(videos), 1):
                self.proc_status.configure(text=f"Processing {idx}/{total}", text_color="orange")
                self.log(f"\n[{idx}/{total}] {os.path.basename(video)}")
                self.convert_video(video)
                self.proc_progress.set(idx/total)

                out_file = os.path.join(self.output_folder.get(), f"shorts_{os.path.splitext(os.path.basename(video))[0]}.mp4")
                if self.youtube_enabled.get() and self.youtube_authenticated and os.path.exists(out_file):
                    self.upload_to_youtube(out_file)

            self.proc_status.configure(text="Complete", text_color="green")
            self.log(f"All done! {total} video(s) processed.")
            if not auto:
                messagebox.showinfo("Success", f"Processed {total} video(s)!")
        except Exception as e:
            self.proc_status.configure(text="Error", text_color="red")
            self.log(f"Error: {e}")
            if not auto:
                messagebox.showerror("Error", str(e))
        finally:
            self.processing = False
            self.proc_progress.set(0)

    # -------- Rendering helpers --------
    def load_emoji_font(self, size=80):
        candidates = [
            "Segoe UI Emoji",
            "Apple Color Emoji",
            "NotoColorEmoji.ttf",
            "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "Arial",
        ]
        for fc in candidates:
            try:
                return ImageFont.truetype(fc, size)
            except:
                continue
        return ImageFont.load_default()

    def create_bg_with_text(self, hex_color, size, text, text_color, font_size):
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        img_pil = Image.new('RGB', size, (r, g, b))
        draw = ImageDraw.Draw(img_pil)
        if text:
            font = self.load_emoji_font(size=font_size)
            bbox = draw.textbbox((0,0), text, font=font)
            tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
            x = (size[0]-tw)//2
            y = (size[1]-th)//2
            tc = text_color.lstrip('#')
            tr, tg, tb = int(tc[0:2],16), int(tc[2:4],16), int(tc[4:6],16)
            draw.text((x,y), text, fill=(tr,tg,tb), font=font)
        return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    # -------- Audio: copy from source --------
    def merge_original_audio(self, processed_video, original_video):
        """Copy audio from original into processed video (re-encode video to H.264, copy audio)."""
        try:
            probe_cmd = (
                f'ffprobe -v error -select_streams a -show_entries stream=index '
                f'-of default=nk=1:nw=1 "{original_video}"'
            )
            probe_res = subprocess.run(probe_cmd, shell=True, capture_output=True, text=True)
            if probe_res.returncode != 0 or not probe_res.stdout.strip():
                self.log("  No audio stream in source; output will stay silent")
                return True
            final_path = processed_video.replace(".mp4", "_final.mp4")
            cmd = (
                f'ffmpeg -y -loglevel error '
                f'-i "{processed_video}" '
                f'-i "{original_video}" '
                f'-map 0:v:0 -map 1:a:0 '
                f'-c:v libx264 -pix_fmt yuv420p '
                f'-c:a copy '
                f'-movflags +faststart -shortest '
                f'"{final_path}"'
            )
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if res.returncode != 0:
                self.log(f"  Audio merge error: {res.stderr[:200]}")
                return False
            os.replace(final_path, processed_video)
            self.log("  Audio copied from original successfully")
            return True
        except Exception as e:
            self.log(f"  Audio merge failed: {e}")
            return False

    # -------- Convert video --------
    def convert_video(self, video_path):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise Exception("Cannot open video")

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or fps > 60:
            fps = 30
        fps = round(fps)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.log(f"  {width}x{height} @ {fps}fps")

        top_img = self.create_bg_with_text(
            self.top_bg_color.get(),
            (self.OUTPUT_WIDTH, self.TOP_SECTION_HEIGHT),
            self.top_text.get(),
            self.top_text_color.get(),
            self.top_font_size.get()
        )
        bot_img = self.create_bg_with_text(
            self.bottom_bg_color.get(),
            (self.OUTPUT_WIDTH, self.BOTTOM_SECTION_HEIGHT),
            self.bottom_text.get(),
            self.bottom_text_color.get(),
            self.bottom_font_size.get()
        )

        aspect = width / height
        target_aspect = self.OUTPUT_WIDTH / self.MIDDLE_SECTION_HEIGHT
        if aspect > target_aspect:
            new_w = self.OUTPUT_WIDTH
            new_h = int(new_w / aspect)
        else:
            new_h = self.MIDDLE_SECTION_HEIGHT
            new_w = int(new_h * aspect)
        if new_w % 2: new_w -= 1
        if new_h % 2: new_h -= 1
        x_off = (self.OUTPUT_WIDTH - new_w) // 2
        y_off = (self.MIDDLE_SECTION_HEIGHT - new_h) // 2

        base = os.path.splitext(os.path.basename(video_path))[0]
        out_path = os.path.join(self.output_folder.get(), f"shorts_{base}.mp4")
        if os.path.exists(out_path):
            os.remove(out_path)

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # simple codec; final H.264 via ffmpeg
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

        self.log("  Merging original audio (if present)...")
        self.merge_original_audio(out_path, video_path)

        if not os.path.exists(out_path):
            raise Exception("Output not created")
        size = os.path.getsize(out_path) / 1024 / 1024
        self.log(f"  Saved {size:.1f}MB")

    # -------- YouTube --------
    def authenticate_youtube(self):
        try:
            self.log("Authenticating YouTube...")
            SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=8080)
            self.youtube_service = build('youtube', 'v3', credentials=creds)
            self.youtube_authenticated = True
            self.auth_label.configure(text="Authenticated", text_color="green")
            self.log("YouTube authenticated.")
            messagebox.showinfo("Success", "YouTube authenticated!")
        except FileNotFoundError:
            messagebox.showerror("Error", "client_secrets.json not found")
        except Exception as e:
            self.log(f"Auth failed: {e}")
            messagebox.showerror("Error", str(e))

    def upload_to_youtube(self, video_path):
        if not self.youtube_authenticated:
            self.log("  Upload skipped (not authenticated)")
            return
        try:
            self.log(f"  Uploading {os.path.basename(video_path)}...")
            base = os.path.splitext(os.path.basename(video_path))[0]
            title = self.youtube_title.get() or base
            desc = self.desc_text.get("1.0", "end").strip() or "Auto-uploaded Shorts"
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
            self.log("  Moved to uploaded folder")
        except Exception as e:
            self.log(f"  Upload failed: {e}")

    def upload_existing_from_output(self):
        if not self.youtube_authenticated:
            messagebox.showerror("Error", "Authenticate YouTube first.")
            return
        if not self.output_folder.get() or not os.path.exists(self.output_folder.get()):
            messagebox.showerror("Error", "Select valid output folder")
            return
        videos = [os.path.join(self.output_folder.get(), f) for f in os.listdir(self.output_folder.get())
                if f.lower().endswith(".mp4") and not f.startswith("uploaded")]
        if not videos:
            messagebox.showinfo("Info", "No .mp4 files found in output folder.")
            return
        threading.Thread(target=self._upload_existing_worker, args=(videos,), daemon=True).start()

    def _upload_existing_worker(self, videos):
        for v in videos:
            self.upload_to_youtube(v)
        messagebox.showinfo("Done", f"Uploaded {len(videos)} video(s) from output folder.")

def main():
    app = TikTokShortsConverter()
    app.mainloop()

if __name__ == "__main__":
    main()