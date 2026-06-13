"""
Tkinter-based User Interface for the Google Maps Leads Scraper.

Provides:
- Keyword input field
- Location input field
- Checkbutton to enable/disable website ads scanning
- Start Scraping button (runs scraper in a background thread)
- Cancel button
- Real-time progress log (auto-scrolling text widget)
- Summary display upon completion

Runs entirely on Python's built-in `tkinter` — zero third-party GUI deps.
"""

import asyncio
import logging
import os
import sys
import threading
from datetime import datetime
from tkinter import (
    BooleanVar,
    Button,
    Checkbutton,
    END,
    Entry,
    Label,
    NORMAL,
    DISABLED,
    scrolledtext,
    Tk,
    W,
    E,
    S,
    N,
    messagebox,
)

# Ensure the project root is on sys.path for direct execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import OUTPUT_DIR
from main import run_scraper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / Colours
# ---------------------------------------------------------------------------
BG_COLOR = "#f0f4f8"
FG_COLOR = "#1a1a2e"
ACCENT_COLOR = "#1a73e8"
BTN_FG = "#ffffff"
TEXT_BG = "#ffffff"
TEXT_FG = "#1a1a2e"

WINDOW_TITLE = "Google Maps Leads Scraper"
WINDOW_SIZE = "780x680"
FONT_FAMILY = "Segoe UI"


