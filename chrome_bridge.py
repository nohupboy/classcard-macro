"""Chrome WebDriver lifecycle and Classcard DOM/API bridge."""

import os
import re
import socket
import sys
import threading
import time

from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeDriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

import config_store

SITE_URL = 'https://www.classcard.net'
CHROME_DEBUG_PORT = 9333

_STUDY_URL_PARTS = ('/memorize/', '/recall/', '/spell/', '/classtest/')

_driver_lock = threading.RLock()
_shared_driver = None
_data_tab = None
_busy_checker = None


def set_busy_checker(fn):
  """Register a callable returning True while study automation is active."""
  global _busy_checker
  _busy_checker = fn


def _is_busy():
  if callable(_busy_checker):
    try:
      return bool(_busy_checker())
    except Exception:
      return False
  return False


# --- JavaScript snippets & Classcard DOM selectors ---

_CLASS_LIST_JS = r"""
var out = [], seen = {};
var skip = ['home', '세트', '설정', '리포트', '쪽지'];
document.querySelectorAll('a[href^="/ClassMain/"], a[href^="/ClassReports/"]').forEach(function (a) {
  var href = a.getAttribute('href') || '';
  var m = href.match(/^\/Class(?:Main|Reports)\/(?:users\/)?(\d+)$/);
  if (!m) return;
  var name = (a.textContent || '').replace(/\s+/g, ' ').trim();
  if (!name || skip.indexOf(name.toLowerCase()) !== -1) return;
  var key = m[1] + '|' + name;
  if (seen[key]) return;
  seen[key] = 1;
  out.push({idx: m[1], name: name});
});
return out;
"""

_CLASS_LIST_FETCH_JS = r"""
var cb = arguments[arguments.length - 1];
fetch('/Main/user', {credentials: 'include'})
  .then(function (r) { return r.text(); })
  .then(function (t) {
    var doc = new DOMParser().parseFromString(t, 'text/html');
    var out = [], seen = {};
    var skip = ['home', '세트', '설정', '리포트', '쪽지'];
    doc.querySelectorAll('a[href^="/ClassMain/"], a[href^="/ClassReports/"]').forEach(function (a) {
      var href = a.getAttribute('href') || '';
      var m = href.match(/^\/Class(?:Main|Reports)\/(?:users\/)?(\d+)$/);
      if (!m) return;
      var name = (a.textContent || '').replace(/\s+/g, ' ').trim();
      if (!name || skip.indexOf(name.toLowerCase()) !== -1) return;
      var key = m[1] + '|' + name;
      if (seen[key]) return;
      seen[key] = 1;
      out.push({idx: m[1], name: name});
    });
    cb(out);
  })
  .catch(function () { cb(null); });
"""

_SET_LIST_JS = r"""
var out = [];
document.querySelectorAll('.set-items[data-idx]').forEach(function (row) {
  var a = row.querySelector('.set-name-a');
  if (!a) return;
  var cnt = a.querySelector('span');
  var name = (a.textContent || '').replace(/\s+/g, ' ').trim();
  var count = cnt ? (cnt.textContent || '').trim() : '';
  if (count) name = name.replace(count, '').trim();
  var icon = row.querySelector('.set-icon');
  out.push({
    idx: row.getAttribute('data-idx'),
    name: name,
    count: count,
    current: row.className.indexOf('disabled') === -1,
    learning: row.className.indexOf('learn_set') !== -1,
    sentence: !!(icon && icon.className.indexOf('sentence') !== -1)
  });
});
return out;
"""

