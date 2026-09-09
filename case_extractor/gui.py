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
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from case_extractor.cli import process_file
from case_extractor.excel_writer import write_rows
from case_extractor.llm_extract import LLMExtractError, parse_json_response
from case_extractor.manual_mode import build_row, load_response, make_prompt_file, read_response_file
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
        self.geometry("1180x760")
        self.configure(bg=BG)
        self.minsize(980, 620)

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
        self.manual_response_files: dict[str, Path] = {}  # stem -> path, 엑셀 합치기 단계에서 폴더 대신 파일 개별 선택 시 사용
        self.manual_output_path = tk.StringVar()
        self.manual_coder_id = tk.StringVar()

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
        style.configure("TLabel", background=BG, font=FONT_BASE)
        style.configure("Card.TLabel", background=CARD_BG, font=FONT_BASE)
        style.configure("Muted.TLabel", background=CARD_BG, font=FONT_BASE, foreground=TEXT_MUTED)
        style.configure("Title.TLabel", background=BG, font=FONT_TITLE)
        style.configure("Section.TLabel", background=CARD_BG, font=FONT_BOLD, foreground="#111827")
        style.configure("Info.TLabel", background=CARD_BG, font=("Helvetica", 10), foreground=TEXT_MUTED)
        style.configure("TEntry", padding=6)
        style.configure("TCheckbutton", background=CARD_BG, font=FONT_BASE)
        style.configure(
            "ModeOn.TButton", font=("Helvetica", 13, "bold"), padding=(18, 14),
            background=ACCENT, foreground="white", borderwidth=0,
        )
        style.map("ModeOn.TButton", background=[("active", ACCENT_DARK)])

        style.configure(
            "ModeOff.TButton", font=("Helvetica", 13, "bold"), padding=(18, 14),
            background="#e5e7eb", foreground="#374151", borderwidth=0,
        )
        style.map("ModeOff.TButton", background=[("active", "#d1d5db")])

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

        ttk.Label(root, text="판례 코딩시트 변환기", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            root,
            text="판결문(PDF/DOCX)을 넣으면 코딩시트 엑셀 항목을 자동으로 채워줍니다.",
            style="TLabel", foreground=TEXT_MUTED,
        ).pack(anchor="w", pady=(2, 14))

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
        row = ttk.Frame(parent, style="TFrame")
        row.pack(fill="x")

        self.mode_api_btn = ttk.Button(
            row, text="🔑  API 모드\nAPI 키로 자동 처리", style="ModeOn.TButton",
            command=lambda: self._set_mode("api"),
        )
        self.mode_api_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.mode_manual_btn = ttk.Button(
            row, text="✂️  수동 모드\nAPI 키 없이 claude.ai 채팅 이용", style="ModeOff.TButton",
            command=lambda: self._set_mode("manual"),
        )
        self.mode_manual_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        self.mode_desc_label = ttk.Label(parent, text="", style="TLabel", foreground=TEXT_MUTED)
        self.mode_desc_label.pack(anchor="w", pady=(8, 0))

    def _set_mode(self, mode: str):
        self.mode = mode
        if mode == "api":
            self.mode_api_btn.configure(style="ModeOn.TButton")
            self.mode_manual_btn.configure(style="ModeOff.TButton")
            self.manual_container.pack_forget()
            self.api_container.pack(fill="both", expand=True)
            self.mode_desc_label.config(
                text="현재 선택: API 모드 — Anthropic API 키가 있으면 버튼 한 번으로 끝까지 자동 처리합니다 (사용량만큼 별도 과금)."
            )
        else:
            self.mode_manual_btn.configure(style="ModeOn.TButton")
            self.mode_api_btn.configure(style="ModeOff.TButton")
            self.api_container.pack_forget()
            self.manual_container.pack(fill="both", expand=True)
            self.mode_desc_label.config(
                text="현재 선택: 수동 모드 — API 키 없이, 이미 쓰는 claude.ai 채팅에 복사/붙여넣기로 진행합니다 (추가 비용 없음)."
            )

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
            self._log("주의: AI가 추출한 값이므로 coding_note에 [AI 추출] 표시가 된 행은 원문과 대조 검수하세요.", "warn")
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

    def _show_error(self, message: str):
        self.after(0, lambda: messagebox.showerror("오류", message))

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
                "③ 받은 답변 전체(JSON)를 복사해서, 아래 '응답 붙여넣어 저장하기'에 붙여넣고 "
                "저장 버튼을 누르면 파일명을 신경 쓰지 않아도 자동으로 올바른 이름으로 저장됩니다.\n"
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
        ttk.Label(card3, text="2. 프롬프트 파일 만들기", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self._labeled_path_row(card3, "프롬프트 저장 폴더", self.prompts_dir, self._manual_pick_prompts_dir)
        self.manual_prompts_btn = ttk.Button(card3, text="📝  프롬프트 파일 만들기", style="Accent.TButton",
                                             command=self._manual_make_prompts)
        self.manual_prompts_btn.pack(anchor="w", pady=(6, 0))

        # 응답 붙여넣어 저장하기
        outer_paste, card_paste = self._card(parent)
        outer_paste.pack(fill="x", pady=(0, 12))
        ttk.Label(card_paste, text="3. 응답 붙여넣어 저장하기", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self._labeled_path_row(card_paste, "응답 저장 폴더", self.responses_dir, self._manual_pick_responses_dir)

        ttk.Label(
            card_paste,
            style="Info.TLabel",
            text="이미 다른 곳에서 만들어 둔 .json 응답 파일이 있다면, 폴더에 미리 옮겨둘 필요 없이 "
                 "아래 버튼으로 바로 추가할 수 있습니다 (파일명이 판결문과 같아야 합니다).",
            wraplength=520, justify="left",
        ).pack(anchor="w", pady=(0, 4))
        ttk.Button(card_paste, text="📄  이미 있는 JSON 파일 추가", style="Ghost.TButton",
                   command=self._manual_add_response_files).pack(anchor="w", pady=(0, 10))

        select_row = ttk.Frame(card_paste, style="Card.TFrame")
        select_row.pack(fill="x", pady=(4, 6))
        ttk.Label(select_row, text="판결문 선택", style="Card.TLabel", width=18).pack(side="left")
        self.manual_paste_combo = ttk.Combobox(select_row, state="readonly", width=40)
        self.manual_paste_combo.pack(side="left", fill="x", expand=True)
        self.manual_paste_combo.bind("<<ComboboxSelected>>", self._manual_on_paste_select)

        self.manual_paste_status_label = ttk.Label(card_paste, text="", style="Muted.TLabel")
        self.manual_paste_status_label.pack(anchor="w", pady=(0, 6))

        self.manual_paste_text = scrolledtext.ScrolledText(
            card_paste, height=8, font=("Menlo", 10), bg="#fafafa", relief="flat",
            highlightthickness=1, highlightbackground="#e5e7eb", padx=8, pady=6,
        )
        self.manual_paste_text.pack(fill="both", expand=True, pady=(0, 8))

        paste_btn_row = ttk.Frame(card_paste, style="Card.TFrame")
        paste_btn_row.pack(fill="x")
        ttk.Button(paste_btn_row, text="💾  저장하고 다음 판결문으로", style="Accent.TButton",
                   command=self._manual_save_pasted_response).pack(side="left")
        ttk.Button(paste_btn_row, text="지우기", style="Ghost.TButton",
                   command=lambda: self.manual_paste_text.delete("1.0", "end")).pack(side="left", padx=8)

        # 2단계
        outer4, card4 = self._card(parent)
        outer4.pack(fill="x", pady=(0, 0))
        ttk.Label(card4, text="4. 응답을 엑셀로 합치기", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self._labeled_path_row(card4, "코딩시트 템플릿 (xlsx)", self.manual_template_path, self._manual_pick_template)
        self._labeled_path_row(card4, "응답(.json) 폴더", self.responses_dir, self._manual_pick_responses_dir)

        or_row = ttk.Frame(card4, style="Card.TFrame")
        or_row.pack(fill="x", pady=(0, 8))
        ttk.Label(or_row, text="", width=18).pack(side="left")
        ttk.Button(or_row, text="또는 응답 파일 개별 선택", style="Ghost.TButton",
                   command=self._manual_pick_response_files_for_import).pack(side="left")
        ttk.Button(or_row, text="선택 지우기", style="Ghost.TButton",
                   command=self._manual_clear_response_files_for_import).pack(side="left", padx=8)
        self.manual_response_files_label = ttk.Label(or_row, text="", style="Muted.TLabel")
        self.manual_response_files_label.pack(side="left", padx=8)

        self._labeled_path_row(card4, "결과 저장 위치 (xlsx)", self.manual_output_path, self._manual_pick_output)

        row = ttk.Frame(card4, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="코딩 담당자 ID", style="Card.TLabel", width=18).pack(side="left")
        ttk.Entry(row, textvariable=self.manual_coder_id, width=16).pack(side="left")

        self.manual_import_btn = ttk.Button(card4, text="📊  엑셀로 합치기", style="Accent.TButton",
                                            command=self._manual_import)
        self.manual_import_btn.pack(anchor="w", pady=(6, 0))

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
        self._manual_refresh_paste_combo()

    def _manual_clear_files(self):
        self.manual_files = []
        self.manual_file_count_label.config(text="선택된 파일 없음")
        self._manual_refresh_paste_combo()

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
        ttk.Label(stats_card, text="현재 작업 요약", style="Section.TLabel").pack(anchor="w", pady=(0, 8))

        tiles = ttk.Frame(stats_card, style="Card.TFrame")
        tiles.pack(fill="x")
        self.stat_total_label = self._stat_tile(tiles, "총 파일", "#111827")
        self.stat_done_label = self._stat_tile(tiles, "완료", "#16a34a")
        self.stat_skipped_label = self._stat_tile(tiles, "건너뜀", "#d97706")
        self.stat_failed_label = self._stat_tile(tiles, "실패", "#dc2626")

        self.mode_status_label = ttk.Label(stats_card, text="", style="Muted.TLabel", wraplength=280)
        self.mode_status_label.pack(anchor="w", pady=(10, 0))

        outer, card = self._card(parent)
        outer.pack(fill="both", expand=True)

        ttk.Label(card, text="진행 상황", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.log = scrolledtext.ScrolledText(
            card, height=10, font=("Menlo", 10), bg="#0f172a", fg="#e2e8f0",
            insertbackground="#e2e8f0", relief="flat", padx=10, pady=8, wrap="word",
        )
        self.log.pack(fill="both", expand=True)
        self.log.tag_config("warn", foreground="#fbbf24")
        self.log.tag_config("err", foreground="#f87171")
        self.log.tag_config("ok", foreground="#4ade80")

    def _stat_tile(self, parent, label, color) -> ttk.Label:
        tile = ttk.Frame(parent, style="Card.TFrame")
        tile.pack(side="left", expand=True, fill="x")
        value_label = ttk.Label(tile, text="0", style="Card.TLabel", font=("Helvetica", 18, "bold"), foreground=color)
        value_label.pack(anchor="w")
        ttk.Label(tile, text=label, style="Muted.TLabel").pack(anchor="w")
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
