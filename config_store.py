"""Thread-safe configuration, encrypted credential, and rate-cache storage."""

import copy
import ctypes
import getpass
import hashlib
import hmac
import json
import os
import platform
import sys
import tempfile
import threading
import uuid


def get_data_dir():
  """Return the platform-specific application data directory."""
  if sys.platform == 'win32':
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'ClasscardMacro')
  if sys.platform == 'darwin':
    return os.path.join(
        os.path.expanduser('~/Library/Application Support'), 'ClasscardMacro'
    )
  return os.path.join(os.path.expanduser('~/.config'), 'ClasscardMacro')


DATA_DIR = get_data_dir()
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
LOGIN_FILE = os.path.join(DATA_DIR, 'login.dat')
RATE_FILE = os.path.join(DATA_DIR, 'rates.json')
_LEGACY_DIR = os.path.join(os.path.expanduser('~'), 'ClasscardMacro')

DEFAULT_CONFIG = {
    'anticheat': True,
    'human_delay': True,
    'theme': 'system',
    'pass_score': 85,
    'class_pass': {},
    'delay_enabled': True,
    'delay_min': 15,
    'delay_max': 45,
    'wrong_enabled': False,
    'wrong_min': 1,
    'wrong_max': 2,
    'study_modes': {
        'memorize': True,
        'recall': True,
        'spell': True,
        'test': True,
    },
    'always_on_top': False,
}

_lock = threading.RLock()
_config_cache = None


def _legacy_path(filename):
  return os.path.join(_LEGACY_DIR, filename)


def _resolve_read_path(primary_path, filename):
  if os.path.exists(primary_path):
    return primary_path
  legacy = _legacy_path(filename)
  if os.path.exists(legacy):
    return legacy
  return None


def _atomic_write_bytes(path, data):
  parent = os.path.dirname(os.path.abspath(path))
  os.makedirs(parent, exist_ok=True)
  fd, tmp_path = tempfile.mkstemp(prefix='.tmp_', dir=parent)
  try:
    with os.fdopen(fd, 'wb') as f:
      f.write(data)
      f.flush()
      os.fsync(f.fileno())
    os.replace(tmp_path, path)
  except Exception:
    try:
      if os.path.exists(tmp_path):
        os.remove(tmp_path)
    except OSError:
      pass
    raise


def _atomic_write_json(path, data, indent=2):
  payload = json.dumps(data, ensure_ascii=False, indent=indent).encode('utf-8')
  _atomic_write_bytes(path, payload)


def _clamp_int(value, default, minimum=None, maximum=None):
  try:
    num = int(value)
  except (TypeError, ValueError):
    num = default
  if minimum is not None:
    num = max(minimum, num)
  if maximum is not None:
    num = min(maximum, num)
  return num


def _normalize_config(raw):
  cfg = copy.deepcopy(DEFAULT_CONFIG)
  if not isinstance(raw, dict):
    return cfg

  # Migrate legacy `test_cutoff` key if `pass_score` is absent.
  if 'pass_score' not in raw and 'test_cutoff' in raw:
    raw = dict(raw)
    raw['pass_score'] = raw['test_cutoff']

  for bool_key in (
      'anticheat',
      'human_delay',
      'delay_enabled',
      'wrong_enabled',
      'always_on_top',
  ):
    if bool_key in raw:
      cfg[bool_key] = bool(raw[bool_key])

  theme = raw.get('theme')
  if theme in ('light', 'dark', 'system'):
    cfg['theme'] = theme

  cfg['pass_score'] = _clamp_int(
      raw.get('pass_score'), DEFAULT_CONFIG['pass_score'], 0, 100
  )
  cfg['delay_min'] = _clamp_int(
      raw.get('delay_min'), DEFAULT_CONFIG['delay_min'], 1, 3600
  )
  cfg['delay_max'] = _clamp_int(
      raw.get('delay_max'), DEFAULT_CONFIG['delay_max'], 1, 3600
  )
  if cfg['delay_max'] < cfg['delay_min']:
    cfg['delay_max'] = cfg['delay_min']

  cfg['wrong_min'] = _clamp_int(
      raw.get('wrong_min'), DEFAULT_CONFIG['wrong_min'], 0, 100
  )
  cfg['wrong_max'] = _clamp_int(
      raw.get('wrong_max'), DEFAULT_CONFIG['wrong_max'], 0, 100
  )
  if cfg['wrong_max'] < cfg['wrong_min']:
    cfg['wrong_max'] = cfg['wrong_min']

  raw_class_pass = raw.get('class_pass')
  if isinstance(raw_class_pass, dict):
    normalized_cp = {}
    for k, v in raw_class_pass.items():
      if k is None or str(k) == '':
        continue
      normalized_cp[str(k)] = _clamp_int(v, cfg['pass_score'], 0, 100)
    cfg['class_pass'] = normalized_cp

  raw_modes = raw.get('study_modes')
  if isinstance(raw_modes, dict):
    for mode in DEFAULT_CONFIG['study_modes']:
      if mode in raw_modes:
        cfg['study_modes'][mode] = bool(raw_modes[mode])

  return cfg


