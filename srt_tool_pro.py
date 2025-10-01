#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
import sqlite3
import threading
import queue
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "SRT Glossary Tool"
APP_DB   = "history.db"
APP_CONF = "config.json"
APP_GLOSSARY = "glossary.json"

# ==========================
# Data models & persistence
# ==========================
@dataclass
class GlossaryRule:
    pattern: str
    replace: str
    enabled: bool = True
    notes: str = ""

class GlossaryManager:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.rules: list[GlossaryRule] = []
        self.load()

    def load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.rules = [GlossaryRule(**r) for r in data.get("rules", [])]
            except Exception:
                self.rules = []
        else:
            # default seed
            self.rules = [
                GlossaryRule(pattern=r"(?i)(?<![A-Za-zÀ-ỹ])hình\s*ảnh(?![A-Za-zÀ-ỹ])|(?<![A-Za-zÀ-ỹ])hinh\s*anh(?![A-Za-zÀ-ỹ])", replace="Image", enabled=True, notes="hình ảnh -> Image"),
                GlossaryRule(pattern=r"(?i)(?<![A-Za-zÀ-ỹ])nút(?![A-Za-zÀ-ỹ])|(?<![A-Za-zÀ-ỹ])nut(?![A-Za-zÀ-ỹ])", replace="node", enabled=True, notes="nút -> node"),
                GlossaryRule(pattern=r"(?i)(?<![A-Za-zÀ-ỹ])thùng\s*chứa(?![A-Za-zÀ-ỹ])|(?<![A-Za-zÀ-ỹ])thùng\s*chưa(?![A-Za-zÀ-ỹ])|(?<![A-Za-zÀ-ỹ])thung\s*chua(?![A-Za-zÀ-ỹ])", replace="container", enabled=True, notes="thùng chứa -> container"),
            ]
            self.save()

    def save(self):
        payload = {"rules": [asdict(r) for r in self.rules]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_json(self, file: Path):
        data = json.loads(Path(file).read_text(encoding="utf-8"))
        rules = data["rules"] if isinstance(data, dict) and "rules" in data else data
        self.rules = [GlossaryRule(**r) for r in rules]
        self.save()

    def export_json(self, file: Path):
        payload = {"rules": [asdict(r) for r in self.rules]}
        Path(file).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

class HistoryDB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._init()

    def _init(self):
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TEXT NOT NULL,
              root TEXT NOT NULL,
              recursive INTEGER NOT NULL,
              dry_run INTEGER NOT NULL,
              backup INTEGER NOT NULL,
              files_total INTEGER NOT NULL,
              files_changed INTEGER NOT NULL,
              rules_active INTEGER NOT NULL,
              log TEXT
            );
            """)
            con.commit()

    def add_run(self, *, ts, root, recursive, dry_run, backup, files_total, files_changed, rules_active, log):
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("""INSERT INTO runs (ts, root, recursive, dry_run, backup, files_total, files_changed, rules_active, log)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (ts, root, int(recursive), int(dry_run), int(backup),
                         files_total, files_changed, rules_active, log))
            con.commit()

    def list_runs(self, limit=200):
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("""SELECT id, ts, root, recursive, dry_run, backup, files_total, files_changed, rules_active
                           FROM runs ORDER BY id DESC LIMIT ?""", (limit,))
            return cur.fetchall()

    def get_log(self, run_id: int):
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("SELECT log FROM runs WHERE id=?", (run_id,))
            row = cur.fetchone()
            return row[0] if row else ""

# ==========================
# Core SRT processing
# ==========================
TIMECODE_RE = re.compile(r"^\s*\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}\s*$")

def is_timecode_line(line: str) -> bool:
    return bool(TIMECODE_RE.match(line))

def is_index_line(line: str) -> bool:
    return line.strip().isdigit()

def detect_encoding(path: Path):
    tried = []
    for enc in ("utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be", "cp1258"):
        try:
            text = path.read_text(encoding=enc)
            return enc, text
        except Exception as e:
            tried.append((enc, str(e)))
    raise UnicodeError(f"Không đọc được file {path} với các encoding: {', '.join(enc for enc,_ in tried)}")

def write_backup(path: Path):
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        bak.write_bytes(path.read_bytes())
    return bak

