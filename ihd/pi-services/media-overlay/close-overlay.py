#!/usr/bin/env python3
"""Floating close button overlay for media apps."""
import subprocess
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gtk, GtkLayerShell, Gdk

BUTTON_SIZE = 80
MARGIN_RIGHT = 20
MARGIN_TOP = 20


def close_media(_widget):
    subprocess.run(
        ["pkill", "-f", "chromium.*media-browser"],
        check=False,
    )
    Gtk.main_quit()


def main():
    win = Gtk.Window()

    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.TOP)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.TOP, True)
    GtkLayerShell.set_anchor(win, GtkLayerShell.Edge.RIGHT, True)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, MARGIN_TOP)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.RIGHT, MARGIN_RIGHT)
    GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
    GtkLayerShell.set_exclusive_zone(win, 0)

    win.set_default_size(BUTTON_SIZE, BUTTON_SIZE)

    css = Gtk.CssProvider()
    css.load_from_data(b"""
        window {
            background: transparent;
        }
        button {
            background: #222222;
            border: 3px solid #ffffff;
            border-radius: 40px;
            color: white;
            font-size: 32px;
            font-weight: bold;
            min-width: 74px;
            min-height: 74px;
            padding: 0;
        }
        button:hover, button:active {
            background: #e50914;
            border-color: #e50914;
        }
    """)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

    btn = Gtk.Button(label="\u2715")
    btn.connect("clicked", close_media)
    win.add(btn)

    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