def load_config():
  """Load and normalize config.json (with legacy ~/ClasscardMacro fallback)."""
  global _config_cache
  with _lock:
    target = _resolve_read_path(CONFIG_FILE, 'config.json')
    raw = {}
    if target:
      try:
        with open(target, 'r', encoding='utf-8') as f:
          data = json.load(f)
        if isinstance(data, dict):
          raw = data
      except Exception:
        raw = {}
    _config_cache = _normalize_config(raw)
    return copy.deepcopy(_config_cache)


def _ensure_loaded():
  if _config_cache is None:
    load_config()


def save_config(cfg=None):
  """Persist configuration atomically to CONFIG_FILE."""
  global _config_cache
  with _lock:
    if cfg is None:
      _ensure_loaded()
      normalized = _normalize_config(_config_cache)
    else:
      normalized = _normalize_config(cfg)
    _config_cache = normalized
    _atomic_write_json(CONFIG_FILE, normalized, indent=2)
    return copy.deepcopy(_config_cache)


def config_get(key, default=None):
  """Thread-safe lookup of a single configuration value."""
  with _lock:
    _ensure_loaded()
    if key in _config_cache:
      return copy.deepcopy(_config_cache[key])
    return copy.deepcopy(default)


def config_set(key, value):
  """Thread-safe update of a single configuration key and immediate save."""
  with _lock:
    _ensure_loaded()
    updated = copy.deepcopy(_config_cache)
    updated[key] = value
    return save_config(updated)


def config_update(updates):
  """Thread-safe batch update of configuration keys and immediate save."""
  if not isinstance(updates, dict):
    return get_all_config()
  with _lock:
    _ensure_loaded()
    updated = copy.deepcopy(_config_cache)
    for k, v in updates.items():
      if k in ('study_modes', 'class_pass') and isinstance(v, dict):
        merged = dict(updated.get(k) or {})
        merged.update(v)
        updated[k] = merged
      else:
        updated[k] = v
    return save_config(updated)


def get_all_config():
  """Return a deep copy of the current configuration."""
  with _lock:
    _ensure_loaded()
    return copy.deepcopy(_config_cache)


def get_class_pass_score(class_idx):
  """Return the pass score cutoff (0-100) for a class, or global pass_score."""
  with _lock:
    _ensure_loaded()
    default_score = _clamp_int(
        _config_cache.get('pass_score'), DEFAULT_CONFIG['pass_score'], 0, 100
    )
    if class_idx is None or str(class_idx) == '':
      return default_score
    overrides = _config_cache.get('class_pass') or {}
    key = str(class_idx)
    if key in overrides:
      return _clamp_int(overrides[key], default_score, 0, 100)
    return default_score


def set_class_pass_score(class_idx, score):
  """Set (or clear if score is None) a per-class pass score override."""
  if class_idx is None or str(class_idx) == '':
    return get_class_pass_score(class_idx)
  with _lock:
    _ensure_loaded()
    updated = copy.deepcopy(_config_cache)
    overrides = dict(updated.get('class_pass') or {})
    key = str(class_idx)
    if score is None:
      overrides.pop(key, None)
    else:
      overrides[key] = _clamp_int(score, updated['pass_score'], 0, 100)
    updated['class_pass'] = overrides
    save_config(updated)
    return get_class_pass_score(class_idx)