_SET_LIST_FETCH_JS = r"""
var cb = arguments[arguments.length - 1];
fetch('/ClassMain/' + arguments[0], {credentials: 'include'})
  .then(function (r) { return r.text(); })
  .then(function (t) {
    var doc = new DOMParser().parseFromString(t, 'text/html');
    var out = [];
    doc.querySelectorAll('.set-items[data-idx]').forEach(function (row) {
      var a = row.querySelector('.set-name-a');
      if (!a) return;
      var cnt = a.querySelector('span');
      var name = (a.textContent || '').replace(/\s+/g, ' ').trim();
      var count = cnt ? (cnt.textContent || '').trim() : '';
      if (count) name = name.replace(count, '').trim();
      var icon = row.querySelector('.set-icon');
      out.push({
        idx: row.getAttribute('data-idx'),
        name: name,
        count: count,
        current: row.className.indexOf('disabled') === -1,
        learning: row.className.indexOf('learn_set') !== -1,
        sentence: !!(icon && icon.className.indexOf('sentence') !== -1)
      });
    });
    cb(out);
  })
  .catch(function () { cb(null); });
"""

_SET_DETAIL_JS = r"""
function rate(sel) {
  var el = document.querySelector(sel);
  if (!el) return null;
  var m = (el.textContent || '').match(/(\d+)\s*%/);
  return m ? parseInt(m[1], 10) : null;
}
var cards = [];
document.querySelectorAll('.flip-card').forEach(function (c) {
  var eng = c.querySelector('.ex_front'), kor = c.querySelector('.ex_back');
  if (!eng || !kor) return;
  var e = (eng.innerText || '').trim(), k = (kor.innerText || '').trim();
  if (e && k) cards.push({eng: e, kor: k});
});
var segs = [], segDone = {};
document.querySelectorAll('a[onclick*="/Memorize/"], a[onclick*="/Recall/"], a[onclick*="/Spell/"]').forEach(function (a) {
  var m = (a.getAttribute('onclick') || '').match(/\/(Memorize|Recall|Spell)\/(\d+)\/(\d+)\/(\d+)/);
  if (!m) return;
  var seg = parseInt(m[3], 10);
  if (seg >= 1000) return;
  var mode = m[1].toLowerCase();
  if (segs.indexOf(seg) === -1) segs.push(seg);
  if (!segDone[seg]) segDone[seg] = {};
  segDone[seg][mode] = a.className.indexOf('progress-100') !== -1;
});
segs.sort(function (a, b) { return a - b; });
return {
  cards: cards,
  segments: segs,
  seg_done: segDone,
  memorize: rate('.mem-total-rate'),
  recall: rate('.recall-total-rate'),
  spell: rate('.spell-total-rate'),
  title: (document.title || '').replace('클래스카드 | ', '').trim()
};
"""

_SET_DETAIL_FETCH_JS = r"""
var cb = arguments[arguments.length - 1];
fetch('/set/' + arguments[0] + '/' + arguments[1], {credentials: 'include'})
  .then(function (r) { return r.text(); })
  .then(function (t) {
    var doc = new DOMParser().parseFromString(t, 'text/html');
    function rate(sel) {
      var el = doc.querySelector(sel);
      if (!el) return null;
      var m = (el.textContent || '').match(/(\d+)\s*%/);
      return m ? parseInt(m[1], 10) : null;
    }
    function cardText(el) {
      if (!el) return '';
      var clone = el.cloneNode(true);
      clone.querySelectorAll('br').forEach(function (br) { br.replaceWith('\n'); });
      return (clone.textContent || '').trim();
    }
    var cards = [];
    doc.querySelectorAll('.flip-card').forEach(function (c) {
      var eng = c.querySelector('.ex_front'), kor = c.querySelector('.ex_back');
      if (!eng || !kor) return;
      var e = cardText(eng), k = cardText(kor);
      if (e && k) cards.push({eng: e, kor: k});
    });
    var segs = [], segDone = {};
    doc.querySelectorAll('a[onclick*="/Memorize/"], a[onclick*="/Recall/"], a[onclick*="/Spell/"]').forEach(function (a) {
      var m = (a.getAttribute('onclick') || '').match(/\/(Memorize|Recall|Spell)\/(\d+)\/(\d+)\/(\d+)/);
      if (!m) return;
      var seg = parseInt(m[3], 10);
      if (seg >= 1000) return;
      var mode = m[1].toLowerCase();
      if (segs.indexOf(seg) === -1) segs.push(seg);
      if (!segDone[seg]) segDone[seg] = {};
      segDone[seg][mode] = a.className.indexOf('progress-100') !== -1;
    });
    segs.sort(function (a, b) { return a - b; });
    var titleEl = doc.querySelector('title');
    var title = titleEl ? (titleEl.textContent || '').replace('클래스카드 | ', '').trim() : '';
    cb({
      cards: cards,
      segments: segs,
      seg_done: segDone,
      memorize: rate('.mem-total-rate'),
      recall: rate('.recall-total-rate'),
      spell: rate('.spell-total-rate'),
      title: title
    });
  })
  .catch(function () { cb(null); });
"""