def revert_from_backup(path: Path) -> bool:
    """Revert file từ backup .bak về file gốc"""
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        return False
    try:
        path.write_bytes(bak.read_bytes())
        return True
    except Exception:
        return False

def find_backup_files(root: Path, recursive: bool) -> list[Path]:
    """Tìm tất cả file .bak trong folder"""
    root = Path(root)
    if recursive:
        return list(root.rglob("*.bak"))
    else:
        return list(root.glob("*.bak"))

def clean_backup_files(root: Path, recursive: bool) -> tuple[int, int]:
    """Xoá tất cả file .bak, trả về (số file đã xoá, số file lỗi)"""
    backup_files = find_backup_files(root, recursive)
    deleted = 0
    errors = 0
    for bak in backup_files:
        try:
            bak.unlink()
            deleted += 1
        except Exception:
            errors += 1
    return deleted, errors

def apply_glossary(line: str, rules: list[GlossaryRule]) -> str:
    new_line = line
    for r in rules:
        if r.enabled and r.pattern and r.replace is not None:
            try:
                new_line = re.sub(r.pattern, r.replace, new_line)
            except re.error as e:
                # skip invalid regex
                pass
    return new_line

def process_srt_text(content: str, rules: list[GlossaryRule]) -> str:
    out_lines = []
    for line in content.splitlines(keepends=False):
        if is_index_line(line) or is_timecode_line(line) or line.strip() == "":
            out_lines.append(line)
        else:
            out_lines.append(apply_glossary(line, rules))
    return "\n".join(out_lines) + ("\n" if content.endswith("\n") else "")

def iter_srt_files(root: Path, recursive: bool):
    root = Path(root)
    if root.is_file() and root.suffix.lower() == ".srt":
        yield root
    elif recursive:
        yield from (p for p in root.rglob("*.srt") if p.is_file())
    else:
        yield from (p for p in root.glob("*.srt") if p.is_file())