# --- Credential encryption (Windows DPAPI + macOS/Linux HMAC-SHA256 MAC1) ---
if sys.platform == 'win32':
  class _DataBlob(ctypes.Structure):
    _fields_ = [
        ('cbData', ctypes.c_ulong),
        ('pbData', ctypes.POINTER(ctypes.c_char)),
    ]

  def _dpapi(func, data):
    """Encrypt or decrypt bytes using Windows DPAPI."""
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _DataBlob(
        len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))
    )
    blob_out = _DataBlob()
    ok = func(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    if not ok:
      raise OSError('Windows DPAPI operation failed.')
    try:
      return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
      ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _get_machine_key():
  parts = [
      str(uuid.getnode()),
      getpass.getuser(),
      platform.node(),
      'ClasscardMacro:Salt:v1',
  ]
  seed = ':'.join(parts).encode('utf-8')
  return hashlib.sha256(seed).digest()


def _keystream(key, nonce, length):
  stream = bytearray()
  counter = 0
  while len(stream) < length:
    block = hmac.new(
        key, nonce + counter.to_bytes(4, 'big'), hashlib.sha256
    ).digest()
    stream.extend(block)
    counter += 1
  return bytes(stream[:length])


def _crypt_non_windows(data, key=None):
  if key is None:
    key = _get_machine_key()
  nonce = os.urandom(16)
  ks = _keystream(key, nonce, len(data))
  ciphertext = bytes(a ^ b for a, b in zip(data, ks))
  tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
  return b'MAC1' + nonce + tag + ciphertext


def _decrypt_non_windows(encrypted_data, key=None):
  if key is None:
    key = _get_machine_key()
  if not encrypted_data.startswith(b'MAC1') or len(encrypted_data) < 4 + 16 + 32:
    raise ValueError('Invalid encrypted credential payload.')
  nonce = encrypted_data[4:20]
  expected_tag = encrypted_data[20:52]
  ciphertext = encrypted_data[52:]
  actual_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
  if not hmac.compare_digest(expected_tag, actual_tag):
    raise ValueError('Credential HMAC verification failed.')
  ks = _keystream(key, nonce, len(ciphertext))
  return bytes(a ^ b for a, b in zip(ciphertext, ks))


def save_login(user_id, user_pw):
  """Encrypt and atomically persist Classcard credentials."""
  raw = json.dumps({'id': user_id, 'pw': user_pw}).encode('utf-8')
  if sys.platform == 'win32':
    enc = _dpapi(ctypes.windll.crypt32.CryptProtectData, raw)
  else:
    enc = _crypt_non_windows(raw)
  with _lock:
    _atomic_write_bytes(LOGIN_FILE, enc)


def load_login():
  """Load and decrypt stored Classcard credentials, or return None."""
  with _lock:
    target = _resolve_read_path(LOGIN_FILE, 'login.dat')
    if not target:
      return None
    try:
      with open(target, 'rb') as f:
        enc = f.read()
      if enc.startswith(b'MAC1'):
        raw = _decrypt_non_windows(enc)
      elif sys.platform == 'win32':
        raw = _dpapi(ctypes.windll.crypt32.CryptUnprotectData, enc)
      else:
        return None
      data = json.loads(raw.decode('utf-8'))
      if data.get('id') and data.get('pw'):
        return {'id': data['id'], 'pw': data['pw']}
    except Exception:
      return None
    return None


def clear_login():
  """Delete stored credential files (current and legacy). Returns True if any deleted."""
  removed = False
  with _lock:
    for path in (LOGIN_FILE, _legacy_path('login.dat')):
      try:
        if os.path.exists(path):
          os.remove(path)
          removed = True
      except OSError:
        pass
  return removed


def load_rate_cache():
  """Load cached set progress and test reports from rates.json."""
  with _lock:
    target = _resolve_read_path(RATE_FILE, 'rates.json')
    if not target:
      return {}
    try:
      with open(target, 'r', encoding='utf-8') as f:
        data = json.load(f)
      return data if isinstance(data, dict) else {}
    except Exception:
      return {}


def save_rate_cache(cache_dict):
  """Atomically save the rate cache dictionary to rates.json."""
  payload = cache_dict if isinstance(cache_dict, dict) else {}
  with _lock:
    _atomic_write_json(RATE_FILE, payload, indent=None)