_RATES_BATCH_JS = r"""
var cb = arguments[arguments.length - 1];
var ids = arguments[0], cls = arguments[1];
function one(id) {
  return fetch('/set/' + id + '/' + cls, {credentials: 'include'})
    .then(function (r) { return r.text(); })
    .then(function (t) {
      var doc = new DOMParser().parseFromString(t, 'text/html');
      function rate(sel) {
        var el = doc.querySelector(sel);
        if (!el) return null;
        var m = (el.textContent || '').match(/(\d+)\s*%/);
        return m ? parseInt(m[1], 10) : null;
      }
      var segs = [], segDone = {};
      doc.querySelectorAll('a[onclick*="/Memorize/"], a[onclick*="/Recall/"], a[onclick*="/Spell/"]').forEach(function (a) {
        var m = (a.getAttribute('onclick') || '').match(/\/(Memorize|Recall|Spell)\/(\d+)\/(\d+)\/(\d+)/);
        if (!m) return;
        var seg = parseInt(m[3], 10);
        if (seg >= 1000) return;
        var mode = m[1].toLowerCase();
        if (segs.indexOf(seg) === -1) segs.push(seg);
        if (!segDone[seg]) segDone[seg] = {};
        segDone[seg][mode] = a.className.indexOf('progress-100') !== -1;
      });
      segs.sort(function (a, b) { return a - b; });
      var got = doc.querySelectorAll('.flip-card').length > 0;
      return {idx: String(id), ok: got, segments: segs, seg_done: segDone,
              memorize: rate('.mem-total-rate'),
              recall: rate('.recall-total-rate'),
              spell: rate('.spell-total-rate')};
    })
    .catch(function (e) { return {idx: String(id), ok: false}; });
}
Promise.all(ids.map(one)).then(cb);
"""

_CLASS_REPORT_JS = r"""
var cb = arguments[arguments.length - 1];
fetch('/ClassReports/users/' + arguments[0], {credentials: 'include'})
  .then(function (r) { return r.text(); })
  .then(function (t) {
    var doc = new DOMParser().parseFromString(t, 'text/html');
    var out = {};
    doc.querySelectorAll('div.class-report-panel').forEach(function (p) {
      var m = (p.className || '').match(/penel-row(\d+)/);
      if (!m) return;
      var rec = {memorize: null, recall: null, spell: null, test: ''};
      p.querySelectorAll('.report-set > div').forEach(function (cell) {
        var s = (cell.textContent || '').replace(/\s+/g, ' ').trim();
        var pct = s.match(/(\d+)\s*%/);
        var n = pct ? parseInt(pct[1], 10) : null;
        if (s.indexOf('암기학습') === 0) rec.memorize = n;
        else if (s.indexOf('리콜학습') === 0) rec.recall = n;
        else if (s.indexOf('스펠학습') === 0) rec.spell = n;
      });
      var a = p.querySelector('a[href*="getTestReport"]');
      if (a) {
        var span = a.querySelector('span');
        var when = span ? (span.textContent || '').trim() : '';
        var rest = (a.textContent || '').replace(when, ' ')
                     .replace(/\s+/g, ' ').trim();
        rec.test = (when + ' | ' + rest).trim();
      }
      out[m[1]] = rec;
    });
    cb(out);
  })
  .catch(function (e) { cb(null); });
"""

