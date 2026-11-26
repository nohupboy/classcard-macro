"""Apple DESIGN.md & Liquid Glass pure-Tkinter UI for Classcard Macro."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox

import chrome_bridge
import config_store
import study_engine

UI_FONT_FAMILY = 'Apple SD Gothic Neo' if sys.platform == 'darwin' else '맑은 고딕'
MONO_FONT_FAMILY = 'Menlo' if sys.platform == 'darwin' else 'Consolas'

SENTENCE_MODE_ENABLED = True

THEMES = {
    'light': {
        'mode': 'light',
        'canvas': '#FFFFFF',
        'parchment': '#F5F5F7',
        'pearl': '#FAFAFC',
        'tile_3': '#EFEFF4',
        'ink': '#1D1D1F',
        'ink_muted': '#333333',
        'ink_subtle': '#7A7A7A',
        'hairline': '#E0E0E0',
        'divider_soft': '#F0F0F0',
        'primary': '#0066CC',
        'primary_focus': '#0071E3',
        'primary_pressed': '#0052A3',
        'primary_soft': '#E8F2FC',
        'link': '#0066CC',
        'on_primary': '#FFFFFF',
        'glass_bg': '#FFFFFF',
        'glass_frosted': '#F5F5F7',
        'glass_specular': '#FFFFFF',
        'glass_rim': '#E0E0E0',
        'row_even': '#FFFFFF',
        'row_odd': '#F5F5F7',
        'row_hover': '#EEF3F9',
        'chip_bg': '#F5F5F7',
        'chip_hover': '#E9E9EE',
        'chip_translucent': '#D2D2D7',
        'track': '#E5E5EA',
        'input_bg': '#FFFFFF',
        'green': '#248A3D',
        'green_soft': '#EAF6EE',
        'amber': '#B25000',
        'amber_soft': '#FFF4E5',
        'red': '#D70015',
        'red_soft': '#FDECEC',
        'purple': '#7B2CBF',
        'purple_soft': '#F3EBFA',
        'cyan': '#007AFF',
    },
    'dark': {
        'mode': 'dark',
        'canvas': '#1D1D1F',
        'parchment': '#272729',
        'pearl': '#2A2A2C',
        'tile_3': '#252527',
        'ink': '#FFFFFF',
        'ink_muted': '#CCCCCC',
        'ink_subtle': '#8E8E93',
        'hairline': '#38383A',
        'divider_soft': '#2C2C2E',
        'primary': '#0066CC',
        'primary_focus': '#2997FF',
        'primary_pressed': '#004E9E',
        'primary_soft': '#1B314B',
        'link': '#2997FF',
        'on_primary': '#FFFFFF',
        'glass_bg': '#272729',
        'glass_frosted': '#252527',
        'glass_specular': '#3E3E42',
        'glass_rim': '#38383A',
        'row_even': '#272729',
        'row_odd': '#2A2A2C',
        'row_hover': '#30333A',
        'chip_bg': '#2A2A2C',
        'chip_hover': '#353538',
        'chip_translucent': '#3A3A3C',
        'track': '#38383A',
        'input_bg': '#252527',
        'green': '#30D158',
        'green_soft': '#193322',
        'amber': '#FF9F0A',
        'amber_soft': '#362712',
        'red': '#FF453A',
        'red_soft': '#3A1A1A',
        'purple': '#BF5AF2',
        'purple_soft': '#2F1D3B',
        'cyan': '#64D2FF',
    },
}


def font(size: int, weight: str = 'normal', mono: bool = False) -> tuple:
  family = MONO_FONT_FAMILY if mono else UI_FONT_FAMILY
  if weight and weight != 'normal':
    return (family, size, weight)
  return (family, size)


def detect_system_dark_mode() -> bool:
  """OS 다크 모드 여부를 감지한다."""
  if sys.platform == 'darwin':
    try:
      res = subprocess.run(
          ['defaults', 'read', '-g', 'AppleInterfaceStyle'],
          capture_output=True, text=True, timeout=1,
      )
      return res.stdout.strip().lower() == 'dark'
    except Exception:
      return False
  if sys.platform == 'win32':
    try:
      import winreg
      with winreg.OpenKey(
          winreg.HKEY_CURRENT_USER,
          r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize',
      ) as key:
        val, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
        return int(val) == 0
    except Exception:
      return False
  return False


def resolve_theme(pref: str | None = None) -> dict:
  mode = (pref or config_store.config_get('theme', 'system') or 'system').lower()
  if mode == 'system':
    mode = 'dark' if detect_system_dark_mode() else 'light'
  return THEMES['dark' if mode == 'dark' else 'light']


def draw_round_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float = 18,
    fill: str = '',
    outline: str = '',
    width: int = 1,
    specular: str = '',
    tags: str | tuple = (),
) -> None:
  """Canvas 위에 안티에일리어싱된 라운드 사각형/캡슐과 상단 스페큘러 림을 그린다."""
  w = max(0.0, x2 - x1)
  h = max(0.0, y2 - y1)
  if w < 2 or h < 2:
    return
  r = max(0.0, min(float(radius), w / 2.0, h / 2.0))

  if r < 1.0:
    if fill:
      canvas.create_rectangle(x1, y1, x2, y2, fill=fill, width=0, tags=tags)
    if outline and width > 0:
      canvas.create_rectangle(x1, y1, x2, y2, outline=outline, width=width, tags=tags)
    return

  if fill:
    d = 2.0 * r
    canvas.create_oval(x1, y1, x1 + d, y1 + d, fill=fill, outline='', width=0, tags=tags)
    canvas.create_oval(x2 - d, y1, x2, y1 + d, fill=fill, outline='', width=0, tags=tags)
    canvas.create_oval(x1, y2 - d, x1 + d, y2, fill=fill, outline='', width=0, tags=tags)
    canvas.create_oval(x2 - d, y2 - d, x2, y2, fill=fill, outline='', width=0, tags=tags)
    if x2 - x1 > d - 0.5:
      canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline='', width=0, tags=tags)
    if y2 - y1 > d - 0.5:
      canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline='', width=0, tags=tags)

  if specular and w > 6 and h > 6:
    sr = max(1.0, r - 1.0)
    sd = 2.0 * sr
    canvas.create_arc(
        x1 + 1, y1 + 1, x1 + 1 + sd, y1 + 1 + sd,
        start=105, extent=65, style='arc', outline=specular, width=1, tags=tags,
    )
    canvas.create_arc(
        x2 - 1 - sd, y1 + 1, x2 - 1, y1 + 1 + sd,
        start=10, extent=65, style='arc', outline=specular, width=1, tags=tags,
    )
    if x2 - x1 > 2 * sr + 2:
      canvas.create_line(x1 + 1 + sr, y1 + 1, x2 - 1 - sr, y1 + 1, fill=specular, width=1, tags=tags)

  if outline and width > 0:
    d = 2.0 * r
    canvas.create_arc(x1, y1, x1 + d, y1 + d, start=90, extent=90, style='arc', outline=outline, width=width, tags=tags)
    canvas.create_arc(x2 - d, y1, x2, y1 + d, start=0, extent=90, style='arc', outline=outline, width=width, tags=tags)
    canvas.create_arc(x1, y2 - d, x1 + d, y2, start=180, extent=90, style='arc', outline=outline, width=width, tags=tags)
    canvas.create_arc(x2 - d, y2 - d, x2, y2, start=270, extent=90, style='arc', outline=outline, width=width, tags=tags)
    if x2 - x1 > d:
      canvas.create_line(x1 + r, y1, x2 - r, y1, fill=outline, width=width, tags=tags)
      canvas.create_line(x1 + r, y2, x2 - r, y2, fill=outline, width=width, tags=tags)
    if y2 - y1 > d:
      canvas.create_line(x1, y1 + r, x1, y2 - r, fill=outline, width=width, tags=tags)
      canvas.create_line(x2, y1 + r, x2, y2 - r, fill=outline, width=width, tags=tags)


# ── Reusable Liquid Glass Canvas Widgets ────────────────────────────────────


class GlassCard(tk.Canvas):
  """18px 라운드 + 헤어라인 + 상단 스페큘러 림을 갖춘 Liquid Glass 카드 컨테이너."""

  def __init__(
      self,
      parent,
      theme: dict,
      radius: int = 18,
      padding: tuple[int, int] = (16, 14),
      surface_key: str = 'glass_bg',
      parent_bg_key: str = 'canvas',
      **kw,
  ):
    self._theme = theme
    self._radius = radius
    self._pad_x, self._pad_y = padding
    self._surface_key = surface_key
    self._parent_bg_key = parent_bg_key
    super().__init__(
        parent,
        bg=theme[parent_bg_key],
        highlightthickness=0,
        bd=0,
        **kw,
    )
    self.body = tk.Frame(self, bg=theme[surface_key], bd=0, highlightthickness=0)
    self._win_id = self.create_window(self._pad_x, self._pad_y, window=self.body, anchor='nw')
    self.bind('<Configure>', self._on_configure)
    self.body.bind('<Configure>', self._on_body_configure)

  def _on_body_configure(self, _event=None):
    req_h = self.body.winfo_reqheight() + self._pad_y * 2
    if req_h > 0 and int(self.cget('height') or 0) != req_h and not self.winfo_ismapped():
      self.configure(height=req_h)

  def _on_configure(self, event=None):
    w = event.width if event else self.winfo_width()
    h = event.height if event else self.winfo_height()
    if w < 10 or h < 10:
      return
    inner_w = max(1, w - self._pad_x * 2)
    inner_h = max(1, h - self._pad_y * 2)
    self.coords(self._win_id, self._pad_x, self._pad_y)
    self.itemconfigure(self._win_id, width=inner_w, height=inner_h)
    self._redraw(w, h)

  def _redraw(self, w: int | None = None, h: int | None = None):
    w = w or self.winfo_width()
    h = h or self.winfo_height()
    if w < 6 or h < 6:
      return
    self.delete('glass_bg')
    t = self._theme
    draw_round_rect(
        self, 1, 1, w - 2, h - 2,
        radius=self._radius,
        fill=t[self._surface_key],
        outline=t['hairline'],
        width=1,
        specular=t['glass_specular'],
        tags=('glass_bg',),
    )
    self.tag_lower('glass_bg')

  def apply_theme(self, theme: dict):
    self._theme = theme
    self.configure(bg=theme[self._parent_bg_key])
    self.body.configure(bg=theme[self._surface_key])
    self._redraw()


class GlassPillButton(tk.Canvas):
  """9999px 캡슐 모양의 Liquid Glass Pill 버튼."""

  def __init__(
      self,
      parent,
      text: str,
      command=None,
      theme: dict | None = None,
      variant: str = 'secondary',
      height: int = 34,
      padx: int = 16,
      min_width: int = 0,
      font_spec: tuple | None = None,
      enabled: bool = True,
      parent_bg_key: str = 'canvas',
  ):
    self._theme = theme or THEMES['light']
    self._text = text
    self._command = command
    self._variant = variant
    self._height = height
    self._padx = padx
    self._min_width = min_width
    self._font = font_spec or font(11, 'bold' if variant == 'primary' else 'normal')
    self._enabled = enabled
    self._parent_bg_key = parent_bg_key
    self._hovered = False
    self._pressed = False

    w = self._measure_width()
    super().__init__(
        parent,
        width=w,
        height=height,
        bg=self._theme[parent_bg_key],
        highlightthickness=0,
        bd=0,
        cursor='hand2' if enabled else 'arrow',
    )
    self.bind('<Configure>', lambda _e: self._redraw())
    self.bind('<Enter>', self._on_enter)
    self.bind('<Leave>', self._on_leave)
    self.bind('<ButtonPress-1>', self._on_press)
    self.bind('<ButtonRelease-1>', self._on_release)
    self._redraw()

  def _measure_width(self) -> int:
    # 한글/영문 폭을 넉넉히 추정 (Tk Font measure 폴백 포함)
    try:
      import tkinter.font as tkfont
      tw = tkfont.Font(font=self._font).measure(self._text)
    except Exception:
      tw = len(self._text) * 11
    return max(self._min_width, tw + self._padx * 2)

  def _colors(self) -> tuple[str, str, str, str]:
    """(fill, outline, text_color, specular) 반환."""
    t = self._theme
    if not self._enabled:
      return t['divider_soft'], t['hairline'], t['ink_subtle'], ''

    v = self._variant
    if v == 'primary':
      fill = t['primary_pressed'] if self._pressed else (t['primary_focus'] if self._hovered else t['primary'])
      return fill, '', t['on_primary'], ''
    if v == 'danger':
      fill = t['red'] if self._pressed else (t['red_soft'] if not self._hovered else t['red'])
      fg = t['on_primary'] if (self._pressed or self._hovered) else t['red']
      return fill, t['red'], fg, ''
    if v == 'warning':
      fill = t['amber_soft'] if not self._hovered else t['amber']
      fg = t['on_primary'] if self._hovered else t['amber']
      return fill, t['amber'], fg, ''
    if v == 'pearl':
      fill = t['chip_hover'] if self._hovered else t['pearl']
      return fill, t['hairline'], t['ink_muted'], t['glass_specular']
    if v == 'ghost':
      fill = t['chip_hover'] if (self._hovered or self._pressed) else t[self._parent_bg_key]
      outline = t['hairline'] if self._hovered else ''
      return fill, outline, t['link'], ''
    # secondary
    fill = t['primary_soft'] if self._hovered else t['glass_bg']
    return fill, t['hairline'] if not self._hovered else t['link'], t['link'], t['glass_specular']

  def _redraw(self):
    self.delete('all')
    w = max(int(self.cget('width')), self.winfo_width())
    h = max(int(self.cget('height')), self.winfo_height())
    if w < 4 or h < 4:
      return
    fill, outline, fg, spec = self._colors()
    inset = 2 if (self._pressed and self._enabled) else 1
    draw_round_rect(
        self, inset, inset, w - inset - 1, h - inset - 1,
        radius=9999,
        fill=fill,
        outline=outline,
        width=1,
        specular=spec,
    )
    self.create_text(w / 2.0, h / 2.0, text=self._text, font=self._font, fill=fg, anchor='center')

  def _on_enter(self, _e):
    if self._enabled:
      self._hovered = True
      self._redraw()

  def _on_leave(self, _e):
    self._hovered = False
    self._pressed = False
    self._redraw()

  def _on_press(self, _e):
    if self._enabled:
      self._pressed = True
      self._redraw()

  def _on_release(self, event):
    was_pressed = self._pressed
    self._pressed = False
    self._redraw()
    if was_pressed and self._enabled and self._command:
      w, h = self.winfo_width(), self.winfo_height()
      if 0 <= event.x <= w and 0 <= event.y <= h:
        self._command()

  def set_text(self, text: str):
    if self._text != text:
      self._text = text
      self.configure(width=self._measure_width())
      self._redraw()

  def set_enabled(self, enabled: bool):
    enabled = bool(enabled)
    if self._enabled != enabled:
      self._enabled = enabled
      self.configure(cursor='hand2' if enabled else 'arrow')
      self._redraw()

  def set_variant(self, variant: str):
    if self._variant != variant:
      self._variant = variant
      self._redraw()

  def set_command(self, command):
    self._command = command

  def apply_theme(self, theme: dict, parent_bg_key: str | None = None):
    self._theme = theme
    if parent_bg_key:
      self._parent_bg_key = parent_bg_key
    self.configure(bg=theme[self._parent_bg_key])
    self._redraw()


class GlassChipToggle(tk.Canvas):
  """필터 / ANTICHEAT / 모드 선택용 캡슐 토글 칩."""

  def __init__(
      self,
      parent,
      text: str,
      selected: bool = False,
      on_toggle=None,
      theme: dict | None = None,
      height: int = 28,
      padx: int = 12,
      active_style: str = 'soft',  # 'soft' | 'solid' | 'green'
      parent_bg_key: str = 'glass_bg',
  ):
    self._theme = theme or THEMES['light']
    self._text = text
    self._selected = bool(selected)
    self._on_toggle = on_toggle
    self._height = height
    self._padx = padx
    self._active_style = active_style
    self._parent_bg_key = parent_bg_key
    self._hovered = False

    self._font = font(10, 'bold' if selected else 'normal')
    w = self._measure_width()
    super().__init__(
        parent,
        width=w,
        height=height,
        bg=self._theme[parent_bg_key],
        highlightthickness=0,
        bd=0,
        cursor='hand2',
    )
    self.bind('<Configure>', lambda _e: self._redraw())
    self.bind('<Enter>', lambda _e: self._set_hover(True))
    self.bind('<Leave>', lambda _e: self._set_hover(False))
    self.bind('<ButtonRelease-1>', self._handle_click)
    self._redraw()

  def _measure_width(self) -> int:
    try:
      import tkinter.font as tkfont
      tw = tkfont.Font(font=font(10, 'bold')).measure(self._text)
    except Exception:
      tw = len(self._text) * 10
    return max(44, tw + self._padx * 2)

  def _set_hover(self, state: bool):
    self._hovered = state
    self._redraw()

  def _handle_click(self, _e):
    self._selected = not self._selected
    self._redraw()
    if self._on_toggle:
      self._on_toggle(self._selected)

  def _redraw(self):
    self.delete('all')
    w = max(int(self.cget('width')), self.winfo_width())
    h = max(int(self.cget('height')), self.winfo_height())
    t = self._theme
    if self._selected:
      if self._active_style == 'solid':
        fill, outline, fg, lw = t['primary'], t['primary_focus'], t['on_primary'], 1
      elif self._active_style == 'green':
        fill, outline, fg, lw = t['green_soft'], t['green'], t['green'], 1
      else:
        fill, outline, fg, lw = t['primary_soft'], t['primary_focus'], t['link'], 2
    else:
      fill = t['chip_hover'] if self._hovered else t['chip_bg']
      outline = t['hairline']
      fg = t['ink_muted']
      lw = 1

    draw_round_rect(self, 1, 1, w - 2, h - 2, radius=9999, fill=fill, outline=outline, width=lw)
    self.create_text(
        w / 2.0, h / 2.0,
        text=self._text,
        font=font(10, 'bold' if self._selected else 'normal'),
        fill=fg,
        anchor='center',
    )

  def is_selected(self) -> bool:
    return self._selected

  def set_selected(self, selected: bool, silent: bool = True):
    self._selected = bool(selected)
    self._redraw()
    if not silent and self._on_toggle:
      self._on_toggle(self._selected)

  def set_text(self, text: str):
    if self._text != text:
      self._text = text
      self.configure(width=self._measure_width())
      self._redraw()

  def apply_theme(self, theme: dict, parent_bg_key: str | None = None):
    self._theme = theme
    if parent_bg_key:
      self._parent_bg_key = parent_bg_key
    self.configure(bg=theme[self._parent_bg_key])
    self._redraw()


class GlassSearchBar(tk.Canvas):
  """9999px 캡슐 형태의 Apple 검색 입력 바."""

  def __init__(
      self,
      parent,
      theme: dict,
      placeholder: str = '세트 이름 검색...',
      on_change=None,
      height: int = 34,
      width: int = 240,
      parent_bg_key: str = 'glass_bg',
  ):
    self._theme = theme
    self._placeholder = placeholder
    self._on_change = on_change
    self._height = height
    self._parent_bg_key = parent_bg_key
    self._focused = False
    self._showing_placeholder = True

    super().__init__(
        parent,
        width=width,
        height=height,
        bg=theme[parent_bg_key],
        highlightthickness=0,
        bd=0,
    )
    self.var = tk.StringVar()
    self.entry = tk.Entry(
        self,
        textvariable=self.var,
        bd=0,
        highlightthickness=0,
        font=font(11),
        bg=theme['input_bg'],
        fg=theme['ink_subtle'],
        insertbackground=theme['ink'],
    )
    self.entry.insert(0, placeholder)
    self._entry_win = self.create_window(32, height // 2, window=self.entry, anchor='w', width=max(80, width - 60))

    self.entry.bind('<FocusIn>', self._on_focus_in)
    self.entry.bind('<FocusOut>', self._on_focus_out)
    self.entry.bind('<KeyRelease>', self._on_key)
    self.bind('<Configure>', self._on_configure)
    self.bind('<Button-1>', self._on_canvas_click)
    self._redraw()

  def _on_configure(self, event=None):
    w = event.width if event else self.winfo_width()
    h = event.height if event else self.winfo_height()
    if w < 40:
      return
    self.coords(self._entry_win, 30, h / 2.0)
    self.itemconfigure(self._entry_win, width=max(40, w - 56))
    self._redraw(w, h)

  def _redraw(self, w: int | None = None, h: int | None = None):
    w = w or int(self.cget('width')) or self.winfo_width()
    h = h or int(self.cget('height')) or self.winfo_height()
    self.delete('search_chrome')
    t = self._theme
    outline = t['primary_focus'] if self._focused else t['hairline']
    lw = 2 if self._focused else 1
    draw_round_rect(
        self, 1, 1, w - 2, h - 2,
        radius=9999,
        fill=t['input_bg'],
        outline=outline,
        width=lw,
        tags=('search_chrome',),
    )
    # Leading search glyph
    self.create_text(16, h / 2.0, text='⌕', font=font(14), fill=t['ink_subtle'], tags=('search_chrome',))
    # Clear glyph when non-empty
    if not self._showing_placeholder and self.var.get():
      self.create_text(w - 15, h / 2.0, text='✕', font=font(10), fill=t['ink_subtle'], tags=('search_chrome', 'clear_btn'))

  def _on_canvas_click(self, event):
    w = self.winfo_width()
    if not self._showing_placeholder and self.var.get() and event.x >= w - 28:
      self.clear()
      return
    self.entry.focus_set()

  def _on_focus_in(self, _e):
    self._focused = True
    if self._showing_placeholder:
      self._showing_placeholder = False
      self.entry.delete(0, tk.END)
      self.entry.configure(fg=self._theme['ink'])
    self._redraw()

  def _on_focus_out(self, _e):
    self._focused = False
    if not self.entry.get():
      self._showing_placeholder = True
      self.entry.insert(0, self._placeholder)
      self.entry.configure(fg=self._theme['ink_subtle'])
    self._redraw()

  def _on_key(self, _e=None):
    self._redraw()
    if self._on_change:
      self._on_change(self.get_query())

  def get_query(self) -> str:
    if self._showing_placeholder:
      return ''
    return self.var.get().strip()

  def clear(self):
    self._showing_placeholder = False
    self.entry.delete(0, tk.END)
    self.entry.configure(fg=self._theme['ink'])
    if not self._focused:
      self._showing_placeholder = True
      self.entry.insert(0, self._placeholder)
      self.entry.configure(fg=self._theme['ink_subtle'])
    self._redraw()
    if self._on_change:
      self._on_change('')

  def apply_theme(self, theme: dict, parent_bg_key: str | None = None):
    self._theme = theme
    if parent_bg_key:
      self._parent_bg_key = parent_bg_key
    self.configure(bg=theme[self._parent_bg_key])
    fg = theme['ink_subtle'] if self._showing_placeholder else theme['ink']
    self.entry.configure(bg=theme['input_bg'], fg=fg, insertbackground=theme['ink'])
    self._redraw()


class GlassProgressBar(tk.Canvas):
  """매끄러운 캡슐형 Liquid Glass 프로그레스 바."""

  def __init__(
      self,
      parent,
      theme: dict,
      height: int = 10,
      parent_bg_key: str = 'glass_frosted',
  ):
    self._theme = theme
    self._height = height
    self._pct = 0.0
    self._color_key = 'primary'
    self._parent_bg_key = parent_bg_key
    super().__init__(
        parent,
        height=height,
        bg=theme[parent_bg_key],
        highlightthickness=0,
        bd=0,
    )
    self.bind('<Configure>', lambda _e: self._redraw())

  def set_progress(self, pct: float, color_key: str = 'primary'):
    pct = max(0.0, min(100.0, float(pct)))
    if abs(self._pct - pct) < 0.05 and self._color_key == color_key:
      return
    self._pct = pct
    self._color_key = color_key
    self._redraw()

  def _redraw(self):
    self.delete('all')
    w = self.winfo_width()
    h = self._height
    if w < 10:
      return
    t = self._theme
    draw_round_rect(self, 0, 0, w - 1, h - 1, radius=9999, fill=t['track'])
    if self._pct > 0:
      fill_w = max(h, int(w * (self._pct / 100.0)))
      fill_w = min(w - 1, fill_w)
      fill_color = t.get(self._color_key, t['primary'])
      draw_round_rect(self, 0, 0, fill_w, h - 1, radius=9999, fill=fill_color)

  def apply_theme(self, theme: dict, parent_bg_key: str | None = None):
    self._theme = theme
    if parent_bg_key:
      self._parent_bg_key = parent_bg_key
    self.configure(bg=theme[self._parent_bg_key])
    self._redraw()


class GlassStepper(tk.Canvas):
  """네이티브 Spinbox를 대체하는 깔끔한 캡슐형 − / + 스테퍼."""

  def __init__(
      self,
      parent,
      theme: dict,
      value: int,
      min_val: int,
      max_val: int,
      step: int = 1,
      suffix: str = '',
      on_change=None,
      width: int = 92,
      height: int = 28,
      parent_bg_key: str = 'glass_bg',
  ):
    self._theme = theme
    self._value = int(value)
    self._min = int(min_val)
    self._max = int(max_val)
    self._step = int(step)
    self._suffix = suffix
    self._on_change = on_change
    self._height = height
    self._parent_bg_key = parent_bg_key
    self._hover_side = None  # 'dec' | 'inc' | None

    super().__init__(
        parent,
        width=width,
        height=height,
        bg=theme[parent_bg_key],
        highlightthickness=0,
        bd=0,
        cursor='hand2',
    )
    self.bind('<Configure>', lambda _e: self._redraw())
    self.bind('<Motion>', self._on_motion)
    self.bind('<Leave>', lambda _e: self._set_hover(None))
    self.bind('<ButtonRelease-1>', self._on_click)
    self._redraw()

  def _set_hover(self, side):
    if self._hover_side != side:
      self._hover_side = side
      self._redraw()

  def _on_motion(self, event):
    w = self.winfo_width()
    if event.x < 26:
      self._set_hover('dec')
    elif event.x > w - 26:
      self._set_hover('inc')
    else:
      self._set_hover(None)

  def _on_click(self, event):
    w = self.winfo_width()
    if event.x < 26:
      self.set_value(self._value - self._step, notify=True)
    elif event.x > w - 26:
      self.set_value(self._value + self._step, notify=True)

  def get_value(self) -> int:
    return self._value

  def set_value(self, value: int, notify: bool = False):
    clamped = max(self._min, min(self._max, int(value)))
    if clamped != self._value:
      self._value = clamped
      self._redraw()
      if notify and self._on_change:
        self._on_change(self._value)

  def _redraw(self):
    self.delete('all')
    w = max(int(self.cget('width')), self.winfo_width())
    h = max(int(self.cget('height')), self.winfo_height())
    t = self._theme
    draw_round_rect(
        self, 1, 1, w - 2, h - 2,
        radius=9999,
        fill=t['pearl'],
        outline=t['hairline'],
        width=1,
    )
    dec_fg = t['link'] if self._hover_side == 'dec' else t['ink_muted']
    inc_fg = t['link'] if self._hover_side == 'inc' else t['ink_muted']
    self.create_text(14, h / 2.0, text='−', font=font(12, 'bold'), fill=dec_fg)
    self.create_text(w / 2.0, h / 2.0, text=f'{self._value}{self._suffix}', font=font(10, 'bold'), fill=t['ink'])
    self.create_text(w - 14, h / 2.0, text='+', font=font(12, 'bold'), fill=inc_fg)

  def apply_theme(self, theme: dict, parent_bg_key: str | None = None):
    self._theme = theme
    if parent_bg_key:
      self._parent_bg_key = parent_bg_key
    self.configure(bg=theme[self._parent_bg_key])
    self._redraw()


# ── Main Application ────────────────────────────────────────────────────────


class GlassApp:
  """Classcard Macro Liquid Glass 메인 애플리케이션."""

  def __init__(self, root: tk.Tk | None = None, auto_load: bool = True):
    self.root = root or tk.Tk()
    self.root.title('Classcard Macro')
    self.root.geometry('1200x760')
    self.root.minsize(980, 620)
    self.root.resizable(True, True)

    self.theme_pref = config_store.config_get('theme', 'system')
    self.theme = resolve_theme(self.theme_pref)
    self.root.configure(bg=self.theme['canvas'])
    self.root.wm_attributes('-topmost', bool(config_store.config_get('always_on_top', False)))

    # macOS 표준 단축키
    if sys.platform == 'darwin':
      for cls in ('Entry', 'Text'):
        self.root.bind_class(cls, '<Command-a>', self._mac_select_all)
        self.root.bind_class(cls, '<Command-c>', lambda e: e.widget.event_generate('<<Copy>>'))
        self.root.bind_class(cls, '<Command-v>', lambda e: e.widget.event_generate('<<Paste>>'))
        self.root.bind_class(cls, '<Command-x>', lambda e: e.widget.event_generate('<<Cut>>'))
    self.root.bind('<Escape>', lambda _e: self.stop_all())

    # 상태 데이터
    self._state_lock = threading.RLock()
    self.classes: list[dict] = []
    self.sets: list[dict] = []
    self.current_class_idx = None
    self.checked_targets: dict[str, int] = {}
    self.goal_all: int = 100
    self.rate_cache: dict = config_store.load_rate_cache() or {}
    self.search_query: str = ''
    self.filter_key: str = 'all'  # all | incomplete | failed | word | sentence

    # UI 위젯 레지스트리 (테마 전환 및 상태 갱신용)
    self._themed_widgets: list = []
    self._scrollable_canvases: list[tk.Canvas] = []
    self._class_row_widgets: list[dict] = []
    self._set_row_widgets: list[dict] = []
    self._kpi_canvases: list[tuple[tk.Canvas, dict]] = []
    self._kpi_values: list[dict] = []

    # 모달 창 레퍼런스
    self._settings_win: tk.Toplevel | None = None
    self._dashboard_win: tk.Toplevel | None = None
    self._log_win: tk.Toplevel | None = None
    self._manual_win: tk.Toplevel | None = None
    self._login_win: tk.Toplevel | None = None

    # 수동 모드 상태
    self.manual_kind = tk.StringVar(value='' if SENTENCE_MODE_ENABLED else 'word')
    self.manual_words: list[dict] = []
    self.manual_loaded_set_idx = None
    self._manual_status_var = tk.StringVar(value='크롬에서 세트를 연 뒤 [크롬에서 불러오기]')
    self._manual_kind_chips: dict[str, GlassChipToggle] = {}
    self._manual_refresh_fn = None

    # 1초 라이브 루프 & 체크박스 동기화
    self._tick_job = None
    self._destroyed = False
    self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    # 전역 마우스 휠 라우터
    self.root.bind_all('<MouseWheel>', self._route_mousewheel)
    self.root.bind_all('<Button-4>', lambda e: self._route_mousewheel(e, delta=1))
    self.root.bind_all('<Button-5>', lambda e: self._route_mousewheel(e, delta=-1))

    self._register_engine_callbacks()
    self._build_layout()
    self._apply_theme_everywhere()
    self._render_kpis()
    self._schedule_tick()

    if auto_load:
      self.root.after(250, self.load_classes)

  # ── Theme & Helpers ─────────────────────────────────────────────────────

  @staticmethod
  def _mac_select_all(event):
    w = event.widget
    if isinstance(w, tk.Text):
      w.tag_add('sel', '1.0', 'end-1c')
    else:
      w.select_range(0, 'end')
    return 'break'

  def _ui_call(self, fn, *args, **kwargs):
    if self._destroyed:
      return
    try:
      self.root.after(0, lambda: self._safe_run(fn, *args, **kwargs))
    except tk.TclError:
      pass

  def _safe_run(self, fn, *args, **kwargs):
    if self._destroyed:
      return
    try:
      fn(*args, **kwargs)
    except tk.TclError:
      pass

  def _route_mousewheel(self, event, delta: int | None = None):
    widget = event.widget
    target_canvas = None
    cur = widget
    while cur is not None:
      if cur in self._scrollable_canvases:
        target_canvas = cur
        break
      cur = getattr(cur, 'master', None)
    if target_canvas is None and self._scrollable_canvases:
      target_canvas = self._scrollable_canvases[-1]
    if target_canvas is None:
      return
    try:
      if delta is not None:
        step = -delta
      elif sys.platform == 'darwin':
        d = event.delta
        if d == 0:
          return
        step = int(-1 * (d / abs(d)) if abs(d) < 1 else -1 * d)
      else:
        step = -1 if event.delta > 0 else 1
      target_canvas.yview_scroll(step, 'units')
    except tk.TclError:
      pass

  def toggle_theme(self):
    next_mode = 'light' if self.theme['mode'] == 'dark' else 'dark'
    self.set_theme(next_mode)

  def set_theme(self, mode: str):
    self.theme_pref = mode
    config_store.config_set('theme', mode)
    self.theme = resolve_theme(mode)
    self._apply_theme_everywhere()

  def _apply_theme_everywhere(self):
    t = self.theme
    self.root.configure(bg=t['canvas'])
    self.hdr_frame.configure(bg=t['canvas'])
    self.hdr_left.configure(bg=t['canvas'])
    self.hdr_right.configure(bg=t['canvas'])
    self.lbl_app_title.configure(bg=t['canvas'], fg=t['ink'])
    self.lbl_app_sub.configure(bg=t['canvas'], fg=t['ink_subtle'])

    self.kpi_row.configure(bg=t['canvas'])
    self.body_frame.configure(bg=t['canvas'])
    self.dock_outer.configure(bg=t['canvas'])

    for w in self._themed_widgets:
      if hasattr(w, 'apply_theme'):
        w.apply_theme(t)

    # Sidebar & Set headers / scroll canvases
    self.sidebar_head.configure(bg=t['glass_bg'])
    self.lbl_sidebar_title.configure(bg=t['glass_bg'], fg=t['ink'])
    self.lbl_class_badge.configure(bg=t['primary_soft'], fg=t['link'])
    self.class_canvas.configure(bg=t['glass_bg'])
    self.class_inner.configure(bg=t['glass_bg'])

    self.sets_head.configure(bg=t['glass_bg'])
    self.sets_head_left.configure(bg=t['glass_bg'])
    self.sets_head_right.configure(bg=t['glass_bg'])
    self.lbl_sets_title.configure(bg=t['glass_bg'], fg=t['ink'])
    self.lbl_sets_count.configure(bg=t['chip_bg'], fg=t['ink_muted'])
    self.lbl_class_cutoff.configure(bg=t['primary_soft'], fg=t['link'])

    self.filter_bar.configure(bg=t['glass_bg'])
    self.chip_bar.configure(bg=t['glass_bg'])
    self.action_bar.configure(bg=t['glass_bg'])
    self.sets_canvas.configure(bg=t['glass_bg'])
    self.sets_inner.configure(bg=t['glass_bg'])

    # Dock frames
    self.dock_top.configure(bg=t['glass_frosted'])
    self.dock_bottom.configure(bg=t['glass_frosted'])
    self.dock_btns_left.configure(bg=t['glass_frosted'])
    self.dock_controls_right.configure(bg=t['glass_frosted'])
    self.lbl_live_status.configure(bg=t['glass_frosted'], fg=t['ink'])
    self.lbl_live_metrics.configure(bg=t['glass_frosted'], fg=t['ink_subtle'])
    self.lbl_cutoff_label.configure(bg=t['glass_frosted'], fg=t['ink_muted'])
    self.lbl_modes_sep.configure(bg=t['glass_frosted'], fg=t['hairline'])

    self.btn_theme.set_text('☀' if t['mode'] == 'dark' else '☾')

    self._render_kpis()
    self._render_class_list()
    self._render_set_rows()

    # Open modal refreshes
    for win, retheme_fn in (
        (self._settings_win, getattr(self, '_retheme_settings', None)),
        (self._dashboard_win, getattr(self, '_retheme_dashboard', None)),
        (self._log_win, getattr(self, '_retheme_logs', None)),
        (self._manual_win, getattr(self, '_retheme_manual', None)),
        (self._login_win, getattr(self, '_retheme_login', None)),
    ):
      if win is not None and win.winfo_exists() and callable(retheme_fn):
        retheme_fn()

  # ── Main Window Layout ──────────────────────────────────────────────────

  def _build_layout(self):
    t = self.theme

    # 1. Top Liquid Glass Header Bar
    self.hdr_frame = tk.Frame(self.root, bg=t['canvas'])
    self.hdr_frame.pack(fill='x', padx=20, pady=(16, 10))

    self.hdr_left = tk.Frame(self.hdr_frame, bg=t['canvas'])
    self.hdr_left.pack(side='left')
    self.lbl_app_title = tk.Label(
        self.hdr_left, text='Classcard Macro', font=font(20, 'bold'),
        bg=t['canvas'], fg=t['ink'],
    )
    self.lbl_app_title.pack(side='left')
    self.lbl_app_sub = tk.Label(
        self.hdr_left, text='Liquid Glass Edition', font=font(11),
        bg=t['canvas'], fg=t['ink_subtle'],
    )
    self.lbl_app_sub.pack(side='left', padx=(10, 0), pady=(4, 0))

    self.hdr_right = tk.Frame(self.hdr_frame, bg=t['canvas'])
    self.hdr_right.pack(side='right')

    self.btn_theme = GlassPillButton(
        self.hdr_right, text='☾', command=self.toggle_theme,
        theme=t, variant='pearl', height=32, padx=12, min_width=36,
        font_spec=font(13), parent_bg_key='canvas',
    )
    self.btn_theme.pack(side='right', padx=(6, 0))
    self._themed_widgets.append(self.btn_theme)

    header_actions = [
        ('재시작', self.restart_program, 'ghost'),
        ('설정', self.open_settings_sheet, 'pearl'),
        ('로그', self.open_log_sheet, 'pearl'),
        ('학습 통계', self.open_dashboard_sheet, 'pearl'),
        ('수동 모드', self.open_manual_sheet, 'pearl'),
        ('목록 새로고침', self.load_classes, 'secondary'),
        ('자동 로그인', self.open_login_sheet, 'pearl'),
    ]
    for label, cmd, variant in header_actions:
      btn = GlassPillButton(
          self.hdr_right, text=label, command=cmd,
          theme=t, variant=variant, height=32, padx=13,
          font_spec=font(11), parent_bg_key='canvas',
      )
      btn.pack(side='right', padx=(6, 0))
      self._themed_widgets.append(btn)

    # 2. 4 Inline KPI Glass Tiles
    self.kpi_row = tk.Frame(self.root, bg=t['canvas'])
    self.kpi_row.pack(fill='x', padx=20, pady=(0, 12))
    self.kpi_row.columnconfigure((0, 1, 2, 3), weight=1, uniform='kpi')

    for col in range(4):
      cv = tk.Canvas(self.kpi_row, height=78, bg=t['canvas'], highlightthickness=0, bd=0)
      pad = (0, 6) if col == 0 else ((6, 0) if col == 3 else (6, 6))
      cv.grid(row=0, column=col, sticky='ew', padx=pad)
      cv.bind('<Configure>', lambda _e, idx=col: self._draw_single_kpi(idx))
      self._kpi_canvases.append((cv, {}))

    # 3. Split Body: Left Sidebar (내 클래스) + Right Content (학습할 세트)
    self.body_frame = tk.Frame(self.root, bg=t['canvas'])
    self.body_frame.pack(fill='both', expand=True, padx=20, pady=(0, 12))

    # Left Sidebar Card
    self.sidebar_card = GlassCard(
        self.body_frame, theme=t, radius=18, padding=(12, 12),
        surface_key='glass_bg', parent_bg_key='canvas', width=250,
    )
    self.sidebar_card.pack(side='left', fill='y', padx=(0, 12))
    self.sidebar_card.pack_propagate(False)
    self._themed_widgets.append(self.sidebar_card)

    self.sidebar_head = tk.Frame(self.sidebar_card.body, bg=t['glass_bg'])
    self.sidebar_head.pack(fill='x', pady=(0, 8))
    self.lbl_sidebar_title = tk.Label(
        self.sidebar_head, text='내 클래스', font=font(13, 'bold'),
        bg=t['glass_bg'], fg=t['ink'],
    )
    self.lbl_sidebar_title.pack(side='left', padx=(4, 0))
    self.lbl_class_badge = tk.Label(
        self.sidebar_head, text='0', font=font(10, 'bold'),
        bg=t['primary_soft'], fg=t['link'], padx=8, pady=1,
    )
    self.lbl_class_badge.pack(side='right', padx=(0, 2))

    self.class_canvas = tk.Canvas(
        self.sidebar_card.body, bg=t['glass_bg'], highlightthickness=0, bd=0,
    )
    self.class_canvas.pack(fill='both', expand=True)
    self.class_inner = tk.Frame(self.class_canvas, bg=t['glass_bg'])
    self._class_win = self.class_canvas.create_window((0, 0), window=self.class_inner, anchor='nw')
    self.class_canvas.bind(
        '<Configure>', lambda e: self.class_canvas.itemconfigure(self._class_win, width=e.width),
    )
    self.class_inner.bind(
        '<Configure>', lambda _e: self.class_canvas.configure(scrollregion=self.class_canvas.bbox('all')),
    )
    self._scrollable_canvases.append(self.class_canvas)

    # Right Content Card
    self.sets_card = GlassCard(
        self.body_frame, theme=t, radius=18, padding=(16, 14),
        surface_key='glass_bg', parent_bg_key='canvas',
    )
    self.sets_card.pack(side='left', fill='both', expand=True)
    self._themed_widgets.append(self.sets_card)

    # Right Header
    self.sets_head = tk.Frame(self.sets_card.body, bg=t['glass_bg'])
    self.sets_head.pack(fill='x', pady=(0, 10))
    self.sets_head_left = tk.Frame(self.sets_head, bg=t['glass_bg'])
    self.sets_head_left.pack(side='left')
    self.lbl_sets_title = tk.Label(
        self.sets_head_left, text='학습할 세트', font=font(14, 'bold'),
        bg=t['glass_bg'], fg=t['ink'],
    )
    self.lbl_sets_title.pack(side='left')
    self.lbl_sets_count = tk.Label(
        self.sets_head_left, text='0개 선택', font=font(10),
        bg=t['chip_bg'], fg=t['ink_muted'], padx=8, pady=2,
    )
    self.lbl_sets_count.pack(side='left', padx=(8, 0))

    self.sets_head_right = tk.Frame(self.sets_head, bg=t['glass_bg'])
    self.sets_head_right.pack(side='right')
    self.lbl_class_cutoff = tk.Label(
        self.sets_head_right, text='커트라인 85점', font=font(10, 'bold'),
        bg=t['primary_soft'], fg=t['link'], padx=10, pady=3,
    )
    self.lbl_class_cutoff.pack(side='right')

    # Inline Search & Filter Bar
    self.filter_bar = tk.Frame(self.sets_card.body, bg=t['glass_bg'])
    self.filter_bar.pack(fill='x', pady=(0, 8))

    self.search_bar = GlassSearchBar(
        self.filter_bar, theme=t, placeholder='세트 이름으로 검색...',
        on_change=self._on_search_change, height=32, width=210,
        parent_bg_key='glass_bg',
    )
    self.search_bar.pack(side='left', padx=(0, 10))
    self._themed_widgets.append(self.search_bar)

    self.chip_bar = tk.Frame(self.filter_bar, bg=t['glass_bg'])
    self.chip_bar.pack(side='left', fill='x')

    self._filter_chips: dict[str, GlassChipToggle] = {}
    for key, label in (
        ('all', '전체'),
        ('incomplete', '미완료'),
        ('failed', '테스트 미달'),
        ('word', '단어'),
        ('sentence', '문장'),
    ):
      chip = GlassChipToggle(
          self.chip_bar, text=label, selected=(key == 'all'),
          on_toggle=lambda _s, k=key: self._set_filter(k),
          theme=t, height=28, padx=11, active_style='solid',
          parent_bg_key='glass_bg',
      )
      chip.pack(side='left', padx=(0, 5))
      self._filter_chips[key] = chip
      self._themed_widgets.append(chip)

    # Quick Actions Bar
    self.action_bar = tk.Frame(self.sets_card.body, bg=t['glass_bg'])
    self.action_bar.pack(fill='x', pady=(0, 10))

    quick_selects = [
        ('모두 선택', lambda: self._select_filtered(True)),
        ('미완료만', self._select_incomplete),
        ('미달만', self._select_failed),
        ('모두 해제', lambda: self._select_filtered(False)),
    ]
    for label, cmd in quick_selects:
      btn = GlassPillButton(
          self.action_bar, text=label, command=cmd, theme=t,
          variant='pearl', height=27, padx=10, font_spec=font(10),
          parent_bg_key='glass_bg',
      )
      btn.pack(side='left', padx=(0, 6))
      self._themed_widgets.append(btn)

    self.btn_apply_goal = GlassPillButton(
        self.action_bar, text='목표 일괄 적용', command=self._apply_goal_all,
        theme=t, variant='secondary', height=27, padx=11, font_spec=font(10, 'bold'),
        parent_bg_key='glass_bg',
    )
    self.btn_apply_goal.pack(side='right')
    self._themed_widgets.append(self.btn_apply_goal)

    self.goal_all_stepper = GlassStepper(
        self.action_bar, theme=t, value=100, min_val=100, max_val=1000,
        step=100, suffix='%', on_change=self._on_goal_all_change,
        width=92, height=27, parent_bg_key='glass_bg',
    )
    self.goal_all_stepper.pack(side='right', padx=(0, 6))
    self._themed_widgets.append(self.goal_all_stepper)

    # Scrollable Set Rows
    self.sets_canvas = tk.Canvas(
        self.sets_card.body, bg=t['glass_bg'], highlightthickness=0, bd=0,
    )
    self.sets_scroll = tk.Scrollbar(
        self.sets_card.body, orient='vertical', command=self.sets_canvas.yview,
    )
    self.sets_canvas.configure(yscrollcommand=self.sets_scroll.set)
    self.sets_scroll.pack(side='right', fill='y')
    self.sets_canvas.pack(side='left', fill='both', expand=True)

    self.sets_inner = tk.Frame(self.sets_canvas, bg=t['glass_bg'])
    self._sets_win = self.sets_canvas.create_window((0, 0), window=self.sets_inner, anchor='nw')
    self.sets_canvas.bind(
        '<Configure>', lambda e: self.sets_canvas.itemconfigure(self._sets_win, width=e.width),
    )
    self.sets_inner.bind(
        '<Configure>', lambda _e: self.sets_canvas.configure(scrollregion=self.sets_canvas.bbox('all')),
    )
    self._scrollable_canvases.append(self.sets_canvas)

    # 4. Floating Liquid Glass Bottom Dock
    self.dock_outer = tk.Frame(self.root, bg=t['canvas'])
    self.dock_outer.pack(fill='x', padx=20, pady=(0, 16))

    self.dock_card = GlassCard(
        self.dock_outer, theme=t, radius=18, padding=(18, 12),
        surface_key='glass_frosted', parent_bg_key='canvas', height=116,
    )
    self.dock_card.pack(fill='x')
    self._themed_widgets.append(self.dock_card)

    self.dock_top = tk.Frame(self.dock_card.body, bg=t['glass_frosted'])
    self.dock_top.pack(fill='x', pady=(0, 6))

    self.lbl_live_status = tk.Label(
        self.dock_top, text='크롬에서 클래스 목록을 읽는 중...',
        font=font(11, 'bold'), bg=t['glass_frosted'], fg=t['ink'], anchor='w',
    )
    self.lbl_live_status.pack(side='left', fill='x', expand=True)

    self.lbl_live_metrics = tk.Label(
        self.dock_top, text='대기 중 · 00:00',
        font=font(10, mono=True), bg=t['glass_frosted'], fg=t['ink_subtle'], anchor='e',
    )
    self.lbl_live_metrics.pack(side='right')

    self.live_progress = GlassProgressBar(
        self.dock_card.body, theme=t, height=8, parent_bg_key='glass_frosted',
    )
    self.live_progress.pack(fill='x', pady=(0, 10))
    self._themed_widgets.append(self.live_progress)

    self.dock_bottom = tk.Frame(self.dock_card.body, bg=t['glass_frosted'])
    self.dock_bottom.pack(fill='x')

    self.dock_btns_left = tk.Frame(self.dock_bottom, bg=t['glass_frosted'])
    self.dock_btns_left.pack(side='left')

    self.btn_auto_start = GlassPillButton(
        self.dock_btns_left, text='자동 시작',
        command=lambda: self.start_auto(test_only=False),
        theme=t, variant='primary', height=34, padx=20, font_spec=font(12, 'bold'),
        parent_bg_key='glass_frosted',
    )
    self.btn_auto_start.pack(side='left', padx=(0, 8))
    self._themed_widgets.append(self.btn_auto_start)

    self.btn_test_only = GlassPillButton(
        self.dock_btns_left, text='테스트만',
        command=lambda: self.start_auto(test_only=True),
        theme=t, variant='secondary', height=34, padx=16, font_spec=font(11, 'bold'),
        parent_bg_key='glass_frosted',
    )
    self.btn_test_only.pack(side='left', padx=(0, 8))
    self._themed_widgets.append(self.btn_test_only)

    self.btn_pause = GlassPillButton(
        self.dock_btns_left, text='일시정지',
        command=self.toggle_pause,
        theme=t, variant='warning', height=34, padx=14, font_spec=font(11, 'bold'),
        enabled=False, parent_bg_key='glass_frosted',
    )
    self.btn_pause.pack(side='left', padx=(0, 8))
    self._themed_widgets.append(self.btn_pause)

    self.btn_stop_auto = GlassPillButton(
        self.dock_btns_left, text='정지',
        command=self.stop_all,
        theme=t, variant='danger', height=34, padx=14, font_spec=font(11, 'bold'),
        enabled=False, parent_bg_key='glass_frosted',
    )
    self.btn_stop_auto.pack(side='left')
    self._themed_widgets.append(self.btn_stop_auto)

    # Right Controls: Mode chips + Cutoff stepper + ANTICHEAT toggle
    self.dock_controls_right = tk.Frame(self.dock_bottom, bg=t['glass_frosted'])
    self.dock_controls_right.pack(side='right')

    anticheat_on = bool(config_store.config_get('anticheat', True))
    self.chip_anticheat = GlassChipToggle(
        self.dock_controls_right,
        text='ANTICHEAT ON' if anticheat_on else 'ANTICHEAT OFF',
        selected=anticheat_on,
        on_toggle=self._on_anticheat_toggle,
        theme=t, height=28, padx=12, active_style='green',
        parent_bg_key='glass_frosted',
    )
    self.chip_anticheat.pack(side='right')
    self._themed_widgets.append(self.chip_anticheat)

    default_cutoff = int(config_store.config_get('pass_score', 85))
    self.cutoff_stepper = GlassStepper(
        self.dock_controls_right, theme=t, value=default_cutoff,
        min_val=0, max_val=100, step=5, suffix='점',
        on_change=self._on_cutoff_change, width=88, height=28,
        parent_bg_key='glass_frosted',
    )
    self.cutoff_stepper.pack(side='right', padx=(0, 8))
    self._themed_widgets.append(self.cutoff_stepper)

    self.lbl_cutoff_label = tk.Label(
        self.dock_controls_right, text='커트라인', font=font(10),
        bg=t['glass_frosted'], fg=t['ink_muted'],
    )
    self.lbl_cutoff_label.pack(side='right', padx=(8, 4))

    self.lbl_modes_sep = tk.Label(
        self.dock_controls_right, text='|', font=font(11),
        bg=t['glass_frosted'], fg=t['hairline'],
    )
    self.lbl_modes_sep.pack(side='right', padx=(6, 4))

    saved_modes = config_store.config_get('study_modes', None) or {
        'memorize': True, 'recall': True, 'spell': True, 'test': True,
    }
    self._mode_chips: dict[str, GlassChipToggle] = {}
    for m_key, m_label in (('test', '테스트'), ('spell', '스펠'), ('recall', '리콜'), ('memorize', '암기')):
      chip = GlassChipToggle(
          self.dock_controls_right,
          text=m_label,
          selected=bool(saved_modes.get(m_key, True)),
          on_toggle=lambda s, k=m_key: self._on_mode_toggle(k, s),
          theme=t, height=28, padx=10, active_style='soft',
          parent_bg_key='glass_frosted',
      )
      chip.pack(side='right', padx=(0, 4))
      self._mode_chips[m_key] = chip
      self._themed_widgets.append(chip)

  # ── KPI Calculation & Rendering ─────────────────────────────────────────

  def _current_cutoff(self) -> int:
    if self.current_class_idx is not None:
      return int(config_store.get_class_pass_score(self.current_class_idx))
    return int(config_store.config_get('pass_score', 85))

  def calculate_stats(self) -> dict:
    cutoff = self._current_cutoff()
    total_sets = len(self.sets)
    class_name = '선택된 클래스 없음'
    for c in self.classes:
      if str(c.get('idx')) == str(self.current_class_idx):
        class_name = c.get('name', '클래스')
        break

    if total_sets == 0:
      return {
          'total_sets': 0, 'class_name': class_name, 'cutoff': cutoff,
          'm_avg': 0.0, 'm_done': 0, 'r_avg': 0.0, 'r_done': 0,
          's_avg': 0.0, 's_done': 0, 't_taken': 0, 't_passed': 0,
          't_failed': 0, 't_pass_rate': 0.0, 't_avg_score': 0.0,
          'score_100': 0, 'score_90_99': 0, 'score_pass': 0,
          'score_fail': 0, 'score_none': 0, 'overall_pct': 0.0,
      }

    m_scores, r_scores, s_scores = [], [], []
    m_done = r_done = s_done = 0
    t_taken = t_passed = t_failed = t_score_sum = 0
    score_100 = score_90_99 = score_pass = score_fail = score_none = 0

    for item in self.sets:
      rates = item.get('rates') or self.rate_cache.get(str(item.get('idx', ''))) or {}
      mv = rates.get('memorize') or 0
      rv = rates.get('recall') or 0
      sv = rates.get('spell') or 0
      m_scores.append(mv)
      r_scores.append(rv)
      s_scores.append(sv)
      if mv >= 100:
        m_done += 1
      if rv >= 100:
        r_done += 1
      if sv >= 100:
        s_done += 1

      test = rates.get('test')
      if not test:
        score_none += 1
      else:
        score = study_engine.parse_test_score(test)
        failed = study_engine.test_failed(test, cutoff)
        t_taken += 1
        if score is not None:
          t_score_sum += score
        if failed:
          t_failed += 1
          score_fail += 1
        else:
          t_passed += 1
          if score == 100:
            score_100 += 1
          elif score is not None and score >= 90:
            score_90_99 += 1
          else:
            score_pass += 1

    m_avg = round(sum(m_scores) / total_sets, 1)
    r_avg = round(sum(r_scores) / total_sets, 1)
    s_avg = round(sum(s_scores) / total_sets, 1)
    t_avg_score = round(t_score_sum / t_taken, 1) if t_taken else 0.0
    t_pass_rate = round(t_passed / total_sets * 100, 1)
    overall_pct = round((m_avg + r_avg + s_avg + t_pass_rate) / 4.0, 1)

    return {
        'total_sets': total_sets, 'class_name': class_name, 'cutoff': cutoff,
        'm_avg': m_avg, 'm_done': m_done, 'r_avg': r_avg, 'r_done': r_done,
        's_avg': s_avg, 's_done': s_done, 't_taken': t_taken, 't_passed': t_passed,
        't_failed': t_failed, 't_pass_rate': t_pass_rate, 't_avg_score': t_avg_score,
        'score_100': score_100, 'score_90_99': score_90_99, 'score_pass': score_pass,
        'score_fail': score_fail, 'score_none': score_none, 'overall_pct': overall_pct,
    }

  def _render_kpis(self):
    s = self.calculate_stats()
    self._kpi_values = [
        {'title': '암기 평균 진도', 'val': f"{s['m_avg']}%", 'sub': f"{s['m_done']}/{s['total_sets']} 세트 완료", 'accent': 'primary'},
        {'title': '리콜 평균 진도', 'val': f"{s['r_avg']}%", 'sub': f"{s['r_done']}/{s['total_sets']} 세트 완료", 'accent': 'green'},
        {'title': '스펠 평균 진도', 'val': f"{s['s_avg']}%", 'sub': f"{s['s_done']}/{s['total_sets']} 세트 완료", 'accent': 'amber'},
        {'title': '테스트 통과율', 'val': f"{s['t_pass_rate']}%", 'sub': f"평균 {s['t_avg_score']}점 · {s['t_passed']}/{s['total_sets']} 통과", 'accent': 'purple'},
    ]
    for i in range(len(self._kpi_canvases)):
      self._draw_single_kpi(i)

  def _draw_single_kpi(self, idx: int):
    if idx >= len(self._kpi_canvases) or idx >= len(self._kpi_values):
      return
    cv, _ = self._kpi_canvases[idx]
    data = self._kpi_values[idx]
    t = self.theme
    cv.configure(bg=t['canvas'])
    cv.delete('all')
    w = cv.winfo_width()
    h = cv.winfo_height()
    if w < 30 or h < 30:
      return
    draw_round_rect(
        cv, 1, 1, w - 2, h - 2,
        radius=16, fill=t['glass_bg'], outline=t['hairline'], width=1,
        specular=t['glass_specular'],
    )
    accent = t.get(data['accent'], t['primary'])
    cv.create_text(16, 18, text=data['title'], font=font(10), fill=t['ink_subtle'], anchor='w')
    cv.create_text(16, 44, text=data['val'], font=font(19, 'bold'), fill=accent, anchor='w')
    cv.create_text(16, 65, text=data['sub'], font=font(9), fill=t['ink_subtle'], anchor='w')

  # ── Classes & Sets Loading ──────────────────────────────────────────────

  def load_classes(self):
    self._set_live_status('크롬에서 클래스 목록을 읽는 중...', 'link')

    def work():
      try:
        driver = chrome_bridge.get_driver()
      except Exception as e:
        self._ui_call(self._set_live_status, f'크롬을 열지 못했습니다: {e}', 'red')
        return
      classes = chrome_bridge.fetch_classes(driver)
      if not classes and config_store.load_login():
        self._ui_call(self._set_live_status, '저장된 계정으로 자동 로그인 중...', 'link')
        if chrome_bridge.auto_login(driver):
          classes = chrome_bridge.fetch_classes(driver)
      if not classes:
        self._ui_call(
            self._set_live_status,
            '클래스를 못 읽었습니다. 크롬에서 로그인하거나 [자동 로그인]을 설정하세요.',
            'red',
        )
        return
      self._ui_call(self._on_classes_loaded, classes)

    threading.Thread(target=work, daemon=True).start()

  def _on_classes_loaded(self, classes: list[dict]):
    self.classes = classes
    self.lbl_class_badge.configure(text=str(len(classes)))
    if not classes:
      self._render_class_list()
      return

    # 기존 선택 유지
    target_cls = classes[0]
    for c in classes:
      if str(c.get('idx')) == str(self.current_class_idx):
        target_cls = c
        break
    self.select_class(target_cls)

  def _cutoff_badge_text(self, score: int | None = None) -> str:
    if score is None:
      score = self._current_cutoff()
    overrides = config_store.config_get('class_pass', {}) or {}
    is_custom = (
        self.current_class_idx is not None
        and str(self.current_class_idx) in overrides
    )
    return f'커트라인 {score}점 (개별)' if is_custom else f'커트라인 {score}점'

  def select_class(self, cls: dict):
    snap = study_engine.engine.snapshot()
    if snap.get('active'):
      return
    self.current_class_idx = cls['idx']
    cutoff = config_store.get_class_pass_score(self.current_class_idx)
    self.cutoff_stepper.set_value(cutoff, notify=False)
    self.lbl_class_cutoff.configure(text=self._cutoff_badge_text(cutoff))
    self._render_class_list()
    self._set_live_status(f"'{cls['name']}'의 세트를 읽는 중...", 'link')

    def work():
      try:
        driver = chrome_bridge.get_driver()
      except Exception as e:
        self._ui_call(self._set_live_status, f'크롬을 열지 못했습니다: {e}', 'red')
        return
      sets = chrome_bridge.fetch_sets(driver, cls['idx'])
      if not sets:
        self._ui_call(self._set_live_status, f"'{cls['name']}'의 세트를 못 읽었습니다.", 'red')
        return
      enriched = [dict(x, class_idx=cls['idx']) for x in sets]
      self._ui_call(self._on_sets_loaded, cls['idx'], enriched)

    threading.Thread(target=work, daemon=True).start()

  def _on_sets_loaded(self, class_idx, sets: list[dict]):
    if str(class_idx) != str(self.current_class_idx):
      return
    self.sets = sets
    self._render_set_rows()
    self._render_kpis()
    self._set_live_status(
        f'세트 {len(sets)}개 로드됨 · 학습할 세트를 선택하고 [자동 시작]을 누르세요.',
        'ink',
    )
    self._load_class_report(class_idx)

  def _load_class_report(self, class_idx):
    def work():
      snap = study_engine.engine.snapshot()
      if snap.get('active'):
        return
      try:
        driver = chrome_bridge.get_driver()
      except Exception:
        return
      try:
        if 'classcard.net' not in (driver.current_url or ''):
          chrome_bridge.open_site(driver, '/Main/user')
      except Exception:
        pass
      data = chrome_bridge.fetch_class_report(driver, class_idx)
      if str(self.current_class_idx) != str(class_idx):
        return
      if not data:
        self._ui_call(self._set_live_status, '진도를 못 읽었습니다. [목록 새로고침]을 눌러보세요.', 'red')
        return
      self._ui_call(self._apply_report_data, class_idx, data)

    threading.Thread(target=work, daemon=True).start()

  def _apply_report_data(self, class_idx, data: dict):
    if str(self.current_class_idx) != str(class_idx):
      return
    for item in self.sets:
      got = data.get(str(item['idx'])) or {}
      rates = {m: (got.get(m) or 0) for m in ('memorize', 'recall', 'spell')}
      rates['test'] = got.get('test') or ''
      item['rates'] = rates
      self.rate_cache[str(item['idx'])] = rates
    config_store.save_rate_cache(self.rate_cache)
    self._render_set_rows()
    self._render_kpis()
    cnt = len(self.checked_targets)
    self._set_live_status(
        f'진도 동기화 완료 · 선택된 세트 {cnt}개', 'ink',
    )

  def _render_class_list(self):
    for w in self.class_inner.winfo_children():
      w.destroy()
    self._class_row_widgets.clear()
    t = self.theme

    if not self.classes:
      lbl = tk.Label(
          self.class_inner, text='클래스 없음', font=font(11),
          bg=t['glass_bg'], fg=t['ink_subtle'], pady=20,
      )
      lbl.pack(fill='x')
      return

    for c in self.classes:
      active = str(c.get('idx')) == str(self.current_class_idx)
      bg = t['primary'] if active else t['glass_bg']
      fg = t['on_primary'] if active else t['ink']
      row = tk.Frame(self.class_inner, bg=bg, cursor='hand2')
      row.pack(fill='x', pady=2)
      lbl = tk.Label(
          row, text=f"  {c['name']}", anchor='w',
          font=font(11, 'bold' if active else 'normal'),
          bg=bg, fg=fg, padx=10, pady=8, cursor='hand2',
      )
      lbl.pack(fill='x')
      for widget in (row, lbl):
        widget.bind('<ButtonRelease-1>', lambda _e, cls=c: self.select_class(cls))
      self._class_row_widgets.append({'frame': row, 'label': lbl, 'cls': c})

  # ── Set Filtering & Row Rendering ───────────────────────────────────────

  def _on_search_change(self, query: str):
    self.search_query = query.lower()
    self._render_set_rows()

  def _set_filter(self, key: str):
    self.filter_key = key
    for k, chip in self._filter_chips.items():
      chip.set_selected(k == key, silent=True)
    self._render_set_rows()

  def _is_set_incomplete(self, item: dict) -> bool:
    rates = item.get('rates') or self.rate_cache.get(str(item.get('idx'))) or {}
    cutoff = self._current_cutoff()
    for m in ('memorize', 'recall', 'spell'):
      if (rates.get(m) or 0) < 100:
        return True
    test = rates.get('test')
    if not test or study_engine.test_failed(test, cutoff):
      return True
    return False

  def _is_set_test_failed(self, item: dict) -> bool:
    rates = item.get('rates') or self.rate_cache.get(str(item.get('idx'))) or {}
    test = rates.get('test')
    return bool(not test or study_engine.test_failed(test, self._current_cutoff()))

  def _filtered_sets(self) -> list[dict]:
    out = []
    q = self.search_query
    fk = self.filter_key
    for item in self.sets:
      if q and q not in (item.get('name') or '').lower():
        continue
      if fk == 'word' and item.get('sentence'):
        continue
      if fk == 'sentence' and not item.get('sentence'):
        continue
      if fk == 'incomplete' and not self._is_set_incomplete(item):
        continue
      if fk == 'failed' and not self._is_set_test_failed(item):
        continue
      out.append(item)
    return out

  def _render_set_rows(self):
    for w in self.sets_inner.winfo_children():
      w.destroy()
    self._set_row_widgets.clear()
    t = self.theme
    cutoff = self._current_cutoff()
    visible = self._filtered_sets()

    if not visible:
      empty_msg = '표시할 세트가 없습니다.' if self.sets else '왼쪽에서 클래스를 선택하세요.'
      tk.Label(
          self.sets_inner, text=empty_msg, font=font(12),
          bg=t['glass_bg'], fg=t['ink_subtle'], pady=36,
      ).pack(fill='x')
      self._update_selected_badge()
      return

    for i, item in enumerate(visible):
      bg = t['row_even'] if i % 2 == 0 else t['row_odd']
      s_idx = str(item['idx'])
      checked = s_idx in self.checked_targets
      is_cur = bool(item.get('current') or item.get('learning'))
      rates = item.get('rates') or self.rate_cache.get(s_idx)
      dim = 'rates' not in item

      row = tk.Frame(self.sets_inner, bg=bg)
      row.pack(fill='x')

      # Subtle 1px divider
      tk.Frame(row, bg=t['divider_soft'], height=1).pack(fill='x', side='bottom')

      inner = tk.Frame(row, bg=bg)
      inner.pack(fill='x', padx=10, pady=8)

      # Checkbox pill
      chk_cv = tk.Canvas(inner, width=22, height=22, bg=bg, highlightthickness=0, bd=0, cursor='hand2')
      chk_cv.pack(side='left', padx=(0, 8))
      self._draw_checkbox(chk_cv, checked)

      # Current indicator + Title
      mark = '▶ ' if is_cur else ''
      title_fg = t['green'] if is_cur else t['ink']
      lbl_name = tk.Label(
          inner,
          text=f"{mark}{item['name']}",
          font=font(11, 'bold' if is_cur else 'normal'),
          bg=bg, fg=title_fg, anchor='w', width=28, cursor='hand2',
      )
      lbl_name.pack(side='left', padx=(0, 6))

      # Kind pill badge
      is_sent = bool(item.get('sentence'))
      badge_bg = t['purple_soft'] if is_sent else t['primary_soft']
      badge_fg = t['purple'] if is_sent else t['link']
      kind_txt = f"{'문장' if is_sent else '단어'} · {item.get('count', 0)}"
      lbl_kind = tk.Label(
          inner, text=kind_txt, font=font(9, 'bold'),
          bg=badge_bg, fg=badge_fg, padx=7, pady=2,
      )
      lbl_kind.pack(side='left', padx=(0, 8))

      # Progress chips
      chips_frame = tk.Frame(inner, bg=bg)
      chips_frame.pack(side='left', fill='x', expand=True)

      cells = {}
      for m_key, m_label in (('memorize', '암기'), ('recall', '리콜'), ('spell', '스펠')):
        val = (rates or {}).get(m_key)
        c_bg, c_fg, txt = self._rate_chip_style(m_label, val, dim)
        lbl = tk.Label(chips_frame, text=txt, font=font(9, 'bold'), bg=c_bg, fg=c_fg, padx=6, pady=2)
        lbl.pack(side='left', padx=(0, 4))
        cells[m_key] = lbl

      t_bg, t_fg, t_txt = self._test_chip_style((rates or {}).get('test'), cutoff, dim)
      lbl_test = tk.Label(chips_frame, text=t_txt, font=font(9, 'bold'), bg=t_bg, fg=t_fg, padx=7, pady=2)
      lbl_test.pack(side='left', padx=(2, 4))
      cells['test'] = lbl_test

      # Goal % stepper on right
      goal_val = self.checked_targets.get(s_idx, self.goal_all)
      goal_stepper = GlassStepper(
          inner, theme=t, value=goal_val, min_val=100, max_val=1000,
          step=100, suffix='%',
          on_change=lambda v, idx=s_idx: self._on_row_goal_change(idx, v),
          width=88, height=26, parent_bg_key='row_even' if i % 2 == 0 else 'row_odd',
      )
      goal_stepper.pack(side='right', padx=(6, 0))

      row_info = {
          'item': item, 's_idx': s_idx, 'chk': chk_cv,
          'stepper': goal_stepper, 'cells': cells, 'bg': bg,
      }
      for clickable in (chk_cv, lbl_name):
        clickable.bind('<ButtonRelease-1>', lambda _e, info=row_info: self._toggle_row(info))
      self._set_row_widgets.append(row_info)

    self._update_selected_badge()

  def _draw_checkbox(self, cv: tk.Canvas, checked: bool):
    cv.delete('all')
    t = self.theme
    if checked:
      draw_round_rect(cv, 2, 2, 19, 19, radius=6, fill=t['primary'], outline=t['primary'])
      cv.create_text(11, 11, text='✓', font=font(11, 'bold'), fill=t['on_primary'])
    else:
      draw_round_rect(cv, 2, 2, 19, 19, radius=6, fill=t['canvas'], outline=t['hairline'], width=1)

  def _rate_chip_style(self, name: str, val, dim: bool) -> tuple[str, str, str]:
    t = self.theme
    txt = f"{name} {val}%" if val is not None else f'{name} -'
    if dim:
      return t['chip_bg'], t['ink_subtle'], txt
    if not val:
      return t['chip_bg'], t['ink_subtle'], txt
    if val >= 100:
      return t['green_soft'], t['green'], txt
    return t['amber_soft'], t['amber'], txt

  def _test_chip_style(self, test_str, cutoff: int, dim: bool) -> tuple[str, str, str]:
    t = self.theme
    txt = study_engine.format_test_text(test_str, cutoff)
    if dim or not test_str:
      return t['chip_bg'], t['ink_subtle'], txt
    if study_engine.test_failed(test_str, cutoff):
      return t['red_soft'], t['red'], txt
    return t['green_soft'], t['green'], txt

  def _toggle_row(self, row_info: dict):
    s_idx = row_info['s_idx']
    if s_idx in self.checked_targets:
      self.checked_targets.pop(s_idx, None)
      checked = False
    else:
      self.checked_targets[s_idx] = row_info['stepper'].get_value()
      checked = True
    self._draw_checkbox(row_info['chk'], checked)
    self._update_selected_badge()

  def _on_row_goal_change(self, s_idx: str, val: int):
    if s_idx in self.checked_targets:
      self.checked_targets[s_idx] = val

  def _on_goal_all_change(self, val: int):
    self.goal_all = val

  def _apply_goal_all(self):
    val = self.goal_all_stepper.get_value()
    self.goal_all = val
    for info in self._set_row_widgets:
      info['stepper'].set_value(val, notify=False)
      s_idx = info['s_idx']
      if s_idx in self.checked_targets:
        self.checked_targets[s_idx] = val

  def _select_filtered(self, select: bool):
    for info in self._set_row_widgets:
      s_idx = info['s_idx']
      if select:
        self.checked_targets[s_idx] = info['stepper'].get_value()
      else:
        self.checked_targets.pop(s_idx, None)
      self._draw_checkbox(info['chk'], select)
    self._update_selected_badge()

  def _select_incomplete(self):
    for info in self._set_row_widgets:
      inc = self._is_set_incomplete(info['item'])
      s_idx = info['s_idx']
      if inc:
        self.checked_targets[s_idx] = info['stepper'].get_value()
      else:
        self.checked_targets.pop(s_idx, None)
      self._draw_checkbox(info['chk'], inc)
    self._update_selected_badge()

  def _select_failed(self):
    for info in self._set_row_widgets:
      fail = self._is_set_test_failed(info['item'])
      s_idx = info['s_idx']
      if fail:
        self.checked_targets[s_idx] = info['stepper'].get_value()
      else:
        self.checked_targets.pop(s_idx, None)
      self._draw_checkbox(info['chk'], fail)
    self._update_selected_badge()

  def _update_selected_badge(self):
    cnt = len(self.checked_targets)
    self.lbl_sets_count.configure(text=f'{cnt}개 선택')

  # ── Bottom Dock Controls & Engine Execution ─────────────────────────────

  def _on_anticheat_toggle(self, state: bool):
    config_store.config_set('anticheat', bool(state))
    self.chip_anticheat.set_text('ANTICHEAT ON' if state else 'ANTICHEAT OFF')

  def _on_cutoff_change(self, score: int):
    if self.current_class_idx is not None:
      default_score = int(config_store.config_get('pass_score', 85))
      config_store.set_class_pass_score(
          self.current_class_idx,
          None if score == default_score else score,
      )
    else:
      config_store.config_set('pass_score', score)
    self.lbl_class_cutoff.configure(text=self._cutoff_badge_text(score))
    self._render_set_rows()
    self._render_kpis()

  def _on_mode_toggle(self, mode_key: str, state: bool):
    modes = dict(config_store.config_get('study_modes', None) or {})
    modes[mode_key] = bool(state)
    config_store.config_set('study_modes', modes)

  def _get_selected_modes(self) -> dict:
    return {k: chip.is_selected() for k, chip in self._mode_chips.items()}

  def _register_engine_callbacks(self):
    study_engine.engine.set_callbacks(
        on_status=lambda text, color: self._ui_call(self._on_engine_status, text, color),
        on_manual_status=lambda text, color: self._ui_call(self._on_manual_status, text, color),
        on_rate_update=lambda s_idx, rates: self._ui_call(self._on_engine_rate_update, s_idx, rates),
        on_state_change=lambda snap: self._ui_call(self._on_engine_state_change, snap),
        on_error=lambda title, msg: self._ui_call(messagebox.showerror, title, msg),
        on_kind_change=lambda kind: self._ui_call(self._on_engine_kind_change, kind),
        on_cards_loaded=lambda cards, src, s_idx: self._ui_call(self._on_engine_cards_loaded, cards, src, s_idx),
    )

  def _map_status_color_key(self, color: str) -> str:
    c = (color or '').upper()
    if c in ('#2E7D32', '#388E3C', '#248A3D', '#30D158'):
      return 'green'
    if c in ('#E65100', '#B25000', '#FF9F0A'):
      return 'amber'
    if c in ('#D32F2F', '#C62828', '#D70015', '#FF453A'):
      return 'red'
    if c in ('#0066CC', '#0288D1', '#1565C0', '#1976D2', '#2997FF'):
      return 'link'
    return 'ink'

  def _on_engine_status(self, text: str, color: str = '#0066CC'):
    self._set_live_status(text, self._map_status_color_key(color))

  def _on_manual_status(self, text: str, _color: str = '#0066CC'):
    self._manual_status_var.set(text)

  def _on_engine_kind_change(self, kind: str):
    if SENTENCE_MODE_ENABLED and kind in ('word', 'sentence'):
      self.manual_kind.set(kind)
      for k, chip in self._manual_kind_chips.items():
        if chip.winfo_exists():
          chip.set_selected(k == kind, silent=True)
      if callable(self._manual_refresh_fn):
        self._manual_refresh_fn()

  def _on_engine_cards_loaded(self, cards: list[dict], source: str, set_idx):
    self.manual_words = list(cards or [])
    self.manual_loaded_set_idx = set_idx
    if callable(self._manual_refresh_fn):
      self._manual_refresh_fn()

  def _on_engine_state_change(self, snap: dict):
    active = bool(snap.get('active'))
    paused = bool(snap.get('paused'))
    self._set_running_ui(active)
    if active:
      self.btn_pause.set_text('재개' if paused else '일시정지')
    if callable(self._manual_refresh_fn):
      self._manual_refresh_fn()

  def _provide_next_set(self, done_idx: set[str]):
    with self._state_lock:
      picked = dict(self.checked_targets)
      sets_copy = list(self.sets)
    for item in sets_copy:
      idx = str(item['idx'])
      if idx in done_idx or idx not in picked:
        continue
      return dict(item, target=picked[idx])
    return None

  def _set_live_status(self, text: str, color_key: str = 'ink'):
    t = self.theme
    fg = t.get(color_key, t['ink'])
    self.lbl_live_status.configure(text=text, fg=fg)

  def start_auto(self, test_only: bool = False):
    snap = study_engine.engine.snapshot()
    if snap.get('active'):
      messagebox.showinfo('자동 학습', '이미 진행 중입니다. 먼저 [정지]를 누르세요.')
      return
    with self._state_lock:
      has_targets = bool(self.checked_targets)
    if not has_targets:
      messagebox.showwarning('자동 학습', '학습할 세트를 하나 이상 선택하세요.')
      return

    modes = self._get_selected_modes()
    if not test_only and not any(modes.values()):
      messagebox.showwarning('자동 학습', '최소 한 개 이상의 학습 모드를 선택하세요.')
      return

    plan = {
        'class_idx': self.current_class_idx,
        'test': True,
        'test_only': test_only,
        'modes': modes,
    }
    self._set_running_ui(True)
    study_engine.engine.start_auto(plan, set_provider=self._provide_next_set)

  def _on_engine_rate_update(self, set_idx, rates: dict):
    s_idx = str(set_idx)
    with self._state_lock:
      for item in self.sets:
        if str(item.get('idx')) == s_idx:
          merged = dict(item.get('rates') or {})
          merged.update(rates)
          item['rates'] = merged
          self.rate_cache[s_idx] = merged
          break
    config_store.save_rate_cache(self.rate_cache)
    self._render_set_rows()
    self._render_kpis()

  def toggle_pause(self):
    paused = study_engine.engine.toggle_pause()
    self.btn_pause.set_text('재개' if paused else '일시정지')

  def stop_all(self):
    study_engine.engine.stop()
    self._set_running_ui(False)
    self._set_live_status('정지했습니다.', 'red')

  def _set_running_ui(self, running: bool):
    self.btn_auto_start.set_enabled(not running)
    self.btn_test_only.set_enabled(not running)
    self.btn_pause.set_enabled(running)
    if not running:
      self.btn_pause.set_text('일시정지')
    self.btn_stop_auto.set_enabled(running)

  # ── 1-Second Live Refresh Loop ──────────────────────────────────────────

  def _schedule_tick(self):
    if self._destroyed:
      return
    self._tick()
    self._tick_job = self.root.after(1000, self._schedule_tick)

  def _tick(self):
    snap = study_engine.engine.snapshot()
    active = bool(snap.get('active'))
    paused = bool(snap.get('paused'))

    if active:
      rest_rem = int(snap.get('auto_rest_remaining') or 0)
      rest_tot = max(1, int(snap.get('auto_rest_total') or 1))
      elapsed_s = int(max(0, snap.get('elapsed_seconds') or 0))
      mm, ss = divmod(elapsed_s, 60)

      if paused:
        self.live_progress.set_progress(self.live_progress._pct, color_key='amber')
        self.lbl_live_metrics.configure(text=f'일시정지 · {mm:02d}:{ss:02d}', fg=self.theme['amber'])
      elif rest_rem > 0:
        pct = max(0.0, min(100.0, (rest_tot - rest_rem) / rest_tot * 100.0))
        self.live_progress.set_progress(pct, color_key='amber')
        self._set_live_status(f'⏳ 탐지 방지 휴식 중 ({rest_rem}초 남음)', 'amber')
        self.lbl_live_metrics.configure(text=f'휴식 {rest_rem}s · {mm:02d}:{ss:02d}', fg=self.theme['amber'])
      else:
        s_done = int(snap.get('site_done') or 0)
        s_tot = int(snap.get('site_total') or 0)
        if s_tot > 0:
          done, tot = s_done, s_tot
        else:
          done = int(snap.get('cards_done') or 0)
          tot = int(snap.get('cards_total') or 0)
        pct = int(done / tot * 100) if tot > 0 else 0
        self.live_progress.set_progress(pct, color_key='primary')
        cur_name = snap.get('current_set_name') or self._set_name_by_idx(snap.get('current_set_idx'))
        cur_mode = snap.get('current_mode')
        m_name = {'memorize': '암기', 'recall': '리콜', 'spell': '스펠', 'test': '테스트'}.get(
            cur_mode, cur_mode or '학습',
        )
        if cur_name and cur_mode:
          self._set_live_status(f'▶ [{m_name}] {cur_name}', 'link')
        metric = f'{done}/{tot} ({pct}%) · {mm:02d}:{ss:02d}' if tot > 0 else f'준비 중 · {mm:02d}:{ss:02d}'
        self.lbl_live_metrics.configure(text=metric, fg=self.theme['ink_subtle'])
    else:
      self.live_progress.set_progress(0, color_key='primary')
      self.lbl_live_metrics.configure(text='대기 중 · 00:00', fg=self.theme['ink_subtle'])
      self._set_running_ui(False)

    self._render_kpis()

  def _set_name_by_idx(self, s_idx) -> str:
    if not s_idx:
      return ''
    for s in self.sets:
      if str(s.get('idx')) == str(s_idx):
        return s.get('name', '')
    return ''

  # ── Modal Sheets ────────────────────────────────────────────────────────

  def _make_sheet(self, title: str, geometry: str) -> tk.Toplevel:
    t = self.theme
    win = tk.Toplevel(self.root)
    win.title(title)
    win.geometry(geometry)
    win.configure(bg=t['canvas'])
    if bool(config_store.config_get('always_on_top', False)):
      win.wm_attributes('-topmost', True)
    return win

  def open_settings_sheet(self):
    if self._settings_win and self._settings_win.winfo_exists():
      self._settings_win.deiconify()
      self._settings_win.lift()
      return

    t = self.theme
    win = self._make_sheet('옵션 설정', '500x540')
    win.resizable(False, False)
    self._settings_win = win

    cfg = config_store.get_all_config()

    card = GlassCard(win, theme=t, radius=18, padding=(20, 18), surface_key='glass_bg', parent_bg_key='canvas')
    card.pack(fill='both', expand=True, padx=18, pady=18)

    lbl_hdr = tk.Label(card.body, text='옵션 설정', font=font(16, 'bold'), bg=t['glass_bg'], fg=t['ink'])
    lbl_hdr.pack(anchor='w', pady=(0, 12))

    # Theme selector
    row_theme = tk.Frame(card.body, bg=t['glass_bg'])
    row_theme.pack(fill='x', pady=6)
    tk.Label(row_theme, text='화면 테마', font=font(11, 'bold'), bg=t['glass_bg'], fg=t['ink']).pack(side='left')
    theme_chips: dict[str, GlassChipToggle] = {}

    def pick_theme(val: str):
      self.set_theme(val)
      for k, c in theme_chips.items():
        c.set_selected(k == val, silent=True)

    for k, label in (('dark', '다크'), ('light', '라이트'), ('system', '시스템')):
      c = GlassChipToggle(
          row_theme, text=label, selected=(self.theme_pref == k),
          on_toggle=lambda _s, v=k: pick_theme(v), theme=t, height=26, padx=10,
          active_style='solid', parent_bg_key='glass_bg',
      )
      c.pack(side='right', padx=(4, 0))
      theme_chips[k] = c

    # Toggles
    var_human = tk.BooleanVar(value=bool(cfg.get('human_delay', True)))
    var_delay = tk.BooleanVar(value=bool(cfg.get('delay_enabled', True)))
    var_wrong = tk.BooleanVar(value=bool(cfg.get('wrong_enabled', False)))
    var_top = tk.BooleanVar(value=bool(cfg.get('always_on_top', False)))

    def make_toggle_row(label: str, var: tk.BooleanVar) -> GlassChipToggle:
      rf = tk.Frame(card.body, bg=t['glass_bg'])
      rf.pack(fill='x', pady=6)
      tk.Label(rf, text=label, font=font(11), bg=t['glass_bg'], fg=t['ink']).pack(side='left')
      chip = GlassChipToggle(
          rf, text='ON' if var.get() else 'OFF', selected=var.get(),
          on_toggle=lambda s, v=var: (v.set(s), chip.set_text('ON' if s else 'OFF')),
          theme=t, height=26, padx=12, active_style='green', parent_bg_key='glass_bg',
      )
      chip.pack(side='right')
      return chip

    chip_human = make_toggle_row('인간형 미세 지연 (0.1~0.7초)', var_human)
    chip_delay = make_toggle_row('세트 간 랜덤 휴식 사용', var_delay)

    row_d_range = tk.Frame(card.body, bg=t['glass_bg'])
    row_d_range.pack(fill='x', pady=(0, 8))
    tk.Label(row_d_range, text='휴식 범위 (초)', font=font(10), bg=t['glass_bg'], fg=t['ink_subtle']).pack(side='left', padx=(12, 0))
    st_d_max = GlassStepper(row_d_range, theme=t, value=int(cfg.get('delay_max', 45)), min_val=5, max_val=300, step=5, suffix='s', width=86, height=26, parent_bg_key='glass_bg')
    st_d_max.pack(side='right')
    tk.Label(row_d_range, text='~', font=font(11), bg=t['glass_bg'], fg=t['ink_subtle']).pack(side='right', padx=6)
    st_d_min = GlassStepper(row_d_range, theme=t, value=int(cfg.get('delay_min', 15)), min_val=5, max_val=300, step=5, suffix='s', width=86, height=26, parent_bg_key='glass_bg')
    st_d_min.pack(side='right')

    chip_wrong = make_toggle_row('테스트 일부러 틀리기', var_wrong)

    row_w_range = tk.Frame(card.body, bg=t['glass_bg'])
    row_w_range.pack(fill='x', pady=(0, 8))
    tk.Label(row_w_range, text='오답 개수 범위', font=font(10), bg=t['glass_bg'], fg=t['ink_subtle']).pack(side='left', padx=(12, 0))
    st_w_max = GlassStepper(row_w_range, theme=t, value=int(cfg.get('wrong_max', 2)), min_val=0, max_val=20, step=1, suffix='개', width=86, height=26, parent_bg_key='glass_bg')
    st_w_max.pack(side='right')
    tk.Label(row_w_range, text='~', font=font(11), bg=t['glass_bg'], fg=t['ink_subtle']).pack(side='right', padx=6)
    st_w_min = GlassStepper(row_w_range, theme=t, value=int(cfg.get('wrong_min', 1)), min_val=0, max_val=20, step=1, suffix='개', width=86, height=26, parent_bg_key='glass_bg')
    st_w_min.pack(side='right')

    row_pass = tk.Frame(card.body, bg=t['glass_bg'])
    row_pass.pack(fill='x', pady=6)
    tk.Label(row_pass, text='기본 테스트 통과 커트라인', font=font(11), bg=t['glass_bg'], fg=t['ink']).pack(side='left')
    st_pass = GlassStepper(row_pass, theme=t, value=int(cfg.get('pass_score', 85)), min_val=0, max_val=100, step=5, suffix='점', width=92, height=26, parent_bg_key='glass_bg')
    st_pass.pack(side='right')

    chip_top = make_toggle_row('창 항상 위 (Always on Top)', var_top)

    btns = tk.Frame(card.body, bg=t['glass_bg'])
    btns.pack(fill='x', side='bottom', pady=(14, 0))

    def save_and_close():
      d_min = st_d_min.get_value()
      d_max = max(d_min, st_d_max.get_value())
      w_min = st_w_min.get_value()
      w_max = max(w_min, st_w_max.get_value())
      config_store.config_update({
          'human_delay': bool(var_human.get()),
          'delay_enabled': bool(var_delay.get()),
          'delay_min': d_min,
          'delay_max': d_max,
          'wrong_enabled': bool(var_wrong.get()),
          'wrong_min': w_min,
          'wrong_max': w_max,
          'pass_score': st_pass.get_value(),
          'always_on_top': bool(var_top.get()),
      })
      self.root.wm_attributes('-topmost', bool(var_top.get()))
      cur_cutoff = self._current_cutoff()
      self.cutoff_stepper.set_value(cur_cutoff, notify=False)
      self.lbl_class_cutoff.configure(text=self._cutoff_badge_text(cur_cutoff))
      self._render_set_rows()
      self._render_kpis()
      win.destroy()

    GlassPillButton(btns, '닫기', command=win.destroy, theme=t, variant='pearl', height=32, padx=16, parent_bg_key='glass_bg').pack(side='right', padx=(8, 0))
    GlassPillButton(btns, '저장', command=save_and_close, theme=t, variant='primary', height=32, padx=20, parent_bg_key='glass_bg').pack(side='right')

    self._retheme_settings = lambda: (win.destroy(), self.open_settings_sheet())

  def open_dashboard_sheet(self):
    if self._dashboard_win and self._dashboard_win.winfo_exists():
      self._dashboard_win.deiconify()
      self._dashboard_win.lift()
      return

    win = self._make_sheet('학습 통계 대시보드', '860x640')
    win.minsize(780, 560)
    self._dashboard_win = win

    head = tk.Frame(win, bg=self.theme['canvas'])
    head.pack(fill='x', padx=20, pady=(16, 8))
    lbl_title = tk.Label(head, text='학습 통계 대시보드', font=font(18, 'bold'), bg=self.theme['canvas'], fg=self.theme['ink'])
    lbl_title.pack(side='left')
    lbl_sub = tk.Label(head, text='', font=font(11), bg=self.theme['canvas'], fg=self.theme['ink_subtle'])
    lbl_sub.pack(side='left', padx=(12, 0), pady=(4, 0))

    btn_close = GlassPillButton(head, '닫기', command=win.destroy, theme=self.theme, variant='pearl', height=30, padx=14, parent_bg_key='canvas')
    btn_close.pack(side='right')

    cv_live = tk.Canvas(win, height=74, bg=self.theme['canvas'], highlightthickness=0, bd=0)
    cv_live.pack(fill='x', padx=20, pady=(0, 12))

    charts = tk.Frame(win, bg=self.theme['canvas'])
    charts.pack(fill='both', expand=True, padx=20, pady=(0, 20))
    charts.columnconfigure((0, 1), weight=1, uniform='dash')
    charts.rowconfigure(0, weight=1)

    cv_left = tk.Canvas(charts, bg=self.theme['canvas'], highlightthickness=0, bd=0)
    cv_left.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
    cv_right = tk.Canvas(charts, bg=self.theme['canvas'], highlightthickness=0, bd=0)
    cv_right.grid(row=0, column=1, sticky='nsew', padx=(8, 0))

    def draw_bar(cv: tk.Canvas, x: float, y: float, w: float, h: float, pct: float, color: str):
      t = self.theme
      draw_round_rect(cv, x, y, x + w, y + h, radius=9999, fill=t['track'])
      pct = max(0.0, min(100.0, float(pct)))
      if pct > 0:
        fw = max(h, int(w * pct / 100.0))
        draw_round_rect(cv, x, y, x + fw, y + h, radius=9999, fill=color)

    def render():
      if not (win and win.winfo_exists()):
        return
      t = self.theme
      s = self.calculate_stats()
      win.configure(bg=t['canvas'])
      head.configure(bg=t['canvas'])
      charts.configure(bg=t['canvas'])
      lbl_title.configure(bg=t['canvas'], fg=t['ink'])
      lbl_sub.configure(
          bg=t['canvas'], fg=t['ink_subtle'],
          text=f"{s['class_name']} · 총 {s['total_sets']}개 · 커트라인 {s['cutoff']}점",
      )
      btn_close.apply_theme(t)

      # Live banner
      cv_live.configure(bg=t['canvas'])
      cv_live.delete('all')
      wl = max(400, cv_live.winfo_width())
      draw_round_rect(cv_live, 1, 1, wl - 2, 72, radius=16, fill=t['glass_bg'], outline=t['hairline'], specular=t['glass_specular'])
      snap = study_engine.engine.snapshot()
      if snap.get('active'):
        s_done = int(snap.get('site_done') or 0)
        s_tot = int(snap.get('site_total') or 0)
        done = s_done if s_tot > 0 else int(snap.get('cards_done') or 0)
        tot = s_tot if s_tot > 0 else int(snap.get('cards_total') or 0)
        pct = int(done / tot * 100) if tot else 0
        cv_live.create_text(18, 22, text=f"LIVE · 진행 {done}/{tot} ({pct}%)", font=font(12, 'bold'), fill=t['green'], anchor='w')
        draw_bar(cv_live, 18, 44, wl - 36, 10, pct, t['primary'])
      else:
        cv_live.create_text(18, 24, text='대기 중', font=font(12, 'bold'), fill=t['ink_muted'], anchor='w')
        cv_live.create_text(18, 48, text=f"종합 달성도 {s['overall_pct']}% · 테스트 평균 {s['t_avg_score']}점", font=font(11), fill=t['ink_subtle'], anchor='w')

      # Left chart: Mode achievement
      cv_left.configure(bg=t['canvas'])
      cv_left.delete('all')
      w_l, h_l = max(340, cv_left.winfo_width()), max(360, cv_left.winfo_height())
      draw_round_rect(cv_left, 1, 1, w_l - 2, h_l - 2, radius=18, fill=t['glass_bg'], outline=t['hairline'], specular=t['glass_specular'])
      cv_left.create_text(20, 26, text='모드별 종합 달성도', font=font(14, 'bold'), fill=t['ink'], anchor='w')

      mode_rows = [
          ('암기 평균', s['m_avg'], f"{s['m_done']}/{s['total_sets']} 완료", t['primary']),
          ('리콜 평균', s['r_avg'], f"{s['r_done']}/{s['total_sets']} 완료", t['green']),
          ('스펠 평균', s['s_avg'], f"{s['s_done']}/{s['total_sets']} 완료", t['amber']),
          ('테스트 통과율', s['t_pass_rate'], f"{s['t_passed']}/{s['total_sets']} 통과", t['purple']),
          ('종합 달성도', s['overall_pct'], '전체 통합', t['link']),
      ]
      for idx, (m_lbl, m_pct, m_sub, m_col) in enumerate(mode_rows):
        ry = 70 + idx * 62
        cv_left.create_text(20, ry, text=m_lbl, font=font(11, 'bold'), fill=t['ink'], anchor='w')
        cv_left.create_text(w_l - 20, ry, text=f'{m_pct}% ({m_sub})', font=font(10), fill=t['ink_subtle'], anchor='e')
        draw_bar(cv_left, 20, ry + 16, w_l - 40, 10, m_pct, m_col)

      # Right chart: Score distribution
      cv_right.configure(bg=t['canvas'])
      cv_right.delete('all')
      w_r, h_r = max(340, cv_right.winfo_width()), max(360, cv_right.winfo_height())
      draw_round_rect(cv_right, 1, 1, w_r - 2, h_r - 2, radius=18, fill=t['glass_bg'], outline=t['hairline'], specular=t['glass_specular'])
      cv_right.create_text(20, 26, text='테스트 성적 분포', font=font(14, 'bold'), fill=t['ink'], anchor='w')

      t_tot = max(1, s['total_sets'])
      dist_rows = [
          ('100점 만점', s['score_100'], t['cyan']),
          ('90 ~ 99점', s['score_90_99'], t['green']),
          (f"{s['cutoff']} ~ 89점 (통과)", s['score_pass'], t['primary']),
          (f"{s['cutoff']}점 미달", s['score_fail'], t['red']),
          ('미응시', s['score_none'], t['ink_subtle']),
      ]
      for idx, (d_lbl, d_cnt, d_col) in enumerate(dist_rows):
        ry = 70 + idx * 62
        d_pct = round(d_cnt / t_tot * 100, 1)
        cv_right.create_text(20, ry, text=d_lbl, font=font(11, 'bold'), fill=t['ink'], anchor='w')
        cv_right.create_text(w_r - 20, ry, text=f'{d_cnt}개 ({d_pct}%)', font=font(10, 'bold'), fill=d_col, anchor='e')
        draw_bar(cv_right, 20, ry + 16, w_r - 40, 10, d_pct, d_col)

    def loop():
      if win and win.winfo_exists():
        render()
        win.after(1000, loop)

    self._retheme_dashboard = render
    win.after(60, loop)

  def open_log_sheet(self):
    if self._log_win and self._log_win.winfo_exists():
      self._log_win.deiconify()
      self._log_win.lift()
      return

    t = self.theme
    win = self._make_sheet('실시간 활동 로그', '760x520')
    self._log_win = win

    head = tk.Frame(win, bg=t['canvas'])
    head.pack(fill='x', padx=20, pady=(16, 10))
    tk.Label(head, text='실시간 활동 로그', font=font(16, 'bold'), bg=t['canvas'], fg=t['ink']).pack(side='left')

    filter_level = {'val': 'ALL'}
    chips = {}

    def pick_lvl(lvl: str):
      filter_level['val'] = lvl
      for k, c in chips.items():
        c.set_selected(k == lvl, silent=True)
      refresh_logs()

    for lvl in ('ALL', 'INFO', 'WARN', 'ERROR'):
      c = GlassChipToggle(
          head, text=lvl, selected=(lvl == 'ALL'),
          on_toggle=lambda _s, l=lvl: pick_lvl(l), theme=t,
          height=26, padx=10, active_style='solid', parent_bg_key='canvas',
      )
      c.pack(side='left', padx=(8, 0))
      chips[lvl] = c

    card = GlassCard(win, theme=t, radius=18, padding=(14, 14), surface_key='glass_bg', parent_bg_key='canvas')
    card.pack(fill='both', expand=True, padx=20, pady=(0, 12))

    txt = tk.Text(
        card.body, font=font(10, mono=True),
        bg=t['glass_bg'], fg=t['ink'], bd=0, highlightthickness=0,
        wrap='word', state='disabled',
    )
    sb = tk.Scrollbar(card.body, orient='vertical', command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    sb.pack(side='right', fill='y')
    txt.pack(side='left', fill='both', expand=True)

    foot = tk.Frame(win, bg=t['canvas'])
    foot.pack(fill='x', padx=20, pady=(0, 16))

    def copy_logs():
      content = txt.get('1.0', 'end-1c')
      win.clipboard_clear()
      win.clipboard_append(content)

    def clear_logs():
      study_engine.engine.clear_logs()
      refresh_logs()

    GlassPillButton(foot, '닫기', command=win.destroy, theme=t, variant='pearl', height=30, padx=14, parent_bg_key='canvas').pack(side='right', padx=(8, 0))
    GlassPillButton(foot, '지우기', command=clear_logs, theme=t, variant='danger', height=30, padx=14, parent_bg_key='canvas').pack(side='right', padx=(8, 0))
    GlassPillButton(foot, '복사', command=copy_logs, theme=t, variant='secondary', height=30, padx=14, parent_bg_key='canvas').pack(side='right')

    last_sig = {'val': None}

    def refresh_logs():
      if not (win and win.winfo_exists()):
        return
      logs = study_engine.engine.get_logs(level=None if filter_level['val'] == 'ALL' else filter_level['val'])
      sig = (len(logs), logs[-1] if logs else None, filter_level['val'])
      if sig == last_sig['val']:
        return
      last_sig['val'] = sig
      lines = [f"[{ts}] [{lvl:<5}] {msg}" for ts, lvl, msg in logs]
      txt.configure(state='normal')
      txt.delete('1.0', tk.END)
      txt.insert('1.0', '\n'.join(lines) if lines else '기록된 로그가 없습니다.')
      txt.see(tk.END)
      txt.configure(state='disabled')

    def loop():
      if win and win.winfo_exists():
        refresh_logs()
        win.after(1000, loop)

    self._retheme_logs = lambda: (win.destroy(), self.open_log_sheet())
    loop()

  def open_manual_sheet(self):
    if self._manual_win and self._manual_win.winfo_exists():
      self._manual_win.deiconify()
      self._manual_win.lift()
      return

    t = self.theme
    win = self._make_sheet('수동 모드', '480x560')
    win.resizable(False, False)
    self._manual_win = win
    win.bind('<Escape>', lambda _e: self.stop_all())

    card = GlassCard(win, theme=t, radius=18, padding=(18, 16), surface_key='glass_bg', parent_bg_key='canvas')
    card.pack(fill='both', expand=True, padx=18, pady=18)

    tk.Label(card.body, text='수동 학습 컨트롤', font=font(15, 'bold'), bg=t['glass_bg'], fg=t['ink']).pack(anchor='w')
    lbl_st = tk.Label(
        card.body, textvariable=self._manual_status_var, font=font(10),
        bg=t['glass_bg'], fg=t['link'], justify='left', wraplength=400, pady=8,
    )
    lbl_st.pack(anchor='w', fill='x')

    # Word / Sentence toggle
    kind_row = tk.Frame(card.body, bg=t['glass_bg'])
    if SENTENCE_MODE_ENABLED:
      kind_row.pack(fill='x', pady=(4, 10))
    self._manual_kind_chips = {}

    def pick_kind(k: str):
      self.manual_kind.set(k)
      study_engine.engine.set_study_kind(k)
      for key, chip in self._manual_kind_chips.items():
        chip.set_selected(key == k, silent=True)
      refresh_manual_buttons()

    for k, label in (('word', '단어 모드'), ('sentence', '문장 모드')):
      c = GlassChipToggle(
          kind_row, text=label, selected=(self.manual_kind.get() == k),
          on_toggle=lambda _s, v=k: pick_kind(v),
          theme=t, height=30, padx=14, active_style='solid', parent_bg_key='glass_bg',
      )
      c.pack(side='left', padx=(0, 8))
      self._manual_kind_chips[k] = c

    # Load row
    load_row = tk.Frame(card.body, bg=t['glass_bg'])
    load_row.pack(fill='x', pady=(0, 12))

    btn_load_chrome = GlassPillButton(
        load_row, '크롬에서 불러오기', command=lambda: self._manual_load_chrome(refresh_manual_buttons),
        theme=t, variant='primary', height=32, padx=14, parent_bg_key='glass_bg',
    )
    btn_load_chrome.pack(side='left', padx=(0, 8))
    btn_load_clip = GlassPillButton(
        load_row, '클립보드 불러오기', command=lambda: self._manual_load_clipboard(refresh_manual_buttons),
        theme=t, variant='secondary', height=32, padx=14, parent_bg_key='glass_bg',
    )
    btn_load_clip.pack(side='left')

    # Mode triggers
    memo_row = tk.Frame(card.body, bg=t['glass_bg'])
    memo_row.pack(fill='x', pady=6)
    btn_memo = GlassPillButton(
        memo_row, '암기 시작', command=lambda: self._manual_run('memorize', refresh_manual_buttons),
        theme=t, variant='pearl', height=34, padx=16, parent_bg_key='glass_bg',
    )
    btn_memo.pack(side='left', padx=(0, 8))
    btn_memo_go = GlassPillButton(
        memo_row, '준비 완료 [시작]', command=self._manual_memo_go,
        theme=t, variant='primary', height=34, padx=14, enabled=False, parent_bg_key='glass_bg',
    )
    btn_memo_go.pack(side='left')

    btn_recall = GlassPillButton(
        card.body, '리콜 자동 풀이 시작', command=lambda: self._manual_run('recall', refresh_manual_buttons),
        theme=t, variant='pearl', height=36, padx=18, parent_bg_key='glass_bg',
    )
    btn_recall.pack(fill='x', pady=6)

    btn_spell = GlassPillButton(
        card.body, '스펠 자동 풀이 시작', command=lambda: self._manual_run('spell', refresh_manual_buttons),
        theme=t, variant='pearl', height=36, padx=18, parent_bg_key='glass_bg',
    )
    btn_spell.pack(fill='x', pady=6)

    btn_test = GlassPillButton(
        card.body, '테스트 자동 풀이 시작', command=lambda: self._manual_run('test', refresh_manual_buttons),
        theme=t, variant='pearl', height=36, padx=18, parent_bg_key='glass_bg',
    )
    btn_test.pack(fill='x', pady=6)

    foot = tk.Frame(card.body, bg=t['glass_bg'])
    foot.pack(fill='x', side='bottom', pady=(12, 0))
    btn_stop = GlassPillButton(
        foot, '정지', command=lambda: (self.stop_all(), refresh_manual_buttons()),
        theme=t, variant='danger', height=32, padx=18, parent_bg_key='glass_bg',
    )
    btn_stop.pack(side='left')
    GlassPillButton(
        foot, '닫기', command=win.destroy, theme=t, variant='pearl',
        height=32, padx=16, parent_bg_key='glass_bg',
    ).pack(side='right')

    def refresh_manual_buttons():
      if not (win and win.winfo_exists()):
        return
      chosen = self.manual_kind.get() in ('word', 'sentence')
      is_sent = self.manual_kind.get() == 'sentence'
      snap = study_engine.engine.snapshot()
      running = bool(snap.get('active'))
      has_words = bool(self.manual_words)

      btn_load_chrome.set_enabled(chosen and not running)
      btn_load_clip.set_enabled(chosen and not running)
      btn_memo.set_text('영작 연습 시작' if is_sent else '암기 시작')
      can_start = chosen and has_words and not running
      btn_memo.set_enabled(can_start)
      btn_recall.set_enabled(can_start)
      btn_spell.set_enabled(can_start)
      btn_test.set_enabled(can_start)
      btn_stop.set_enabled(running)
      btn_memo_go.set_enabled(running and not is_sent and bool(snap.get('waiting_memo_go')))

    self._manual_refresh_fn = refresh_manual_buttons
    self._retheme_manual = lambda: (win.destroy(), self.open_manual_sheet())
    refresh_manual_buttons()

  def _manual_load_chrome(self, on_done):
    self._manual_status_var.set('크롬에서 세트를 읽는 중...')
    study_engine.engine.load_words_from_chrome(async_run=True)
    on_done()

  def _manual_load_clipboard(self, on_done):
    try:
      raw = self.root.clipboard_get().strip()
    except Exception:
      raw = ''
    ok, msg = study_engine.engine.load_words_from_json(raw)
    if ok:
      self._manual_status_var.set(msg)
      on_done()
    else:
      messagebox.showerror('에러', msg)

  def _manual_memo_go(self):
    study_engine.engine.press_memo_go()
    if callable(self._manual_refresh_fn):
      self._manual_refresh_fn()

  def _manual_run(self, mode: str, on_done):
    if not self.manual_words:
      messagebox.showwarning('알림', '먼저 단어를 불러오세요.')
      return
    kind = 'sentence' if self.manual_kind.get() == 'sentence' else 'word'
    study_engine.engine.set_study_kind(kind)
    ok, msg = study_engine.engine.start_manual(mode)
    if not ok:
      messagebox.showwarning('알림', msg)
    else:
      self._manual_status_var.set(msg)
    on_done()

  def open_login_sheet(self):
    if self._login_win and self._login_win.winfo_exists():
      self._login_win.deiconify()
      self._login_win.lift()
      return

    t = self.theme
    win = self._make_sheet('자동 로그인 설정', '420x320')
    win.resizable(False, False)
    self._login_win = win

    card = GlassCard(win, theme=t, radius=18, padding=(22, 18), surface_key='glass_bg', parent_bg_key='canvas')
    card.pack(fill='both', expand=True, padx=18, pady=18)

    tk.Label(card.body, text='클래스카드 계정', font=font(16, 'bold'), bg=t['glass_bg'], fg=t['ink']).pack(anchor='w')
    tk.Label(
        card.body,
        text='이 컴퓨터에서만 복호화 가능하도록 암호화해 저장합니다.',
        font=font(10), bg=t['glass_bg'], fg=t['ink_subtle'],
    ).pack(anchor='w', pady=(2, 14))

    form = tk.Frame(card.body, bg=t['glass_bg'])
    form.pack(fill='x')

    tk.Label(form, text='아이디', font=font(11), bg=t['glass_bg'], fg=t['ink_muted'], width=8, anchor='w').grid(row=0, column=0, pady=6)
    ent_id = tk.Entry(form, font=font(11), bg=t['input_bg'], fg=t['ink'], insertbackground=t['ink'], relief='solid', bd=1, highlightthickness=0)
    ent_id.grid(row=0, column=1, sticky='ew', pady=6)

    tk.Label(form, text='비밀번호', font=font(11), bg=t['glass_bg'], fg=t['ink_muted'], width=8, anchor='w').grid(row=1, column=0, pady=6)
    ent_pw = tk.Entry(form, font=font(11), show='•', bg=t['input_bg'], fg=t['ink'], insertbackground=t['ink'], relief='solid', bd=1, highlightthickness=0)
    ent_pw.grid(row=1, column=1, sticky='ew', pady=6)
    form.columnconfigure(1, weight=1)

    saved = config_store.load_login()
    if saved:
      ent_id.insert(0, saved['id'])
      ent_pw.insert(0, saved['pw'])

    lbl_msg = tk.Label(
        card.body,
        text='저장된 계정이 있습니다.' if saved else '저장된 계정이 없습니다.',
        font=font(10), bg=t['glass_bg'], fg=t['ink_subtle'],
    )
    lbl_msg.pack(anchor='w', pady=(8, 0))

    def do_save():
      uid, upw = ent_id.get().strip(), ent_pw.get()
      if not uid or not upw:
        messagebox.showwarning('자동 로그인', '아이디와 비밀번호를 모두 입력하세요.')
        return
      try:
        config_store.save_login(uid, upw)
        lbl_msg.configure(text='계정을 암호화해 저장했습니다.', fg=t['green'])
      except Exception as e:
        messagebox.showerror('자동 로그인', f'저장 실패:\n{e}')

    def do_clear():
      config_store.clear_login()
      ent_id.delete(0, tk.END)
      ent_pw.delete(0, tk.END)
      lbl_msg.configure(text='저장된 계정을 삭제했습니다.', fg=t['red'])

    btns = tk.Frame(card.body, bg=t['glass_bg'])
    btns.pack(fill='x', side='bottom', pady=(14, 0))
    GlassPillButton(btns, '닫기', command=win.destroy, theme=t, variant='pearl', height=32, padx=14, parent_bg_key='glass_bg').pack(side='right', padx=(6, 0))
    GlassPillButton(btns, '지우기', command=do_clear, theme=t, variant='danger', height=32, padx=14, parent_bg_key='glass_bg').pack(side='right', padx=(6, 0))
    GlassPillButton(btns, '저장', command=do_save, theme=t, variant='primary', height=32, padx=18, parent_bg_key='glass_bg').pack(side='right')

    self._retheme_login = lambda: (win.destroy(), self.open_login_sheet())

  # ── Lifecycle & Restart ─────────────────────────────────────────────────

  def restart_program(self):
    study_engine.engine.stop()
    self._set_live_status('재시작 중...', 'red')
    self.root.update_idletasks()
    chrome_bridge.close_driver_service()

    if getattr(sys, 'frozen', False):
      args = [sys.executable] + sys.argv[1:]
    else:
      args = [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:]

    env = dict(os.environ)
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    try:
      subprocess.Popen(args, env=env, close_fds=True)
    except Exception as e:
      messagebox.showerror('재시작 실패', f'다시 시작하지 못했습니다:\n{e}')
      return
    self._on_close()
    os._exit(0)

  def _on_close(self):
    self._destroyed = True
    if self._tick_job is not None:
      try:
        self.root.after_cancel(self._tick_job)
      except Exception:
        pass
    try:
      study_engine.engine.stop()
    except Exception:
      pass
    try:
      self.root.destroy()
    except Exception:
      pass

  def run(self):
    self.root.mainloop()
