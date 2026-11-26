"""Classcard Macro study automation engine (Tkinter-free).

Unifies upstream v2.0.1 improvements (multi-segment continuation, '/' chunking
fix, MAX_TEST_TRIES retry loop, human-like micro-delays & mode transition
delays, live progress polling) with origin features (set rest delay countdown,
configurable random wrong answers, test_only mode) plus selective mode
execution, pause/resume, structured activity log, and session statistics.
"""

from collections import deque
import json
import random
import re
import threading
import time
from typing import Any, Callable, Optional

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

import chrome_bridge
import config_store

MAX_TEST_TRIES = 3

MODE_ORDER = ('memorize', 'recall', 'spell')
MODE_PATH = {'memorize': 'Memorize', 'recall': 'Recall', 'spell': 'Spell'}
MODE_NAME = {'memorize': '암기', 'recall': '리콜', 'spell': '스펠', 'test': '테스트'}

_MEMORIZE_URL_HINT = '/memorize/'
_CLASS_TEST_URL_HINT = '/classtest/'
_STUDY_URL_HINTS = ('/memorize/', '/recall/', '/spell/', '/classtest/')

_SECTION_DONE_LABELS = ['다음 구간으로 이동', '다음 구간 이동', '계속하기']
_SECTION_NEXT_LABELS = ['다음 구간으로 이동', '다음 구간 이동']
_SECTION_AGAIN_LABELS = ['계속하기', '제출 결과 확인']
_TEST_DONE_LABELS = ['완료', '제출 결과 확인', '결과 확인']
_CANCEL_LABELS = ['취소']
_NEXT_CARD_LABELS = ['다음 카드', '다음카드', '다음 문제']
_SECTION_DONE_PATTERNS = [r'^\d+% ?도전$']
_WRITE_PRACTICE_LABELS = ['영작 연습하기']

_QUOTE_MAP = {
    '‘': "'",
    '’': "'",
    '“': '"',
    '”': '"',
}

# ── Shared JavaScript Helpers ────────────────────────────────────────────────

_JS_IS_VISIBLE = r"""
function isReallyVisible(e) {
  if (!document.hidden && typeof e.checkVisibility === 'function') {
    try { return e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}); }
    catch (err) {}
  }
  var r = e.getBoundingClientRect();
  if (!(r.width > 0 && r.height > 0)) return false;
  for (var n = e; n && n.nodeType === 1; n = n.parentElement) {
    var cs = getComputedStyle(n);
    if (cs.display === 'none' || cs.visibility === 'hidden' ||
        parseFloat(cs.opacity) === 0) return false;
  }
  return true;
}
"""

_JS_GEOMETRY = r"""
function clippedAway(el, cx, cy) {
  for (var a = el.parentElement; a && a !== document.body; a = a.parentElement) {
    var cs = getComputedStyle(a);
    if (/(hidden|clip|scroll|auto)/.test(cs.overflow + cs.overflowX + cs.overflowY)) {
      var ar = a.getBoundingClientRect();
      if (cx < ar.left || cx > ar.right || cy < ar.top || cy > ar.bottom) return true;
    }
  }
  return false;
}
function hitOk(el, cx, cy) {
  var hit = document.elementFromPoint(cx, cy);
  if (!hit) return false;
  if (hit === el || el.contains(hit)) return true;
  return hit !== document.body && hit !== document.documentElement && hit.contains(el);
}
"""

_VISIBLE_JS = _JS_IS_VISIBLE + r"""
var el = arguments[0];
return {text: (el.textContent || '').trim(), visible: isReallyVisible(el)};
"""

_FIND_INPUT_NEAR_JS = r"""
var el = arguments[0];
for (var levels = 0, node = el; levels < 8 && node; levels++, node = node.parentElement) {
  var inputs = node.querySelectorAll('input[name="input_answer"]');
  for (var i = 0; i < inputs.length; i++) {
    var r = inputs[i].getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return inputs[i];
  }
}
return null;
"""

_ON_SCREEN_JS = _JS_IS_VISIBLE + _JS_GEOMETRY + r"""
var sel = arguments[0];
var hitTest = arguments[1] !== false;
var W = window.innerWidth || document.documentElement.clientWidth;
var H = window.innerHeight || document.documentElement.clientHeight;
var out = [];
var nodes = document.querySelectorAll(sel);
for (var i = 0; i < nodes.length; i++) {
  var el = nodes[i];
  if (!isReallyVisible(el)) continue;
  var r = el.getBoundingClientRect();
  var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  if (cx < 0 || cx > W || cy < 0 || cy > H) continue;
  if (clippedAway(el, cx, cy)) continue;
  if (hitTest && !hitOk(el, cx, cy)) continue;
  var t = (el.textContent || '').trim();
  if (t) out.push({el: el, text: t});
}
return out;
"""

_QUESTION_WORD_JS = _JS_IS_VISIBLE + _JS_GEOMETRY + r"""
var vocab = arguments[0] || {};
var hitTest = arguments[1] !== false;
var W = window.innerWidth || document.documentElement.clientWidth;
var H = window.innerHeight || document.documentElement.clientHeight;
var out = [];
var nodes = document.querySelectorAll('body *');
for (var i = 0; i < nodes.length; i++) {
  var el = nodes[i];
  if (el.children.length) continue;
  var t = (el.textContent || '').replace(/\s+/g, ' ').trim();
  if (!t || t.length > 80) continue;
  if (!vocab[t] && !vocab[t.toLowerCase()]) continue;
  if (el.closest && el.closest('.cc-table.middle.fill-parent')) continue;
  if (!isReallyVisible(el)) continue;
  var r = el.getBoundingClientRect();
  var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  if (cx < 0 || cx > W || cy < 0 || cy > H) continue;
  if (clippedAway(el, cx, cy)) continue;
  if (hitTest && !hitOk(el, cx, cy)) continue;
  if (out.indexOf(t) === -1) out.push(t);
}
return out;
"""

_REFOCUS_JS = r"""
var a = document.activeElement;
if (a && a !== document.body && typeof a.blur === 'function') {
  try { a.blur(); } catch (e) {}
}
"""

_CHOICE_TAKEN_JS = _JS_IS_VISIBLE + r"""
var el = arguments[0], txt = arguments[1];
if (!el || !el.isConnected) return true;
var l = el.closest ? el.closest('label') : null;
if (l && l.control && l.control.checked) return true;
if ((el.textContent || '').trim() !== txt) return true;
return !isReallyVisible(el);
"""

_WAIT_WORD_SCREEN_JS = _JS_IS_VISIBLE + _JS_GEOMETRY + r"""
var wordSel = arguments[0], choiceSel = arguments[1];
var exclude = arguments[2] || [], timeoutMs = arguments[3] || 3000;
var done = arguments[arguments.length - 1];
function onScreen(sel, hitTest) {
  var W = window.innerWidth || document.documentElement.clientWidth;
  var H = window.innerHeight || document.documentElement.clientHeight;
  var out = [], nodes = document.querySelectorAll(sel);
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    if (!isReallyVisible(el)) continue;
    var r = el.getBoundingClientRect();
    var cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    if (cx < 0 || cx > W || cy < 0 || cy > H) continue;
    if (clippedAway(el, cx, cy)) continue;
    if (hitTest && !hitOk(el, cx, cy)) continue;
    var t = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (t) out.push(t);
  }
  return out;
}
var start = Date.now(), goneAt = 0;
(function tick() {
  try {
    if (onScreen(choiceSel, true).length) {
      goneAt = 0;
    } else {
      if (!goneAt) goneAt = Date.now();
      var all = onScreen(wordSel, false);
      var words = all.filter(function (t) { return exclude.indexOf(t) === -1; });
      if (!words.length && all.length && Date.now() - goneAt > 250) words = all;
      if (words.length) { done({ok: true, words: words}); return; }
    }
  } catch (e) {}
  if (Date.now() - start > timeoutMs) { done({ok: false, words: []}); return; }
  setTimeout(tick, 5);
})();
"""

_SCRAMBLE_JS = _JS_IS_VISIBLE + r"""
var nodes = document.querySelectorAll('.scramble-item, .btn-scramble, [class*="c2NyYW1i"]');
var parents = [], groups = [];
for (var i = 0; i < nodes.length; i++) {
  var el = nodes[i];
  var vis = isReallyVisible(el);
  var r = el.getBoundingClientRect();
  var cs = getComputedStyle(el);
  var p = el.parentElement;
  var idx = parents.indexOf(p);
  if (idx === -1) {
    parents.push(p);
    groups.push([]);
    idx = groups.length - 1;
  }
  groups[idx].push({
    el: el,
    text: (el.textContent || '').trim(),
    vis: vis,
    clk: el.classList.contains('clickable'),
    used: el.classList.contains('clicked') || /,\s*0\s*\)$/.test(cs.color),
    top: r.top
  });
}
return groups;
"""

_CLICK_CHIP_JS = r"""
var el = arguments[0];
var opts = {bubbles: true, cancelable: true, view: window, button: 0};
el.dispatchEvent(new MouseEvent('mouseover', opts));
el.dispatchEvent(new MouseEvent('mousedown', opts));
el.dispatchEvent(new MouseEvent('mouseup', opts));
el.dispatchEvent(new MouseEvent('click', opts));
"""

_PLACED_TEXT_JS = _JS_IS_VISIBLE + r"""
var CHIP = '.scramble-item, .btn-scramble, [class*="c2NyYW1i"]';
function isUsedChip(c) {
  if (c.classList.contains('clicked')) return true;
  try { return /,\s*0\s*\)$/.test(getComputedStyle(c).color); }
  catch (e) { return false; }
}
var out = [];
var nodes = document.querySelectorAll('div, span, p, td, li, h1, h2, h3, label');
for (var i = 0; i < nodes.length && out.length < 300; i++) {
  var el = nodes[i];
  if (el.closest && el.closest(CHIP)) continue;
  var inner = el.querySelectorAll(CHIP);
  var hasUnused = false;
  for (var j = 0; j < inner.length; j++) {
    if (!isUsedChip(inner[j])) { hasUnused = true; break; }
  }
  if (hasUnused) continue;
  var t = (el.textContent || '').replace(/\s+/g, ' ').trim();
  if (!t || t.length > 300) continue;
  if (!isReallyVisible(el)) continue;
  out.push(t);
}
var boxes = document.querySelectorAll('.input-box');
for (var b = 0; b < boxes.length; b++) {
  var box = boxes[b];
  var br = box.getBoundingClientRect();
  if (br.width <= 0 || br.height <= 0) continue;
  var words = [];
  for (var c = 0; c < box.children.length; c++) {
    var ch = box.children[c];
    if (ch.classList && ch.classList.contains('now')) continue;
    var ct = (ch.textContent || '').replace(/\s+/g, ' ').trim();
    if (!ct || /^[0-9]+\.$/.test(ct)) continue;
    words.push(ct);
  }
  if (words.length) out.push(words.join(' '));
}
return out;
"""