# ==========================
# GUI
# ==========================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("900x620")
        self.minsize(880, 600)

        # state
        self.folder_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=True)
        self.dryrun_var = tk.BooleanVar(value=False)
        self.backup_var = tk.BooleanVar(value=True)

        self.glossary = GlossaryManager(Path(APP_GLOSSARY))
        self.history = HistoryDB(Path(APP_DB))

        self._stop_flag = threading.Event()
        self._worker_thread = None
        self._log_queue = queue.Queue()

        self._build_ui()
        self.after(100, self._poll_log_queue)

    # ---------- UI build ----------
    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self.tab_run = ttk.Frame(nb)
        self.tab_gloss = ttk.Frame(nb)
        self.tab_hist = ttk.Frame(nb)
        self.tab_settings = ttk.Frame(nb)

        nb.add(self.tab_run, text="Run")
        nb.add(self.tab_gloss, text="Glossary")
        nb.add(self.tab_hist, text="History")
        nb.add(self.tab_settings, text="Settings")

        self._build_run_tab()
        self._build_gloss_tab()
        self._build_hist_tab()
        self._build_settings_tab()

    # ---------- Run tab ----------
    def _build_run_tab(self):
        top = ttk.Frame(self.tab_run, padding=12)
        top.pack(fill="x")

        ttk.Label(top, text="Folder .srt:").pack(side="left")
        ent = ttk.Entry(top, textvariable=self.folder_var)
        ent.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="Browse…", command=self._browse).pack(side="left")
        ttk.Button(top, text="Dán đường dẫn", command=self._paste_path).pack(side="left", padx=(6, 0))

        opts = ttk.Frame(self.tab_run, padding=(12, 6))
        opts.pack(fill="x")
        ttk.Checkbutton(opts, text="Đệ quy (subfolders)", variable=self.recursive_var).pack(side="left")
        ttk.Checkbutton(opts, text="Dry-run (không ghi file)", variable=self.dryrun_var).pack(side="left", padx=(12, 0))
        ttk.Checkbutton(opts, text="Tạo backup *.bak", variable=self.backup_var).pack(side="left", padx=(12, 0))

        # active rules counter
        self.lbl_rules = ttk.Label(opts, text="")
        self.lbl_rules.pack(side="right")
        self._update_active_rules_label()

        pr = ttk.Frame(self.tab_run, padding=(12, 6))
        pr.pack(fill="x")
        self.progress = ttk.Progressbar(pr, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", expand=True, side="left")
        self.lbl_prog = ttk.Label(pr, text="0 / 0")
        self.lbl_prog.pack(side="left", padx=8)

        btns = ttk.Frame(self.tab_run, padding=(12, 6))
        btns.pack(fill="x")
        self.btn_start = ttk.Button(btns, text="Start", command=self._start)
        self.btn_stop  = ttk.Button(btns, text="Stop", command=self._stop, state="disabled")
        self.btn_start.pack(side="left")
        self.btn_stop.pack(side="left", padx=6)
        
        # Backup management buttons
        ttk.Separator(btns, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(btns, text="Revert từ .bak", command=self._revert_backups).pack(side="left", padx=(0,6))
        ttk.Button(btns, text="Xoá .bak files", command=self._clean_backups).pack(side="left")
        
        ttk.Button(btns, text="Mở folder", command=self._open_folder).pack(side="right")

        # log
        frm_log = ttk.LabelFrame(self.tab_run, text="Log", padding=8)
        frm_log.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self.txt_log = tk.Text(frm_log, height=20, wrap="word")
        self.txt_log.pack(fill="both", expand=True, side="left")
        yscroll = ttk.Scrollbar(frm_log, orient="vertical", command=self.txt_log.yview)
        yscroll.pack(side="right", fill="y")
        self.txt_log.configure(yscrollcommand=yscroll.set)
        self.txt_log.insert("end", "Tip: copy đường dẫn rồi bấm “Dán đường dẫn”.\n")

    # ---------- Glossary tab ----------
    def _build_gloss_tab(self):
        bar = ttk.Frame(self.tab_gloss, padding=12)
        bar.pack(fill="x")
        ttk.Button(bar, text="Thêm rule", command=self._add_rule_dialog).pack(side="left")
        ttk.Button(bar, text="Sửa rule", command=self._edit_selected_rule).pack(side="left", padx=6)
        ttk.Button(bar, text="Xoá rule", command=self._delete_selected_rule).pack(side="left")
        ttk.Button(bar, text="Bật/Tắt", command=self._toggle_selected_rule).pack(side="left", padx=(6,0))
        ttk.Button(bar, text="Up", command=lambda: self._move_rule(-1)).pack(side="right")
        ttk.Button(bar, text="Down", command=lambda: self._move_rule(1)).pack(side="right")

        io = ttk.Frame(self.tab_gloss, padding=(12,0))
        io.pack(fill="x")
        ttk.Button(io, text="Import JSON…", command=self._import_glossary).pack(side="left")
        ttk.Button(io, text="Export JSON…", command=self._export_glossary).pack(side="left", padx=6)
        ttk.Button(io, text="Reset mặc định", command=self._reset_glossary).pack(side="left")

        # table
        frm = ttk.Frame(self.tab_gloss, padding=12)
        frm.pack(fill="both", expand=True)

        cols = ("enabled", "pattern", "replace", "notes")
        self.tree = ttk.Treeview(frm, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("enabled", text="On")
        self.tree.heading("pattern", text="Pattern (regex)")
        self.tree.heading("replace", text="Replace")
        self.tree.heading("notes", text="Notes")

        self.tree.column("enabled", width=40, anchor="center")
        self.tree.column("pattern", width=420)
        self.tree.column("replace", width=180)
        self.tree.column("notes", width=200)

        self.tree.pack(fill="both", expand=True, side="left")
        y = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview)
        y.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=y.set)

        self._reload_tree()

    # ---------- History tab ----------
    def _build_hist_tab(self):
        top = ttk.Frame(self.tab_hist, padding=12)
        top.pack(fill="x")
        ttk.Button(top, text="Refresh", command=self._reload_history).pack(side="left")

        frm = ttk.Frame(self.tab_hist, padding=12)
        frm.pack(fill="both", expand=True)

        cols = ("id", "ts", "root", "recursive", "dry_run", "backup", "files_total", "files_changed", "rules_active")
        self.hist_tree = ttk.Treeview(frm, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            self.hist_tree.heading(c, text=c)
        self.hist_tree.column("id", width=60, anchor="center")
        self.hist_tree.column("ts", width=150)
        self.hist_tree.column("root", width=300)
        self.hist_tree.column("recursive", width=80, anchor="center")
        self.hist_tree.column("dry_run", width=80, anchor="center")
        self.hist_tree.column("backup", width=80, anchor="center")
        self.hist_tree.column("files_total", width=90, anchor="e")
        self.hist_tree.column("files_changed", width=100, anchor="e")
        self.hist_tree.column("rules_active", width=90, anchor="e")
        self.hist_tree.pack(fill="both", expand=True, side="left")

        y = ttk.Scrollbar(frm, orient="vertical", command=self.hist_tree.yview)
        y.pack(side="right", fill="y")
        self.hist_tree.configure(yscrollcommand=y.set)

        # log preview
        bottom = ttk.LabelFrame(self.tab_hist, text="Log của lần chạy đã chọn", padding=8)
        bottom.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self.hist_log = tk.Text(bottom, height=10, wrap="word")
        self.hist_log.pack(fill="both", expand=True)
        self.hist_tree.bind("<<TreeviewSelect>>", self._show_selected_history_log)

        self._reload_history()

    # ---------- Settings tab ----------
    def _build_settings_tab(self):
        frm = ttk.Frame(self.tab_settings, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="File cấu hình & dữ liệu:").grid(row=0, column=0, sticky="w")
        ttk.Label(frm, text=f"- Glossary: {Path(APP_GLOSSARY).resolve()}").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Label(frm, text=f"- History DB: {Path(APP_DB).resolve()}").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Label(frm, text="Gợi ý regex tiếng Việt:\nSử dụng rào chữ: (?<![A-Za-zÀ-ỹ]) ... (?![A-Za-zÀ-ỹ]) để match nguyên từ có dấu/không dấu.\nVí dụ: (?i)(?<![A-Za-zÀ-ỹ])nút(?![A-Za-zÀ-ỹ])|(?<![A-Za-zÀ-ỹ])nut(?![A-Za-zÀ-ỹ])").grid(row=3, column=0, sticky="w", pady=8)

    # ---------- Actions ----------
    def _browse(self):
        path = filedialog.askdirectory()
        if path:
            self.folder_var.set(path)

    def _paste_path(self):
        try:
            txt = self.clipboard_get().strip().strip('"')
            if txt:
                self.folder_var.set(txt)
        except tk.TclError:
            messagebox.showwarning("Clipboard", "Không lấy được đường dẫn từ clipboard.")

    def _open_folder(self):
        p = self.folder_var.get().strip()
        if not p: return
        pth = Path(p)
        if not pth.exists():
            messagebox.showwarning("Mở folder", "Đường dẫn không tồn tại.")
            return
        try:
            if os.name == "nt":
                os.startfile(str(pth))
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(pth)])
        except Exception as e:
            messagebox.showerror("Mở folder", str(e))

    def _revert_backups(self):
        root = self.folder_var.get().strip()
        if not root:
            messagebox.showwarning("Thiếu folder", "Hãy chọn hoặc nhập đường dẫn folder chứa .srt và .bak.")
            return
        
        p = Path(root)
        if not p.exists():
            messagebox.showerror("Lỗi", f"Không tìm thấy: {p}")
            return

        recursive = self.recursive_var.get()
        backup_files = find_backup_files(p, recursive)
        
        if not backup_files:
            messagebox.showinfo("Revert", "Không tìm thấy file .bak nào.")
            return

        # Show confirmation with list of files
        file_list = "\n".join([f"• {bak.name} -> {bak.with_suffix('').name}" for bak in backup_files[:10]])
        if len(backup_files) > 10:
            file_list += f"\n... và {len(backup_files) - 10} file khác"
        
        msg = f"Tìm thấy {len(backup_files)} file .bak.\nRevert tất cả về file gốc?\n\n{file_list}"
        if not messagebox.askyesno("Xác nhận Revert", msg):
            return

        # Perform revert
        success = 0
        errors = 0
        error_details = []
        
        for bak in backup_files:
            original = bak.with_suffix('')  # Remove .bak extension
            try:
                if revert_from_backup(original):
                    success += 1
                else:
                    errors += 1
                    error_details.append(f"Không thể revert {bak.name}")
            except Exception as e:
                errors += 1
                error_details.append(f"Lỗi revert {bak.name}: {str(e)}")

        # Show results
        result_msg = f"Revert hoàn tất:\n• Thành công: {success} file\n• Lỗi: {errors} file"
        if error_details:
            result_msg += f"\n\nChi tiết lỗi:\n" + "\n".join(error_details[:5])
            if len(error_details) > 5:
                result_msg += f"\n... và {len(error_details) - 5} lỗi khác"
        
        if errors == 0:
            messagebox.showinfo("Revert thành công", result_msg)
        else:
            messagebox.showwarning("Revert hoàn tất với lỗi", result_msg)

    def _clean_backups(self):
        root = self.folder_var.get().strip()
        if not root:
            messagebox.showwarning("Thiếu folder", "Hãy chọn hoặc nhập đường dẫn folder chứa .bak files.")
            return
        
        p = Path(root)
        if not p.exists():
            messagebox.showerror("Lỗi", f"Không tìm thấy: {p}")
            return

        recursive = self.recursive_var.get()
        backup_files = find_backup_files(p, recursive)
        
        if not backup_files:
            messagebox.showinfo("Clean Backup", "Không tìm thấy file .bak nào.")
            return

        # Show confirmation with list of files
        file_list = "\n".join([f"• {bak.name}" for bak in backup_files[:15]])
        if len(backup_files) > 15:
            file_list += f"\n... và {len(backup_files) - 15} file khác"
        
        msg = f"Tìm thấy {len(backup_files)} file .bak.\nXoá tất cả?\n\n{file_list}\n\n⚠️ Hành động này không thể hoàn tác!"
        if not messagebox.askyesno("Xác nhận Xoá Backup", msg):
            return

        # Perform cleanup
        deleted, errors = clean_backup_files(p, recursive)
        
        # Show results
        result_msg = f"Xoá backup hoàn tất:\n• Đã xoá: {deleted} file\n• Lỗi: {errors} file"
        
        if errors == 0:
            messagebox.showinfo("Xoá backup thành công", result_msg)
        else:
            messagebox.showwarning("Xoá backup hoàn tất với lỗi", result_msg)

    def _start(self):
        root = self.folder_var.get().strip()
        if not root:
            messagebox.showwarning("Thiếu folder", "Hãy chọn hoặc nhập đường dẫn folder chứa .srt.")
            return
        p = Path(root)
        if not p.exists():
            messagebox.showerror("Lỗi", f"Không tìm thấy: {p}")
            return

        self._stop_flag.clear()
        self._set_running(True)
        self.txt_log.delete("1.0", "end")
        self._append_log(f"=== Bắt đầu: {p} ===\n")

        recursive = self.recursive_var.get()
        dryrun = self.dryrun_var.get()
        backup = self.backup_var.get()
        active_rules = [r for r in self.glossary.rules if r.enabled]

        self._worker_thread = threading.Thread(
            target=self._worker_run,
            args=(p, recursive, dryrun, backup, active_rules),
            daemon=True
        )
        self._worker_thread.start()

    def _stop(self):
        self._stop_flag.set()
        self._append_log("Đang dừng...\n")

    def _set_running(self, running: bool):
        self.btn_start.config(state="disabled" if running else "normal")
        self.btn_stop.config(state="normal" if running else "disabled")

    def _append_log(self, msg: str):
        self.txt_log.insert("end", msg)
        self.txt_log.see("end")

    def _poll_log_queue(self):
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _worker_run(self, root: Path, recursive: bool, dryrun: bool, backup: bool, rules: list[GlossaryRule]):
        files = list(iter_srt_files(root, recursive))
        total = len(files)
        changed = 0
        self.progress.config(maximum=max(1, total), value=0)
        self.lbl_prog.config(text=f"0 / {total}")

        run_log_lines = []
        try:
            for i, srt in enumerate(files, start=1):
                if self._stop_flag.is_set():
                    self._log_queue.put("Đã dừng bởi người dùng.\n")
                    break
                try:
                    enc, original = detect_encoding(srt)
                    transformed = process_srt_text(original, rules)
                    if transformed != original:
                        if not dryrun:
                            if backup:
                                write_backup(srt)
                            srt.write_text(transformed, encoding="utf-8")
                        changed += 1
                        msg = f"[CHANGED] {srt}\n"
                    else:
                        msg = f"[OK]      {srt}\n"
                    self._log_queue.put(msg)
                    run_log_lines.append(msg.strip())
                except Exception as e:
                    err = f"[ERROR]   {srt} -> {e}\n"
                    self._log_queue.put(err)
                    run_log_lines.append(err.strip())

                self.progress.after(0, self.progress.config, {"value": i})
                self.lbl_prog.after(0, self.lbl_prog.config, {"text": f"{i} / {total}"})

            summary = f"\nTổng: {total} file, đã thay đổi: {changed}. {'(dry-run)' if dryrun else ''}\n"
            self._log_queue.put(summary)
            run_log_lines.append(summary.strip())

            # save history
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.history.add_run(
                ts=ts,
                root=str(root),
                recursive=recursive,
                dry_run=dryrun,
                backup=backup,
                files_total=total,
                files_changed=changed,
                rules_active=len(rules),
                log="\n".join(run_log_lines)
            )
        finally:
            self.after(0, self._set_running, False)
            self.after(0, self._reload_history)

    # ---------- Glossary helpers ----------
    def _reload_tree(self):
        self.tree.delete(*self.tree.get_children())
        for idx, r in enumerate(self.glossary.rules):
            self.tree.insert("", "end", iid=str(idx), values=("✓" if r.enabled else "", r.pattern, r.replace, r.notes))
        self._update_active_rules_label()

    def _update_active_rules_label(self):
        total = len(self.glossary.rules)
        on = sum(1 for r in self.glossary.rules if r.enabled)
        self.lbl_rules.config(text=f"Rules đang bật: {on}/{total}")

    def _selected_rule_index(self):
        sel = self.tree.selection()
        if not sel: return None
        return int(sel[0])

    def _add_rule_dialog(self):
        RuleDialog(self, title="Thêm rule", on_ok=self._add_rule).show()

    def _add_rule(self, pattern, replace, enabled, notes):
        self.glossary.rules.append(GlossaryRule(pattern=pattern, replace=replace, enabled=enabled, notes=notes))
        self.glossary.save()
        self._reload_tree()

    def _edit_selected_rule(self):
        idx = self._selected_rule_index()
        if idx is None:
            messagebox.showinfo("Chú ý", "Chọn 1 rule để sửa.")
            return
        r = self.glossary.rules[idx]
        RuleDialog(self, title="Sửa rule", rule=r, on_ok=lambda p, rep, en, no: self._edit_rule(idx, p, rep, en, no)).show()

    def _edit_rule(self, idx, pattern, replace, enabled, notes):
        self.glossary.rules[idx].pattern = pattern
        self.glossary.rules[idx].replace = replace
        self.glossary.rules[idx].enabled = enabled
        self.glossary.rules[idx].notes = notes
        self.glossary.save()
        self._reload_tree()

    def _delete_selected_rule(self):
        idx = self._selected_rule_index()
        if idx is None: return
        if messagebox.askyesno("Xác nhận", "Xoá rule đã chọn?"):
            self.glossary.rules.pop(idx)
            self.glossary.save()
            self._reload_tree()

    def _toggle_selected_rule(self):
        idx = self._selected_rule_index()
        if idx is None: return
        self.glossary.rules[idx].enabled = not self.glossary.rules[idx].enabled
        self.glossary.save()
        self._reload_tree()

    def _move_rule(self, step):
        idx = self._selected_rule_index()
        if idx is None: return
        new_idx = idx + step
        if not (0 <= new_idx < len(self.glossary.rules)): return
        self.glossary.rules[idx], self.glossary.rules[new_idx] = self.glossary.rules[new_idx], self.glossary.rules[idx]
        self.glossary.save()
        self._reload_tree()
        self.tree.selection_set(str(new_idx))

    def _import_glossary(self):
        f = filedialog.askopenfilename(title="Chọn file JSON", filetypes=[("JSON","*.json")])
        if not f: return
        try:
            self.glossary.import_json(Path(f))
            self._reload_tree()
            messagebox.showinfo("Import", "Import glossary thành công.")
        except Exception as e:
            messagebox.showerror("Import lỗi", str(e))

    def _export_glossary(self):
        f = filedialog.asksaveasfilename(title="Lưu JSON", defaultextension=".json", filetypes=[("JSON","*.json")])
        if not f: return
        try:
            self.glossary.export_json(Path(f))
            messagebox.showinfo("Export", "Đã export glossary.")
        except Exception as e:
            messagebox.showerror("Export lỗi", str(e))

    def _reset_glossary(self):
        if messagebox.askyesno("Xác nhận", "Reset về bộ rule mặc định?"):
            if Path(APP_GLOSSARY).exists():
                Path(APP_GLOSSARY).unlink(missing_ok=True)
            self.glossary.load()
            self._reload_tree()

    # ---------- History helpers ----------
    def _reload_history(self):
        self.hist_tree.delete(*self.hist_tree.get_children())
        for row in self.history.list_runs(limit=200):
            # row: id, ts, root, recursive, dry_run, backup, files_total, files_changed, rules_active
            self.hist_tree.insert("", "end", iid=str(row[0]), values=row)

    def _show_selected_history_log(self, evt=None):
        sel = self.hist_tree.selection()
        if not sel: return
        run_id = int(sel[0])
        log = self.history.get_log(run_id)
        self.hist_log.delete("1.0", "end")
        self.hist_log.insert("end", log)

