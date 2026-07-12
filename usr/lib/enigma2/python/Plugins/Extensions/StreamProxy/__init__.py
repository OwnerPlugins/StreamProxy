# -*- coding: utf-8 -*-

from __future__ import absolute_import
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from Components.Language import language
import gettext
import os
import traceback

# try:
# from Crypto.Cipher import AES
# CRYPTO_AVAILABLE = True
# except ImportError:
# CRYPTO_AVAILABLE = False

print("[StreamProxy] Plugin init")

__license__ = "GPL-v2"
__version__ = "1.3_20260712"


PluginLanguageDomain = "streamproxy"
PluginLanguagePath = "Extensions/StreamProxy/locale"


def localeInit():
    lang = language.getLanguage()[:2]  # es. "it", "en"
    os.environ["LANGUAGE"] = lang
    gettext.bindtextdomain(
        PluginLanguageDomain,
        resolveFilename(
            SCOPE_PLUGINS,
            PluginLanguagePath))


def _(txt):
    return gettext.dgettext(PluginLanguageDomain, txt) if txt else ""


localeInit()
language.addCallback(localeInit)

PLUGIN_PATH = "/usr/lib/enigma2/python/Plugins/Extensions/StreamProxy"


def get_screen_resolution():
    """Get the current screen resolution."""
    print("[StreamProxy DEBUG] get_screen_resolution START")
    from enigma import getDesktop
    try:
        s = getDesktop(0).size()
        width, height = s.width(), s.height()
        print("[StreamProxy DEBUG] Resolution: {}x{}".format(width, height))
        return (width, height)
    except Exception as e:
        print("[StreamProxy DEBUG] get_screen_resolution ERROR: {}".format(e))
        return (1920, 1080)


def get_resolution_type():
    """Determine the resolution type based on screen width."""
    print("[StreamProxy DEBUG] get_resolution_type START")
    try:
        width = get_screen_resolution()[0]
        if width >= 3840:
            res = "uhd"
        elif width >= 2560:
            res = "wqhd"
        elif width >= 1920:
            res = "fhd"
        elif width >= 1280:
            res = "hd"
        else:
            res = "sd"
        print("[StreamProxy DEBUG] Resolution type: {}".format(res))
        return res
    except Exception as e:
        print("[StreamProxy DEBUG] get_resolution_type ERROR: {}".format(e))
        return "hd"


def load_skin(screen_name):
    """Load a skin file for the given screen name based on current resolution."""
    print("[StreamProxy DEBUG] load_skin START: {}".format(screen_name))
    try:
        res = get_resolution_type()
        skin_path = "{}/skins/{}/{}.xml".format(PLUGIN_PATH, res, screen_name)
        print("[StreamProxy DEBUG] Looking for skin: {}".format(skin_path))

        if not os.path.exists(skin_path):
            skin_path = "{}/skins/hd/{}.xml".format(PLUGIN_PATH, screen_name)
            print("[StreamProxy DEBUG] Fallback to: {}".format(skin_path))

        if os.path.exists(skin_path):
            with open(skin_path, "r") as f:
                content = f.read()
                print(
                    "[StreamProxy DEBUG] Skin loaded, size: {} bytes".format(
                        len(content)))
                return content
        else:
            print("[StreamProxy DEBUG] Skin file NOT FOUND")
            return None
    except Exception as e:
        print("[StreamProxy DEBUG] load_skin ERROR: {}".format(e))
        print("[StreamProxy DEBUG] Traceback: {}".format(traceback.format_exc()))
        return None

