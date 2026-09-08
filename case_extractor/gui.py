"""macOS/Windows용 GUI. 터미널이 낯선 경우 이걸 실행하세요.

실행: python3 gui.py
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from case_extractor.cli import process_file
from case_extractor.excel_writer import write_rows
from case_extractor.llm_extract import LLMExtractError
from case_extractor.text_extract import TextExtractError, find_case_files
from case_extractor.validate import NotJudgmentLikelyError

BG = "#f4f5f7"
CARD_BG = "#ffffff"
ACCENT = "#2f6fed"
ACCENT_DARK = "#1f4fbf"
DANGER = "#d64545"
TEXT_MUTED = "#6b7280"
FONT_BASE = ("Helvetica", 11)
FONT_BOLD = ("Helvetica", 11, "bold")
FONT_TITLE = ("Helvetica", 16, "bold")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("판례 코딩시트 변환기")
        self.geometry("720x680")
        self.configure(bg=BG)
        self.minsize(640, 600)

        self.template_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.coder_id = tk.StringVar()
        self.api_key = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        self.selected_files: list[Path] = []

        self._stop_event = threading.Event()
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._worker: threading.Thread | None = None

        self._build_style()
        self._build_widgets()
        self.after(200, self._drain_log_queue)

    # ---------- 스타일 ----------
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("TLabel", background=BG, font=FONT_BASE)
        style.configure("Card.TLabel", background=CARD_BG, font=FONT_BASE)
        style.configure("Muted.TLabel", background=CARD_BG, font=FONT_BASE, foreground=TEXT_MUTED)
        style.configure("Title.TLabel", background=BG, font=FONT_TITLE)
        style.configure("Section.TLabel", background=CARD_BG, font=FONT_BOLD, foreground="#111827")
        style.configure("TEntry", padding=6)
        style.configure("TCheckbutton", background=CARD_BG, font=FONT_BASE)

        style.configure(
            "Accent.TButton",
            font=FONT_BOLD,
            padding=(14, 10),
            background=ACCENT,
            foreground="white",
            borderwidth=0,
        )
        style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#9db6f5")])

        style.configure(
            "Danger.TButton",
            font=FONT_BOLD,
            padding=(14, 10),
            background=DANGER,
            foreground="white",
            borderwidth=0,
        )
        style.map("Danger.TButton", background=[("active", "#b83a3a"), ("disabled", "#e6b3b3")])

        style.configure("Ghost.TButton", font=FONT_BASE, padding=(10, 6))

        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#e5e7eb",
            background=ACCENT,
            thickness=10,
        )

    def _card(self, parent) -> ttk.Frame:
        outer = ttk.Frame(parent, style="TFrame")
        card = ttk.Frame(outer, style="Card.TFrame", padding=16)
        card.pack(fill="both", expand=True)
        return outer, card

    # ---------- 위젯 구성 ----------
    def _build_widgets(self):
        root = ttk.Frame(self, style="TFrame", padding=20)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="판례 코딩시트 변환기", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            root,
            text="판결문(PDF/DOCX)을 넣으면 코딩시트 엑셀 항목을 자동으로 채워줍니다.",
            style="TLabel",
            foreground=TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 14))

        self._build_files_card(root)
        self._build_settings_card(root)
        self._build_run_card(root)
        self._build_log_card(root)

    def _build_files_card(self, parent):
        outer, card = self._card(parent)
        outer.pack(fill="x", pady=(0, 12))

        ttk.Label(card, text="1. 판결문 입력", style="Section.TLabel").pack(anchor="w", pady=(0, 8))

        btn_row = ttk.Frame(card, style="Card.TFrame")
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="📁 폴더에서 전체 선택", style="Ghost.TButton",
                   command=self._pick_input_dir).pack(side="left")
        ttk.Button(btn_row, text="📄 파일 개별 선택 (여러 개 가능)", style="Ghost.TButton",
                   command=self._pick_input_files).pack(side="left", padx=8)
        ttk.Button(btn_row, text="비우기", style="Ghost.TButton",
                   command=self._clear_files).pack(side="left")

        list_frame = ttk.Frame(card, style="Card.TFrame")
        list_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.file_listbox = tk.Listbox(
            list_frame, height=6, font=FONT_BASE, bg="#fafafa",
            selectbackground=ACCENT, relief="flat", highlightthickness=1,
            highlightbackground="#e5e7eb",
        )
        self.file_listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.file_listbox.config(yscrollcommand=scrollbar.set)

        self.file_count_label = ttk.Label(card, text="선택된 파일 없음", style="Muted.TLabel")
        self.file_count_label.pack(anchor="w", pady=(6, 0))

    def _build_settings_card(self, parent):
        outer, card = self._card(parent)
        outer.pack(fill="x", pady=(0, 12))

        ttk.Label(card, text="2. 설정", style="Section.TLabel").pack(anchor="w", pady=(0, 8))

        self._labeled_path_row(card, "코딩시트 템플릿 (xlsx)", self.template_path, self._pick_template)
        self._labeled_path_row(card, "결과 저장 위치 (xlsx)", self.output_path, self._pick_output)

        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="코딩 담당자 ID", style="Card.TLabel", width=18).pack(side="left")
        ttk.Entry(row, textvariable=self.coder_id, width=16).pack(side="left")

        row2 = ttk.Frame(card, style="Card.TFrame")
        row2.pack(fill="x", pady=(8, 0))
        ttk.Label(row2, text="Anthropic API 키", style="Card.TLabel", width=18).pack(side="left")
        ttk.Entry(row2, textvariable=self.api_key, show="*").pack(side="left", fill="x", expand=True)

    def _labeled_path_row(self, card, label, var, command):
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text=label, style="Card.TLabel", width=18).pack(side="left")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="선택", style="Ghost.TButton", command=command).pack(side="left")

    def _build_run_card(self, parent):
        row = ttk.Frame(parent, style="TFrame")
        row.pack(fill="x", pady=(4, 12))

        self.run_btn = ttk.Button(row, text="▶  변환 시작", style="Accent.TButton", command=self._start)
        self.run_btn.pack(side="left")

        self.stop_btn = ttk.Button(row, text="■  중지", style="Danger.TButton",
                                   command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=10)

        self.progress = ttk.Progressbar(row, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(10, 0))

    def _build_log_card(self, parent):
        outer, card = self._card(parent)
        outer.pack(fill="both", expand=True)

        ttk.Label(card, text="진행 상황", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.log = scrolledtext.ScrolledText(
            card, height=12, font=("Menlo", 10), bg="#0f172a", fg="#e2e8f0",
            insertbackground="#e2e8f0", relief="flat", padx=10, pady=8,
        )
        self.log.pack(fill="both", expand=True)
        self.log.tag_config("warn", foreground="#fbbf24")
        self.log.tag_config("err", foreground="#f87171")
        self.log.tag_config("ok", foreground="#4ade80")

    # ---------- 파일 선택 ----------
    def _pick_template(self):
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if path:
            self.template_path.set(path)
            if not self.output_path.get():
                p = Path(path)
                self.output_path.set(str(p.with_name(p.stem + "_결과.xlsx")))

    def _pick_input_dir(self):
        path = filedialog.askdirectory()
        if not path:
            return
        files = find_case_files(Path(path))
        if not files:
            messagebox.showwarning("알림", "선택한 폴더에서 .pdf/.docx 파일을 찾지 못했습니다.")
            return
        self._add_files(files)

    def _pick_input_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("판결문 파일", "*.pdf *.docx"), ("모든 파일", "*.*")])
        if paths:
            self._add_files([Path(p) for p in paths])

    def _add_files(self, files: list[Path]):
        existing = {str(f) for f in self.selected_files}
        for f in files:
            if str(f) not in existing:
                self.selected_files.append(f)
                existing.add(str(f))
        self._refresh_file_list()

    def _clear_files(self):
        self.selected_files = []
        self._refresh_file_list()

    def _refresh_file_list(self):
        self.file_listbox.delete(0, "end")
        for f in self.selected_files:
            self.file_listbox.insert("end", f.name)
        n = len(self.selected_files)
        self.file_count_label.config(text=f"{n}개 파일 선택됨" if n else "선택된 파일 없음")

    def _pick_output(self):
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if path:
            self.output_path.set(path)

    # ---------- 로그 ----------
    def _log(self, msg: str, tag: str | None = None):
        self._log_queue.put((msg, tag))

    def _drain_log_queue(self):
        try:
            while True:
                msg, tag = self._log_queue.get_nowait()
                self.log.insert("end", msg + "\n", tag or ())
                self.log.see("end")
        except queue.Empty:
            pass
        self.after(200, self._drain_log_queue)

    # ---------- 실행/중지 ----------
    def _start(self):
        if not self.selected_files:
            messagebox.showerror("오류", "판결문 파일을 폴더 또는 파일 선택으로 최소 1개 이상 넣어주세요.")
            return
        if not self.template_path.get() or not self.output_path.get():
            messagebox.showerror("오류", "코딩시트 템플릿과 저장 위치를 모두 선택하세요.")
            return
        if self.api_key.get():
            os.environ["ANTHROPIC_API_KEY"] = self.api_key.get()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            messagebox.showerror("오류", "Anthropic API 키를 입력하세요.")
            return

        self._stop_event.clear()
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.config(value=0, maximum=len(self.selected_files))
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _stop(self):
        self._stop_event.set()
        self.stop_btn.config(state="disabled")
        self._log("중지 요청됨. 진행 중인 파일까지만 처리하고 멈춥니다...", "warn")

    def _run(self):
        try:
            files = list(self.selected_files)
            self._log(f"총 {len(files)}개 파일 처리 시작...")
            rows = []

            for i, path in enumerate(files, start=1):
                if self._stop_event.is_set():
                    self._log(f"사용자 요청으로 중지됨 ({i-1}/{len(files)}개 처리 완료).", "warn")
                    break

                self._log(f"[{i}/{len(files)}] {path.name} 처리 중...")
                try:
                    row = process_file(path, coder_id=self.coder_id.get(), model=None)
                    rows.append(row)
                    self._log(f"  완료: {path.name}", "ok")
                except NotJudgmentLikelyError as e:
                    self._log(f"  건너뜀: {e}", "warn")
                except (TextExtractError, LLMExtractError) as e:
                    self._log(f"  실패: {e}", "err")
                finally:
                    self.progress.step(1)

            if rows:
                out = write_rows(Path(self.template_path.get()), Path(self.output_path.get()), rows)
                self._log(f"완료: {len(rows)}건을 {out} 에 저장했습니다.", "ok")
                self._log("주의: AI가 추출한 값이므로 coding_note에 [AI 추출] 표시가 된 행은 원문과 대조 검수하세요.", "warn")
            elif not self._stop_event.is_set():
                self._log("저장할 결과가 없습니다.", "warn")
        finally:
            self.run_btn.config(state="normal")
            self.stop_btn.config(state="disabled")


if __name__ == "__main__":
    App().mainloop()