_SET_CARDS_FETCH_JS = r"""
var cb = arguments[arguments.length - 1];
fetch('/set/' + arguments[0] + '/' + arguments[1], {credentials: 'include'})
  .then(function (r) { return r.text(); })
  .then(function (t) {
    var doc = new DOMParser().parseFromString(t, 'text/html');
    var out = [];
    doc.querySelectorAll('.flip-card').forEach(function (c) {
      var e = c.querySelector('.ex_front'), k = c.querySelector('.ex_back');
      if (!e || !k) return;
      var a = (e.textContent || '').trim(), b = (k.textContent || '').trim();
      if (a && b) out.push({eng: a, kor: b});
    });
    cb(out);
  })
  .catch(function () { cb(null); });
"""

_LOGIN_FILL_JS = r"""
function visible(el) {
  if (!el) return null;
  var r = el.getBoundingClientRect();
  return (r.width > 0 && r.height > 0) ? el : null;
}
var id = visible(document.querySelector('input[name="login_id"]'))
      || visible(document.querySelector('#login_id'))
      || visible(document.querySelector('input[name="user_id"]'));
var pw = visible(document.querySelector('input[type="password"]'))
      || visible(document.querySelector('input[name="login_pwd"]'))
      || visible(document.querySelector('#login_pwd'));
if (!id || !pw) return 0;
function fill(el, value) {
  el.focus();
  el.value = value;
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
  el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
}
fill(id, arguments[0]);
fill(pw, arguments[1]);
return (pw.value || '').length;
"""

_BUTTON_BY_TEXT_JS = r"""
var wanted = arguments[0] || [];
var patterns = arguments[1] || [];
var nodes = document.querySelectorAll('a, button, input[type="button"], div, span, p');
for (var i = 0; i < nodes.length; i++) {
  var el = nodes[i];
  var t = (el.textContent || el.value || '').replace(/\s+/g, ' ').trim();
  if (!t) continue;
  var hit = wanted.indexOf(t) !== -1;
  for (var k = 0; !hit && k < patterns.length; k++) {
    try {
      if (new RegExp(patterns[k]).test(t)) hit = true;
    } catch (e) {}
  }
  if (!hit) continue;
  if (!document.hidden && typeof el.checkVisibility === 'function') {
    try {
      if (!el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) continue;
    } catch (e) {}
  }
  var r = el.getBoundingClientRect();
  if (r.width > 0 && r.height > 0) return el;
}
return null;
"""

_DISPATCH_KEY_JS = r"""
var key = arguments[0];
var opts = {key: key, code: key === ' ' ? 'Space' : 'Digit' + key,
  keyCode: key === ' ' ? 32 : key.charCodeAt(0),
  which: key === ' ' ? 32 : key.charCodeAt(0),
  bubbles: true, cancelable: true};
document.activeElement.dispatchEvent(new KeyboardEvent('keydown', opts));
document.activeElement.dispatchEvent(new KeyboardEvent('keypress', opts));
document.activeElement.dispatchEvent(new KeyboardEvent('keyup', opts));
"""

PROGRESS_JS = r"""
var t = (document.body.innerText || '').split('\n');
for (var i = 0; i < t.length; i++) {
  var m = t[i].trim().match(/^([0-9]+)\s*\/\s*([0-9]+)$/);
  if (m) return [parseInt(m[1], 10), parseInt(m[2], 10)];
}
return null;
"""


# --- Driver lifecycle ---

def _chrome_debug_port_open():
  try:
    with socket.create_connection(('127.0.0.1', CHROME_DEBUG_PORT), timeout=0.3):
      return True
  except OSError:
    return False


