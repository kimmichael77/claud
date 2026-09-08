"""아주 간단한 macOS용 GUI. 터미널이 낯선 경우 이걸 실행하세요.

실행: python3 gui.py
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from case_extractor.coding_book import LLM_REQUESTED_FIELDS, SHEET_COLUMN_ORDER
from case_extractor.cli import process_file
from case_extractor.excel_writer import write_rows
from case_extractor.text_extract import TextExtractError, find_case_files
from case_extractor.llm_extract import LLMExtractError


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("판례 코딩시트 변환기")
        self.geometry("640x520")

        self.template_path = tk.StringVar()
        self.input_dir = tk.StringVar()
        self.output_path = tk.StringVar()
        self.coder_id = tk.StringVar()
        self.api_key = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))

        self._build_widgets()
        self._log_queue: queue.Queue[str] = queue.Queue()
        self.after(200, self._drain_log_queue)

    def _build_widgets(self):
        pad = {"padx": 10, "pady": 6}

        self._path_row("코딩시트 템플릿 (xlsx)", self.template_path, self._pick_template, pad)
        self._path_row("판결문 폴더 (PDF/DOCX)", self.input_dir, self._pick_input_dir, pad)
        self._path_row("결과 저장 위치 (xlsx)", self.output_path, self._pick_output, pad)

        row = ttk.Frame(self)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="코딩 담당자 ID (coder_id)").pack(side="left")
        ttk.Entry(row, textvariable=self.coder_id, width=15).pack(side="left", padx=8)

        row2 = ttk.Frame(self)
        row2.pack(fill="x", **pad)
        ttk.Label(row2, text="Anthropic API 키").pack(side="left")
        ttk.Entry(row2, textvariable=self.api_key, width=40, show="*").pack(side="left", padx=8)

        self.run_btn = ttk.Button(self, text="변환 시작", command=self._start)
        self.run_btn.pack(pady=10)

        self.log = scrolledtext.ScrolledText(self, height=18)
        self.log.pack(fill="both", expand=True, padx=10, pady=10)

    def _path_row(self, label, var, command, pad):
        row = ttk.Frame(self)
        row.pack(fill="x", **pad)
        ttk.Label(row, text=label, width=22).pack(side="left")
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row, text="선택", command=command).pack(side="left")

    def _pick_template(self):
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if path:
            self.template_path.set(path)
            if not self.output_path.get():
                p = Path(path)
                self.output_path.set(str(p.with_name(p.stem + "_결과.xlsx")))

    def _pick_input_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.input_dir.set(path)

    def _pick_output(self):
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if path:
            self.output_path.set(path)

    def _log(self, msg: str):
        self._log_queue.put(msg)

    def _drain_log_queue(self):
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self.log.insert("end", msg + "\n")
                self.log.see("end")
        except queue.Empty:
            pass
        self.after(200, self._drain_log_queue)

    def _start(self):
        if not self.template_path.get() or not self.input_dir.get() or not self.output_path.get():
            messagebox.showerror("오류", "템플릿/입력폴더/저장경로를 모두 선택하세요.")
            return
        if self.api_key.get():
            os.environ["ANTHROPIC_API_KEY"] = self.api_key.get()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            messagebox.showerror("오류", "Anthropic API 키를 입력하세요.")
            return

        self.run_btn.config(state="disabled")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            input_dir = Path(self.input_dir.get())
            files = find_case_files(input_dir)
            if not files:
                self._log("오류: 폴더에서 .pdf/.docx 파일을 찾지 못했습니다.")
                return

            self._log(f"총 {len(files)}개 파일 처리 시작...")
            rows = []
            for i, path in enumerate(files, start=1):
                self._log(f"[{i}/{len(files)}] {path.name} 처리 중...")
                try:
                    row = process_file(path, coder_id=self.coder_id.get(), model=None)
                    rows.append(row)
                except (TextExtractError, LLMExtractError) as e:
                    self._log(f"  실패: {e}")

            if rows:
                out = write_rows(Path(self.template_path.get()), Path(self.output_path.get()), rows)
                self._log(f"완료: {len(rows)}건을 {out} 에 저장했습니다.")
                self._log("주의: AI가 추출한 값이므로 coding_note에 [AI 추출] 표시가 된 행은 원문과 대조 검수하세요.")
            else:
                self._log("저장할 결과가 없습니다.")
        finally:
            self.run_btn.config(state="normal")


if __name__ == "__main__":
    App().mainloop()
