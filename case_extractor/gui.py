"""macOS/Windows용 GUI. 터미널이 낯선 경우 이걸 실행하세요.

실행: python3 gui.py

화면 위쪽의 큰 버튼 두 개로 모드를 고릅니다:
- "API 모드": Anthropic API 키가 있을 때. 자동으로 끝까지 처리합니다.
- "수동 모드": API 키가 없을 때. claude.ai 웹 채팅에 복사/붙여넣기로 진행합니다.
왼쪽에 선택한 모드의 입력/설정이, 오른쪽에는 항상 "진행 상황" 로그가 보입니다.
"""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

import platform as _platform

from case_extractor.cli import process_file
from case_extractor.excel_writer import notes_path_for, write_rows
from case_extractor.llm_extract import LLMExtractError, parse_json_response
from case_extractor.manual_mode import build_prompt, build_row, load_response, make_prompt_file, read_response_file
from case_extractor.text_extract import TextExtractError, extract_text, find_case_files
from case_extractor.validate import NotJudgmentLikelyError

_FONT = "Segoe UI" if _platform.system() == "Windows" else "Helvetica Neue"

BG = "#f0f2fc"
CARD_BG = "#ffffff"
BORDER = "#e2e5f0"
ACCENT = "#5b50e8"
ACCENT_DARK = "#4338ca"
ACCENT_LIGHT = "#ede9fe"
DANGER = "#e53e3e"
SUCCESS = "#22863a"
WARN_COLOR = "#c08000"
TEXT = "#1a1f36"
TEXT_MUTED = "#74778b"
STEP1_BG = "#ede9fe"   # 연보라 - 복사 단계
STEP2_BG = "#d1fae5"   # 연초록 - 저장 단계
FONT_BASE = (_FONT, 11)
FONT_BOLD = (_FONT, 11, "bold")
FONT_TITLE = (_FONT, 17, "bold")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Case Law Coding Sheet Converter")
        self.geometry("1200x780")
        self.configure(bg=BG)
        self.minsize(1000, 640)

        # API 모드 상태
        self.template_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.coder_id = tk.StringVar()
        self.api_key = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        self.selected_files: list[Path] = []
        self._stop_event = threading.Event()

        # 수동 모드 상태
        self.manual_files: list[Path] = []
        self.manual_selected_idx: int = -1
        self.manual_done_stems: set[str] = set()
        self.manual_template_path = tk.StringVar()
        self.manual_output_path = tk.StringVar()
        self.manual_coder_id = tk.StringVar()
        # 하위 호환 (reset_all에서 참조)
        self.prompts_dir = tk.StringVar()
        self.responses_dir = tk.StringVar()
        self.manual_response_files: dict[str, Path] = {}

        self._log_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._stats = {"total": 0, "done": 0, "skipped": 0, "failed": 0}

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
        style.configure("TLabel", background=BG, font=FONT_BASE, foreground=TEXT)
        style.configure("Card.TLabel", background=CARD_BG, font=FONT_BASE, foreground=TEXT)
        style.configure("Muted.TLabel", background=CARD_BG, font=FONT_BASE, foreground=TEXT_MUTED)
        style.configure("Title.TLabel", background=BG, font=FONT_TITLE, foreground=TEXT)
        style.configure("Section.TLabel", background=CARD_BG, font=FONT_BOLD, foreground=TEXT)
        style.configure("Info.TLabel", background=CARD_BG, font=(_FONT, 10), foreground=TEXT_MUTED)
        style.configure("TSeparator", background=BORDER)
        style.configure("TEntry", padding=7, fieldbackground="#fafbff",
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
        style.configure("TCheckbutton", background=CARD_BG, font=FONT_BASE)
        style.configure(
            "Accent.TButton", font=FONT_BOLD, padding=(14, 10),
            background=ACCENT, foreground="white", borderwidth=0,
        )
        style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#a5b4fc")])

        style.configure(
            "Danger.TButton", font=FONT_BOLD, padding=(14, 10),
            background=DANGER, foreground="white", borderwidth=0,
        )
        style.map("Danger.TButton", background=[("active", "#b91c1c"), ("disabled", "#fca5a5")])

        style.configure("Ghost.TButton", font=FONT_BASE, padding=(10, 6),
                        background=CARD_BG, borderwidth=1,
                        relief="solid", bordercolor=BORDER)
        style.map("Ghost.TButton",
                  background=[("active", ACCENT_LIGHT)],
                  foreground=[("active", ACCENT)])

        style.configure("Horizontal.TProgressbar",
                        troughcolor="#e0e4f0", background=ACCENT, thickness=8)

    def _card(self, parent) -> tuple:
        wrapper = tk.Frame(parent, bg=BORDER)
        card = ttk.Frame(wrapper, style="Card.TFrame", padding=16)
        card.pack(fill="both", expand=True, padx=1, pady=1)
        return wrapper, card

    def _section_header(self, card, step: str, text: str):
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(anchor="w", fill="x", pady=(0, 10))
        badge = tk.Label(row, text=f" {step} ", bg=ACCENT, fg="white",
                         font=(_FONT, 9, "bold"), padx=2, pady=1)
        badge.pack(side="left")
        ttk.Label(row, text=f"  {text}", style="Section.TLabel").pack(side="left")

    def _add_text_context_menu(self, widget):
        """텍스트 위젯에 우클릭 붙여넣기/복사/잘라내기 컨텍스트 메뉴를 추가한다."""
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="붙여넣기 (Paste)",
                         command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_command(label="복사 (Copy)",
                         command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="잘라내기 (Cut)",
                         command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_separator()
        menu.add_command(label="전체 선택 (Select All)",
                         command=lambda: widget.tag_add("sel", "1.0", "end"))

        def _show_menu(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        widget.bind("<Button-3>", _show_menu)
        if _platform.system() == "Darwin":
            widget.bind("<Button-2>", _show_menu)

    def _scrollable(self, parent) -> ttk.Frame:
        """세로로 스크롤되는 영역을 만들고, 그 안에 내용을 채울 프레임을 반환한다."""
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        vscroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, style="TFrame")
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(inner_id, width=event.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=vscroll.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")
        return inner

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

        title_row = tk.Frame(root, bg=BG)
        title_row.pack(fill="x", pady=(0, 14))

        accent_bar = tk.Frame(title_row, bg=ACCENT, width=5)
        accent_bar.pack(side="left", fill="y", padx=(0, 14))

        title_text = tk.Frame(title_row, bg=BG)
        title_text.pack(side="left")
        tk.Label(title_text, text="Case Law Coding Sheet Converter", bg=BG, fg=TEXT,
                 font=(_FONT, 18, "bold")).pack(anchor="w")
        tk.Label(title_text, text="판결문(PDF/DOCX) → 코딩시트 엑셀 자동 변환",
                 bg=BG, fg=TEXT_MUTED, font=(_FONT, 10)).pack(anchor="w")

        ttk.Button(
            title_row, text="↺  전체 초기화", style="Ghost.TButton", command=self._reset_all,
        ).pack(side="right", anchor="n", pady=4)

        self._build_mode_selector(root)

        body = ttk.Frame(root, style="TFrame")
        body.pack(fill="both", expand=True, pady=(14, 0))
        body.columnconfigure(0, weight=3, minsize=400)
        body.columnconfigure(1, weight=2, minsize=280)
        body.rowconfigure(0, weight=1)

        left_outer = ttk.Frame(body, style="TFrame")
        left_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left_content = self._scrollable(left_outer)

        self.api_container = ttk.Frame(left_content, style="TFrame")
        self.manual_container = ttk.Frame(left_content, style="TFrame")
        self._build_api_tab(self.api_container)
        self._build_manual_tab(self.manual_container)

        log_outer = ttk.Frame(body, style="TFrame")
        log_outer.grid(row=0, column=1, sticky="nsew")
        self._build_log_card(log_outer)

        self._set_mode("api")

    def _build_mode_selector(self, parent):
        container = tk.Frame(parent, bg=BORDER)
        container.pack(fill="x")
        inner = tk.Frame(container, bg=CARD_BG)
        inner.pack(fill="x", padx=1, pady=1)

        self.mode_api_btn = tk.Button(
            inner, text="🔑  API 모드   —   API 키로 자동 처리",
            font=(_FONT, 11, "bold"), bg=ACCENT, fg="white",
            relief="flat", bd=0, padx=18, pady=13, cursor="hand2",
            activebackground=ACCENT_DARK, activeforeground="white",
            command=lambda: self._set_mode("api"),
        )
        self.mode_api_btn.pack(side="left", fill="x", expand=True)

        tk.Frame(inner, bg=BORDER, width=1).pack(side="left", fill="y")

        self.mode_manual_btn = tk.Button(
            inner, text="✂️  수동 모드   —   claude.ai 채팅 이용",
            font=(_FONT, 11), bg=CARD_BG, fg=TEXT_MUTED,
            relief="flat", bd=0, padx=18, pady=13, cursor="hand2",
            activebackground=ACCENT_LIGHT, activeforeground=ACCENT,
            command=lambda: self._set_mode("manual"),
        )
        self.mode_manual_btn.pack(side="left", fill="x", expand=True)

        self.mode_desc_label = ttk.Label(parent, text="", style="TLabel", foreground=TEXT_MUTED)
        self.mode_desc_label.pack(anchor="w", pady=(8, 0))

    def _reset_all(self):
        """API/수동 모드에서 입력한 모든 내용, 로그, 진행 상황을 처음 상태로 되돌린다."""
        if not messagebox.askyesno("전체 초기화", "입력한 모든 내용을 지우고 처음 상태로 되돌릴까요?"):
            return

        # API 모드
        self.template_path.set("")
        self.output_path.set("")
        self.coder_id.set("")
        self.api_key.set(os.environ.get("ANTHROPIC_API_KEY", ""))
        self.selected_files = []
        self._refresh_file_list()
        self.progress.config(value=0)

        # 수동 모드
        self.manual_files = []
        self.manual_selected_idx = -1
        self.manual_done_stems = set()
        self.manual_template_path.set("")
        self.manual_output_path.set("")
        self.manual_coder_id.set("")
        self.manual_paste_text.delete("1.0", "end")
        self._manual_update_file_list()

        # 요약 + 로그
        self.log.delete("1.0", "end")
        self._stats = {"total": 0, "done": 0, "skipped": 0, "failed": 0}
        self._refresh_stats_labels()
        self.mode_status_label.config(text="")
        self._last_result_path = None
        self.open_result_btn.config(state="disabled")
        self.open_result_folder_btn.config(state="disabled")

        self._log("전체 입력을 초기화했습니다.", "warn")

    def _set_mode(self, mode: str):
        self.mode = mode
        if mode == "api":
            self.mode_api_btn.config(bg=ACCENT, fg="white", font=(_FONT, 11, "bold"))
            self.mode_manual_btn.config(bg=CARD_BG, fg=TEXT_MUTED, font=(_FONT, 11))
            self.manual_container.pack_forget()
            self.api_container.pack(fill="both", expand=True)
            self.mode_desc_label.config(
                text="API 모드 — Anthropic API 키로 버튼 한 번에 자동 처리합니다 (사용량만큼 별도 과금)."
            )
        else:
            self.mode_manual_btn.config(bg=ACCENT, fg="white", font=(_FONT, 11, "bold"))
            self.mode_api_btn.config(bg=CARD_BG, fg=TEXT_MUTED, font=(_FONT, 11))
            self.api_container.pack_forget()
            self.manual_container.pack(fill="both", expand=True)
            self.mode_desc_label.config(
                text="수동 모드 — API 키 없이 claude.ai 채팅에 복사/붙여넣기로 진행합니다 (추가 비용 없음)."
            )

    # ================= API 모드 =================
    def _build_api_tab(self, parent):
        self._build_files_card(parent)
        self._build_settings_card(parent)
        self._build_run_card(parent)

    def _build_files_card(self, parent):
        outer, card = self._card(parent)
        outer.pack(fill="x", pady=(0, 12))

        self._section_header(card, "1", "판결문 입력")

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
            list_frame, height=6, font=FONT_BASE, bg="#fafbff", fg=TEXT,
            selectbackground=ACCENT, selectforeground="white",
            relief="flat", highlightthickness=1,
            highlightbackground=BORDER, activestyle="none",
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

        self._section_header(card, "2", "설정")

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
            self._init_stats(len(files))
            self._set_mode_status("API 모드로 판결문을 자동 처리하고 있습니다.")
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
                    self._bump_stat("done")
                except NotJudgmentLikelyError as e:
                    self._log(f"  건너뜀: {e}", "warn")
                    self._bump_stat("skipped")
                except (TextExtractError, LLMExtractError) as e:
                    self._log(f"  실패: {e}", "err")
                    self._bump_stat("failed")
                finally:
                    self.progress.step(1)

            if rows:
                self._safe_write_rows(Path(self.template_path.get()), Path(self.output_path.get()), rows)
            elif not self._stop_event.is_set():
                self._log("저장할 결과가 없습니다.", "warn")
        except Exception as e:  # 예상 못한 오류도 화면에 반드시 표시한다
            self._log(f"예상치 못한 오류로 중단됨: {e}", "err")
            self._show_error(str(e))
        finally:
            self.run_btn.config(state="normal")
            self.stop_btn.config(state="disabled")

    # ---------- 공통 유틸 ----------
    def _safe_write_rows(self, template: Path, output: Path, rows: list[dict]) -> None:
        """엑셀 저장을 시도하고, 실패하면 원인을 화면에 명확히 표시한다."""
        try:
            out = write_rows(template, output, rows)
            self._log(f"완료: {len(rows)}건을 {out} 에 저장했습니다.", "ok")
            notes = notes_path_for(out)
            if notes.exists():
                self._log(f"코딩노트: {notes}", "ok")
            self._log("주의: AI가 추출한 값이므로 coding_note에 [AI 추출] 표시가 된 행은 원문과 대조 검수하세요.", "warn")
            self.after(0, lambda p=out: self._set_result_path(p))
        except PermissionError:
            msg = (
                f"엑셀 파일을 저장하지 못했습니다: {output}\n\n"
                "이 파일이 Excel(또는 다른 프로그램)에서 이미 열려 있어서 저장이 막혔을 가능성이 큽니다. "
                "그 파일을 닫은 뒤 다시 시도해주세요."
            )
            self._log(f"저장 실패(파일이 열려 있는 것 같습니다): {output}", "err")
            self._show_error(msg)
        except FileNotFoundError as e:
            self._log(f"저장 실패: {e}", "err")
            self._show_error(f"템플릿 또는 저장 경로를 찾을 수 없습니다.\n{e}")
        except Exception as e:
            self._log(f"저장 실패: {e}", "err")
            self._show_error(f"엑셀 저장 중 오류가 발생했습니다.\n{e}")

    def _set_result_path(self, path: Path):
        self._last_result_path = path
        self.open_result_btn.config(state="normal")
        self.open_result_folder_btn.config(state="normal")

    def _open_result_file(self):
        if not self._last_result_path or not self._last_result_path.exists():
            messagebox.showwarning("알림", "저장된 결과 파일을 찾을 수 없습니다.")
            return
        try:
            sys_name = _platform.system()
            if sys_name == "Darwin":
                subprocess.Popen(["open", str(self._last_result_path)])
            elif sys_name == "Windows":
                os.startfile(str(self._last_result_path))
            else:
                subprocess.Popen(["xdg-open", str(self._last_result_path)])
        except Exception as e:
            messagebox.showerror("열기 오류", f"파일을 열 수 없습니다:\n{e}")

    def _open_result_folder(self):
        if not self._last_result_path:
            messagebox.showwarning("알림", "저장된 결과 파일을 찾을 수 없습니다.")
            return
        folder = self._last_result_path.parent
        try:
            sys_name = _platform.system()
            if sys_name == "Darwin":
                subprocess.Popen(["open", str(folder)])
            elif sys_name == "Windows":
                subprocess.Popen(["explorer", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as e:
            messagebox.showerror("열기 오류", f"폴더를 열 수 없습니다:\n{e}")

    def _show_error(self, message: str):
        self.after(0, lambda: messagebox.showerror("오류", message))

    # ================= 수동 모드 =================
    def _build_manual_tab(self, parent):
        # ── 엑셀 출력 설정 카드 ──────────────────────────────────
        outer_cfg, card_cfg = self._card(parent)
        outer_cfg.pack(fill="x", pady=(0, 12))
        self._section_header(card_cfg, "⚙", "엑셀 출력 설정")
        self._labeled_path_row(card_cfg, "코딩시트 템플릿 (xlsx)", self.manual_template_path, self._manual_pick_template)
        self._labeled_path_row(card_cfg, "결과 저장 위치 (xlsx)", self.manual_output_path, self._manual_pick_output)
        id_row = ttk.Frame(card_cfg, style="Card.TFrame")
        id_row.pack(fill="x")
        ttk.Label(id_row, text="코딩 담당자 ID", style="Card.TLabel", width=18).pack(side="left")
        ttk.Entry(id_row, textvariable=self.manual_coder_id, width=16).pack(side="left")

        # ── 파일 선택 + 두 패널 카드 ─────────────────────────────
        outer_main, card_main = self._card(parent)
        outer_main.pack(fill="both", expand=True)
        self._section_header(card_main, "1→3", "판결문 선택 → 복사 → 붙여넣기 → 저장")

        # 파일 선택 버튼 행
        btn_row = ttk.Frame(card_main, style="Card.TFrame")
        btn_row.pack(fill="x", pady=(0, 10))
        ttk.Button(btn_row, text="📁  폴더 선택", style="Ghost.TButton",
                   command=self._manual_pick_dir).pack(side="left")
        ttk.Button(btn_row, text="📄  파일 선택", style="Ghost.TButton",
                   command=self._manual_pick_files).pack(side="left", padx=8)
        ttk.Button(btn_row, text="비우기", style="Ghost.TButton",
                   command=self._manual_clear_files).pack(side="left")
        self.manual_file_count_label = ttk.Label(btn_row, text="선택된 파일 없음", style="Muted.TLabel")
        self.manual_file_count_label.pack(side="left", padx=(12, 0))

        # ── 두 패널 분할 ─────────────────────────────────────────
        split = tk.Frame(card_main, bg=CARD_BG)
        split.pack(fill="both", expand=True)

        # 왼쪽: 파일 목록
        left_wrap = tk.Frame(split, bg=BORDER, width=222)
        left_wrap.pack(side="left", fill="y", padx=(0, 10))
        left_wrap.pack_propagate(False)
        left_inner = tk.Frame(left_wrap, bg=CARD_BG)
        left_inner.pack(fill="both", expand=True, padx=1, pady=1)

        self.manual_file_listbox = tk.Listbox(
            left_inner,
            font=(_FONT, 10), bg=CARD_BG, fg=TEXT,
            selectbackground=ACCENT_LIGHT, selectforeground=ACCENT,
            relief="flat", bd=0, highlightthickness=0,
            activestyle="none", height=14,
        )
        list_scroll = ttk.Scrollbar(left_inner, command=self.manual_file_listbox.yview)
        self.manual_file_listbox.config(yscrollcommand=list_scroll.set)
        list_scroll.pack(side="right", fill="y")
        self.manual_file_listbox.pack(side="left", fill="both", expand=True)
        self.manual_file_listbox.bind("<<ListboxSelect>>", self._manual_on_file_select)

        # 오른쪽: 처리 패널
        right = tk.Frame(split, bg=CARD_BG)
        right.pack(side="left", fill="both", expand=True)

        self.manual_detail_label = tk.Label(
            right, text="← 왼쪽에서 판결문을 선택하세요",
            bg=CARD_BG, fg=TEXT_MUTED, font=(_FONT, 11, "bold"), anchor="w",
        )
        self.manual_detail_label.pack(fill="x", pady=(0, 8))

        # 미리보기 토글
        self.manual_preview_btn = ttk.Button(
            right, text="👁  판결문 내용 미리보기 ▼",
            style="Ghost.TButton", command=self._manual_toggle_preview, state="disabled",
        )
        self.manual_preview_btn.pack(anchor="w", pady=(0, 4))

        self.manual_preview_frame = tk.Frame(right, bg=CARD_BG)
        preview_toolbar = tk.Frame(self.manual_preview_frame, bg=CARD_BG)
        preview_toolbar.pack(fill="x", pady=(0, 4))
        tk.Label(preview_toolbar, text="판결문 원문 (추출 텍스트)", bg=CARD_BG,
                 fg=TEXT_MUTED, font=(_FONT, 9)).pack(side="left")
        ttk.Button(preview_toolbar, text="✕ 닫기", style="Ghost.TButton",
                   command=self._manual_close_preview).pack(side="right")
        ttk.Button(preview_toolbar, text="지우기", style="Ghost.TButton",
                   command=self._manual_clear_preview).pack(side="right", padx=(0, 6))
        self.manual_open_file_btn = ttk.Button(
            preview_toolbar, text="📄 PDF 원본 열기", style="Ghost.TButton",
            command=self._manual_open_file, state="disabled",
        )
        self.manual_open_file_btn.pack(side="right", padx=(0, 6))
        self.manual_preview_text = scrolledtext.ScrolledText(
            self.manual_preview_frame, height=12, font=("Menlo", 9),
            bg="#f8f9fa", fg=TEXT_MUTED,
            relief="flat", highlightthickness=1, highlightbackground=BORDER,
            padx=8, pady=6, state="disabled", wrap="word",
        )
        self.manual_preview_text.pack(fill="both", expand=True)

        # ① 프롬프트 복사 박스
        step1_box = tk.Frame(right, bg=STEP1_BG, padx=12, pady=10)
        step1_box.pack(fill="x", pady=(8, 6))

        step1_title_row = tk.Frame(step1_box, bg=STEP1_BG)
        step1_title_row.pack(fill="x", pady=(0, 6))
        badge1 = tk.Label(step1_title_row, text=" ① ", bg=ACCENT, fg="white",
                          font=(_FONT, 9, "bold"), padx=4, pady=2)
        badge1.pack(side="left")
        tk.Label(step1_title_row, text="  claude.ai에 보낼 프롬프트 복사",
                 bg=STEP1_BG, fg=TEXT, font=(_FONT, 11, "bold")).pack(side="left")

        self.manual_copy_prompt_btn = tk.Button(
            step1_box, text="📋  클립보드에 복사",
            font=(_FONT, 11, "bold"), bg=ACCENT, fg="white",
            relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
            activebackground=ACCENT_DARK, activeforeground="white",
            command=self._manual_copy_prompt, state="disabled",
        )
        self.manual_copy_prompt_btn.pack(anchor="w")

        self.manual_copy_status_label = tk.Label(
            step1_box, text="", bg=STEP1_BG, fg=ACCENT, font=(_FONT, 10), anchor="w",
        )
        self.manual_copy_status_label.pack(fill="x", pady=(4, 0))

        # ② 응답 붙여넣기 박스
        step2_box = tk.Frame(right, bg=STEP2_BG, padx=12, pady=10)
        step2_box.pack(fill="both", expand=True, pady=(0, 0))

        step2_title_row = tk.Frame(step2_box, bg=STEP2_BG)
        step2_title_row.pack(fill="x", pady=(0, 6))
        badge2 = tk.Label(step2_title_row, text=" ② ", bg=SUCCESS, fg="white",
                          font=(_FONT, 9, "bold"), padx=4, pady=2)
        badge2.pack(side="left")
        tk.Label(step2_title_row, text="  claude.ai 응답(JSON) 붙여넣고 저장",
                 bg=STEP2_BG, fg=TEXT, font=(_FONT, 11, "bold")).pack(side="left")

        self.manual_paste_text = scrolledtext.ScrolledText(
            step2_box, height=8, font=("Menlo", 10), bg="#f0faf4", fg=TEXT,
            relief="flat", highlightthickness=1, highlightbackground="#bbf7d0",
            padx=10, pady=8,
        )
        self.manual_paste_text.pack(fill="both", expand=True, pady=(0, 8))
        self._add_text_context_menu(self.manual_paste_text)

        save_row = tk.Frame(step2_box, bg=STEP2_BG)
        save_row.pack(fill="x")
        self.manual_save_btn = tk.Button(
            save_row, text="✅  엑셀에 저장",
            font=(_FONT, 11, "bold"), bg=SUCCESS, fg="white",
            relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
            activebackground="#166534", activeforeground="white",
            command=self._manual_save_direct, state="disabled",
        )
        self.manual_save_btn.pack(side="left")
        ttk.Button(save_row, text="지우기", style="Ghost.TButton",
                   command=lambda: self.manual_paste_text.delete("1.0", "end")).pack(side="left", padx=8)

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
        self._manual_update_file_list()

    def _manual_clear_files(self):
        self.manual_files = []
        self.manual_selected_idx = -1
        self.manual_done_stems = set()
        self._manual_update_file_list()
        self.manual_detail_label.config(text="← 왼쪽에서 판결문을 선택하세요", fg=TEXT_MUTED)
        self.manual_preview_btn.config(state="disabled")
        self.manual_open_file_btn.config(state="disabled")
        self.manual_copy_prompt_btn.config(state="disabled")
        self.manual_save_btn.config(state="disabled")
        self.manual_copy_status_label.config(text="")

    def _manual_update_file_list(self):
        self.manual_file_listbox.delete(0, "end")
        for f in self.manual_files:
            icon = "✅" if f.stem in self.manual_done_stems else "⬜"
            self.manual_file_listbox.insert("end", f"  {icon}  {f.name}")
        n = len(self.manual_files)
        self.manual_file_count_label.config(text=f"{n}개 파일 선택됨" if n else "선택된 파일 없음")

    def _manual_on_file_select(self, event=None):
        sel = self.manual_file_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.manual_selected_idx = idx
        path = self.manual_files[idx]
        done = path.stem in self.manual_done_stems
        self.manual_detail_label.config(
            text=f"{'✅' if done else '📄'}  {path.name}", fg=SUCCESS if done else TEXT,
        )
        self.manual_preview_btn.config(state="normal")
        self.manual_open_file_btn.config(state="normal")
        self.manual_copy_prompt_btn.config(state="normal")
        self.manual_save_btn.config(state="normal")
        self.manual_copy_status_label.config(text="")
        if self.manual_preview_frame.winfo_ismapped():
            self._manual_load_preview(path)

    def _manual_open_file(self):
        if not (0 <= self.manual_selected_idx < len(self.manual_files)):
            return
        path = self.manual_files[self.manual_selected_idx]
        try:
            sys_name = _platform.system()
            if sys_name == "Darwin":
                subprocess.Popen(["open", str(path)])
            elif sys_name == "Windows":
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            messagebox.showerror("열기 오류", f"파일을 열 수 없습니다:\n{e}")

    def _manual_close_preview(self):
        self.manual_preview_frame.pack_forget()
        self.manual_preview_btn.config(text="👁  판결문 내용 미리보기 ▼")

    def _manual_clear_preview(self):
        self.manual_preview_text.config(state="normal")
        self.manual_preview_text.delete("1.0", "end")
        self.manual_preview_text.config(state="disabled")

    def _manual_toggle_preview(self):
        if self.manual_preview_frame.winfo_ismapped():
            self.manual_preview_frame.pack_forget()
            self.manual_preview_btn.config(text="👁  판결문 내용 미리보기 ▼")
        else:
            self.manual_preview_frame.pack(fill="both", expand=True, pady=(0, 8))
            self.manual_preview_btn.config(text="👁  판결문 내용 미리보기 ▲")
            if 0 <= self.manual_selected_idx < len(self.manual_files):
                self._manual_load_preview(self.manual_files[self.manual_selected_idx])

    def _manual_load_preview(self, path: Path):
        self.manual_preview_text.config(state="normal")
        self.manual_preview_text.delete("1.0", "end")
        self.manual_preview_text.insert("end", "불러오는 중...")
        self.manual_preview_text.config(state="disabled")
        threading.Thread(target=self._manual_load_preview_worker, args=(path,), daemon=True).start()

    def _manual_load_preview_worker(self, path: Path):
        try:
            text = extract_text(path)
        except Exception as e:
            text = f"[미리보기 오류: {e}]"
        self.after(0, lambda t=text: self._manual_set_preview(t))

    def _manual_set_preview(self, text: str):
        self.manual_preview_text.config(state="normal")
        self.manual_preview_text.delete("1.0", "end")
        self.manual_preview_text.insert("end", text)
        self.manual_preview_text.config(state="disabled")

    def _manual_copy_prompt(self):
        if not (0 <= self.manual_selected_idx < len(self.manual_files)):
            return
        path = self.manual_files[self.manual_selected_idx]
        self.manual_copy_prompt_btn.config(state="disabled", text="⏳  생성 중...")
        self.manual_copy_status_label.config(text="")

        def _worker():
            try:
                text = extract_text(path)
                prompt = build_prompt(text)
                self.after(0, lambda: self._manual_do_copy(prompt, path.name))
            except Exception as e:
                self.after(0, lambda: (
                    self.manual_copy_prompt_btn.config(state="normal", text="📋  클립보드에 복사"),
                    self._log(f"프롬프트 생성 실패: {e}", "err"),
                ))
        threading.Thread(target=_worker, daemon=True).start()

    def _manual_do_copy(self, text: str, filename: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.manual_copy_prompt_btn.config(state="normal", text="📋  클립보드에 복사")
        self.manual_copy_status_label.config(
            text="✅  복사됨! claude.ai 채팅창에 붙여넣고 응답을 받으세요.",
        )
        self._log(f"프롬프트 복사됨: {filename}", "ok")

    def _manual_save_direct(self):
        if not self.manual_template_path.get():
            messagebox.showerror("오류", "코딩시트 템플릿(.xlsx)을 먼저 선택하세요.")
            return
        if not self.manual_output_path.get():
            messagebox.showerror("오류", "결과 저장 위치(.xlsx)를 선택하세요.")
            return
        if not (0 <= self.manual_selected_idx < len(self.manual_files)):
            messagebox.showerror("오류", "왼쪽 목록에서 판결문을 선택하세요.")
            return
        content = self.manual_paste_text.get("1.0", "end").strip()
        if not content:
            messagebox.showerror("오류", "claude.ai 응답(JSON)을 붙여넣으세요.")
            return
        source = self.manual_files[self.manual_selected_idx]
        try:
            extracted = parse_json_response(content)
        except Exception as e:
            messagebox.showerror(
                "JSON 형식 오류",
                f"붙여넣은 내용이 올바른 JSON이 아닙니다.\n{e}\n\nclaude.ai 응답 전체를 그대로 붙여넣어 보세요.",
            )
            return
        row = build_row(source, extracted, coder_id=self.manual_coder_id.get())
        self._safe_write_rows(
            Path(self.manual_template_path.get()),
            Path(self.manual_output_path.get()),
            [row],
        )
        self.manual_done_stems.add(source.stem)
        self.manual_paste_text.delete("1.0", "end")
        self.manual_copy_status_label.config(text="")
        self._manual_update_file_list()
        self.manual_detail_label.config(text=f"✅  {source.name}", fg=SUCCESS)
        # 다음 미처리 파일 자동 선택
        not_done = [i for i, f in enumerate(self.manual_files) if f.stem not in self.manual_done_stems]
        if not_done:
            ni = not_done[0]
            self.manual_file_listbox.selection_clear(0, "end")
            self.manual_file_listbox.selection_set(ni)
            self.manual_file_listbox.see(ni)
            self.manual_selected_idx = ni
            self.manual_detail_label.config(text=f"📄  {self.manual_files[ni].name}", fg=TEXT)
        else:
            self._log("🎉 모든 판결문 처리 완료!", "ok")

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
            self._manual_refresh_paste_combo()

    def _manual_add_response_files(self):
        """이미 만들어져 있는 .json 응답 파일들을 폴더 정리 없이 바로 추가한다."""
        if not self.responses_dir.get():
            path = filedialog.askdirectory(title="응답을 모아둘 폴더를 선택하거나 새로 만드세요")
            if not path:
                return
            self.responses_dir.set(path)

        paths = filedialog.askopenfilenames(
            title="claude.ai 응답이 저장된 JSON 파일 선택 (여러 개 가능)",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
        )
        if not paths:
            return

        dest_dir = Path(self.responses_dir.get())
        dest_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for p in paths:
            src = Path(p)
            dest = dest_dir / src.name
            if src.resolve() != dest.resolve():
                dest.write_bytes(src.read_bytes())
            copied += 1
            self._log(f"응답 파일 추가됨: {src.name}", "ok")

        self._log(f"{copied}개 JSON 파일을 '{dest_dir}' 에 추가했습니다.", "ok")
        self._manual_refresh_paste_combo()

    # ---------- 응답 붙여넣어 저장하기 ----------
    def _manual_file_by_name(self, name: str) -> Path | None:
        for f in self.manual_files:
            if f.name == name:
                return f
        return None

    def _manual_response_exists(self, source: Path) -> bool:
        responses_dir = self.responses_dir.get()
        if not responses_dir:
            return False
        return (Path(responses_dir) / f"{source.stem}.json").exists()

    def _manual_refresh_paste_combo(self):
        names = [f.name for f in self.manual_files]
        current = self.manual_paste_combo.get()
        self.manual_paste_combo.config(values=names)
        if current in names:
            self.manual_paste_combo.set(current)
        elif names:
            # 아직 응답이 저장되지 않은 첫 파일을 기본 선택
            not_done = [n for n in names if not self._manual_response_exists(self._manual_file_by_name(n))]
            self.manual_paste_combo.set(not_done[0] if not_done else names[0])
        else:
            self.manual_paste_combo.set("")
        self._manual_update_paste_status()

    def _manual_update_paste_status(self):
        name = self.manual_paste_combo.get()
        if not name:
            self.manual_paste_status_label.config(text="판결문을 먼저 선택하세요.")
            return
        source = self._manual_file_by_name(name)
        done = source is not None and self._manual_response_exists(source)
        total = len(self.manual_files)
        saved = sum(1 for f in self.manual_files if self._manual_response_exists(f))
        status = "✅ 이미 저장된 응답이 있습니다 (덮어쓰려면 그대로 저장하세요)" if done else "⬜ 아직 저장된 응답이 없습니다"
        self.manual_paste_status_label.config(text=f"{status}   |   전체 {saved}/{total}개 저장됨")

    def _manual_on_paste_select(self, event=None):
        self._manual_update_paste_status()

    def _manual_save_pasted_response(self):
        if not self.manual_files:
            messagebox.showerror("오류", "판결문 파일을 먼저 선택하세요.")
            return
        if not self.responses_dir.get():
            messagebox.showerror("오류", "응답을 저장할 폴더를 먼저 선택하세요.")
            return
        name = self.manual_paste_combo.get()
        source = self._manual_file_by_name(name)
        if source is None:
            messagebox.showerror("오류", "저장할 판결문을 목록에서 선택하세요.")
            return
        content = self.manual_paste_text.get("1.0", "end").strip()
        if not content:
            messagebox.showerror("오류", "claude.ai에서 받은 응답을 먼저 붙여넣으세요.")
            return

        responses_dir = Path(self.responses_dir.get())
        responses_dir.mkdir(parents=True, exist_ok=True)
        out_path = responses_dir / f"{source.stem}.json"
        out_path.write_text(content, encoding="utf-8")

        try:
            parse_json_response(content)
            self._log(f"저장됨: {out_path.name} (JSON 형식 확인됨)", "ok")
        except Exception as e:
            self._log(f"저장은 했지만 JSON 형식이 아닌 것 같습니다: {out_path.name} — {e}", "warn")
            messagebox.showwarning(
                "확인 필요",
                f"{out_path.name}로 저장은 했지만, 내용이 올바른 JSON 형식인지 확인이 필요합니다.\n"
                "claude.ai 응답 전체(설명 문구 없이 JSON 부분)를 다시 붙여넣어 보세요.",
            )

        self.manual_paste_text.delete("1.0", "end")

        names = [f.name for f in self.manual_files]
        not_done = [n for n in names if not self._manual_response_exists(self._manual_file_by_name(n))]
        if not_done:
            self.manual_paste_combo.set(not_done[0])
        self._manual_update_paste_status()

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
        self.manual_prompts_btn.config(state="disabled")
        threading.Thread(target=self._manual_make_prompts_worker, daemon=True).start()

    def _manual_make_prompts_worker(self):
        try:
            files = list(self.manual_files)
            self._init_stats(len(files))
            self._set_mode_status("수동 모드: 판결문마다 claude.ai용 프롬프트를 만들고 있습니다.")
            out_dir = Path(self.prompts_dir.get())
            self._log(f"{len(files)}개 파일의 프롬프트를 만듭니다...")
            made = 0
            for f in files:
                try:
                    out = make_prompt_file(f, out_dir)
                    self._log(f"  {f.name} -> {out.name}", "ok")
                    made += 1
                    self._bump_stat("done")
                except NotJudgmentLikelyError as e:
                    self._log(f"  건너뜀: {e}", "warn")
                    self._bump_stat("skipped")
                except TextExtractError as e:
                    self._log(f"  실패: {e}", "err")
                    self._bump_stat("failed")
            self._log(f"완료: {made}개 프롬프트 파일을 {out_dir} 에 만들었습니다.", "ok")
            self._log("각 .prompt.txt 내용을 claude.ai에 붙여넣고, 받은 JSON 응답을 같은 이름(.json)으로 저장하세요.", "warn")
        except Exception as e:
            self._log(f"예상치 못한 오류로 중단됨: {e}", "err")
            self._show_error(f"프롬프트 파일을 만드는 중 오류가 발생했습니다.\n{e}")
        finally:
            self.after(0, lambda: self.manual_prompts_btn.config(state="normal"))

    def _manual_pick_response_files_for_import(self):
        paths = filedialog.askopenfilenames(
            title="claude.ai 응답 파일 선택 (여러 개 가능)",
            filetypes=[("JSON/텍스트 파일", "*.json *.txt"), ("모든 파일", "*.*")],
        )
        if not paths:
            return
        for p in paths:
            path = Path(p)
            self.manual_response_files[path.stem] = path
        n = len(self.manual_response_files)
        self.manual_response_files_label.config(text=f"{n}개 파일 선택됨 (폴더 대신 사용)")

    def _manual_clear_response_files_for_import(self):
        self.manual_response_files = {}
        self.manual_response_files_label.config(text="")

    def _manual_import(self):
        if not self.manual_files:
            messagebox.showerror("오류", "판결문 파일을 먼저 선택하세요 (1단계와 동일한 파일이어야 합니다).")
            return
        if not self.manual_template_path.get() or not self.manual_output_path.get():
            messagebox.showerror("오류", "코딩시트 템플릿과 결과 저장 위치를 선택하세요.")
            return
        if not self.responses_dir.get() and not self.manual_response_files:
            messagebox.showerror(
                "오류",
                "claude.ai 응답을 지정하세요 — '응답(.json) 폴더'를 선택하거나, "
                "'또는 응답 파일 개별 선택'으로 파일을 직접 골라도 됩니다.",
            )
            return
        self.manual_import_btn.config(state="disabled")
        threading.Thread(target=self._manual_import_worker, daemon=True).start()

    def _manual_import_worker(self):
        try:
            files = list(self.manual_files)
            self._init_stats(len(files))
            self._set_mode_status("수동 모드: 저장된 응답들을 엑셀로 합치고 있습니다.")

            use_files = bool(self.manual_response_files)
            if use_files:
                self._log(f"{len(files)}개 파일의 응답을 불러옵니다 (개별 선택한 {len(self.manual_response_files)}개 파일 사용)...")
            else:
                responses_dir = Path(self.responses_dir.get())
                self._log(f"{len(files)}개 파일의 응답을 불러옵니다 (응답 폴더: {responses_dir})...")

            rows = []
            for f in files:
                try:
                    if use_files:
                        match = self.manual_response_files.get(f.stem)
                        if match is None:
                            raise LLMExtractError(
                                f"{f.name}: 개별 선택한 파일 중 이름이 같은 응답('{f.stem}.json' 등)이 없습니다."
                            )
                        extracted = read_response_file(match)
                    else:
                        extracted = load_response(f, Path(self.responses_dir.get()))
                    rows.append(build_row(f, extracted, coder_id=self.manual_coder_id.get()))
                    self._log(f"  불러옴: {f.name}", "ok")
                    self._bump_stat("done")
                except LLMExtractError as e:
                    self._log(f"  건너뜀: {e}", "warn")
                    self._bump_stat("skipped")

            if rows:
                self._safe_write_rows(
                    Path(self.manual_template_path.get()), Path(self.manual_output_path.get()), rows
                )
            else:
                where = (
                    f"개별 선택한 {len(self.manual_response_files)}개 파일 중"
                    if use_files else f"'{self.responses_dir.get()}' 폴더에"
                )
                msg = (
                    "불러올 수 있는 응답이 없어 엑셀을 만들지 못했습니다.\n\n"
                    "위 '진행 상황' 로그에 파일마다 건너뛴 이유가 표시되어 있습니다. 자주 있는 원인:\n"
                    f"1) 응답 파일 이름이 판결문과 다름 — '판결문1.pdf'의 응답은 반드시 "
                    f"{where} '판결문1.json' 이라는 이름으로 있어야 합니다.\n"
                    "2) claude.ai 답변이 JSON 형식이 아님 — 답변에 설명 문구나 거절 메시지가 섞여 있으면 "
                    "안 됩니다. JSON 객체만 붙여넣거나, 응답 전체를 그대로 붙여넣어 보세요."
                )
                self._log("저장할 결과가 없습니다. 로그의 개별 건너뜀 사유를 확인하세요.", "warn")
                self._show_error(msg)
        except Exception as e:
            self._log(f"예상치 못한 오류로 중단됨: {e}", "err")
            self._show_error(f"엑셀로 합치는 중 오류가 발생했습니다.\n{e}")
        finally:
            self.after(0, lambda: self.manual_import_btn.config(state="normal"))

    # ---------- 요약 + 로그 (공통, 화면 오른쪽) ----------
    def _build_log_card(self, parent):
        stats_outer, stats_card = self._card(parent)
        stats_outer.pack(fill="x", pady=(0, 10))
        self._section_header(stats_card, "📊", "작업 요약")

        tiles = tk.Frame(stats_card, bg=CARD_BG)
        tiles.pack(fill="x")
        self.stat_total_label = self._stat_tile(tiles, "총 파일", TEXT, "#f1f3f9")
        self.stat_done_label = self._stat_tile(tiles, "완료", SUCCESS, "#dcfce7")
        self.stat_skipped_label = self._stat_tile(tiles, "건너뜀", WARN_COLOR, "#fef9c3")
        self.stat_failed_label = self._stat_tile(tiles, "실패", DANGER, "#fee2e2")

        self.mode_status_label = ttk.Label(stats_card, text="", style="Muted.TLabel", wraplength=280)
        self.mode_status_label.pack(anchor="w", pady=(10, 0))

        result_btn_row = tk.Frame(stats_card, bg=CARD_BG)
        result_btn_row.pack(fill="x", pady=(8, 0))
        self.open_result_btn = tk.Button(
            result_btn_row, text="📊  결과 파일 열기",
            font=(_FONT, 10, "bold"), bg=ACCENT, fg="white",
            relief="flat", bd=0, padx=10, pady=6, cursor="hand2",
            activebackground=ACCENT_DARK, activeforeground="white",
            command=self._open_result_file, state="disabled",
        )
        self.open_result_btn.pack(side="left")
        self.open_result_folder_btn = tk.Button(
            result_btn_row, text="📁  폴더 열기",
            font=(_FONT, 10), bg="#e8eaf6", fg=TEXT,
            relief="flat", bd=0, padx=10, pady=6, cursor="hand2",
            activebackground="#d1d5fa", activeforeground=TEXT,
            command=self._open_result_folder, state="disabled",
        )
        self.open_result_folder_btn.pack(side="left", padx=(6, 0))
        self._last_result_path: Path | None = None

        outer, card = self._card(parent)
        outer.pack(fill="both", expand=True)

        self._section_header(card, "▶", "진행 상황")
        self.log = scrolledtext.ScrolledText(
            card, height=10, font=("Menlo", 10), bg="#0d1117", fg="#e6edf3",
            insertbackground="#e6edf3", relief="flat", padx=12, pady=10, wrap="word",
        )
        self.log.pack(fill="both", expand=True)
        self.log.tag_config("warn", foreground="#e3b341")
        self.log.tag_config("err", foreground="#ff7b72")
        self.log.tag_config("ok", foreground="#3fb950")

    def _stat_tile(self, parent, label, color, bg_color) -> tk.Label:
        tile = tk.Frame(parent, bg=bg_color, padx=12, pady=10)
        tile.pack(side="left", expand=True, fill="x", padx=(0, 6))
        value_label = tk.Label(tile, text="0", bg=bg_color, fg=color,
                               font=(_FONT, 22, "bold"))
        value_label.pack(anchor="w")
        tk.Label(tile, text=label, bg=bg_color, fg=TEXT_MUTED,
                 font=(_FONT, 10)).pack(anchor="w")
        return value_label

    # ---------- 작업 요약 카운터 ----------
    def _init_stats(self, total: int):
        self._stats = {"total": total, "done": 0, "skipped": 0, "failed": 0}
        self.after(0, self._refresh_stats_labels)

    def _bump_stat(self, key: str):
        self._stats[key] = self._stats.get(key, 0) + 1
        self.after(0, self._refresh_stats_labels)

    def _refresh_stats_labels(self):
        s = self._stats
        self.stat_total_label.config(text=str(s["total"]))
        self.stat_done_label.config(text=str(s["done"]))
        self.stat_skipped_label.config(text=str(s["skipped"]))
        self.stat_failed_label.config(text=str(s["failed"]))

    def _set_mode_status(self, text: str):
        self.after(0, lambda: self.mode_status_label.config(text=text))

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