def keep_page_awake(driver):
  """Prevent Chrome from throttling background or occluded study tabs."""
  try:
    driver.execute_cdp_cmd('Emulation.setFocusEmulationEnabled', {'enabled': True})
  except Exception:
    pass


def get_shared_driver():
  """Return the currently tracked WebDriver instance without creating one."""
  with _driver_lock:
    return _shared_driver


def get_driver():
  """Return a live Chrome WebDriver, reconnecting on debug port or launching Chrome."""
  global _shared_driver
  with _driver_lock:
    if _shared_driver is not None:
      try:
        _ = _shared_driver.current_url
        return _shared_driver
      except Exception:
        _shared_driver = None

    if _chrome_debug_port_open():
      try:
        attach = ChromeOptions()
        attach.add_experimental_option(
            'debuggerAddress', f'127.0.0.1:{CHROME_DEBUG_PORT}'
        )
        _shared_driver = ChromeDriver(options=attach)
        keep_page_awake(_shared_driver)
        return _shared_driver
      except Exception:
        _shared_driver = None

    options = ChromeOptions()
    options.add_experimental_option('detach', True)
    options.add_argument(f'--remote-debugging-port={CHROME_DEBUG_PORT}')
    for flag in (
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '--disable-background-timer-throttling',
    ):
      options.add_argument(flag)

    if sys.platform == 'darwin':
      default_mac_chrome = (
          '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
      )
      if os.path.exists(default_mac_chrome) and not options.binary_location:
        options.binary_location = default_mac_chrome

    _shared_driver = ChromeDriver(options=options)
    keep_page_awake(_shared_driver)
    _shared_driver.get(SITE_URL)
    return _shared_driver


def close_driver_service():
  """Stop chromedriver service cleanly while leaving the detached Chrome window open."""
  global _shared_driver, _data_tab
  with _driver_lock:
    if _shared_driver is not None:
      try:
        _shared_driver.service.stop()
      except Exception:
        pass
      _shared_driver = None
    _data_tab = None


# --- Navigation, tabs & auth ---

def wait_page_ready(driver, timeout=8.0):
  """Wait until document.readyState reaches 'complete'."""
  end = time.time() + timeout
  while time.time() < end:
    try:
      if driver.execute_script('return document.readyState;') == 'complete':
        return True
    except Exception:
      return False
    time.sleep(0.1)
  return False


def _on_classcard_site(driver) -> bool:
  try:
    return 'classcard.net' in (driver.current_url or '').lower()
  except Exception:
    return False


def _js_navigate_and_wait(driver, url: str, timeout: float = 8.0) -> bool:
  """Navigate via window.location.href (same-origin) and wait for the new page load."""
  try:
    prev_url = driver.current_url or ''
  except Exception:
    prev_url = ''

  if prev_url.rstrip('/') == url.rstrip('/'):
    driver.execute_script('window.location.reload();')
    time.sleep(0.3)
    return wait_page_ready(driver, timeout)

  driver.execute_script('window.location.href = arguments[0];', url)
  end = time.time() + timeout
  saw_change = False
  while time.time() < end:
    try:
      cur = driver.current_url or ''
      if cur != prev_url:
        saw_change = True
      if saw_change and driver.execute_script('return document.readyState;') == 'complete':
        return True
    except Exception:
      pass
    time.sleep(0.08)
  return wait_page_ready(driver, 1.5)


def open_site(driver, path):
  """Navigate to a Classcard path (or full URL) without stealing OS window focus."""
  url = path if str(path).startswith('http') else SITE_URL + path
  try:
    cur = (driver.current_url or '').rstrip('/')
    if cur != url.rstrip('/'):
      if _on_classcard_site(driver) and 'classcard.net' in url.lower():
        return _js_navigate_and_wait(driver, url, 8.0)
      driver.get(url)
    wait_page_ready(driver)
    return True
  except Exception:
    return False


