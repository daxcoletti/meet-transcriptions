"""Atajo de teclado global para iniciar/detener la grabación.

Usa pynput (hooks Win32 en Windows, Xlib en X11) — las mismas plataformas
donde hoy funciona la grabación. En Wayland no hay captura global de teclas
(hasta integrar el portal GlobalShortcuts, pendiente junto con la fase 1c).

El callback de pynput llega en SU hilo listener: la GUI lo puentea con una
señal Qt, como todo lo demás.
"""

import os


def available():
    """¿Se puede registrar un atajo global en esta sesión?"""
    if os.name == "nt":
        return True
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
        return False
    return bool(os.environ.get("DISPLAY"))


MODIFIERS = {"ctrl", "alt", "shift", "meta", "cmd", "win"}


def parse_sequence(sequence):
    """"Ctrl+Alt+R" → ({"ctrl", "alt"}, "r"). La tecla principal queda en
    minúsculas; los sinónimos de modificadores se normalizan."""
    synonyms = {"win": "cmd", "meta": "cmd"}
    mods = set()
    main = None
    for p in (x.strip().lower() for x in sequence.split("+") if x.strip()):
        if p in MODIFIERS:
            mods.add(synonyms.get(p, p))
        else:
            main = p
    if not main:
        raise ValueError(f"atajo sin tecla principal: {sequence!r}")
    return mods, main


class HotkeyListener:
    """Registra UN atajo global y dispara el callback al presionarlo.

    Matcher propio en vez de pynput.GlobalHotKeys: con Ctrl apretado, la
    tecla principal puede llegar como carácter de control (Ctrl+R → '\\x12')
    y GlobalHotKeys no matchea. Acá se rastrean los modificadores y la tecla
    principal se compara por carácter canónico, carácter de control mapeado,
    o código virtual (vk), lo que cubra la plataforma.
    """

    def __init__(self, sequence, callback):
        self.sequence = sequence
        self.callback = callback
        self._listener = None
        self._mods_needed, self._main = parse_sequence(sequence)
        self._mods_down = set()

    # --- helpers de matching ---
    @staticmethod
    def _normalize_mod(key, keyboard):
        k = keyboard.Key
        table = {
            k.ctrl: "ctrl", k.ctrl_l: "ctrl", k.ctrl_r: "ctrl",
            k.alt: "alt", k.alt_l: "alt", k.alt_r: "alt", k.alt_gr: "alt",
            k.shift: "shift", k.shift_l: "shift", k.shift_r: "shift",
            k.cmd: "cmd", k.cmd_l: "cmd", k.cmd_r: "cmd",
        }
        return table.get(key)

    def _is_main_key(self, key, keyboard):
        # Teclas con nombre ("f9", "home", "space"…)
        if len(self._main) > 1:
            named = getattr(keyboard.Key, self._main, None)
            return named is not None and key == named
        # Un carácter: probar canónico, control-char y vk
        target = self._main
        try:
            canon = self._listener.canonical(key)
        except Exception:
            canon = key
        char = getattr(canon, "char", None) or getattr(key, "char", None)
        if char:
            if char.lower() == target:
                return True
            if 1 <= ord(char) <= 26 and chr(ord(char) + 96) == target:
                return True  # Ctrl+R llega como '\x12'
        vk = getattr(key, "vk", None)
        if vk is not None and vk in (ord(target.lower()), ord(target.upper())):
            return True
        return False

    def start(self):
        from pynput import keyboard  # import perezoso: solo si hay atajo

        def on_press(key):
            mod = self._normalize_mod(key, keyboard)
            if mod:
                self._mods_down.add(mod)
                return
            if self._mods_needed <= self._mods_down and self._is_main_key(key, keyboard):
                try:
                    self.callback()
                except Exception:
                    pass

        def on_release(key):
            mod = self._normalize_mod(key, keyboard)
            if mod:
                self._mods_down.discard(mod)

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
