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
    stem = stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return " ".join([w if any(c.isdigit() for c in w) else w.capitalize() for w in stem.split()])

def load_deck(deck_path: str) -> List[TextQuestion]:
    if not os.path.exists(deck_path):
        raise FileNotFoundError(f"Deck file not found: {deck_path}")

    with open(deck_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        raise ValueError("Deck JSON must be a list of question objects.")

    questions: List[TextQuestion] = []
    for i, obj in enumerate(raw):
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
    return questions


# ----------------------------
# Deck Picker Dialog
# ----------------------------

class DeckPickerDialog(QDialog):
    def __init__(self, decks: List[Path], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} – Deck auswählen")
        self.resize(520, 420)

        self._decks = decks
        self.selected_path: Optional[Path] = None

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
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.list.addItem(item)

        if self.list.count() > 0:
            self.list.setCurrentRow(0)

        self.list.itemDoubleClicked.connect(self._accept_selected)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_selected(self):
        item = self.list.currentItem()
        if not item:
            return
        p = Path(item.data(Qt.ItemDataRole.UserRole))
        self.selected_path = p
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
    def __init__(self, deck_path: Path):
        super().__init__()

        self.setWindowTitle(APP_NAME)
        self.resize(980, 680)

        self.deck_path = deck_path
        self.deck_file = deck_path.name

        self.questions: List[TextQuestion] = load_deck(str(self.deck_path))
        self.q_by_id: Dict[str, TextQuestion] = {q.id: q for q in self.questions}

        self.queue: List[str] = [q.id for q in self.questions]
        random.shuffle(self.queue)

        self.mastered: set[str] = set()
        self.attempts: Dict[str, int] = {q.id: 0 for q in self.questions}
        self.fail_counts: Dict[str, int] = {q.id: 0 for q in self.questions}
        self.points: Dict[str, int] = {q.id: -1 for q in self.questions}

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
        self.deck_label = QLabel(f"Deck: {pretty_deck_name(self.deck_file)}")
        self.deck_label.setStyleSheet("font-size: 13px; color: #555;")
        top.addWidget(self.deck_label)

        top.addStretch(1)

        self.progress_text = QLabel("")
        self.progress_text.setStyleSheet("font-size: 13px; color: #555;")
        top.addWidget(self.progress_text)

        layout.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v / %m bestanden")
        self.progress.setMinimum(0)
        self.progress.setMaximum(len(self.questions))
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
        self.question_label.setStyleSheet("color: #222;")
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

    def _update_progress(self):
        total = len(self.questions)
        done = len(self.mastered)
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.progress_text.setText(f"Progress: {done}/{total}")

    def _load_current(self):
        self._update_progress()

        if len(self.mastered) == len(self.questions):
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
            remaining = [q.id for q in self.questions if q.id not in self.mastered]
            random.shuffle(remaining)
            self.queue = remaining[:]

        self.current_id = self.queue[0]
        q = self.q_by_id[self.current_id]

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
                rubric_lines.append(f"✅ {label}  (matched: '{m}')")
            else:
                rubric_lines.append(f"❌ {label}")

        right = "Rubrik-Details:\n" + "\n".join(rubric_lines)
        return left, right

    def on_check(self):
        if not self.current_id:
            return

        q = self.q_by_id[self.current_id]

        # darf leer sein
        user_text = self.text.toPlainText()

        self.attempts[self.current_id] += 1
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
            self.fail_counts[self.current_id] += 1
            if self.queue and self.queue[0] == self.current_id:
                self.queue.pop(0)
            self.queue.append(self.current_id)

        self._update_progress()

        sol = q.example.strip() if q.example else "(keine Beispielantwort hinterlegt)"
        self.solution_view.setText("LÖSUNG:\n" + sol)

        self.check_btn.setDisabled(True)
        self.next_btn.setEnabled(True)

    def on_next(self):
        self._load_current()

    def on_reset(self):
        resp = QMessageBox.question(self, APP_NAME, "Session wirklich zurücksetzen?")
        if resp != QMessageBox.StandardButton.Yes:
            return

        self.queue = [q.id for q in self.questions]
        random.shuffle(self.queue)

        self.mastered.clear()
        self.attempts = {q.id: 0 for q in self.questions}
        self.fail_counts = {q.id: 0 for q in self.questions}
        self.points = {q.id: -1 for q in self.questions}

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
    if picker.exec() != QDialog.DialogCode.Accepted or not picker.selected_path:
        return

    try:
        win = LumioMainWindow(picker.selected_path)
    except Exception as e:
        QMessageBox.critical(None, APP_NAME, f"Fehler beim Laden des Decks:\n{e}")
        return

    win.show()
    app.exec()


if __name__ == "__main__":
    main()