def navigate_study_url(driver, url: str, timeout: float = 6.0) -> bool:
  """Navigate the active tab to a Classcard study/test URL without raising the Chrome window."""
  try:
    if _on_classcard_site(driver) and 'classcard.net' in (url or '').lower():
      return _js_navigate_and_wait(driver, url, timeout)
    driver.get(url)
    wait_page_ready(driver, timeout)
    return True
  except Exception:
    return False


def dismiss_alert(driver):
  """Accept an active browser alert dialog if present."""
  try:
    alert = driver.switch_to.alert
  except Exception:
    return False
  try:
    _ = alert.text
    alert.accept()
    return True
  except Exception:
    return False


def logged_in(driver):
  """Return True if the active browser session is authenticated on Classcard."""
  try:
    return bool(driver.execute_script('return !!(window.c_u && window.c_u > 0);'))
  except Exception:
    return False


def auto_login(driver, cred=None):
  """Log in using provided or stored encrypted credentials. Returns True on success."""
  if cred is None:
    cred = config_store.load_login()
  if not cred or not cred.get('id') or not cred.get('pw'):
    return False

  dismiss_alert(driver)
  if not open_site(driver, '/Login'):
    return False
  dismiss_alert(driver)
  if logged_in(driver):
    return True

  for attempt in range(3):
    if attempt:
      open_site(driver, '/Login')
    dismiss_alert(driver)

    typed = 0
    end = time.time() + 3.0
    while time.time() < end:
      try:
        typed = driver.execute_script(_LOGIN_FILL_JS, cred['id'], cred['pw'])
      except Exception:
        typed = 0
        if dismiss_alert(driver):
          continue
      if typed:
        break
      time.sleep(0.1)
    if not typed:
      continue

    if not click_button_by_text(driver, ['로그인'], wait_after=0):
      try:
        driver.execute_script(
            'var f = document.querySelector(\'input[name="login_pwd"]\');'
            'if (f && f.form) f.form.submit();'
        )
      except Exception:
        pass

    end = time.time() + 8.0
    while time.time() < end:
      if logged_in(driver):
        return True
      if dismiss_alert(driver):
        break
      time.sleep(0.12)
  return False


def idx_from_url(url):
  """Extract (set_idx, class_idx) from a Classcard set/study/test URL."""
  clean = (url or '').split('?')[0]
  m = re.search(r'/(?:Memorize|Recall|Spell)/(\d+)/\d+/(\d+)', clean, re.I) or re.search(
      r'/set/(\d+)/(\d+)', clean, re.I
  )
  if m:
    return m.group(1), m.group(2)
  m = re.search(r'/ClassTest/(\d+)/(\d+)', clean, re.I)
  return (m.group(2), m.group(1)) if m else (None, None)


def is_study_tab(url):
  """Return True if the URL corresponds to an active study or test screen."""
  low = (url or '').lower()
  return any(part in low for part in _STUDY_URL_PARTS)


def enter_data_tab(driver, allow_new_tab=None):
  """Switch to a non-study tab for scraping and return the previous window handle."""
  global _data_tab
  try:
    prev = driver.current_window_handle
    handles = driver.window_handles
  except Exception:
    return None

  try:
    if not is_study_tab(driver.current_url):
      _data_tab = prev
      return prev
  except Exception:
    pass

  if _data_tab in handles and _data_tab != prev:
    try:
      driver.switch_to.window(_data_tab)
      return prev
    except Exception:
      pass

  for handle in handles:
    if handle == prev:
      continue
    try:
      driver.switch_to.window(handle)
      if not is_study_tab(driver.current_url):
        _data_tab = handle
        return prev
    except Exception:
      continue

  try:
    driver.switch_to.window(prev)
  except Exception:
    return None

  should_open = _is_busy() if allow_new_tab is None else bool(allow_new_tab)
  if not should_open:
    _data_tab = prev
    return prev

  try:
    driver.switch_to.new_window('tab')
    _data_tab = driver.current_window_handle
  except Exception:
    return None
  return prev