class ScraperApp:
    """Main Tkinter application window."""

    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.resizable(True, True)
        self.root.configure(bg=BG_COLOR)

        # --- State --------------------------------------------------------
        self._is_running = False
        self._cancel_event = threading.Event()
        self._progress_log: list[str] = []
        self._scrape_thread: threading.Thread | None = None
        self._poll_after_id: str | None = None

        # --- Build UI -----------------------------------------------------
        self._build_widgets()

        # Handle window close gracefully
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ======================================================================
    # UI Construction
    # ======================================================================
    def _build_widgets(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)  # progress box stretches

        # -- Title --
        title = Label(
            self.root,
            text="🗺️ Google Maps Leads Scraper",
            font=(FONT_FAMILY, 18, "bold"),
            bg=BG_COLOR,
            fg=FG_COLOR,
            pady=12,
        )
        title.grid(row=0, column=0, sticky="ew")

        # -- Input frame --
        input_frame = self._make_frame(self.root, row=1, padx=12, pady=(0, 8))

        # Keyword row
        Label(input_frame, text="Keyword:", font=(FONT_FAMILY, 10), bg=BG_COLOR, fg=FG_COLOR)\
            .grid(row=0, column=0, sticky=W, padx=(0, 6), pady=4)

        self.keyword_entry = Entry(
            input_frame,
            font=(FONT_FAMILY, 10),
            bg=TEXT_BG,
            fg=TEXT_FG,
            relief="solid",
            bd=1,
        )
        self.keyword_entry.insert(0, "Plumber")
        self.keyword_entry.grid(row=0, column=1, sticky="ew", pady=4)
        input_frame.columnconfigure(1, weight=1)

        # Location row
        Label(input_frame, text="Location:", font=(FONT_FAMILY, 10), bg=BG_COLOR, fg=FG_COLOR)\
            .grid(row=1, column=0, sticky=W, padx=(0, 6), pady=4)

        self.location_entry = Entry(
            input_frame,
            font=(FONT_FAMILY, 10),
            bg=TEXT_BG,
            fg=TEXT_FG,
            relief="solid",
            bd=1,
        )
        self.location_entry.insert(0, "Austin, Texas")
        self.location_entry.grid(row=1, column=1, sticky="ew", pady=4)

        # Ads check
        self.ads_var = BooleanVar(value=True)
        ads_check = Checkbutton(
            input_frame,
            text="Check websites for Google Ads / FB Pixel (slower)",
            variable=self.ads_var,
            font=(FONT_FAMILY, 9),
            bg=BG_COLOR,
            fg=FG_COLOR,
            selectcolor=BG_COLOR,
            anchor=W,
        )
        ads_check.grid(row=2, column=0, columnspan=2, sticky=W, pady=(2, 4))

        # -- Button frame --
        btn_frame = self._make_frame(self.root, row=3, padx=12, pady=(0, 8))

        self.start_btn = Button(
            btn_frame,
            text="▶ Start Scraping",
            font=(FONT_FAMILY, 10, "bold"),
            bg=ACCENT_COLOR,
            fg=BTN_FG,
            relief="flat",
            bd=0,
            padx=20,
            pady=6,
            cursor="hand2",
            activebackground="#1557b0",
            command=self._start_scrape,
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        self.cancel_btn = Button(
            btn_frame,
            text="⛔ Cancel",
            font=(FONT_FAMILY, 10),
            bg="#e74c3c",
            fg=BTN_FG,
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2",
            activebackground="#c0392b",
            state=DISABLED,
            command=self._cancel_scrape,
        )
        self.cancel_btn.pack(side="left")

        # -- Progress log --
        self.progress_text = scrolledtext.ScrolledText(
            self.root,
            font=("Consolas", 9),
            bg=TEXT_BG,
            fg=TEXT_FG,
            relief="solid",
            bd=1,
            wrap="word",
            state=DISABLED,
        )
        self.progress_text.grid(row=2, column=0, sticky=N + S + E + W, padx=12, pady=(0, 8))

        # -- Summary / status bar --
        self.summary_label = Label(
            self.root,
            text="Ready. Enter keyword and location, then click Start Scraping.",
            font=(FONT_FAMILY, 9),
            bg=BG_COLOR,
            fg="#555555",
            anchor=W,
            padx=12,
            pady=4,
        )
        self.summary_label.grid(row=4, column=0, sticky="ew")

    @staticmethod
    def _make_frame(parent, row: int, padx: int, pady: int):
        """Convenience: create a labelled frame with padding."""
        frame = LabelFrame if False else None  # keep it simple

        import tkinter as tk
        f = tk.Frame(parent, bg=BG_COLOR)
        f.grid(row=row, column=0, sticky="ew", padx=padx, pady=pady)
        f.columnconfigure(1, weight=1)
        return f

    # ======================================================================
    # Logging helper
    # ======================================================================
    def _update_progress(self, msg: str) -> None:
        """Thread-safe: appends a timestamped message to the progress log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {msg}"
        self._progress_log.append(formatted)
        logger.info(msg)

    def _flush_log_to_ui(self) -> None:
        """Write all pending log lines into the ScrolledText widget."""
        if not self._progress_log:
            return
        self.progress_text.config(state=NORMAL)
        for line in self._progress_log:
            self.progress_text.insert(END, line + "\n")
        self._progress_log.clear()
        # Auto-scroll to bottom
        self.progress_text.see(END)
        self.progress_text.config(state=DISABLED)

    # ======================================================================
    # Scrape orchestration (runs in a background thread)
    # ======================================================================
    def _start_scrape(self) -> None:
        keyword = self.keyword_entry.get().strip()
        location = self.location_entry.get().strip()

        if not keyword or not location:
            messagebox.showwarning("Input Error", "Please fill in both Keyword and Location fields.")
            return

        if self._is_running:
            messagebox.showinfo("Already Running", "A scraping job is already in progress.")
            return

        # Reset state
        self._is_running = True
        self._cancel_event.clear()
        self._progress_log.clear()

        # Clear the progress text widget
        self.progress_text.config(state=NORMAL)
        self.progress_text.delete("1.0", END)
        self.progress_text.config(state=DISABLED)

        # Disable / enable buttons
        self.start_btn.config(state=DISABLED, text="⏳ Running...")
        self.cancel_btn.config(state=NORMAL)
        self.summary_label.config(text="Scraping in progress...", fg="#555555")

        self._update_progress(f"🚀 Starting scrape for keyword='{keyword}', location='{location}'")
        self._flush_log_to_ui()

        # Launch the scraper in a background thread
        self._scrape_thread = threading.Thread(
            target=self._run_scrape_worker,
            args=(keyword, location, self.ads_var.get()),
            daemon=True,
        )
        self._scrape_thread.start()

        # Start polling the thread for completion
        self._poll_thread()

    def _run_scrape_worker(self, keyword: str, location: str, ads_check: bool) -> None:
        """Runs in a background thread; calls the async scraper."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            results = loop.run_until_complete(
                run_scraper(
                    keyword=keyword,
                    location=location,
                    enable_ads_check=ads_check,
                    progress_callback=self._update_progress,
                    cancel_event=self._cancel_event,
                )
            )
            loop.close()

            if self._cancel_event.is_set():
                self._update_progress("⛔ Scraping cancelled by user.")
                self._set_summary("⛔ Scraping cancelled.", "#e74c3c")
            else:
                lead_count = len(results)
                self._update_progress(f"✅ Scraping complete! Found {lead_count} leads.")

                # Build summary
                lines = [f"✅ Scraping Complete!  |  Leads: {lead_count}"]
                if lead_count > 0:
                    ads_count = sum(
                        1 for r in results
                        if r.get("has_google_ads") or r.get("has_facebook_pixel")
                    )
                    lines.append(f"Businesses with Ads / FB Pixel: {ads_count}")
                    csv_path = os.path.join(OUTPUT_DIR, "gmaps_leads.csv")
                    if os.path.exists(csv_path):
                        lines.append(f"CSV → {csv_path}")
                    pdf_path = os.path.join(OUTPUT_DIR, "gmaps_leads.pdf")
                    if os.path.exists(pdf_path):
                        lines.append(f"PDF → {pdf_path}  (watermarked)")
                self._set_summary("  |  ".join(lines), "#27ae60")

        except Exception as e:
            logger.exception("Scraping failed")
            self._update_progress(f"❌ Fatal error: {e}")
            self._set_summary(f"❌ Error: {e}", "#e74c3c")
        finally:
            self._is_running = False
            # Schedule UI reset on the main thread
            self.root.after(0, self._reset_buttons)

    def _reset_buttons(self) -> None:
        """Re-enable the Start button, disable Cancel."""
        self.start_btn.config(state=NORMAL, text="▶ Start Scraping")
        self.cancel_btn.config(state=DISABLED)

    def _set_summary(self, text: str, colour: str = "#27ae60") -> None:
        """Thread-safe: update the summary label."""
        self.root.after(0, lambda: self.summary_label.config(text=text, fg=colour))

    # ======================================================================
    # Polling (periodic check from the main thread)
    # ======================================================================
    def _poll_thread(self) -> None:
        """Called every 400 ms via `root.after` to flush logs and check completion."""
        self._flush_log_to_ui()

        if self._is_running:
            self._poll_after_id = self.root.after(400, self._poll_thread)

    # ======================================================================
    # Cancel
    # ======================================================================
    def _cancel_scrape(self) -> None:
        """Signal cancellation to the worker thread."""
        self._cancel_event.set()
        self._update_progress("⛔ Cancellation requested...")
        self._flush_log_to_ui()

    # ======================================================================
    # Cleanup
    # ======================================================================
    def _on_close(self) -> None:
        """If a scrape is running, cancel it and wait for the thread."""
        if self._is_running:
            self._cancel_event.set()
            if self._scrape_thread and self._scrape_thread.is_alive():
                self._scrape_thread.join(timeout=3)
        if self._poll_after_id:
            self.root.after_cancel(self._poll_after_id)
        self.root.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def launch_ui() -> None:
    """Create and run the Tkinter GUI."""
    root = Tk()
    app = ScraperApp(root)
    root.mainloop()


if __name__ == "__main__":
    launch_ui()