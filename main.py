"""Entry point for Classcard Macro (Apple DESIGN.md & Liquid Glass UI)."""

import ctypes
import sys

from glass_ui import GlassApp


def _enable_windows_dpi_awareness() -> None:
  """Enable per-monitor DPI awareness on Windows before creating Tk windows."""
  if sys.platform != 'win32':
    return
  try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
  except Exception:
    try:
      ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
      pass


def main() -> None:
  _enable_windows_dpi_awareness()
  app = GlassApp()
  app.run()


if __name__ == '__main__':
  main()
