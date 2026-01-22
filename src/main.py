# lumio_qt.py
# Run: python lumio_qt.py
# Requirements: pip install PySide6
#
# Project layout:
#   src/main.py (or this file)
#   decks/
#     Mathe_fuer_Info_2.json
#     Key_Competences.json

import json
import os
import re
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import date
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QProgressBar,
    QMessageBox,
    QFrame,
    QSizePolicy,
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
)

APP_NAME = "Lumio"
DECKS_DIR = "decks"
PROGRESS_FILE = "progress.json"
DATA_DIR = "data"

# ----------------------------
# Data Model
# ----------------------------

@dataclass
class TextQuestion:
    id: str
    prompt: str
    rubric: List[List[str]]
    pass_ratio: float = 0.7
    min_words: int = 20
    max_repeats: int = 999999
    example: str = ""

@dataclass
class DeckMeta:
    title: Optional[str] = None
    due_date: Optional[date] = None

# ----------------------------
# Text Scoring
# ----------------------------

def normalize(text: str) -> str:
    t = text.strip().lower()
    t = (
        t.replace("ä", "ae")
         .replace("ö", "oe")
         .replace("ü", "ue")
         .replace("ß", "ss")
    )
    t = re.sub(r"[^\w\s=*+\-/<>()]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def word_count(norm_text: str) -> int:
    return 0 if not norm_text else len(norm_text.split())

def rubric_hits_details(rubric: List[List[str]], norm_text: str) -> Tuple[int, List[bool], List[Optional[str]]]:
    hits: List[bool] = []
    matched: List[Optional[str]] = []
    for group in rubric:
        found = None
        for phrase in group:
            if phrase in norm_text:
                found = phrase
                break
        ok = found is not None
        hits.append(ok)
        matched.append(found)
    return sum(hits), hits, matched

def compute_score(q: TextQuestion, user_text: str) -> Dict[str, Any]:
    norm = normalize(user_text)
    wc = word_count(norm)

    hit_count, hits, matched = rubric_hits_details(q.rubric, norm)
    total = max(len(q.rubric), 1)
    coverage = hit_count / total

    length_ok = wc >= q.min_words
    effective = coverage if length_ok else coverage * 0.85
    passed = (effective >= q.pass_ratio) and length_ok

    return {
        "word_count": wc,
        "hit_count": hit_count,
        "total": total,
        "coverage": coverage,
        "effective": effective,
        "passed": passed,
        "length_ok": length_ok,
        "hits": hits,
        "matched": matched,
    }

# ----------------------------
# Deck Loading / Paths
# ----------------------------

def project_root() -> Path:
    here = Path(__file__).resolve()
    for p in here.parents:
        if p.name == "src":
            return p.parent
    return here.parent

def decks_dir_path() -> Path:
    return project_root() / DECKS_DIR

def ensure_decks_dir() -> Path:
    d = decks_dir_path()
    d.mkdir(parents=True, exist_ok=True)
    return d

def list_decks(decks_dir: Path) -> List[Path]:
    return sorted([p for p in decks_dir.glob("*.json") if p.is_file()], key=lambda x: x.name.lower())

def pretty_deck_name(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[_-]+", " ", stem)       # Trenner -> Space
    stem = re.sub(r"\s+", " ", stem).strip() # Mehrfachspaces
    return stem

def load_deck(deck_path: str) -> Tuple[DeckMeta, List[TextQuestion]]:
    if not os.path.exists(deck_path):
        raise FileNotFoundError(f"Deck file not found: {deck_path}")

    with open(deck_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    meta = DeckMeta()
    items = None

    # Neues Format: {"meta": {...}, "questions": [...]}
    if isinstance(raw, dict):
        meta_obj = raw.get("meta", {})
        if isinstance(meta_obj, dict):
            title = meta_obj.get("title")
            if isinstance(title, str) and title.strip():
                meta.title = title.strip()

            due = meta_obj.get("due_date")
            if isinstance(due, str) and due.strip():
                try:
                    y, m, d = due.strip().split("-")
                    meta.due_date = date(int(y), int(m), int(d))
                except Exception:
                    raise ValueError(f"Invalid meta.due_date (expected YYYY-MM-DD): {due}")

        items = raw.get("questions")
        if not isinstance(items, list):
            raise ValueError("Deck JSON: 'questions' must be a list.")

    # Altes Format: [...]
    elif isinstance(raw, list):
        items = raw

    else:
        raise ValueError("Deck JSON must be a list OR an object with {meta, questions}.")

    questions: List[TextQuestion] = []
    for i, obj in enumerate(items):
        if not isinstance(obj, dict):
            raise ValueError(f"Question at index {i} is not an object.")
        if obj.get("type") != "text":
            continue

        qid = str(obj.get("id", f"q{i+1}"))
        prompt = obj.get("prompt")
        rubric = obj.get("rubric")

        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"Question '{qid}' missing/invalid 'prompt'.")
        if not isinstance(rubric, list) or not all(isinstance(g, list) and all(isinstance(p, str) for p in g) for g in rubric):
            raise ValueError(f"Question '{qid}' missing/invalid 'rubric'.")

        questions.append(
            TextQuestion(
                id=qid,
                prompt=prompt.strip(),
                rubric=rubric,
                pass_ratio=float(obj.get("pass_ratio", 0.7)),
                min_words=int(obj.get("min_words", 20)),
                max_repeats=int(obj.get("max_repeats", 999999)),
                example=str(obj.get("example", "")).strip(),
            )
        )

    if not questions:
        raise ValueError("No 'text' questions found in deck.")

    return meta, questions

def data_dir_path() -> Path:
    d = project_root() / DATA_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d

def progress_file_path() -> Path:
    return data_dir_path() / PROGRESS_FILE

def load_progress() -> dict:
    p = progress_file_path()
    if not p.exists():
        return {"version": 1, "decks": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "decks": {}}

def save_progress(db: dict) -> None:
    p = progress_file_path()
    p.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

def deck_key(deck_path: Path) -> str:
    # stabiler Key (relativ zum project root)
    try:
        return str(deck_path.resolve().relative_to(project_root().resolve())).replace("\\", "/")
    except Exception:
        return str(deck_path.resolve()).replace("\\", "/")

def deck_daily_quota(meta_due: Optional[date], remaining: int) -> int:
        if remaining <= 0:
            return 0
        if not meta_due:
            return 0  # ohne due_date keine Pflichtquote (oder setze Default)
        today = date.today()
        days_left = (meta_due - today).days
        if days_left <= 0:
            return remaining
        return int(math.ceil(remaining / days_left))

# ----------------------------
# Deck Picker Dialog
# ----------------------------

class DeckPickerDialog(QDialog):
    def __init__(self, decks: List[Path], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} – Deck auswählen")
        self.resize(520, 420)

        self._decks = decks

        layout = QVBoxLayout(self)

        title = QLabel("Wähle ein Deck:")
        tf = QFont()
        tf.setPointSize(12)
        tf.setBold(True)
        title.setFont(tf)
        layout.addWidget(title)

        self.list = QListWidget()
        self.list.setStyleSheet("font-size: 13px;")
        layout.addWidget(self.list)

        for p in decks:
            label = pretty_deck_name(p.name)
            try:
                m, _qs = load_deck(str(p))
                if m.title:
                    label = m.title
            except Exception:
                pass

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)



        if self.list.count() > 0:
            self.list.setCurrentRow(0)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_selected(self):
        selected = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(Path(item.data(Qt.ItemDataRole.UserRole)))
        if not selected:
            return
        self.selected_paths = selected
        self.accept()

# ----------------------------
# TextEdit: Enter=Submit, Shift+Enter=Newline
# ----------------------------

class SubmitTextEdit(QTextEdit):
    def __init__(self, on_submit, parent=None):
        super().__init__(parent)
        self._on_submit = on_submit

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Shift+Enter => normaler Zeilenumbruch
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                return super().keyPressEvent(e)
            # Enter => Submit (Check oder Next)
            self._on_submit()
            return
        return super().keyPressEvent(e)


# ----------------------------
# Main Window
# ----------------------------

class LumioMainWindow(QMainWindow):
    def __init__(self, deck_paths: List[Path]):
        super().__init__()

        self.setWindowTitle(APP_NAME)
        self.resize(980, 680)

        self.deck_paths = deck_paths

        # progress
        self.progress_db = load_progress()

        # multi-deck store
        self.decks: Dict[str, Dict[str, Any]] = {}          # dk -> {path, meta, questions}
        self.all_questions: Dict[str, TextQuestion] = {}    # gqid -> TextQuestion
        self.global_to_deck: Dict[str, str] = {}            # gqid -> dk

        for dp in self.deck_paths:
            dk = deck_key(dp)
            meta, questions = load_deck(str(dp))
            self.decks[dk] = {"path": dp, "meta": meta, "questions": questions}

            for q in questions:
                gqid = f"{dk}::{q.id}"
                self.all_questions[gqid] = q
                self.global_to_deck[gqid] = dk

        # state
        self.mastered: set[str] = set()
        self.attempts: Dict[str, int] = {}
        self.fail_counts: Dict[str, int] = {}
        self.points: Dict[str, int] = {}

        # load persisted state
        for gqid, q in self.all_questions.items():
            dk = self.global_to_deck[gqid]
            qid = q.id
            deck_entry = self.progress_db.get("decks", {}).get(dk, {})
            q_entry = deck_entry.get("questions", {}).get(qid, {})

            if bool(q_entry.get("mastered", False)):
                self.mastered.add(gqid)

            self.attempts[gqid] = int(q_entry.get("attempts", 0))
            self.fail_counts[gqid] = int(q_entry.get("fails", 0))
            self.points[gqid] = int(q_entry.get("points", -1))

        # today's pack
        self.queue: List[str] = self._build_daily_queue()
        self.today_set = set(self.queue)
        random.shuffle(self.queue)

        self.current_id: Optional[str] = None
        self.last_result: Optional[Dict[str, Any]] = None

        self._build_ui()
        self._load_current()

    def on_submit(self):
        # Enter: wenn Next enabled -> Next, sonst -> Check
        if self.next_btn.isEnabled():
            self.on_next()
        else:
            self.on_check()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        self.deck_label = QLabel(f"Decks: {len(self.deck_paths)} ausgewählt")
        self.deck_label.setStyleSheet("font-size: 13px; color: #AAA;")
        top.addWidget(self.deck_label)

        top.addStretch(1)

        self.progress_text = QLabel("")
        self.progress_text.setStyleSheet("font-size: 13px; color: #AAA;")
        top.addWidget(self.progress_text)

        layout.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v / %m bestanden")
        self.progress.setMinimum(0)
        self.progress.setMaximum(max(len(self.today_set), 1))
        self.progress.setValue(0)
        self.progress.setFixedHeight(22)
        layout.addWidget(self.progress)

        qbox = QFrame()
        qbox.setFrameShape(QFrame.Shape.StyledPanel)
        qbox.setStyleSheet("QFrame { background: #fafafa; border-radius: 12px; }")
        qbox_layout = QVBoxLayout(qbox)
        qbox_layout.setContentsMargins(16, 16, 16, 16)

        self.question_label = QLabel("")
        self.question_label.setWordWrap(True)
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        self.question_label.setFont(f)
        self.question_label.setStyleSheet("color: #333;")
        qbox_layout.addWidget(self.question_label)

        layout.addWidget(qbox)

        # Input (editable)
        self.text = SubmitTextEdit(self.on_submit)
        self.text.setPlaceholderText("Antwort eingeben …")
        self.text.setFixedHeight(150)
        self.text.setStyleSheet("font-size: 13px;")
        layout.addWidget(self.text)

        # Buttons
        btn_row = QHBoxLayout()

        self.check_btn = QPushButton("Check")
        self.check_btn.clicked.connect(self.on_check)
        btn_row.addWidget(self.check_btn)

        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.on_next)
        self.next_btn.setEnabled(False)
        btn_row.addWidget(self.next_btn)

        self.reset_btn = QPushButton("Reset Session")
        self.reset_btn.clicked.connect(self.on_reset)
        btn_row.addWidget(self.reset_btn)

        layout.addLayout(btn_row)

        # Feedback (2 columns)
        fb_row = QHBoxLayout()

        self.feedback_left = QLabel("")
        self.feedback_left.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.feedback_left.setWordWrap(True)
        self.feedback_left.setStyleSheet("font-size: 13px; color: #CCC;")
        self.feedback_left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.feedback_right = QLabel("")
        self.feedback_right.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.feedback_right.setWordWrap(True)
        self.feedback_right.setStyleSheet("font-size: 13px; color: #ccc;")
        self.feedback_right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        fb_row.addWidget(self.feedback_left, 1)
        fb_row.addWidget(self.feedback_right, 1)
        layout.addLayout(fb_row)

        # Solution always bottom
        self.solution_view = QLabel("")
        self.solution_view.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.solution_view.setWordWrap(True)
        self.solution_view.setStyleSheet("font-size: 13px; color: #ccc;")
        self.solution_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.solution_view)

        # Shortcuts (optional)
        self.check_btn.setShortcut("Ctrl+Return")
        self.next_btn.setShortcut("Ctrl+N")

    def _build_daily_queue(self) -> List[str]:
        qids = []
        for dk, d in self.decks.items():
            meta = d["meta"]
            qs: List[TextQuestion] = d["questions"]

            # remaining in deck
            total = len(qs)
            mastered_in_deck = sum(1 for q in qs if f"{dk}::{q.id}" in self.mastered)
            remaining = total - mastered_in_deck

            quota = deck_daily_quota(getattr(meta, "due_date", None), remaining)
            if quota <= 0:
                continue

            # Kandidaten: nicht mastered
            candidates = [f"{dk}::{q.id}" for q in qs if f"{dk}::{q.id}" not in self.mastered]
            random.shuffle(candidates)
            qids.extend(candidates[:quota])

        # Wenn gar keine due_dates gesetzt: fallback = alle offenen mischen (optional)
        if not qids:
            # fallback: einfach alles offene mischen
            qids = [gqid for gqid in self.all_questions.keys() if gqid not in self.mastered]
        return qids

    def _update_progress(self):
        # Tagesziel = len(queue)+mastered_today? -> Wir definieren: today's pack = self.today_set
        today_total = len(self.today_set)
        today_done = sum(1 for gqid in self.today_set if gqid in self.mastered)

        overall_total = len(self.all_questions)
        overall_done = len(self.mastered)

        self.progress.setMaximum(today_total if today_total > 0 else 1)
        self.progress.setValue(today_done)
        self.progress.setFormat("%v / %m heute bestanden")

        self.progress_text.setText(
            f"Heute: {today_done}/{today_total} | Gesamt: {overall_done}/{overall_total}"
        )

    def _load_current(self):
        self._update_progress()

        if len(self.mastered) == len(self.all_questions):
            self.current_id = None
            self.question_label.setText("Fertig. Alle Fragen bestanden.")
            self.text.setDisabled(True)
            self.check_btn.setDisabled(True)
            self.next_btn.setDisabled(True)
            self.feedback_left.setText("")
            self.feedback_right.setText("")
            self.solution_view.setText("")
            return

        while self.queue and (self.queue[0] in self.mastered):
            self.queue.pop(0)

        if not self.queue:
            # Tagespaket leer -> neu bauen
            self.queue = self._build_daily_queue()
            self.today_set = set(self.queue)
            random.shuffle(self.queue)

            if not self.queue:
                self.current_id = None
                self.question_label.setText("Keine offenen Fragen im Tagespaket.")
                return

        self.current_id = self.queue[0]
        q = self.all_questions[self.current_id]
        dk = self.global_to_deck[self.current_id]
        meta = self.decks[dk]["meta"]
        title = meta.title or pretty_deck_name(self.decks[dk]["path"].name)
        self.deck_label.setText(f"Aktuelles Deck: {title}")
        self.question_label.setText(q.prompt)
        self.text.clear()
        self.last_result = None

        self.feedback_left.setText("")
        self.feedback_right.setText("")
        self.solution_view.setText("")

        self.text.setDisabled(False)
        self.check_btn.setEnabled(True)
        self.next_btn.setEnabled(False)
        self.text.setFocus()


    def _format_feedback(self, q: TextQuestion, result: Dict[str, Any], points: Optional[int] = None) -> Tuple[str, str]:
        eff = result["effective"] * 100
        cov = result["coverage"] * 100
        status = "BESTANDEN" if result["passed"] else "NICHT BESTANDEN"

        length_line = f"Wörter: {result['word_count']} (min {q.min_words})"
        score_line = f"Score: {eff:.1f}% (Coverage {cov:.1f}%, benötigt >= {q.pass_ratio*100:.1f}%)"
        hits_line = f"Rubrik: {result['hit_count']}/{result['total']} Gruppen getroffen"
        points_line = f"Punkte: {points}" if points is not None else ""

        left_lines = [status, score_line, length_line, hits_line]
        if points_line:
            left_lines.append(points_line)
        left = "\n".join(left_lines).strip()

        hits = result.get("hits", [])
        matched = result.get("matched", [])
        rubric_lines = []
        for i, group in enumerate(q.rubric):
            ok = hits[i] if i < len(hits) else False
            m = matched[i] if i < len(matched) else None
            label = group[0] if group else f"Gruppe {i+1}"
            if ok:
                rubric_lines.append(f"Wort verwendet: {label}  (matched: '{m}')")
            else:
                rubric_lines.append(f"Es Fehlt: {label}")

        right = "Rubrik-Details:\n" + "\n".join(rubric_lines)
        return left, right

    def on_check(self):
        if not self.current_id:
            return

        q = self.all_questions[self.current_id]
        user_text = self.text.toPlainText()

        self.attempts[self.current_id] = self.attempts.get(self.current_id, 0) + 1
        result = compute_score(q, user_text)
        self.last_result = result

        pts = int(round(result["effective"] * 100))
        self.points[self.current_id] = pts

        left, right = self._format_feedback(q, result, points=pts)
        self.feedback_left.setText(left)
        self.feedback_right.setText(right)

        if result["passed"]:
            self.mastered.add(self.current_id)
            if self.queue and self.queue[0] == self.current_id:
                self.queue.pop(0)
        else:
            self.fail_counts[self.current_id] = self.fail_counts.get(self.current_id, 0) + 1
            if self.queue and self.queue[0] == self.current_id:
                self.queue.pop(0)
            self.queue.append(self.current_id)

        self._persist_question_state(self.current_id)
        self._update_progress()

        sol = q.example.strip() if q.example else "(keine Beispielantwort hinterlegt)"
        self.solution_view.setText("LÖSUNG:\n" + sol)

        self.check_btn.setDisabled(True)
        self.next_btn.setEnabled(True)

    def on_next(self):
        self._load_current()

    def _persist_question_state(self, gqid: str) -> None:
        q = self.all_questions[gqid]
        dk = self.global_to_deck[gqid]
        qid = q.id

        decks = self.progress_db.setdefault("decks", {})
        d = decks.setdefault(dk, {})
        qs = d.setdefault("questions", {})

        qs[qid] = {
            "mastered": (gqid in self.mastered),
            "attempts": int(self.attempts.get(gqid, 0)),
            "fails": int(self.fail_counts.get(gqid, 0)),
            "points": int(self.points.get(gqid, -1)),
            "updated_at": int(__import__("time").time()),
        }
        save_progress(self.progress_db)

    def on_reset(self):
        resp = QMessageBox.question(self, APP_NAME, "Heutiges Tagespaket neu würfeln?")
        if resp != QMessageBox.StandardButton.Yes:
            return

        self.queue = self._build_daily_queue()
        self.today_set = set(self.queue)
        random.shuffle(self.queue)

        self.check_btn.setEnabled(True)
        self.next_btn.setEnabled(False)
        self._load_current()


def main():
    app = QApplication([])

    ddir = ensure_decks_dir()
    decks = list_decks(ddir)
    if not decks:
        QMessageBox.critical(None, APP_NAME, f"Keine Decks gefunden in:\n{ddir}\nLege *.json Dateien in den Ordner.")
        return

    picker = DeckPickerDialog(decks)
    if picker.exec() != QDialog.DialogCode.Accepted or not picker.selected_paths:
        return

    try:
        win = LumioMainWindow(picker.selected_paths)
    except Exception as e:
        QMessageBox.critical(None, APP_NAME, f"Fehler beim Laden der Decks:\n{e}")
        return


    win.show()
    app.exec()


if __name__ == "__main__":
    main()