def leave_data_tab(driver, prev):
  """Return focus to the window handle returned by enter_data_tab() only if tab changed."""
  try:
    if prev and driver.current_window_handle != prev and prev in driver.window_handles:
      driver.switch_to.window(prev)
  except Exception:
    pass


def focus_study_tab(driver, hint=None):
  """Switch focus to a Chrome tab matching hint (or any Classcard study tab)."""
  wanted = (hint.lower(),) if hint else _STUDY_URL_PARTS

  def matches(url):
    low = (url or '').lower()
    return any(h in low for h in wanted)

  try:
    if matches(driver.current_url):
      return True
  except Exception:
    return False

  try:
    current = driver.current_window_handle
  except Exception:
    current = None

  try:
    targets = driver.execute_cdp_cmd('Target.getTargets', {})
    for info in targets.get('targetInfos', []):
      if info.get('type') != 'page' or not matches(info.get('url')):
        continue
      handle = info.get('targetId')
      if not handle or handle == current:
        continue
      try:
        driver.switch_to.window(handle)
        return True
      except Exception:
        continue
  except Exception:
    pass

  # Fallback when CDP Target.getTargets is unavailable.
  try:
    for handle in driver.window_handles:
      if handle == current:
        continue
      try:
        driver.switch_to.window(handle)
        if matches(driver.current_url):
          return True
      except Exception:
        continue
    if current and current in driver.window_handles:
      driver.switch_to.window(current)
  except Exception:
    pass
  return False


# --- Data fetchers ---

def unique_cards(cards):
  """Deduplicate card dicts while preserving order and stripping whitespace."""
  seen = set()
  uniq = []
  for c in cards or []:
    eng = (c.get('eng') or '').strip()
    kor = (c.get('kor') or '').strip()
    if eng and kor and (eng, kor) not in seen:
      seen.add((eng, kor))
      uniq.append({'eng': eng, 'kor': kor})
  return uniq


def _read_until(driver, script, tries=6, gap=0.4):
  for i in range(tries):
    try:
      out = driver.execute_script(script) or []
    except Exception:
      out = []
    if out:
      return out
    if i < tries - 1:
      time.sleep(gap)
  return []


def fetch_classes(driver):
  """Return [{'idx', 'name'}, ...] for the logged-in user, or []."""
  if _on_classcard_site(driver) and logged_in(driver):
    try:
      out = driver.execute_async_script(_CLASS_LIST_FETCH_JS) or []
      if out:
        return out
    except Exception:
      pass

  prev = enter_data_tab(driver)
  try:
    if not open_site(driver, '/Main/user'):
      return []
    if not logged_in(driver):
      return []
    return _read_until(driver, _CLASS_LIST_JS)
  except Exception:
    return []
  finally:
    leave_data_tab(driver, prev)


def fetch_sets(driver, class_idx):
  """Return set metadata rows for a class using background fetch when possible."""
  if _on_classcard_site(driver):
    try:
      out = driver.execute_async_script(_SET_LIST_FETCH_JS, str(class_idx)) or []
      if out:
        return out
    except Exception:
      pass

  prev = enter_data_tab(driver)
  try:
    if not open_site(driver, f'/ClassMain/{class_idx}'):
      return []
    return _read_until(driver, _SET_LIST_JS)
  except Exception:
    return []
  finally:
    leave_data_tab(driver, prev)