# ---------- Rule Dialog ----------
class RuleDialog(tk.Toplevel):
    def __init__(self, master, title="Rule", rule: GlossaryRule|None=None, on_ok=None):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.grab_set()
        self.resizable(width=True, height=False)

        self.var_pattern = tk.StringVar(value=rule.pattern if rule else "")
        self.var_replace = tk.StringVar(value=rule.replace if rule else "")
        self.var_enabled = tk.BooleanVar(value=rule.enabled if rule else True)
        self.txt_notes = None
        self.on_ok = on_ok

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Pattern (regex):").grid(row=0, column=0, sticky="w")
        ent_p = ttk.Entry(frm, textvariable=self.var_pattern, width=80)
        ent_p.grid(row=1, column=0, sticky="we", columnspan=2, pady=(0,8))

        ttk.Label(frm, text="Replace:").grid(row=2, column=0, sticky="w")
        ent_r = ttk.Entry(frm, textvariable=self.var_replace, width=80)
        ent_r.grid(row=3, column=0, sticky="we", columnspan=2, pady=(0,8))

        ttk.Checkbutton(frm, text="Enable", variable=self.var_enabled).grid(row=4, column=0, sticky="w", pady=(0,8))

        ttk.Label(frm, text="Notes:").grid(row=5, column=0, sticky="w")
        self.txt_notes = tk.Text(frm, height=4, width=80)
        self.txt_notes.grid(row=6, column=0, columnspan=2, sticky="we")
        if rule and rule.notes:
            self.txt_notes.insert("end", rule.notes)

        btns = ttk.Frame(frm)
        btns.grid(row=7, column=0, columnspan=2, sticky="e", pady=(10,0))
        ttk.Button(btns, text="Cancel", command=self._cancel).pack(side="right")
        ttk.Button(btns, text="OK", command=self._ok).pack(side="right", padx=6)

        self.columnconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)

    def _ok(self):
        pattern = self.var_pattern.get().strip()
        replace = self.var_replace.get()
        enabled = self.var_enabled.get()
        notes = self.txt_notes.get("1.0","end").strip()
        if not pattern:
            messagebox.showwarning("Thiếu pattern", "Pattern (regex) không được để trống.")
            return
        try:
            re.compile(pattern)
        except re.error as e:
            if not messagebox.askyesno("Regex lỗi", f"Regex không hợp lệ:\n{e}\n\nVẫn lưu rule này?"):
                return
        if self.on_ok:
            self.on_ok(pattern, replace, enabled, notes)
        self.destroy()

    def _cancel(self):
        self.destroy()

# ==========================
# Main
# ==========================
def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