_UNARRANGED_WARNING_JS = r"""
var nodes = document.querySelectorAll('body *');
for (var i = 0; i < nodes.length; i++) {
  var el = nodes[i];
  if (el.children.length) continue;
  if ((el.textContent || '').indexOf('배열하지 않은') === -1) continue;
  var r = el.getBoundingClientRect();
  if (r.width > 0 && r.height > 0) return true;
}
return false;
"""

_EMPTY_STUDY_JS = r"""
var t = (document.body.innerText || '').replace(/\s+/g, ' ');
return /(^|\s)0\s*\/\s*0(\s|$)/.test(t);
"""

_FIND_TEXT_EL_JS = r"""
var want = arguments[0];
var els = document.querySelectorAll('a, div, label, span, button');
for (var i = 0; i < els.length; i++) {
  var e = els[i];
  if (e.children.length) continue;
  if ((e.textContent || '').replace(/\s+/g, ' ').trim() !== want) continue;
  var r = e.getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) continue;
  return e;
}
return null;
"""


# ── Pure Helpers (Text Normalization, Matching, Scoring) ─────────────────────

unique_cards = chrome_bridge.unique_cards


def strip_pos_tag(text: str) -> str:
  """Strip leading '[명] ' part-of-speech tag."""
  return re.sub(r'^\[[^\]]+\]\s*', '', text or '').strip()


def norm_space(text: str) -> str:
  """Collapse internal whitespace and strip ends."""
  return re.sub(r'\s+', ' ', text or '').strip()


def norm_quotes(text: str) -> str:
  """Normalize curly quotes to ASCII quotes and collapse whitespace."""
  out = norm_space(text)
  for src, dst in _QUOTE_MAP.items():
    out = out.replace(src, dst)
  return out


def norm_token(text: str) -> str:
  """Lowercase alphanumeric token normalization for scramble comparison."""
  t = norm_quotes(text).lower()
  cleaned = re.sub(r'[^0-9a-zÀ-ɏ]+', '', t)
  return cleaned or t.strip()


def case_token(text: str) -> str:
  """Case-preserving alphanumeric token normalization for chip tie-breaking."""
  t = norm_quotes(text)
  cleaned = re.sub(r'[^0-9A-Za-zÀ-ɏ]+', '', t)
  return cleaned or t.strip()


def norm_meaning(text: str) -> str:
  """Normalize Korean meaning separators for choice comparison."""
  t = norm_quotes(text).replace(';', ',').replace('·', ',')
  t = re.sub(r'\s*,\s*', ',', t)
  return t.strip().strip(',.')


def sentence_chunks(sentence: str) -> list[str]:
  """Split chunked sentences ('A / B') into [full, part1, part2, ...]."""
  parts = re.split(r'\s+/\s+', sentence or '')
  if len(parts) == 1:
    return [sentence]
  return [' '.join(parts)] + [part for part in parts if part.strip()]


def sentence_tokens(sentence: str) -> list[str]:
  """Tokenize an English sentence into normalized word tokens."""
  return [t for t in (norm_token(w) for w in norm_quotes(sentence).split()) if t]


def study_unit_count(cards) -> int:
  """Count total study units (chunked cards count per chunk)."""
  total = 0
  for card in cards or []:
    parts = sentence_chunks(card.get('eng', '') or '')
    total += len(parts) - 1 if len(parts) > 1 else 1
  return total


def pick_choice(choices, target: str):
  """Find matching choice (idx, el, text) for target answer."""
  target_norm = norm_space(target)
  target_stripped = strip_pos_tag(target_norm)
  target_meaning = norm_meaning(target_stripped)

  items = []
  for idx, (el, raw) in enumerate(choices):
    txt = norm_space(raw)
    if txt:
      stripped = strip_pos_tag(txt)
      items.append((idx, el, txt, stripped, norm_meaning(stripped)))

  for idx, el, txt, _, _ in items:
    if txt == target_norm:
      return idx, el, txt
  for idx, el, txt, stripped, _ in items:
    if target_stripped and stripped == target_stripped:
      return idx, el, txt
  for idx, el, txt, _, meaning in items:
    if target_meaning and meaning == target_meaning:
      return idx, el, txt
  for idx, el, txt, _, _ in items:
    if target_norm and (target_norm in txt or txt in target_norm):
      return idx, el, txt
  return None


def pick_wrong_choice(choices, target: str):
  """Pick a random incorrect choice (idx, el, text) from choices."""
  correct = pick_choice(choices, target)
  correct_idx = correct[0] if correct else -1
  wrongs = []
  for idx, (el, raw) in enumerate(choices):
    if idx == correct_idx:
      continue
    txt = norm_space(raw)
    if txt:
      wrongs.append((idx, el, txt))
  return random.choice(wrongs) if wrongs else None


def is_submultiset(chips: list[str], tokens: list[str]) -> bool:
  """Return True if every chip appears in tokens respecting multiplicity."""
  pool = list(tokens)
  for chip in chips:
    if chip in pool:
      pool.remove(chip)
    else:
      return False
  return True


def usable_items(items):
  """Filter out ellipsis ('...', '…') and empty scramble items."""
  return [
      (el, txt) for el, txt in items
      if norm_token(txt) and not re.fullmatch(r'[.\u2026]+', norm_quotes(txt).strip())
  ]


def chip_match_rank(chip_text: str, raw_word: Optional[str]) -> int:
  """Rank how closely chip_text matches raw_word (0=exact, 3=weakest)."""
  if not raw_word:
    return 2
  a = norm_quotes(chip_text).strip()
  b = norm_quotes(raw_word).strip()
  if a == b:
    return 0
  if case_token(a) == case_token(b):
    return 1
  if norm_token(a) == norm_token(b):
    return 2
  return 3


def next_token_index(tokens: list[str], chips: list[str], placed: Optional[int] = None) -> Optional[int]:
  """Locate the starting token index matching the visible scramble chip window."""
  n = len(chips)
  if n == 0 or n > len(tokens):
    return None
  wanted = sorted(chips)
  found = [
      k for k in range(len(tokens) - n + 1)
      if sorted(tokens[k:k + n]) == wanted
  ]
  if not found:
    return None
  if len(found) == 1 or placed is None:
    return found[0]
  if placed in found:
    return placed
  return None


def match_scramble_sentence(word_list: list[dict], groups):
  """Infer the active sentence card and token list from scramble chip groups."""
  usable = usable_items(groups[0]) if groups else []
  if not usable:
    return None
  chips = [norm_token(t) for _, t in usable]
  best = None
  best_tie = False

  for word in word_list:
    eng = word.get('eng', '')
    for cand in sentence_chunks(eng):
      tokens = sentence_tokens(cand)
      if not tokens or len(chips) > len(tokens):
        continue
      if not is_submultiset(chips, tokens):
        continue
      extra = len(tokens) - len(chips)
      if best is None or extra < best[0]:
        best = (extra, word, tokens, cand)
        best_tie = False
      elif extra == best[0]:
        if tokens != best[2]:
          best_tie = True
        elif (len(sentence_chunks(word.get('eng', '') or ''))
              > len(sentence_chunks(best[1].get('eng', '') or ''))):
          best = (extra, word, tokens, cand)

  if best is None or best_tie:
    return None
  _, word, tokens, source = best
  return usable, word, tokens, source


def parse_test_score(test) -> Optional[int]:
  """Extract integer score from a Classcard test result string, or None."""
  if not test:
    return None
  m = re.search(r'(\d+)\s*점', str(test))
  return int(m.group(1)) if m else None


def test_failed(test, cutoff=85) -> bool:
  """Return True if test result indicates FAIL or score below cutoff."""
  if not test:
    return False
  test_str = str(test)
  if re.search(r'fail|실패', test_str, re.I):
    return True
  if cutoff is None:
    cutoff = config_store.config_get('pass_score', 85)
  score = parse_test_score(test_str)
  if score is not None:
    return score < int(cutoff)
  return False


def format_test_text(test, cutoff=85) -> str:
  """Format a Classcard test result string into a concise Korean summary."""
  test = (test or '').strip()
  if not test:
    return '테스트 안 봄'
  when, _, rest = test.partition('|')
  day = (when.strip().split() or [''])[0]
  score = parse_test_score(rest or test)
  score_text = f'{score}점' if score is not None else ''
  tail = f' ({day})' if day else ''
  if test_failed(test, cutoff):
    label = '미달' if (score is not None and not re.search(r'fail|실패', test, re.I)) else '실패'
    return f'테스트 {score_text} {label}'.replace('  ', ' ') + tail
  if score_text:
    return f'테스트 {score_text}' + tail
  return '테스트 완료'


# ── StudyEngine ──────────────────────────────────────────────────────────────

