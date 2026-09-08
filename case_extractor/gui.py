"""macOS/Windows용 GUI. 터미널이 낯선 경우 이걸 실행하세요.

실행: python3 gui.py

두 가지 탭이 있습니다:
- "API 모드": Anthropic API 키가 있을 때. 자동으로 끝까지 처리합니다.
- "수동 모드": API 키가 없을 때. claude.ai 웹 채팅에 복사/붙여넣기로 진행합니다.
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
from case_extractor.manual_mode import build_row, load_response, make_prompt_file
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
        self.geometry("760x820")
        self.configure(bg=BG)
        self.minsize(680, 680)

        # API 모드 상태
        self.template_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.coder_id = tk.StringVar()
        self.api_key = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        self.selected_files: list[Path] = []
        self._stop_event = threading.Event()

        # 수동 모드 상태
        self.manual_files: list[Path] = []
        self.prompts_dir = tk.StringVar()
        self.manual_template_path = tk.StringVar()
        self.responses_dir = tk.StringVar()
        self.manual_output_path = tk.StringVar()
        self.manual_coder_id = tk.StringVar()

        self._log_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
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
        style.configure("Info.TLabel", background=CARD_BG, font=("Helvetica", 10), foreground=TEXT_MUTED)
        style.configure("TEntry", padding=6)
        style.configure("TCheckbutton", background=CARD_BG, font=FONT_BASE)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=FONT_BOLD, padding=(16, 10))

        style.configure(
            "Accent.TButton", font=FONT_BOLD, padding=(14, 10),
            background=ACCENT, foreground="white", borderwidth=0,
        )
        style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#9db6f5")])

        style.configure(
            "Danger.TButton", font=FONT_BOLD, padding=(14, 10),
            background=DANGER, foreground="white", borderwidth=0,
        )
        style.map("Danger.TButton", background=[("active", "#b83a3a"), ("disabled", "#e6b3b3")])

        style.configure("Ghost.TButton", font=FONT_BASE, padding=(10, 6))

        style.configure("Horizontal.TProgressbar", troughcolor="#e5e7eb", background=ACCENT, thickness=10)

    def _card(self, parent) -> tuple[ttk.Frame, ttk.Frame]:
        outer = ttk.Frame(parent, style="TFrame")
        card = ttk.Frame(outer, style="Card.TFrame", padding=16)
        card.pack(fill="both", expand=True)
        return outer, card

    def _labeled_path_row(self, card, label, var, command, width=18):
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text=label, style="Card.TLabel", width=width).pack(side="left")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="선택", style="Ghost.TButton", command=command).pack(side="left")

    # ---------- 전체 레이아웃 ----------
    def _build_widgets(self):
        root = ttk.Frame(self, style="TFrame", padding=20)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="판례 코딩시트 변환기", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            root,
            text="판결문(PDF/DOCX)을 넣으면 코딩시트 엑셀 항목을 자동으로 채워줍니다.",
            style="TLabel", foreground=TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 14))

        notebook = ttk.Notebook(root)
        notebook.pack(fill="x")

        api_tab = ttk.Frame(notebook, style="TFrame", padding=(0, 14, 0, 0))
        manual_tab = ttk.Frame(notebook, style="TFrame", padding=(0, 14, 0, 0))
        notebook.add(api_tab, text="🔑 API 모드")
        notebook.add(manual_tab, text="✂️ 수동 모드 (API 키 없이)")

        self._build_api_tab(api_tab)
        self._build_manual_tab(manual_tab)

        self._build_log_card(root)

    # ================= API 모드 =================
    def _build_api_tab(self, parent):
        self._build_files_card(parent)
        self._build_settings_card(parent)
        self._build_run_card(parent)

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

    def _build_run_card(self, parent):
        row = ttk.Frame(parent, style="TFrame")
        row.pack(fill="x", pady=(4, 0))

        self.run_btn = ttk.Button(row, text="▶  변환 시작", style="Accent.TButton", command=self._start)
        self.run_btn.pack(side="left")

        self.stop_btn = ttk.Button(row, text="■  중지", style="Danger.TButton",
                                   command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=10)

        self.progress = ttk.Progressbar(row, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(10, 0))

    # ---------- API 모드 파일 선택 ----------
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

    # ---------- API 모드 실행/중지 ----------
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
            messagebox.showerror(
                "오류",
                "Anthropic API 키를 입력하세요. 키가 없다면 '수동 모드' 탭을 이용하면 "
                "API 키 없이도 claude.ai 채팅으로 진행할 수 있습니다.",
            )
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

    # ================= 수동 모드 =================
    def _build_manual_tab(self, parent):
        outer, card = self._card(parent)
        outer.pack(fill="x", pady=(0, 12))
        ttk.Label(card, text="API 키 없이 진행하는 방법", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(
            card,
            style="Info.TLabel",
            justify="left",
            wraplength=680,
            text=(
                "① 아래에서 판결문을 선택하고 '프롬프트 파일 만들기'를 누르면, 파일마다 "
                "claude.ai 채팅창에 붙여넣을 텍스트(.txt)가 생성됩니다.\n"
                "② 생성된 .txt 파일을 열어 내용 전체를 복사한 뒤, 평소 쓰는 claude.ai 채팅에 "
                "붙여넣고 답장을 받습니다.\n"
                "③ 받은 답변 전체(JSON)를 복사해서, 판결문과 같은 이름의 .json 파일로 응답 폴더에 "
                "저장합니다. (예: 판결문1.pdf → 판결문1.json)\n"
                "④ 모든 판결문의 응답을 다 모았으면 '엑셀로 합치기'를 눌러 코딩시트를 완성합니다."
            ),
        ).pack(anchor="w")

        # 판결문 선택 (수동 모드 전용)
        outer2, card2 = self._card(parent)
        outer2.pack(fill="x", pady=(0, 12))
        ttk.Label(card2, text="1. 판결문 선택", style="Section.TLabel").pack(anchor="w", pady=(0, 8))

        btn_row = ttk.Frame(card2, style="Card.TFrame")
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="📁 폴더에서 전체 선택", style="Ghost.TButton",
                   command=self._manual_pick_dir).pack(side="left")
        ttk.Button(btn_row, text="📄 파일 개별 선택", style="Ghost.TButton",
                   command=self._manual_pick_files).pack(side="left", padx=8)
        ttk.Button(btn_row, text="비우기", style="Ghost.TButton",
                   command=self._manual_clear_files).pack(side="left")

        self.manual_file_count_label = ttk.Label(card2, text="선택된 파일 없음", style="Muted.TLabel")
        self.manual_file_count_label.pack(anchor="w", pady=(8, 0))

        # 1단계
        outer3, card3 = self._card(parent)
        outer3.pack(fill="x", pady=(0, 12))
        ttk.Label(card3, text="2. 1단계 — 프롬프트 파일 만들기", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self._labeled_path_row(card3, "프롬프트 저장 폴더", self.prompts_dir, self._manual_pick_prompts_dir)
        ttk.Button(card3, text="📝  프롬프트 파일 만들기", style="Accent.TButton",
                   command=self._manual_make_prompts).pack(anchor="w", pady=(6, 0))

        # 2단계
        outer4, card4 = self._card(parent)
        outer4.pack(fill="x", pady=(0, 0))
        ttk.Label(card4, text="3. 2단계 — 응답을 엑셀로 합치기", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self._labeled_path_row(card4, "코딩시트 템플릿 (xlsx)", self.manual_template_path, self._manual_pick_template)
        self._labeled_path_row(card4, "응답(.json) 폴더", self.responses_dir, self._manual_pick_responses_dir)
        self._labeled_path_row(card4, "결과 저장 위치 (xlsx)", self.manual_output_path, self._manual_pick_output)

        row = ttk.Frame(card4, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="코딩 담당자 ID", style="Card.TLabel", width=18).pack(side="left")
        ttk.Entry(row, textvariable=self.manual_coder_id, width=16).pack(side="left")

        ttk.Button(card4, text="📊  엑셀로 합치기", style="Accent.TButton",
                   command=self._manual_import).pack(anchor="w", pady=(6, 0))

    def _manual_pick_dir(self):
        path = filedialog.askdirectory()
        if not path:
            return
        files = find_case_files(Path(path))
        if not files:
            messagebox.showwarning("알림", "선택한 폴더에서 .pdf/.docx 파일을 찾지 못했습니다.")
            return
        self._manual_add_files(files)

    def _manual_pick_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("판결문 파일", "*.pdf *.docx"), ("모든 파일", "*.*")])
        if paths:
            self._manual_add_files([Path(p) for p in paths])

    def _manual_add_files(self, files: list[Path]):
        existing = {str(f) for f in self.manual_files}
        for f in files:
            if str(f) not in existing:
                self.manual_files.append(f)
                existing.add(str(f))
        n = len(self.manual_files)
        self.manual_file_count_label.config(text=f"{n}개 파일 선택됨" if n else "선택된 파일 없음")

    def _manual_clear_files(self):
        self.manual_files = []
        self.manual_file_count_label.config(text="선택된 파일 없음")

    def _manual_pick_prompts_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.prompts_dir.set(path)

    def _manual_pick_template(self):
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if path:
            self.manual_template_path.set(path)
            if not self.manual_output_path.get():
                p = Path(path)
                self.manual_output_path.set(str(p.with_name(p.stem + "_결과.xlsx")))

    def _manual_pick_responses_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.responses_dir.set(path)

    def _manual_pick_output(self):
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if path:
            self.manual_output_path.set(path)

    def _manual_make_prompts(self):
        if not self.manual_files:
            messagebox.showerror("오류", "판결문 파일을 먼저 선택하세요.")
            return
        if not self.prompts_dir.get():
            messagebox.showerror("오류", "프롬프트를 저장할 폴더를 선택하세요.")
            return
        threading.Thread(target=self._manual_make_prompts_worker, daemon=True).start()

    def _manual_make_prompts_worker(self):
        files = list(self.manual_files)
        out_dir = Path(self.prompts_dir.get())
        self._log(f"{len(files)}개 파일의 프롬프트를 만듭니다...")
        made = 0
        for f in files:
            try:
                out = make_prompt_file(f, out_dir)
                self._log(f"  {f.name} -> {out.name}", "ok")
                made += 1
            except NotJudgmentLikelyError as e:
                self._log(f"  건너뜀: {e}", "warn")
            except TextExtractError as e:
                self._log(f"  실패: {e}", "err")
        self._log(f"완료: {made}개 프롬프트 파일을 {out_dir} 에 만들었습니다.", "ok")
        self._log("각 .prompt.txt 내용을 claude.ai에 붙여넣고, 받은 JSON 응답을 같은 이름(.json)으로 저장하세요.", "warn")

    def _manual_import(self):
        if not self.manual_files:
            messagebox.showerror("오류", "판결문 파일을 먼저 선택하세요 (1단계와 동일한 파일이어야 합니다).")
            return
        if not self.manual_template_path.get() or not self.manual_output_path.get():
            messagebox.showerror("오류", "코딩시트 템플릿과 결과 저장 위치를 선택하세요.")
            return
        if not self.responses_dir.get():
            messagebox.showerror("오류", "claude.ai 응답(.json)이 들어있는 폴더를 선택하세요.")
            return
        threading.Thread(target=self._manual_import_worker, daemon=True).start()

    def _manual_import_worker(self):
        files = list(self.manual_files)
        responses_dir = Path(self.responses_dir.get())
        rows = []
        for f in files:
            try:
                extracted = load_response(f, responses_dir)
                rows.append(build_row(f, extracted, coder_id=self.manual_coder_id.get()))
                self._log(f"  불러옴: {f.name}", "ok")
            except LLMExtractError as e:
                self._log(f"  건너뜀: {e}", "warn")

        if rows:
            out = write_rows(
                Path(self.manual_template_path.get()), Path(self.manual_output_path.get()), rows
            )
            self._log(f"완료: {len(rows)}건을 {out} 에 저장했습니다.", "ok")
            self._log("주의: AI가 추출한 값이므로 coding_note에 [AI 추출-수동] 표시가 된 행은 원문과 대조 검수하세요.", "warn")
        else:
            self._log("저장할 결과가 없습니다. 응답 폴더에 파일명이 일치하는 .json이 있는지 확인하세요.", "warn")

    # ---------- 로그 (공통) ----------
    def _build_log_card(self, parent):
        outer, card = self._card(parent)
        outer.pack(fill="both", expand=True, pady=(14, 0))

        ttk.Label(card, text="진행 상황", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.log = scrolledtext.ScrolledText(
            card, height=10, font=("Menlo", 10), bg="#0f172a", fg="#e2e8f0",
            insertbackground="#e2e8f0", relief="flat", padx=10, pady=8,
        )
        self.log.pack(fill="both", expand=True)
        self.log.tag_config("warn", foreground="#fbbf24")
        self.log.tag_config("err", foreground="#f87171")
        self.log.tag_config("ok", foreground="#4ade80")

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


if __name__ == "__main__":
    App().mainloop()