def fetch_set_detail(driver, set_idx, class_idx):
  """Return cards, segment numbers, per-segment completion, and rates for a set."""
  data = None
  if _on_classcard_site(driver):
    try:
      fetched = driver.execute_async_script(
          _SET_DETAIL_FETCH_JS, str(set_idx), str(class_idx)
      )
      if isinstance(fetched, dict) and fetched.get('cards'):
        data = fetched
    except Exception:
      data = None

  if data is None:
    prev = enter_data_tab(driver)
    try:
      if not open_site(driver, f'/set/{set_idx}/{class_idx}'):
        return None
      data = _read_until(driver, _SET_DETAIL_JS) or {}
    except Exception:
      return None
    finally:
      leave_data_tab(driver, prev)

  if not isinstance(data, dict):
    return None
  data['cards'] = unique_cards(data.get('cards'))
  return data


def fetch_class_report(driver, class_idx):
  """Fetch set progress and test report summaries from /ClassReports/users/<class_idx>."""
  try:
    return driver.execute_async_script(_CLASS_REPORT_JS, str(class_idx)) or {}
  except Exception:
    return {}


def fetch_set_rates(driver, class_idx, set_ids):
  """Batch-fetch progress rates and segment completion for multiple set IDs."""
  ids = [str(i) for i in (set_ids or [])]
  if not ids:
    return {}
  try:
    out = driver.execute_async_script(_RATES_BATCH_JS, ids, str(class_idx))
  except Exception:
    return {}
  return {x['idx']: x for x in (out or []) if isinstance(x, dict) and x.get('ok')}


def fetch_set_cards(driver, set_idx, class_idx):
  """Fetch deduplicated cards for a set in the background without navigating."""
  try:
    cards = driver.execute_async_script(
        _SET_CARDS_FETCH_JS, str(set_idx), str(class_idx)
    )
    return unique_cards(cards)
  except Exception:
    return []


# --- DOM interactions & study progress ---

def dispatch_key(driver, key):
  """Dispatch synthetic keydown/keypress/keyup events to document.activeElement."""
  try:
    driver.execute_script(_DISPATCH_KEY_JS, key)
  except Exception:
    pass


def press_space(driver):
  """Send a Space keypress via ActionChains and synthetic key event fallback."""
  try:
    driver.find_element(By.TAG_NAME, 'body').click()
    time.sleep(0.15)
    ActionChains(driver).send_keys(Keys.SPACE).perform()
    dispatch_key(driver, ' ')
    return True
  except Exception:
    return False


def press_submit(driver):
  """Submit the current answer (RETURN on ClassTest, SPACE on study screens)."""
  try:
    on_test = '/classtest/' in (driver.current_url or '').lower()
  except Exception:
    on_test = False
  if not on_test:
    return press_space(driver)
  try:
    driver.find_element(By.TAG_NAME, 'body').click()
    time.sleep(0.1)
    ActionChains(driver).send_keys(Keys.RETURN).perform()
    return True
  except Exception:
    return False


def find_button_by_text(driver, labels, patterns=None):
  """Return the first visible clickable element matching labels or regex patterns."""
  try:
    return driver.execute_script(_BUTTON_BY_TEXT_JS, labels, patterns or [])
  except Exception:
    return None


def click_button_by_text(
    driver, labels, patterns=None, wait_after=1.2, stop_check=None
):
  """Click a matching button (falling back to Space), then wait up to wait_after seconds."""
  btn = find_button_by_text(driver, labels, patterns)
  if not btn:
    return False

  try:
    btn.click()
    moved = True
  except Exception:
    moved = press_space(driver)

  if moved and wait_after > 0:
    steps = int(wait_after / 0.1)
    for _ in range(steps):
      if callable(stop_check) and stop_check():
        break
      time.sleep(0.1)
    rem = wait_after - (steps * 0.1)
    if rem > 0 and not (callable(stop_check) and stop_check()):
      time.sleep(rem)
  return moved


def read_study_progress(driver):
  """Read (done, total) tuple from the current study screen, or None if unavailable."""
  if driver is None:
    return None
  try:
    out = driver.execute_script(PROGRESS_JS)
  except Exception:
    return None
  if out and len(out) == 2:
    try:
      return int(out[0]), int(out[1])
    except (TypeError, ValueError):
      return None
  return None