class StudyEngine:
  """Thread-safe Classcard automation engine decoupled from UI toolkits."""

  def __init__(self):
    self._lock = threading.RLock()
    self._resume_event = threading.Event()
    self._resume_event.set()

    self.is_running = False
    self.auto_running = False
    self.paused = False
    self.memo_go = threading.Event()
    self.auto_mode_done = threading.Event()
    self.seg_finished = threading.Event()

    self.word_list: list[dict] = []
    self.loaded_set_idx: Optional[str] = None
    self.study_kind: str = 'word'
    self._last_list_sync = 0.0
    self._chip_click_native: dict[str, bool] = {}

    self.current_set_idx: Optional[str] = None
    self.current_set_name: str = ''
    self.current_mode: Optional[str] = None
    self.cards_total: int = 0
    self.cards_done: int = 0
    self.cards_seen: set[str] = set()
    self.site_done: int = 0
    self.site_total: int = 0
    self.auto_rest_remaining: int = 0
    self.auto_rest_total: int = 0

    self.status_text: str = '대기 중'
    self.status_color: str = '#7A7A7A'
    self.manual_status_text: str = '단어를 먼저 불러오세요.'
    self.manual_status_color: str = '#7A7A7A'
    self.waiting_memo_go: bool = False

    self.session_started_at: Optional[float] = None
    self.sets_completed: int = 0
    self.cards_solved: int = 0

    self.logs: deque[tuple[str, str, str]] = deque(maxlen=300)
    self._callbacks: dict[str, Optional[Callable[..., Any]]] = {}
    chrome_bridge.set_busy_checker(self._active)

  # ── Callbacks, Logging, Snapshot ───────────────────────────────────────────

  def set_callbacks(self, **callbacks: Optional[Callable[..., Any]]) -> None:
    """Register UI notification callbacks without importing Tkinter."""
    with self._lock:
      self._callbacks.update(callbacks)

  def _emit(self, name: str, *args, **kwargs) -> None:
    with self._lock:
      cb = self._callbacks.get(name)
    if cb:
      try:
        cb(*args, **kwargs)
      except Exception:
        pass

  def _log(self, level: str, message: str) -> None:
    ts = time.strftime('%H:%M:%S')
    entry = (ts, level, message)
    with self._lock:
      self.logs.append(entry)
    self._emit('on_log', entry)

  def get_logs(self, limit: Optional[int] = None, level: Optional[str] = None) -> list[tuple[str, str, str]]:
    """Return structured activity log entries (hh:mm:ss, level, message)."""
    with self._lock:
      entries = list(self.logs)
    if level and level != 'ALL':
      entries = [e for e in entries if e[1] == level]
    if limit is not None and limit > 0:
      entries = entries[-limit:]
    return entries

  def clear_logs(self) -> None:
    with self._lock:
      self.logs.clear()

  def _set_status(self, text: str, color: str = '#0066CC') -> None:
    with self._lock:
      self.status_text = text
      self.status_color = color
    self._emit('on_status', text, color)

  def _set_manual_status(self, text: str, color: str = '#0066CC') -> None:
    with self._lock:
      self.manual_status_text = text
      self.manual_status_color = color
    self._emit('on_manual_status', text, color)

  def _auto_log(self, text: str, color: str = '#0066CC', level: str = 'INFO') -> None:
    self._log(level, text)
    self._set_status(text, color)
    self._set_manual_status(text, color)

  def _emit_rate(self, set_idx, rates: dict) -> None:
    self._emit('on_rate_update', str(set_idx), dict(rates))

  def _notify_state(self) -> None:
    self._emit('on_state_change', self.snapshot())

  def snapshot(self) -> dict:
    """Return a thread-safe snapshot of engine state for UI rendering."""
    with self._lock:
      elapsed = (
          max(0.0, time.time() - self.session_started_at)
          if self.session_started_at
          else 0.0
      )
      return {
          'is_running': self.is_running,
          'auto_running': self.auto_running,
          'active': self.is_running or self.auto_running,
          'paused': self.paused,
          'waiting_memo_go': self.waiting_memo_go,
          'study_kind': self.study_kind,
          'word_count': len(self.word_list),
          'loaded_set_idx': self.loaded_set_idx,
          'current_set_idx': self.current_set_idx,
          'current_set_name': self.current_set_name,
          'current_mode': self.current_mode,
          'cards_total': self.cards_total,
          'cards_done': self.cards_done,
          'cards_seen': len(self.cards_seen),
          'site_done': self.site_done,
          'site_total': self.site_total,
          'auto_rest_remaining': self.auto_rest_remaining,
          'auto_rest_total': self.auto_rest_total,
          'status_text': self.status_text,
          'status_color': self.status_color,
          'manual_status_text': self.manual_status_text,
          'manual_status_color': self.manual_status_color,
          'session_started_at': self.session_started_at,
          'elapsed_seconds': elapsed,
          'sets_completed': self.sets_completed,
          'cards_solved': self.cards_solved,
      }

  # ── Control: Pause / Resume / Stop / Sleep ─────────────────────────────────

  def _active(self) -> bool:
    return self.is_running or self.auto_running

  def set_paused(self, paused: bool) -> bool:
    """Pause or resume active worker loops and rest countdowns cleanly."""
    with self._lock:
      if not self._active():
        self.paused = False
        self._resume_event.set()
        return False
      self.paused = bool(paused)
      if self.paused:
        self._resume_event.clear()
        self._log('INFO', '학습 일시정지됨')
        self._set_status('일시정지됨', '#E65100')
      else:
        self._resume_event.set()
        self._log('INFO', '학습 재개됨')
        self._set_status('학습 재개 중...', '#0066CC')
    self._notify_state()
    return self.paused

  def toggle_pause(self) -> bool:
    """Toggle pause state and return new paused boolean."""
    return self.set_paused(not self.paused)

  def _wait_if_paused(self) -> bool:
    """Block while paused; return False if stopped."""
    while not self._resume_event.is_set():
      if not self._active():
        return False
      self._resume_event.wait(0.15)
    return self._active()

  def _sleep(self, seconds: float) -> bool:
    """Interruptible, pause-aware sleep. Returns False if stopped."""
    remaining = max(0.0, float(seconds))
    while remaining > 0:
      if not self._active():
        return False
      if not self._wait_if_paused():
        return False
      chunk = min(0.1, remaining)
      time.sleep(chunk)
      remaining -= chunk
    return self._active()

  def _anticheat_human_delay_enabled(self) -> bool:
    return bool(config_store.config_get('anticheat', True)) and bool(
        config_store.config_get('human_delay', True)
    )

  def human_delay(self, lo: float = 0.1, hi: float = 0.7) -> bool:
    """Sleep a random human-like duration when anticheat & human_delay are enabled."""
    if not self._anticheat_human_delay_enabled():
      return self._active()
    return self._sleep(random.uniform(lo, hi))

  def stop(self) -> None:
    """Stop all manual and automatic study workers immediately."""
    with self._lock:
      was_active = self.is_running or self.auto_running
      self.is_running = False
      self.auto_running = False
      self.paused = False
      self.waiting_memo_go = False
      self.auto_rest_remaining = 0
      self.auto_rest_total = 0
      self.current_mode = None
      self._resume_event.set()
      self.auto_mode_done.set()
      self.seg_finished.set()
      self.memo_go.clear()
    if was_active:
      self._log('INFO', '학습 정지됨')
    self._set_status('정지됨', '#D32F2F')
    self._set_manual_status('정지됨', '#D32F2F')
    self._notify_state()

  def stop_auto(self) -> None:
    """Stop automatic study."""
    self.stop()

  def press_memo_go(self) -> None:
    """Signal manual memorize worker to begin sending keys."""
    with self._lock:
      self.waiting_memo_go = False
    self.memo_go.set()
    self._notify_state()

  def set_study_kind(self, kind: str) -> None:
    kind = 'sentence' if kind == 'sentence' else 'word'
    with self._lock:
      self.study_kind = kind
    self._emit('on_kind_change', kind)
    self._notify_state()

  # ── Word Loading ───────────────────────────────────────────────────────────

  def set_loaded_words(
      self,
      cards: list[dict],
      source: str = '세트',
      set_idx: Optional[str] = None,
      kind: Optional[str] = None,
  ) -> list[dict]:
    """Store deduplicated cards and notify UI callbacks."""
    uniq = unique_cards(cards)
    with self._lock:
      self.word_list = uniq
      self.loaded_set_idx = str(set_idx) if set_idx else None
      if kind in ('word', 'sentence'):
        self.study_kind = kind
    if kind in ('word', 'sentence'):
      self._emit('on_kind_change', kind)
    self._set_manual_status(
        f'준비 완료! {source}에서 {len(uniq)}개 불러옴 — 모드 버튼을 누르세요.',
        '#2E7D32',
    )
    self._log('OK', f'{source}에서 카드 {len(uniq)}개 불러옴')
    self._emit('on_cards_loaded', uniq, source, self.loaded_set_idx)
    self._notify_state()
    return uniq

  def load_words_from_json(self, raw_text: str) -> tuple[bool, str]:
    """Parse JSON card list (e.g. from clipboard) and store loaded cards."""
    try:
      data = json.loads((raw_text or '').strip())
      if isinstance(data, list) and data and 'eng' in data[0]:
        uniq = self.set_loaded_words(data, '클립보드')
        return True, f'클립보드에서 {len(uniq)}개 불러옴'
      return False, '올바른 클래스카드 데이터가 아닙니다.'
    except Exception:
      return False, '클립보드 데이터가 유효한 JSON 형식이 아닙니다.'

  def load_words_from_chrome(self, async_run: bool = True) -> None:
    """Load cards from the currently open Classcard set in Chrome."""
    def work():
      try:
        driver = chrome_bridge.get_driver()
      except Exception as e:
        msg = f'크롬을 열지 못했습니다: {e}'
        self._log('ERROR', msg)
        self._set_manual_status(msg, '#D32F2F')
        self._emit('on_error', '불러오기', msg)
        return
      try:
        url = driver.current_url
      except Exception:
        url = ''
      set_idx, class_idx = chrome_bridge.idx_from_url(url)
      if not set_idx:
        self._set_manual_status('크롬에서 공부할 단어장을 먼저 열어주세요.', '#D32F2F')
        self._emit('on_error', '불러오기', '크롬에서 공부할 단어장을 먼저 열어주세요.')
        return
      self._set_manual_status('세트에서 단어를 읽는 중...', '#0288D1')
      detail = chrome_bridge.fetch_set_detail(driver, set_idx, class_idx)
      if not detail or not detail.get('cards'):
        self._set_manual_status('세트에서 단어를 읽지 못했습니다.', '#D32F2F')
        return
      cards = detail['cards']
      kind = None
      sets = chrome_bridge.fetch_sets(driver, class_idx) if class_idx else []
      for item in sets:
        if str(item.get('idx')) == str(set_idx):
          kind = 'sentence' if item.get('sentence') else 'word'
          break
      if kind is None:
        long_cards = sum(1 for c in cards if ' ' in (c.get('eng') or '').strip())
        kind = 'sentence' if long_cards > len(cards) / 2 else 'word'
      self.set_loaded_words(cards, detail.get('title') or '세트', set_idx, kind=kind)

    if async_run:
      threading.Thread(target=work, daemon=True).start()
    else:
      work()

  # ── Live Progress Reader ───────────────────────────────────────────────────

  def poll_live_progress(self) -> Optional[tuple[int, int]]:
    """Read live (done, total) progress from Chrome without blocking workers."""
    driver = chrome_bridge.get_shared_driver()
    if driver is None:
      return None
    try:
      out = chrome_bridge.read_study_progress(driver)
    except Exception:
      return None
    if out and len(out) == 2:
      done, total = int(out[0]), int(out[1])
      with self._lock:
        changed = (done, total) != (self.site_done, self.site_total)
        self.site_done = done
        self.site_total = total
      if changed:
        self._log('DEBUG', f'사이트 진행 {done}/{total}')
      return done, total
    return None

  # ── Selenium DOM & Input Primitives ────────────────────────────────────────

  def _dispatch_key(self, driver, key: str) -> None:
    chrome_bridge.dispatch_key(driver, key)

  def _on_memorize_screen(self, driver) -> bool:
    try:
      return _MEMORIZE_URL_HINT in (driver.current_url or '').lower()
    except Exception:
      return False

  def _on_class_test(self, driver) -> bool:
    try:
      return _CLASS_TEST_URL_HINT in (driver.current_url or '').lower()
    except Exception:
      return False

  def _study_page_kind(self, driver) -> str:
    try:
      url = (driver.current_url or '').lower()
    except Exception:
      return ''
    for hint in _STUDY_URL_HINTS:
      if hint in url:
        return hint
    return ''

  def _press_space_now(self, driver) -> None:
    driver.execute_script(_REFOCUS_JS)
    ActionChains(driver).send_keys(Keys.SPACE).perform()
    chrome_bridge.dispatch_key(driver, ' ')

  def _press_space(self, driver) -> bool:
    return chrome_bridge.press_space(driver)

  def _press_submit(self, driver) -> bool:
    return chrome_bridge.press_submit(driver)

  def _click_button(self, driver, labels, patterns=None, wait_after: float = 1.2) -> bool:
    btn = chrome_bridge.find_button_by_text(driver, labels, patterns)
    if not btn:
      return False
    moved = False
    try:
      btn.click()
      moved = True
    except Exception:
      moved = self._press_space(driver)
    if moved and wait_after > 0:
      self._sleep(wait_after)
    return moved

  def _study_card_total(self, driver) -> int:
    try:
      out = chrome_bridge.read_study_progress(driver)
      if out and len(out) == 2:
        return int(out[1])
    except Exception:
      pass
    return -1

  def _warn_if_no_cards(self, driver) -> bool:
    if self._study_card_total(driver) != 0:
      return False
    self._set_manual_status(
        '이 학습에 남은 카드가 없습니다(0/0). 다음 구간이나 다른 세트를 골라주세요.',
        '#D32F2F',
    )
    return True

  def _ensure_word_list_for_screen(self, driver, min_gap: float = 3.0) -> bool:
    if self.auto_running:
      return False
    now = time.time()
    if now - self._last_list_sync < min_gap:
      return False
    self._last_list_sync = now
    try:
      url = driver.current_url or ''
    except Exception:
      return False
    set_idx, class_idx = chrome_bridge.idx_from_url(url)
    if not set_idx or not class_idx:
      return False
    if self.word_list and str(self.loaded_set_idx) == str(set_idx):
      return False
    cards = chrome_bridge.fetch_set_cards(driver, set_idx, class_idx)
    if not cards:
      return False
    uniq = unique_cards(cards)
    with self._lock:
      self.word_list = uniq
      self.loaded_set_idx = str(set_idx)
    self._set_manual_status(f'화면에 열린 세트에서 {len(uniq)}개를 불러왔습니다.', '#0288D1')
    return True

  def _handle_section_done(self, driver) -> bool:
    if self.auto_running:
      if chrome_bridge.find_button_by_text(driver, _SECTION_AGAIN_LABELS, _SECTION_DONE_PATTERNS):
        self.auto_mode_done.set()
        return False
      if self._on_class_test(driver) and chrome_bridge.find_button_by_text(driver, _TEST_DONE_LABELS):
        self.auto_mode_done.set()
        return False
      if self._click_button(driver, _SECTION_NEXT_LABELS, wait_after=1.5):
        with self._lock:
          self.site_done = 0
          self.site_total = 0
        self.seg_finished.set()
        return True
      return False
    return self._click_button(driver, _SECTION_DONE_LABELS, _SECTION_DONE_PATTERNS, wait_after=1.5)

  def _read_all_texts(self, driver, selector: str) -> list[str]:
    try:
      els = driver.find_elements(By.CSS_SELECTOR, selector)
    except Exception:
      return []
    texts = []
    for el in els:
      try:
        t = driver.execute_script("return (arguments[0].textContent || '').trim();", el)
      except Exception:
        t = ''
      if t:
        texts.append(t)
    return texts

  def _read_visible(self, driver, selector: str) -> list[tuple[Any, str]]:
    try:
      els = driver.find_elements(By.CSS_SELECTOR, selector)
    except Exception:
      return []
    results = []
    for el in els:
      try:
        info = driver.execute_script(_VISIBLE_JS, el)
      except Exception:
        continue
      if info and info.get('visible') and info.get('text'):
        results.append((el, info['text']))
    return results

  def _read_on_screen(self, driver, selector: str, hit_test: bool = True) -> list[tuple[Any, str]]:
    try:
      raw = driver.execute_script(_ON_SCREEN_JS, selector, bool(hit_test)) or []
    except Exception:
      return []
    return [(d['el'], d['text']) for d in raw if d.get('text')]

  def _test_vocab(self) -> dict[str, bool]:
    vocab = {}
    for w in self.word_list:
      eng = (w.get('eng') or '').strip()
      kor = (w.get('kor') or '').strip()
      for key in (eng.lower(), kor, strip_pos_tag(kor)):
        if key:
          vocab[key] = True
    return vocab

  def _read_question_words(self, driver, vocab: dict, hit_test: bool = True) -> list[str]:
    try:
      return driver.execute_script(_QUESTION_WORD_JS, vocab, bool(hit_test)) or []
    except Exception:
      return []

  def _auto_card_done(self, word=None) -> None:
    with self._lock:
      self.cards_solved += 1
      if self.auto_running:
        self.cards_done += 1
        if isinstance(word, dict):
          word = word.get('eng')
        if word:
          self.cards_seen.add(str(word).strip().lower())
    if self.auto_running:
      self.poll_live_progress()

  # ── Manual Workers: Memorize, Recall, Spell ────────────────────────────────

  def _find_visible_question(self, driver, selector: str, last_seen_eng: Optional[str]):
    q_visible = self._read_visible(driver, selector)
    for el, cand in q_visible:
      cand_lower = cand.strip().lower()
      for w in self.word_list:
        if w['eng'].strip().lower() == cand_lower and w['eng'] != last_seen_eng:
          return w, el
    return None, None

  def _idle_study_fallback(self, driver, tab_hint: str, waiting_msg: str) -> None:
    chrome_bridge.focus_study_tab(driver, tab_hint)
    if self._handle_section_done(driver):
      return
    if self._click_button(driver, _NEXT_CARD_LABELS, wait_after=0.4):
      return
    if self._ensure_word_list_for_screen(driver):
      return
    if self._warn_if_no_cards(driver):
      self._sleep(1.0)
      return
    self._set_manual_status(waiting_msg, '#7A7A7A')

  def memo_worker(self) -> None:
    """Word memorize worker: Space -> Shift+Space -> Right Arrow."""
    with self._lock:
      self.is_running = True
    self._notify_state()

    try:
      driver = chrome_bridge.get_driver()
      self._set_manual_status('크롬에서 암기 학습 화면으로 이동하세요. 화면이 뜨면 시작합니다.', '#0288D1')
      ready = False
      if self.auto_running:
        self.memo_go.set()
      else:
        self.memo_go.clear()

      while self.is_running:
        if not self._wait_if_paused():
          break
        if self._handle_section_done(driver):
          continue

        if not self._on_memorize_screen(driver):
          if chrome_bridge.focus_study_tab(driver, _MEMORIZE_URL_HINT) and self._on_memorize_screen(driver):
            continue
          if ready or self.waiting_memo_go:
            ready = False
            with self._lock:
              self.waiting_memo_go = False
            self.memo_go.clear()
            self._notify_state()
          self._set_manual_status('암기 학습 화면을 기다리는 중...', '#7A7A7A')
          self._sleep(0.5)
          continue

        if not ready:
          if not self.memo_go.is_set():
            if not self.waiting_memo_go:
              with self._lock:
                self.waiting_memo_go = True
              self._notify_state()
              self._set_manual_status('사이트에서 학습을 시작한 뒤 [시작]을 누르세요.', '#0066CC')
            self._sleep(0.1)
            continue
          with self._lock:
            self.waiting_memo_go = False
          ready = True
          self._notify_state()
          self._set_manual_status('암기 자동 학습 진행 중...', '#2E7D32')

        try:
          driver.find_element(By.TAG_NAME, 'body').click()
        except Exception:
          pass
        if not self._sleep(0.1):
          break

        ActionChains(driver).send_keys(Keys.SPACE).perform()
        self._dispatch_key(driver, ' ')
        if not self._sleep(0.2):
          break

        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.SPACE).key_up(Keys.SHIFT).perform()
        if not self._sleep(0.2):
          break

        ActionChains(driver).send_keys(Keys.ARROW_RIGHT).perform()
        self._auto_card_done()
        self._sleep(0.3)
    except Exception as e:
      self._log('ERROR', f'암기 워커 오류: {e}')
      self._emit('on_error', '셀레니움 에러', f'오류가 발생했습니다:\n{e}')
    finally:
      if not self.auto_running:
        self.stop()

  def recall_worker(self) -> None:
    """Word recall (4-choice) worker."""
    with self._lock:
      self.is_running = True
    self._notify_state()

    try:
      driver = chrome_bridge.get_driver()
      self._ensure_word_list_for_screen(driver, min_gap=0)
      self._set_manual_status('리콜 학습 화면 감지 대기 중...', '#2E7D32')
      last_seen_eng = None

      while self.is_running:
        if not self._wait_if_paused():
          break
        current_word, _ = self._find_visible_question(driver, '.normal-body', last_seen_eng)

        if current_word and self.is_running:
          target_kor = current_word['kor'].strip()
          self._set_manual_status(f"단어 감지: [{current_word['eng']}] -> '{target_kor}'", '#0288D1')
          if not self._sleep(0.5):
            break

          choices = []
          for _ in range(20):
            if not self.is_running or not self._wait_if_paused():
              break
            choices = self._read_visible(driver, '.cc-ellipsis')
            if len(choices) >= 4:
              break
            self._sleep(0.1)

          pressed = False
          picked = pick_choice(choices[:4], target_kor)
          if picked and self.is_running:
            i, _, _ = picked
            try:
              driver.find_element(By.TAG_NAME, 'body').click()
              self._sleep(0.3)
              ActionChains(driver).send_keys(str(i + 1)).perform()
              pressed = True
            except StaleElementReferenceException:
              pass
            except Exception as e:
              self._log('DEBUG', f'리콜 키 입력 오류: {e}')

          if pressed:
            self._auto_card_done(current_word)
            last_seen_eng = current_word['eng']
            self._set_manual_status(f'정답 [{target_kor}] 선택 성공!', '#2E7D32')
            self._sleep(0.4)
          elif self.is_running:
            if self._handle_section_done(driver) or self._click_button(driver, _NEXT_CARD_LABELS, wait_after=0.4):
              last_seen_eng = current_word['eng']
              continue
        else:
          self._idle_study_fallback(driver, '/recall/', '리콜 학습 화면을 기다리는 중...')

        self._sleep(0.3)
    except Exception as e:
      self._log('ERROR', f'리콜 워커 오류: {e}')
      self._emit('on_error', '셀레니움 에러', f'오류가 발생했습니다:\n{e}')
    finally:
      if not self.auto_running:
        self.stop()

  def _spell_next_card(self, driver, timeout: float = 3.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
      if not self._active():
        return False
      btn = chrome_bridge.find_button_by_text(driver, _NEXT_CARD_LABELS)
      if btn:
        try:
          btn.click()
        except Exception:
          self._press_space_now(driver)
        self._sleep(0.15)
        return True
      time.sleep(0.05)
    return False

  def spell_worker(self) -> None:
    """Word spell (text input) worker."""
    with self._lock:
      self.is_running = True
    self._notify_state()

    try:
      driver = chrome_bridge.get_driver()
      self._ensure_word_list_for_screen(driver, min_gap=0)
      self._set_manual_status('스펠 학습 화면 감지 대기 중...', '#2E7D32')
      last_seen_eng = None

      while self.is_running:
        if not self._wait_if_paused():
          break
        current_word, current_word_el = self._find_visible_question(
            driver, '.spell-content', last_seen_eng
        )

        if current_word and self.is_running:
          target_kor = current_word['kor'].strip()
          self._set_manual_status(f"단어 감지: [{current_word['eng']}] -> '{target_kor}'", '#0288D1')

          input_el = None
          for _ in range(20):
            if not self.is_running or not self._wait_if_paused():
              break
            try:
              input_el = driver.execute_script(_FIND_INPUT_NEAR_JS, current_word_el)
            except StaleElementReferenceException:
              input_el = None
            if input_el:
              break
            self._sleep(0.1)

          typed = False
          if input_el:
            try:
              input_el.click()
              input_el.clear()
              input_el.send_keys(target_kor)
              input_el.send_keys(Keys.RETURN)
              if not self._spell_next_card(driver):
                self._press_space_now(driver)
              typed = True
            except StaleElementReferenceException:
              pass
            except Exception as e:
              self._log('DEBUG', f'스펠 입력 오류: {e}')

          if typed:
            self._auto_card_done(current_word)
            last_seen_eng = current_word['eng']
            self._set_manual_status(f"'{target_kor}' 입력 완료!", '#2E7D32')
          elif self.is_running:
            if self._handle_section_done(driver) or self._click_button(driver, _NEXT_CARD_LABELS, wait_after=0.4):
              last_seen_eng = current_word['eng']
              continue
        else:
          self._idle_study_fallback(driver, '/spell/', '스펠 학습 화면을 기다리는 중...')

        self._sleep(0.02 if current_word else 0.3)
    except Exception as e:
      self._log('ERROR', f'스펠 워커 오류: {e}')
      self._emit('on_error', '셀레니움 에러', f'오류가 발생했습니다:\n{e}')
    finally:
      if not self.auto_running:
        self.stop()

  # ── Test Worker ────────────────────────────────────────────────────────────

  def _choice_digit(self, choice_el) -> Optional[str]:
    try:
      label_el = choice_el.find_element(By.XPATH, './ancestor::label[1]')
      digit = (label_el.get_attribute('for') or '').rsplit('_', 1)[-1]
      return digit if digit.isdigit() else None
    except Exception:
      return None

  def _choice_taken(self, driver, choice_el, text: str) -> bool:
    try:
      return bool(driver.execute_script(_CHOICE_TAKEN_JS, choice_el, text))
    except StaleElementReferenceException:
      return True
    except Exception:
      return False

  def _select_test_choice(self, driver, choice_el, digit: Optional[str], text: str) -> bool:
    self.human_delay(0.1, 0.7)
    if not self.is_running:
      return False

    def digit_key():
      if not digit:
        raise ValueError('번호 속성 없음')
      driver.execute_script(_REFOCUS_JS)
      time.sleep(0.05)
      ActionChains(driver).send_keys(digit).perform()
      self._dispatch_key(driver, digit)

    plan = [
        ('숫자키', digit_key),
        ('숫자키', digit_key),
        ('숫자키', digit_key),
        ('클릭', lambda: choice_el.click()),
        ('JS클릭', lambda: driver.execute_script(_CLICK_CHIP_JS, choice_el)),
        ('숫자키', digit_key),
        ('숫자키', digit_key),
    ]
    for _, action in plan:
      if not self.is_running:
        return False
      if self._choice_taken(driver, choice_el, text):
        return True
      try:
        action()
      except StaleElementReferenceException:
        return True
      except Exception:
        continue
      for _ in range(5):
        time.sleep(0.05)
        if self._choice_taken(driver, choice_el, text):
          return True
    return False

  def _wait_word_screen(self, driver, word_sel: str, choice_sel: str, exclude: list[str], timeout: float = 3.0):
    try:
      driver.set_script_timeout(timeout + 2)
      res = driver.execute_async_script(
          _WAIT_WORD_SCREEN_JS, word_sel, choice_sel, list(exclude), int(timeout * 1000)
      ) or {}
    except Exception:
      return None
    return res.get('words') if res.get('ok') else None

  def _build_test_candidates(self, texts: list[str], seen_keys: set[str]):
    out = []
    for text in texts:
      cand = (text or '').strip()
      if not cand or cand in seen_keys or any(cand == c[0] for c in out):
        continue
      for w in self.word_list:
        if w['eng'].strip().lower() == cand.lower():
          out.append((cand, w, 'eng_to_kor', w['kor'].strip()))
          break
        if strip_pos_tag(w['kor']) == cand or w['kor'].strip() == cand:
          out.append((cand, w, 'kor_to_eng', w['eng'].strip()))
          break
    return out

  def _init_wrong_question_indices(self, total_q: int) -> tuple[bool, set[int]]:
    wrong_enabled = bool(config_store.config_get('wrong_enabled', False))
    if not wrong_enabled:
      return False, set()
    try:
      w_min = max(0, int(config_store.config_get('wrong_min', 1)))
      w_max = max(0, int(config_store.config_get('wrong_max', 2)))
      if w_min > w_max:
        w_min, w_max = w_max, w_min
      target_wrong = random.randint(w_min, w_max)
      if total_q > 1 and target_wrong > 0:
        pool = list(range(1, total_q)) if total_q > 2 else list(range(total_q))
        picked = set(random.sample(pool, min(target_wrong, len(pool))))
        nums = [i + 1 for i in sorted(picked)]
        self._log('INFO', f'탐지 방지: {total_q}문제 중 {len(picked)}문제 의도적 오답 설정 ({nums}번)')
        return True, picked
    except Exception as e:
      self._log('DEBUG', f'오답 설정 초기화 오류: {e}')
    return wrong_enabled, set()

  def test_worker(self) -> None:
    """Word test (final exam) worker with optional intentional wrong answers."""
    with self._lock:
      self.is_running = True
    self._notify_state()

    CURRENT_CARD = '.flip-card:not(.next):not(.hidden)'
    FALLBACK_Q = '.cc-table.middle.fill-parent[class*="font-"]'
    QUESTION_SEL = f'{CURRENT_CARD} {FALLBACK_Q}'
    CHOICE_SEL = '.cc-table.middle.fill-parent:not([class*="font-"])'
    WORD_BOX_SEL = 'div[style*="text-align: center"][style*="overflow: hidden"]'
    SCOPED_CHOICE_SEL = f'{CURRENT_CARD} {CHOICE_SEL}'

    try:
      driver = chrome_bridge.get_driver()
      self._ensure_word_list_for_screen(driver, min_gap=0)
      self._set_manual_status('테스트 학습 화면 감지 대기 중...', '#2E7D32')

      seen_keys: set[str] = set()
      vocab = self._test_vocab()
      fail_counts: dict[str, int] = {}
      empty_streak = 0
      stuck_streak = 0
      space_pressed_early = False
      pending_words: list[str] = []

      total_q = len(self.word_list) if self.word_list else 20
      wrong_enabled, wrong_q_indices = self._init_wrong_question_indices(total_q)
      test_q_count = 0

      while self.is_running:
        if not self._wait_if_paused():
          break

        q_candidates = self._read_question_words(driver, vocab)
        early_words = pending_words
        if pending_words:
          q_candidates = list(pending_words) + [t for t in q_candidates if t not in pending_words]
          pending_words = []
        if q_candidates:
          empty_streak = 0
        else:
          empty_streak += 1
          if empty_streak >= 3:
            q_candidates = self._read_question_words(driver, vocab, hit_test=False)
            if not q_candidates:
              q_candidates = self._read_all_texts(driver, QUESTION_SEL)

        word_boxes = [' '.join(t.split()) for _, t in self._read_on_screen(driver, WORD_BOX_SEL)]
        for t in word_boxes:
          if t not in q_candidates:
            q_candidates = list(q_candidates) + [t]

        candidates = self._build_test_candidates(q_candidates, seen_keys)
        if early_words:
          for c in self._build_test_candidates(early_words, set()):
            if not any(c[0] == x[0] for x in candidates):
              candidates.insert(0, c)

        if candidates:
          stuck_streak = 0
        elif self.is_running:
          stuck_streak += 1
          if (word_boxes or stuck_streak >= 3) and not self._read_on_screen(driver, CHOICE_SEL):
            pool = q_candidates or self._read_question_words(driver, vocab, hit_test=False)
            candidates = self._build_test_candidates(pool, set())

        if candidates and self.is_running:
          current_cand_norm, current_word, _, target_answer = candidates[0]
          self._set_manual_status(f"테스트 감지: '{target_answer}' 찾는 중", '#0288D1')

          stale = [] if space_pressed_early else self._read_on_screen(driver, CHOICE_SEL)
          waited = 0
          while stale and waited < 20 and self.is_running:
            time.sleep(0.05)
            waited += 1
            stale = self._read_on_screen(driver, CHOICE_SEL)

          choices = []
          for space_try in range(25):
            if not self.is_running or not self._wait_if_paused():
              break
            if space_try or not space_pressed_early:
              self._press_space_now(driver)
            window = 0.35 if space_try == 0 else 0.12
            t0 = time.time()

            while self.is_running and time.time() - t0 <= 1.0:
              choices = []
              for sel in (SCOPED_CHOICE_SEL, CHOICE_SEL):
                choices = [
                    (el, t)
                    for el, t in self._read_on_screen(driver, sel)
                    if not any(el == old_el and t == old_t for old_el, old_t in stale)
                ]
                if choices:
                  break
              if choices:
                more = self._build_test_candidates(
                    self._read_question_words(driver, vocab)
                    + [t for _, t in self._read_on_screen(driver, FALLBACK_Q, hit_test=False)],
                    seen_keys,
                )
                for m in more:
                  if not any(m[0] == c[0] for c in candidates):
                    candidates.append(m)
                if any(pick_choice(choices, c[3]) for c in candidates):
                  break
              elif time.time() - t0 > window:
                break
              time.sleep(0.02)

            if choices or not self.is_running:
              break

          space_pressed_early = False
          for c in candidates:
            if pick_choice(choices, c[3]):
              current_cand_norm, current_word, _, target_answer = c
              break

          pressed = False
          is_wrong_turn = wrong_enabled and test_q_count in wrong_q_indices
          if is_wrong_turn and self.is_running:
            picked_wrong = pick_wrong_choice(choices, target_answer)
            if picked_wrong:
              _, choice_el, matched_text = picked_wrong
              digit = self._choice_digit(choice_el)
              pressed = self._select_test_choice(driver, choice_el, digit, matched_text)
              if pressed and self.is_running:
                wrong_q_indices.discard(test_q_count)
                test_q_count += 1
                fail_counts.pop(current_cand_norm, None)
                seen_keys.add(current_cand_norm)
                self._set_manual_status(f'[탐지 방지] 오답 [{matched_text}] 제출 완료', '#E65100')
                self._auto_card_done(current_word)
                self._sleep(0.3)
                if not self._click_button(driver, _NEXT_CARD_LABELS, wait_after=0.4):
                  self._press_space_now(driver)
                words = self._wait_word_screen(driver, WORD_BOX_SEL, CHOICE_SEL, [current_cand_norm])
                if words and self.is_running:
                  self._press_space_now(driver)
                  space_pressed_early = True
                  pending_words = words
                continue

          picked = pick_choice(choices, target_answer)
          if picked and self.is_running:
            _, choice_el, _ = picked
            digit = self._choice_digit(choice_el)
            pressed = self._select_test_choice(driver, choice_el, digit, target_answer)

          if pressed and self.is_running:
            self._auto_card_done(current_word)
            test_q_count += 1
            fail_counts.pop(current_cand_norm, None)
            seen_keys.add(current_cand_norm)
            self._set_manual_status(f'정답 [{target_answer}] 선택 성공!', '#2E7D32')
            words = self._wait_word_screen(driver, WORD_BOX_SEL, CHOICE_SEL, [current_cand_norm])
            if words and self.is_running:
              self._press_space_now(driver)
              space_pressed_early = True
              pending_words = words
          elif self.is_running:
            fail_counts[current_cand_norm] = fail_counts.get(current_cand_norm, 0) + 1
            if fail_counts[current_cand_norm] >= 3:
              seen_keys.add(current_cand_norm)
              fail_counts.pop(current_cand_norm, None)
        else:
          space_pressed_early = False
          self._idle_study_fallback(driver, '/classtest/', '테스트 학습 화면을 기다리는 중...')

        if not space_pressed_early:
          self._sleep(0.1)
    except Exception as e:
      self._log('ERROR', f'테스트 워커 오류: {e}')
      self._emit('on_error', '셀레니움 에러', f'오류가 발생했습니다:\n{e}')
    finally:
      if not self.auto_running:
        self.stop()

  # ── Sentence Scramble Worker ───────────────────────────────────────────────

  def _read_scramble_groups(self, driver):
    try:
      raw = driver.execute_script(_SCRAMBLE_JS) or []
    except Exception:
      return []
    usable = []
    for group in raw:
      if not any(d.get('vis') for d in group):
        continue
      items = [(d['el'], d['text']) for d in group if d.get('text') and not d.get('used')]
      if not items:
        continue
      tops = [d.get('top') or 0 for d in group]
      usable.append({
          'items': items,
          'clickable': all(d.get('clk') for d in group),
          'top': sum(tops) / len(tops),
      })
    if not usable:
      return []
    clickable = [g for g in usable if g['clickable']]
    if clickable:
      usable = clickable
    usable.sort(key=lambda g: -g['top'])
    return [g['items'] for g in usable]

  def _pick_group_for(self, groups, tokens: list[str]):
    wanted = set(tokens)
    for items in groups:
      usable = usable_items(items)
      if any(norm_token(txt) in wanted for _, txt in usable):
        return usable
    return []

  def read_placed_count(self, driver, tokens: list[str], limit: int) -> int:
    """Count words already placed in the sentence tray (filtering '/' chunk markers)."""
    if limit <= 0:
      return 0
    try:
      texts = driver.execute_script(_PLACED_TEXT_JS) or []
    except Exception:
      return 0
    best = 0
    for text in texts:
      words = [
          w for w in (norm_token(x) for x in norm_quotes(text).split())
          if w and w != '/'
      ]
      n = len(words)
      if n <= best or n > limit:
        continue
      if words == tokens[:n]:
        best = n
    return best

  def _click_chip(self, driver, el, native_first: bool = False, allow_js: bool = True) -> bool:
    order = (True, False) if native_first else (False, True)
    if not allow_js:
      order = (True,)
    for native in order:
      try:
        if native:
          el.click()
        else:
          driver.execute_script(_CLICK_CHIP_JS, el)
        return True
      except StaleElementReferenceException:
        return False
      except Exception:
        continue
    return False

  def _click_scramble_in_order(self, driver, tokens: list[str], raw_tokens: Optional[list[str]] = None) -> bool:
    start = None
    needed = 0
    done_count = 0
    used = []
    retries: dict[str, int] = {}
    page = self._study_page_kind(driver)
    in_test = page == _CLASS_TEST_URL_HINT
    native_click = True if in_test else self._chip_click_native.get(page, False)
    need_stable = True

    for _ in range(len(tokens) * 3 + 6):
      if not self.is_running or not self._wait_if_paused():
        return False

      items = []
      for _ in range(30):
        if not self.is_running or not self._wait_if_paused():
          return False
        groups = self._read_scramble_groups(driver)
        items = [
            (el, txt)
            for el, txt in self._pick_group_for(groups, tokens)
            if not any(el == prev for prev in used)
        ]
        if items and in_test and need_stable:
          time.sleep(0.12)
          again = [
              (el, txt)
              for el, txt in self._pick_group_for(self._read_scramble_groups(driver), tokens)
              if not any(el == prev for prev in used)
          ]
          if [e.id for e, _ in again] != [e.id for e, _ in items]:
            items = []
            continue
          items = again
          need_stable = False
        if items:
          break
        time.sleep(0.05)

      if not items:
        return start is not None and done_count >= needed

      if start is None:
        chips = [norm_token(txt) for _, txt in items]
        placed = self.read_placed_count(driver, tokens, len(tokens) - len(chips))
        start = next_token_index(tokens, chips, placed)
        if start is None:
          return False
        needed = len(tokens) - start

      idx = start + done_count
      if idx >= len(tokens):
        return True

      tok = tokens[idx]
      raw_tok = raw_tokens[idx] if raw_tokens and idx < len(raw_tokens) else None
      cands = [(el, txt) for el, txt in items if norm_token(txt) == tok]
      target = None
      if cands:
        target = min(cands, key=lambda it: (chip_match_rank(it[1], raw_tok), cands.index(it)))[0]

      if target is None:
        time.sleep(0.05)
        continue

      if in_test:
        try:
          judged = driver.execute_script(
              "var c = arguments[0].closest('.flip-card');"
              "if (!c) return '';"
              "return c.classList.contains('correct') ? 'correct'"
              " : (c.classList.contains('wrong') ? 'wrong' : '');",
              target,
          )
        except Exception:
          judged = ''
        if judged:
          return judged == 'correct'

      self.human_delay(0.1, 0.7)
      if not self.is_running:
        return False

      flip = retries.get(tok, 0) > 0 and not in_test
      if not self._click_chip(driver, target, native_first=(native_click != flip), allow_js=not in_test):
        need_stable = True
        time.sleep(0.1)
        continue

      used.append(target)
      done_count += 1
      landed = False

      for _ in range(12):
        time.sleep(0.03)
        try:
          state = driver.execute_script(
              "var el = arguments[0];"
              "if (el.classList.contains('clicked')) return 'clicked';"
              "if (el.classList.contains('shake') || el.classList.contains('wrong')) return 'wrong';"
              "var p = el.parentElement;"
              "return p && p.classList.contains('disabled') ? 'wrong' : '';",
              target,
          )
          if state == 'clicked':
            landed = True
            break
          if state == 'wrong':
            return False
        except StaleElementReferenceException:
          landed = True
          break
        except Exception:
          pass
        group = self._pick_group_for(self._read_scramble_groups(driver), tokens)
        if group and not any(el == target for el, _ in group):
          landed = True
          break
        if self.read_placed_count(driver, tokens, len(tokens)) >= idx + 1:
          landed = True
          break

      if len(items) <= 1 or not landed:
        need_stable = True
      if landed and flip and not in_test:
        native_click = not native_click
        self._chip_click_native[page] = native_click
        retries.clear()
      if not landed:
        retries[tok] = retries.get(tok, 0) + 1
        if retries[tok] > 3:
          return False
        used.pop()
        done_count -= 1
      elif done_count >= needed:
        return True

      time.sleep(0.04)

    return False

  def _press_next_question_when_ready(self, driver, timeout: float = 2.0) -> bool:
    end = time.time() + timeout
    while True:
      btn = chrome_bridge.find_button_by_text(driver, _NEXT_CARD_LABELS)
      if btn:
        try:
          btn.click()
        except Exception:
          pass
        time.sleep(0.12)
        if chrome_bridge.find_button_by_text(driver, _NEXT_CARD_LABELS):
          self._press_submit(driver)
          time.sleep(0.1)
        return True
      if not self.is_running or time.time() >= end:
        return False
      time.sleep(0.05)

  def _unarranged_warning_visible(self, driver) -> bool:
    try:
      return bool(driver.execute_script(_UNARRANGED_WARNING_JS))
    except Exception:
      return False

  def _wait_next_sentence(self, driver, solved_key, timeout: float = 1.5) -> None:
    end = time.time() + timeout
    while time.time() < end:
      if not self._active():
        return
      try:
        btn = chrome_bridge.find_button_by_text(driver, _NEXT_CARD_LABELS)
        if btn:
          try:
            btn.click()
          except Exception:
            self._press_space(driver)
          time.sleep(0.15)
          return
        if chrome_bridge.find_button_by_text(driver, _WRITE_PRACTICE_LABELS):
          self._press_space(driver)
          gone = time.time() + 0.6
          while time.time() < gone:
            if not chrome_bridge.find_button_by_text(driver, _WRITE_PRACTICE_LABELS):
              break
            time.sleep(0.06)
          return
        groups = self._read_scramble_groups(driver)
        if groups:
          items = usable_items(groups[0])
          if items:
            key = tuple(sorted(norm_token(t) for _, t in items))
            if key != solved_key:
              return
      except Exception:
        pass
      time.sleep(0.05)

  def sentence_scramble_worker(self, mode_name: str = '문장') -> None:
    """Sentence scramble worker (memorize/recall/spell/test)."""
    with self._lock:
      self.is_running = True
    self._notify_state()

    try:
      driver = chrome_bridge.get_driver()
      self._ensure_word_list_for_screen(driver, min_gap=0)
      self._set_manual_status(f'브라우저 준비 중... {mode_name} 학습 화면으로 이동하세요', '#0288D1')

      solved_key = None
      stuck = 0
      open_tries = 0

      while self.is_running:
        if not self._wait_if_paused():
          break

        if (self._on_class_test(driver) and self._unarranged_warning_visible(driver)
            and self._click_button(driver, _CANCEL_LABELS, wait_after=0.4)):
          solved_key = None
          continue

        if self._handle_section_done(driver):
          solved_key = None
          continue

        if self._on_class_test(driver) and self._press_next_question_when_ready(driver, 0):
          solved_key = None
          continue

        groups = self._read_scramble_groups(driver)
        matched = match_scramble_sentence(self.word_list, groups)

        if not matched:
          if chrome_bridge.find_button_by_text(driver, _WRITE_PRACTICE_LABELS):
            open_tries += 1
            if open_tries == 8 and not self._warn_if_no_cards(driver):
              self._set_manual_status(
                  '화면이 넘어가지 않습니다. 세트 화면에서 학습 버튼을 눌러 다시 들어와 주세요.',
                  '#D32F2F',
              )
            self._press_space(driver)
            self._sleep(0.25)
            if chrome_bridge.find_button_by_text(driver, _WRITE_PRACTICE_LABELS):
              self._click_button(driver, _WRITE_PRACTICE_LABELS, wait_after=0.6)
            continue

          if self._handle_section_done(driver):
            solved_key = None
            continue
          if self._click_button(driver, _NEXT_CARD_LABELS, wait_after=0.2):
            solved_key = None
            continue
          chrome_bridge.focus_study_tab(driver)
          if self._ensure_word_list_for_screen(driver):
            continue
          self._set_manual_status(f'{mode_name} 학습 화면을 기다리는 중...', '#7A7A7A')
          self._sleep(0.3)
          continue

        items, word, tokens, source = matched
        open_tries = 0
        key = tuple(sorted(norm_token(t) for _, t in items))

        if key == solved_key:
          stuck += 1
          if stuck > 14:
            solved_key = None
            stuck = 0
          else:
            if stuck % 2 == 1:
              self._press_space(driver)
            self._sleep(0.12)
          continue

        self._set_manual_status(f"문장 감지: {word['eng']}", '#0288D1')
        raw_tokens = [w for w in norm_quotes(source).split() if norm_token(w)]
        if len(raw_tokens) != len(tokens):
          raw_tokens = None

        chunks = sentence_chunks(word.get('eng', '') or '')
        parts = chunks[1:] if len(chunks) > 1 else chunks
        more_chunks = (
            len(parts) > 1
            and source.strip() != chunks[0].strip()
            and source.strip() != parts[-1].strip()
        )

        done = self._click_scramble_in_order(driver, tokens, raw_tokens)
        if done:
          if len(chunks) > 1 and source.strip() == chunks[0].strip():
            for part in parts:
              self._auto_card_done(part)
          else:
            self._auto_card_done(source)

        if done and self.is_running:
          solved_key = key
          stuck = 0
          self._set_manual_status(f"'{word['eng']}' 완성! 다음 문장 이동", '#2E7D32')
          in_test = self._on_class_test(driver)
          if more_chunks and not in_test:
            self._sleep(0.15)
          elif in_test:
            self._press_submit(driver)
            self._press_next_question_when_ready(driver, timeout=2.0)
          else:
            self._press_submit(driver)
            self._wait_next_sentence(driver, key)
        else:
          self._sleep(0.5)
    except Exception as e:
      self._log('ERROR', f'문장 워커 오류: {e}')
      self._emit('on_error', '셀레니움 에러', f'오류가 발생했습니다:\n{e}')
    finally:
      if not self.auto_running:
        self.stop()

  # ── Manual Start Dispatcher ────────────────────────────────────────────────

  def start_manual(self, mode: str) -> tuple[bool, str]:
    """Start a manual mode worker in a background thread."""
    if not self.word_list:
      return False, '먼저 [불러오기]로 단어/문장을 로드해주세요.'
    if self._active():
      return False, '이미 학습이 진행 중입니다.'

    with self._lock:
      if self.session_started_at is None:
        self.session_started_at = time.time()
      self.paused = False
      self._resume_event.set()
      self.current_mode = mode

    if self.study_kind == 'sentence':
      label = MODE_NAME.get(mode, '문장')
      target = lambda: self.sentence_scramble_worker(label)
    else:
      workers = {
          'memorize': self.memo_worker,
          'recall': self.recall_worker,
          'spell': self.spell_worker,
          'test': self.test_worker,
      }
      target = workers.get(mode)
      if target is None:
        return False, f'알 수 없는 모드: {mode}'

    threading.Thread(target=target, daemon=True).start()
    return True, f'{MODE_NAME.get(mode, mode)} 수동 학습 시작'

  # ── Auto Study Runner ──────────────────────────────────────────────────────

  def _auto_nothing_to_study(self, driver) -> bool:
    try:
      return bool(driver.execute_script(_EMPTY_STUDY_JS))
    except Exception:
      return False

  def _auto_click_text(self, driver, text: str) -> bool:
    try:
      el = driver.execute_script(_FIND_TEXT_EL_JS, text)
    except Exception:
      return False
    if not el:
      return False
    try:
      el.click()
    except Exception:
      try:
        driver.execute_script('arguments[0].click();', el)
      except Exception:
        return False
    return True

  def _auto_handle_start_screen(self, driver, item: dict, mode: str) -> bool:
    try:
      btns = [b for b in driver.find_elements(By.CSS_SELECTOR, 'a.btn-opt-start') if b.is_displayed()]
    except Exception:
      return False
    if not btns:
      return False
    if item.get('sentence'):
      want = '어순배열' if mode == 'spell' else None
    else:
      want = '단어 제시'
    if want:
      self._auto_click_text(driver, want)
      time.sleep(0.2)
    try:
      btns[0].click()
    except Exception:
      try:
        driver.execute_script('arguments[0].click();', btns[0])
      except Exception:
        return False
    time.sleep(0.7)
    return True

  def _auto_run_worker(self, target: Callable[[], None], cards: int = 0, segs_left: int = 1, timeout: float = 1800) -> bool:
    """Run a study worker until the round (across all remaining segments) completes."""
    self.auto_mode_done.clear()
    self.seg_finished.clear()
    with self._lock:
      self.cards_done = 0
      self.cards_seen.clear()
      self.site_done = 0
      self.site_total = 0

    segs_remaining = max(1, int(segs_left))
    seg_counted = False

    t = threading.Thread(target=target, daemon=True)
    t.start()

    remaining_timeout = float(timeout)
    last_tick = time.time()

    while t.is_alive() and self.auto_running and remaining_timeout > 0:
      if self.paused:
        if not self._wait_if_paused():
          break
        last_tick = time.time()
      else:
        now = time.time()
        remaining_timeout -= (now - last_tick)
        last_tick = now

      if self.auto_mode_done.is_set():
        break

      if self.seg_finished.is_set():
        self.seg_finished.clear()
        if not seg_counted:
          segs_remaining -= 1
        seg_counted = False
        if segs_remaining <= 0:
          self.auto_mode_done.set()
          break

      with self._lock:
        s_done, s_total = self.site_done, self.site_total
        c_done = self.cards_done
        c_seen = len(self.cards_seen)

      if s_total and s_done < s_total:
        seg_counted = False
      elif s_total and s_done >= s_total and not seg_counted:
        segs_remaining -= 1
        seg_counted = True
        if segs_remaining <= 0:
          self._log('INFO', f'사이트 진행 {s_done}/{s_total} - 한 바퀴 끝')
          self.auto_mode_done.set()
          break
        self._log('DEBUG', f'구간 완료 ({s_done}/{s_total}) - 다음 구간 대기 (남은 {segs_remaining}구간)')

      if cards and c_seen >= cards and segs_remaining <= 1:
        self._log('INFO', f'카드 {cards}장을 한 번씩 다 해서 한 바퀴 끝')
        self.auto_mode_done.set()
        break

      if cards and c_done >= cards * 2:
        self._log('WARN', f'카드를 {c_done}번 진행했는데 끝나지 않아 종료')
        self.auto_mode_done.set()
        break

      time.sleep(0.2)

    with self._lock:
      self.is_running = False
    self.memo_go.clear()
    t.join(timeout=5)
    return self.auto_mode_done.is_set()

  def _auto_study_segment(self, driver, mode: str, item: dict, class_idx, seg: int, segs_left: int = 1) -> bool:
    url = f"{chrome_bridge.SITE_URL}/{MODE_PATH[mode]}/{item['idx']}/{seg}/{class_idx}"
    if not chrome_bridge.navigate_study_url(driver, url, 6.0):
      self._auto_log('주소 이동 실패', '#D32F2F', level='ERROR')
      return False
    if not self._sleep(0.4):
      return False
    self._auto_handle_start_screen(driver, item, mode)

    if self._auto_nothing_to_study(driver):
      if not self._sleep(1.2):
        return False
      if self._auto_nothing_to_study(driver):
        self._log('INFO', f"{MODE_NAME[mode]} {seg}구간은 공부할 카드가 없어 건너뜀")
        return False

    where = '전체 카드' if seg >= 1000 else f'{seg}구간'
    try:
      if driver.execute_script('return document.hidden;'):
        chrome_bridge.keep_page_awake(driver)
        time.sleep(0.4)
        if driver.execute_script('return document.hidden;'):
          self._auto_log('크롬 창이 가려져 있어 화면을 못 읽습니다. 크롬 창을 열어두세요.', '#E65100', level='WARN')
    except Exception:
      pass

    self._auto_log(f"{item['name']} · {MODE_NAME[mode]} 학습 중 ({where})")

    if item.get('sentence'):
      worker = lambda: self.sentence_scramble_worker(MODE_NAME[mode])
    else:
      worker = {
          'memorize': self.memo_worker,
          'recall': self.recall_worker,
          'spell': self.spell_worker,
      }[mode]
      if mode == 'memorize':
        self.memo_go.set()

    with self._lock:
      self.current_set_idx = str(item['idx'])
      self.current_set_name = item.get('name', '')
      self.current_mode = mode
      self.cards_total = study_unit_count(self.word_list)
    self._notify_state()

    try:
      return self._auto_run_worker(worker, cards=self.cards_total, segs_left=segs_left)
    finally:
      with self._lock:
        self.current_mode = None
      self._notify_state()

  def _auto_study_mode(self, driver, mode: str, item: dict, class_idx) -> bool:
    segments = item.get('segments') or [1]
    seg_done = item.get('seg_done') or {}
    start_idx = None
    for i, seg in enumerate(segments):
      if not (seg_done.get(str(seg)) or {}).get(mode):
        start_idx = i
        break

    if start_idx is not None:
      start = segments[start_idx]
      segs_left = max(
          1,
          sum(1 for s in segments[start_idx:] if not (seg_done.get(str(s)) or {}).get(mode)),
      )
      if start != segments[0]:
        self._log('INFO', f"{MODE_NAME[mode]}: 앞 구간 완료됨 — {start}구간부터 (남은 {segs_left}구간)")
      if self._auto_study_segment(driver, mode, item, class_idx, start, segs_left=segs_left):
        return True
      if not self.auto_running:
        return False

    self._log('INFO', f"{MODE_NAME[mode]}: 전체 카드로 한 바퀴 진행")
    return self._auto_study_segment(driver, mode, item, class_idx, 6000, segs_left=1)

  def _auto_study_test(self, driver, item: dict, class_idx) -> bool:
    url = f"{chrome_bridge.SITE_URL}/ClassTest/{class_idx}/{item['idx']}?p=1&ex=1"
    if not chrome_bridge.navigate_study_url(driver, url, 6.0):
      return False
    chrome_bridge.keep_page_awake(driver)
    if not self._sleep(1.5):
      return False
    self._auto_log(f"{item['name']} · 테스트 시작")

    labels = ['응시', '새로 시작', '테스트 시작', '다음', '시작하기']
    misses = 0
    end = time.time() + 30
    while self.auto_running and time.time() < end:
      if not self._wait_if_paused():
        break
      try:
        if driver.find_elements(By.CSS_SELECTOR, '.flip-card'):
          break
      except Exception:
        pass
      clicked = any(self._click_button(driver, [lbl], wait_after=0) for lbl in labels)
      if clicked:
        misses = 0
        self._sleep(1.2)
        continue
      misses += 1
      if misses >= 6:
        break
      self._sleep(0.4)

    if not self.auto_running:
      return False

    worker = (lambda: self.sentence_scramble_worker('테스트')) if item.get('sentence') else self.test_worker
    with self._lock:
      self.current_set_idx = str(item['idx'])
      self.current_set_name = item.get('name', '')
      self.current_mode = 'test'
      self.cards_total = study_unit_count(self.word_list)
    self._notify_state()

    try:
      done = self._auto_run_worker(worker, cards=self.cards_total, segs_left=1)
    finally:
      with self._lock:
        self.current_mode = None
      self._notify_state()

    if self.auto_running:
      # 방금 본 테스트 점수를 백그라운드 fetch로 즉시 반영 (ClassMain 이동 없이 포커스 유지)
      got = (chrome_bridge.fetch_class_report(driver, class_idx) or {}).get(str(item['idx']))
      if got:
        fresh = {m: (got.get(m) or 0) for m in MODE_ORDER}
        fresh['test'] = got.get('test') or ''
        self._emit_rate(item['idx'], fresh)
    return done

  def _auto_rates(self, driver, item: dict, class_idx) -> dict[str, int]:
    found = chrome_bridge.fetch_set_rates(driver, class_idx, [item['idx']])
    got = found.get(str(item['idx']))
    if not got:
      detail = chrome_bridge.fetch_set_detail(driver, item['idx'], class_idx)
      if not detail:
        return {}
      got = detail
    return {m: (got.get(m) or 0) for m in MODE_ORDER}

  def _rest_between_sets(self, next_name: str) -> None:
    if not config_store.config_get('delay_enabled', False):
      return
    try:
      d_min = max(1, int(config_store.config_get('delay_min', 15)))
      d_max = max(1, int(config_store.config_get('delay_max', 45)))
      if d_min > d_max:
        d_min, d_max = d_max, d_min
      wait_sec = random.randint(d_min, d_max)
    except Exception:
      wait_sec = random.randint(15, 45)

    self._auto_log(f'탐지 방지 휴식: 다음 세트({next_name}) 전 {wait_sec}초 대기', '#E65100')
    with self._lock:
      self.auto_rest_total = wait_sec
      self.auto_rest_remaining = wait_sec
    self._notify_state()

    for remaining in range(wait_sec, 0, -1):
      if not self.auto_running or not self._wait_if_paused():
        break
      with self._lock:
        self.auto_rest_remaining = remaining
      self._set_status(f'다음 세트({next_name}) 전 휴식 중... ({remaining}초)', '#E65100')
      if not self._sleep(1.0):
        break

    with self._lock:
      self.auto_rest_remaining = 0
      self.auto_rest_total = 0
    self._notify_state()

  def start_auto(self, plan: dict, set_provider: Optional[Callable[[set[str]], Optional[dict]]] = None) -> bool:
    """Start automatic study for the given plan in a background thread."""
    if self._active():
      return False

    with self._lock:
      self.auto_running = True
      self.paused = False
      self._resume_event.set()
      self.session_started_at = time.time()
      self.sets_completed = 0
      self.cards_solved = 0
      self.auto_rest_remaining = 0
      self.auto_rest_total = 0
    self._notify_state()

    threading.Thread(
        target=self._auto_worker,
        args=(dict(plan), set_provider),
        daemon=True,
    ).start()
    return True

  def _resolve_next_set(self, done_idx: set[str], static_sets: list[dict], set_provider) -> Optional[dict]:
    if set_provider is not None:
      return set_provider(done_idx)
    for item in static_sets:
      idx = str(item['idx'])
      if idx not in done_idx:
        return dict(item)
    return None

  def _auto_worker(self, plan: dict, set_provider=None) -> None:
    try:
      driver = chrome_bridge.get_driver()
    except Exception as e:
      msg = f'크롬을 열지 못했습니다:\n{e}'
      self._log('ERROR', msg)
      self._emit('on_error', '자동 학습', msg)
      self.stop()
      return

    class_idx = plan['class_idx']
    static_sets = list(plan.get('sets') or [])
    done_idx: set[str] = set()
    test_only = bool(plan.get('test_only', False))
    default_modes = config_store.config_get('study_modes', {}) or {}
    raw_modes = plan.get('modes') if 'modes' in plan else default_modes
    modes = {
        'memorize': bool((raw_modes or {}).get('memorize', True)),
        'recall': bool((raw_modes or {}).get('recall', True)),
        'spell': bool((raw_modes or {}).get('spell', True)),
        'test': bool((raw_modes or {}).get('test', plan.get('test', True))),
    }
    if 'modes' not in plan and 'test' in plan:
      modes['test'] = bool(plan['test'])

    try:
      while self.auto_running:
        if not self._wait_if_paused():
          break

        item = self._resolve_next_set(done_idx, static_sets, set_provider)
        if item is None:
          break
        done_idx.add(str(item['idx']))

        detail = chrome_bridge.fetch_set_detail(driver, item['idx'], class_idx)
        if not detail or not detail.get('cards'):
          self._auto_log(f"{item['name']}: 카드를 못 읽어서 건너뜀", '#E65100', level='WARN')
          continue

        cards = unique_cards(detail['cards'])
        kind = 'sentence' if item.get('sentence') else 'word'
        with self._lock:
          self.word_list = cards
          self.loaded_set_idx = str(item['idx'])
          self.study_kind = kind
          self.current_set_idx = str(item['idx'])
          self.current_set_name = item.get('name', '')
        self._emit('on_kind_change', kind)
        self._auto_log(f"{item['name']}: 카드 {len(cards)}개 불러옴 ({'문장' if kind == 'sentence' else '단어'})")

        item = dict(item)
        item['sentence'] = bool(item.get('sentence'))
        item['segments'] = detail.get('segments') or [1]
        item['seg_done'] = detail.get('seg_done') or {}

        rates = {m: detail.get(m) or 0 for m in MODE_ORDER}
        ran_any_mode = False

        if not test_only:
          enabled_modes = [m for m in MODE_ORDER if modes.get(m, True)]
          for m_idx, mode in enumerate(enabled_modes):
            if not self.auto_running or not self._wait_if_paused():
              break
            target = item.get('target') or (plan.get('targets') or {}).get(mode) or 0
            if not target:
              continue
            rounds = 0
            while self.auto_running and (rates.get(mode) or 0) < target and rounds < 12:
              if not self._wait_if_paused():
                break
              rounds += 1
              self._auto_log(f"{item['name']} · {MODE_NAME[mode]} {rates.get(mode) or 0}% -> 목표 {target}%")
              if not self._auto_study_mode(driver, mode, item, class_idx):
                break
              ran_any_mode = True
              rates = self._auto_rates(driver, item, class_idx) or rates
              self._emit_rate(item['idx'], rates)
              for _ in range(3):
                if not self.auto_running or (rates.get(mode) or 0) >= target:
                  break
                if not self._sleep(0.6):
                  break
                rates = self._auto_rates(driver, item, class_idx) or rates
                self._emit_rate(item['idx'], rates)

            # Mode transition delay (1~3s) when moving to next mode or test
            has_next_step = (m_idx < len(enabled_modes) - 1) or modes.get('test', True)
            if self.auto_running and ran_any_mode and has_next_step:
              self.human_delay(1.0, 3.0)

        run_test = test_only or modes.get('test', True)
        if run_test and self.auto_running:
          cutoff = config_store.get_class_pass_score(class_idx)
          got = (chrome_bridge.fetch_class_report(driver, class_idx) or {}).get(str(item['idx'])) or {}
          prev_test = got.get('test') or ''
          if prev_test and not test_failed(prev_test, cutoff):
            self._auto_log(f"{item['name']} · {format_test_text(prev_test, cutoff)} - 이미 통과해서 건너뜀", '#2E7D32', level='OK')
            self._emit_rate(item['idx'], {'test': prev_test})
          else:
            for attempt in range(1, MAX_TEST_TRIES + 1):
              if not self.auto_running or not self._wait_if_paused():
                break
              if attempt > 1:
                self._auto_log(f"{item['name']} · 테스트 {cutoff}점 미달 — 재시도 ({attempt}/{MAX_TEST_TRIES})", '#E65100', level='WARN')
                self.human_delay(1.0, 2.5)
              self._auto_study_test(driver, item, class_idx)
              if not self.auto_running:
                break
              got = (chrome_bridge.fetch_class_report(driver, class_idx) or {}).get(str(item['idx'])) or {}
              latest_test = got.get('test') or ''
              if latest_test:
                self._emit_rate(item['idx'], {'test': latest_test})
              if latest_test and not test_failed(latest_test, cutoff):
                self._auto_log(f"{item['name']} · {format_test_text(latest_test, cutoff)} 통과", '#2E7D32', level='OK')
                break
              if attempt == MAX_TEST_TRIES and latest_test:
                self._auto_log(
                    f"{item['name']} · {format_test_text(latest_test, cutoff)} (최대 {MAX_TEST_TRIES}회 시도)",
                    '#E65100',
                    level='WARN',
                )

        if self.auto_running:
          with self._lock:
            self.sets_completed += 1
          if test_only:
            self._auto_log(f"{item['name']} 테스트 완료", '#2E7D32', level='OK')
          else:
            self._auto_log(
                f"{item['name']} 완료 (암기 {rates.get('memorize')}% / 리콜 {rates.get('recall')}% / 스펠 {rates.get('spell')}%)",
                '#2E7D32',
                level='OK',
            )

        next_set = self._resolve_next_set(done_idx, static_sets, set_provider)
        if next_set is not None and self.auto_running:
          self._rest_between_sets(next_set.get('name', '다음 세트'))

    except Exception as e:
      self._log('ERROR', f'자동 학습 오류: {e}')
      self._emit('on_error', '자동 학습', f'오류가 발생했습니다:\n{e}')
    finally:
      with self._lock:
        self.auto_running = False
        self.is_running = False
        self.paused = False
        self.current_mode = None
        self.auto_rest_remaining = 0
        self.auto_rest_total = 0
        self._resume_event.set()
      done_msg = '테스트 완료' if test_only else '자동 학습 완료'
      self._auto_log(done_msg, '#2E7D32', level='OK')
      self._notify_state()


engine = StudyEngine()
