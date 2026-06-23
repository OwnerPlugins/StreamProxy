# ServiceMonitor.py - Fix posizionamento lista canali al primo accesso (E2/Py3)
from enigma import eServiceReference, eTimer
from Screens.ChannelSelection import ChannelSelection
from urllib.parse import quote, unquote
import os
import json

try:
    from .StreamProxyLog import enhanced_log
except Exception:
    def enhanced_log(msg, level="DEBUG", tag="ServiceMonitor"):
        print("[%s][%s] %s" % (tag, level, msg))


# Import TVTap WMS Manager
try:
    from .tvtap_wms_manager import (
        tvtap_wms_manager,
        is_wms_tvtap_url,
        resolve_wms_tvtap_url,
        get_wms_proxy_url
    )
    TVTAP_WMS_AVAILABLE = True
    enhanced_log("✅ TVTap WMS Manager disponibile", "INFO", "ServiceMonitor")
except ImportError as e:
    TVTAP_WMS_AVAILABLE = False
    enhanced_log(
        f"⚠️ TVTap WMS Manager non disponibile: {e}",
        "WARNING",
        "ServiceMonitor")

# Import Freeshot Extractor
try:
    from .extractor.freeshot_extractor import freeshot_extractor, is_freeshot_link
    FREESHOT_AVAILABLE = True
    enhanced_log("✅ Freeshot Extractor disponibile", "INFO", "ServiceMonitor")
except ImportError as e:
    FREESHOT_AVAILABLE = False

    def is_freeshot_link(*args, **kwargs):
        return False
    enhanced_log(
        f"⚠️ Freeshot Extractor non disponibile: {e}",
        "WARNING",
        "ServiceMonitor")
# Import Sport99 Extractor
try:
    from .extractor.sport99_extractor import is_sport99_link
    SPORT99_AVAILABLE = True
    enhanced_log("Sport99 Extractor disponibile", "INFO", "ServiceMonitor")
except ImportError as e:
    SPORT99_AVAILABLE = False

    def is_sport99_link(*args, **kwargs):
        return False
    enhanced_log(
        f"Sport99 Extractor non disponibile: {e}",
        "WARNING",
        "ServiceMonitor")


class StreamProxyServiceMonitor:
    """
    Monitora i servizi e forza la selezione del canale corretto
    anche al primo accesso alla ChannelSelection quando si usano servizi proxati.
    """

    PROXY_PATTERNS = ("127.0.0.1:7860", "proxy%2Fm3u", "proxy/m3u")

    def __init__(self, session):
        self.session = session
        self.config_file = os.path.join(
            os.path.dirname(__file__), "SPconfig.txt")

        self.proxy_active = False
        self.last_original_ref = None
        self._orig_playService = None
        self._orig_getters = {}
        self._playservice_signature = None  # Cache per la signature del metodo

        self._hook_navigation()
        self._hook_channelselection()
        enhanced_log("✅ ServiceMonitor inizializzato", "INFO")

    def _hook_channelselection(self):
        """Installa gli hook necessari per la gestione della lista canali."""
        if getattr(ChannelSelection, "_sp_patched", False):
            return

        try:
            # Hook principale: showAllServices (sempre presente in Enigma2)
            orig_show = ChannelSelection.showAllServices

            def _show_wrap(inst, *a, **kw):
                ret = orig_show(inst, *a, **kw)
                try:
                    if self.proxy_active and self.last_original_ref:
                        # Primo timer per il caricamento iniziale
                        timer1 = eTimer()
                        timer1.callback.append(
                            lambda: self._fix_url_channel_selection(inst))
                        timer1.start(50, True)

                        # Secondo timer per assicurarsi che la selezione sia
                        # corretta
                        timer2 = eTimer()
                        timer2.callback.append(
                            lambda: self._fix_url_channel_selection(inst))
                        timer2.start(300, True)
                except Exception as e:
                    enhanced_log(
                        f"Errore hook showAllServices: {e}",
                        "DEBUG",
                        "ServiceMonitor")
                return ret

            ChannelSelection.showAllServices = _show_wrap

            # Hook opzionali per maggiore compatibilità
            for method_name in ['showFavourites', 'pathChanged']:
                if hasattr(ChannelSelection, method_name):
                    orig_method = getattr(ChannelSelection, method_name)

                    def _make_method_wrap(method, name):
                        def _method_wrap(inst, *a, **kw):
                            ret = method(inst, *a, **kw)
                            try:
                                if self.proxy_active and self.last_original_ref:
                                    timer = eTimer()
                                    timer.callback.append(
                                        lambda: self._fix_url_channel_selection(inst))
                                    timer.start(100, True)
                            except Exception as e:
                                enhanced_log(
                                    f"Errore hook {name}: {e}", "DEBUG", "ServiceMonitor")
                            return ret
                        return _method_wrap

                    setattr(
                        ChannelSelection,
                        method_name,
                        _make_method_wrap(
                            orig_method,
                            method_name))
                    enhanced_log(f"✅ Hook aggiunto per {method_name}", "DEBUG")

            ChannelSelection._sp_patched = True
            enhanced_log(
                "✅ Hook ChannelSelection installati correttamente",
                "INFO")

        except Exception as e:
            enhanced_log(
                f"❌ Errore installazione hook ChannelSelection: {e}",
                "ERROR")

    def _fix_url_channel_selection(self, inst):
        """Fix specifico per canali URL/IPTV con proxy attivo e ottimizzato per Enigma2."""
        try:
            if not hasattr(inst, "servicelist"):
                return

            servicelist = inst.servicelist
            if not servicelist:
                return

            # Ottieni il riferimento attualmente in riproduzione
            current_proxy_ref = self.session.nav.getCurrentlyPlayingServiceReference()
            if not current_proxy_ref:
                return

            current_selection = inst.getCurrentSelection()

            # Verifica se siamo nel caso di primo accesso con proxy attivo
            is_first_access = (self.proxy_active and
                               self.last_original_ref and
                               current_selection and
                               servicelist.getCurrentIndex() == 0)

            if is_first_access:
                enhanced_log(
                    "🔍 Rilevato primo accesso con proxy attivo", "DEBUG")

                try:
                    # Usa eServiceCenter per una ricerca più accurata
                    from enigma import eServiceCenter
                    serviceHandler = eServiceCenter.getInstance()

                    root = servicelist.getRoot()
                    if root:
                        services = serviceHandler.list(root)
                        if services:
                            # Prima cerca il riferimento originale
                            original_ref_str = self.last_original_ref.toString()
                            current_proxy_str = current_proxy_ref.toString()

                            # Salva l'indice corrente
                            start_pos = servicelist.getCurrentIndex()

                            # Cerca entrambi i riferimenti
                            servicelist.moveToFirst()
                            found = False

                            while True:
                                service = servicelist.getCurrent()
                                if service:
                                    service_str = service.toString()
                                    if service_str == original_ref_str:
                                        enhanced_log(
                                            "✅ Trovato riferimento originale", "DEBUG")
                                        found = True
                                        break
                                    elif service_str == current_proxy_str:
                                        enhanced_log(
                                            "✅ Trovato riferimento proxy", "DEBUG")
                                        found = True
                                        break

                                if not servicelist.moveToNext():
                                    break

                            if found:
                                # Aspetta un momento per assicurarsi che la UI
                                # sia pronta
                                from enigma import eTimer
                                timer = eTimer()

                                def do_select():
                                    service = servicelist.getCurrent()
                                    if service:
                                        inst.setCurrentSelection(service)
                                        servicelist.refresh()
                                        enhanced_log(
                                            "✅ Selezione canale aggiornata", "DEBUG")

                                timer.callback.append(do_select)
                                timer.start(100, True)
                            else:
                                # Se non trovato, torna alla posizione iniziale
                                servicelist.moveToIndex(start_pos)
                                enhanced_log(
                                    "⚠️ Canale non trovato, mantengo posizione corrente", "WARNING")

                except Exception as e:
                    enhanced_log(
                        f"⚠️ Errore durante la ricerca del canale: {e}", "WARNING")

            elif current_selection and current_selection.toString() != current_proxy_ref.toString():
                # Non è il primo accesso, ma la selezione non è corretta
                inst.setCurrentSelection(current_proxy_ref)
                servicelist.refresh()
                enhanced_log("🔄 Aggiornata selezione canale", "DEBUG")

        except Exception as e:
            enhanced_log(f"❌ Errore fix selezione canale: {e}", "ERROR")

    def _hook_navigation(self):
        nav = getattr(self.session, "nav", None)
        if not nav:
            return

        # Hook playService
        if hasattr(nav, "playService") and not self._orig_playService:
            self._orig_playService = nav.playService
            self._detect_playservice_signature()
            nav.playService = self._interceptPlayService
            enhanced_log("🔗 Hook su playService installato", "INFO")

    def _interceptPlayService(
            self,
            ref,
            checkParentalControl=True,
            forceRestart=False,
            adjust=True):
        try:
            if not ref or not hasattr(ref, "toString"):
                return self._call_orig_playService(
                    ref, checkParentalControl, forceRestart, adjust)

            ref_str = ref.toString() or ""
            enhanced_log(
                f"🔍 [SERVICEMONITOR] Intercettato playService: {ref_str}",
                "INFO")

            # GESTIONE URL PROXY DA PLUGIN ESTERNI
            if self._is_proxy_ref_string(ref_str):
                enhanced_log(
                    "🔄 [SERVICEMONITOR] Service already detected as proxied", "DEBUG"
                )

                # Extract original URL from proxy if possible
                original_url = self._extract_original_url_from_proxy(ref_str)
                if original_url:
                    enhanced_log(
                        "🔍 [SERVICEMONITOR] Extracted original URL: " + original_url[:100] + "...",
                        "DEBUG"
                    )
                    # Save reference for UI handling
                    self.last_original_ref = ref
                    self.proxy_active = True

                    # Save channel info
                    parts = ref_str.split(":")
                    channel_name = ":".join(parts[11:]) if len(parts) > 11 else "External Plugin Stream"
                    self._save_channel_info(ref_str, original_url, channel_name)
                else:
                    enhanced_log(
                        "⚠️ [SERVICEMONITOR] External plugin proxy without original URL",
                        "WARNING"
                    )
                    self.proxy_active = True

                return self._call_orig_playService(
                    ref, checkParentalControl, forceRestart
                )

            parts = ref_str.split(":")
            enhanced_log(
                "🔍 [SERVICEMONITOR] Service parts: " + str(len(parts)) + " elements",
                "DEBUG"
            )

            # Gestione riferimenti con #EXTVLCOPT
            url_part = ""
            channel_name = ""

            if len(parts) > 10:
                url_part = parts[10]
                # If part 10 contains #EXTVLCOPT, look for URL in subsequent parts
                if url_part.startswith("#EXTVLCOPT"):
                    enhanced_log(
                        "🔍 [SERVICEMONITOR] Detected #EXTVLCOPT format", "DEBUG"
                    )

                    # Search for URL in following parts (may be in 11, 12, etc.)
                    found_url = False
                    for i in range(11, len(parts)):
                        part = unquote(parts[i])

                        # Check if the part contains a valid URL
                        if part.startswith("http://") or part.startswith("https://"):
                            url_part = parts[i]
                            channel_name = ":".join(parts[i + 1:]) if i + 1 < len(parts) else ""
                            found_url = True

                            enhanced_log(
                                "✅ [SERVICEMONITOR] URL found at part " + str(i),
                                "DEBUG"
                            )
                            break

                    if not found_url:
                        # #EXTVLCOPT reference without URL - IGNORE and continue
                        enhanced_log(
                            "⚠️ [SERVICEMONITOR] #EXTVLCOPT reference without stream URL, ignored",
                            "WARNING"
                        )
                        self._reset_proxy_state()
                        return self._call_orig_playService(
                            ref, checkParentalControl, forceRestart, adjust
                        )
                else:
                    channel_name = ":".join(parts[11:]) if len(parts) > 11 else ""

            enhanced_log(
                "🔍 [SERVICEMONITOR] URL part: " + url_part[:150] + "...",
                "DEBUG"
            )

            enhanced_log(
                "🔍 [SERVICEMONITOR] Channel name: " + channel_name,
                "DEBUG"
            )

            if not url_part:
                self._reset_proxy_state()
                return self._call_orig_playService(
                    ref, checkParentalControl, forceRestart, adjust
                )

            clean_url = unquote(url_part)

            enhanced_log(
                "🔍 [SERVICEMONITOR] Decoded URL: " + clean_url[:150] + "...",
                "INFO"
            )

            # Check if it's already a proxy URL (external plugin) - HANDLE HLS
            if self._is_already_proxy_url(clean_url):
                enhanced_log(
                    "✅ [SERVICEMONITOR] URL already proxied by external plugin",
                    "INFO"
                )

                # Extract original m3u8 URL
                original_url = self._extract_original_url_from_proxy_url(clean_url)
                if original_url:
                    enhanced_log(
                        "🔍 [SERVICEMONITOR] Original m3u8 URL: " + original_url[:100] + "...",
                        "DEBUG"
                    )

                    # CREATE NEW REFERENCE WITH DIRECT M3U8 URL
                    # Proxy will automatically handle HLS streams
                    self.proxy_active = True
                    self.last_original_ref = ref

                    self._save_channel_info(ref_str, original_url, channel_name)

                    # Create reference with original m3u8 URL for HLS handling
                    prefix = ":".join(parts[0:10])
                    safe_name = channel_name or "External Plugin Stream"

                    # Use original m3u8 URL - proxy will intercept it
                    new_service_str = ":".join([
                        prefix,
                        quote(original_url),
                        safe_name
                    ])

                    m3u8_ref = eServiceReference(new_service_str)

                    enhanced_log(
                        "🎬 [SERVICEMONITOR] Created m3u8 reference for HLS handling",
                        "INFO"
                    )

                    return self._call_orig_playService(
                        m3u8_ref,
                        checkParentalControl,
                        forceRestart,
                        adjust
                    )
                else:
                    # Fallback: passthrough if URL extraction fails
                    enhanced_log(
                        "⚠️ [SERVICEMONITOR] Unable to extract URL, passthrough",
                        "WARNING"
                    )

                    self.proxy_active = True
                    self.last_original_ref = ref
                    self._save_channel_info(ref_str, clean_url, channel_name)

                    return self._call_orig_playService(
                        ref,
                        checkParentalControl,
                        forceRestart,
                        adjust
                    )

            if not self._should_proxy(clean_url):
                enhanced_log(
                    "🔄 [SERVICEMONITOR] URL does not require proxy: " + clean_url[:100] + "...",
                    "DEBUG"
                )
                self._reset_proxy_state()
                return self._call_orig_playService(
                    ref, checkParentalControl, forceRestart, adjust
                )

            # Specific log for powerset
            if "powerset" in clean_url.lower():
                enhanced_log(
                    "🎯 [SERVICEMONITOR] POWERSET channel detected: " + clean_url,
                    "INFO"
                )
                enhanced_log(
                    "🎯 [SERVICEMONITOR] Channel name: " + channel_name,
                    "INFO"
                )

            # Clear cache when switching channel to avoid conflicts
            # Special handling for different streaming providers
            url_lower = clean_url.lower()

            # VIX handling (separate audio/video streams)
            if any(vix_domain in url_lower for vix_domain in ['vix', 'vixcloud', 'vixsrc']):
                enhanced_log(
                    "🎯 [SERVICEMONITOR] VIX channel detected: " + clean_url,
                    "INFO"
                )
                enhanced_log(
                    "🧹 [SERVICEMONITOR] Clearing cache for VIX channel switch",
                    "INFO"
                )
                try:
                    # Dynamic import to avoid circular dependencies
                    from .AppCore import clear_stream_cache
                    clear_stream_cache()

                    # Clear TS segment and stream data cache
                    self._clear_ts_cache()
                except Exception as e:
                    enhanced_log(
                        "⚠️ [SERVICEMONITOR] Error clearing VIX cache: " + str(e),
                        "WARNING"
                    )

            # DADDY handling - ONLY local stream cache cleanup (NOT DLHD cache)
            elif any(d in url_lower for d in ['thedaddy', 'daddy', 'dlhd', 'newkso.ru']):
                enhanced_log(
                    "🎯 [SERVICEMONITOR] DADDY channel detected: " + clean_url,
                    "INFO"
                )
                try:
                    # DO NOT clear DLHD cache (too aggressive)
                    # Only clear local stream cache to avoid segment conflicts
                    from .AppCore import clear_stream_cache
                    clear_stream_cache()

                    enhanced_log(
                        "🧹 [SERVICEMONITOR] Local stream cache cleared",
                        "INFO"
                    )
                except Exception as e:
                    enhanced_log(
                        "⚠️ [SERVICEMONITOR] Cache error: " + str(e),
                        "WARNING"
                    )

            # VAVOO handling - aggressive cleanup
            elif 'vavoo' in url_lower:
                enhanced_log(
                    "🎯 [SERVICEMONITOR] VAVOO channel detected: " + clean_url,
                    "INFO"
                )
                try:
                    from .AppCore import (
                        clear_stream_cache,
                        _clear_vavoo_resolved_url_cache,
                        prefetch_vavoo_m3u8
                    )

                    clear_stream_cache()
                    _clear_vavoo_resolved_url_cache("channel switch")

                    # Force Enigma2 cache cleanup
                    self._clear_ts_cache()

                    prefetch_vavoo_m3u8(clean_url)

                    enhanced_log(
                        "🧹 [SERVICEMONITOR] VAVOO caches cleared and prefetch started",
                        "INFO"
                    )
                except Exception as e:
                    enhanced_log(
                        "⚠️ [SERVICEMONITOR] VAVOO cache error: " + str(e),
                        "WARNING"
                    )

            # DLHD handling
            elif 'dlhd' in url_lower:
                enhanced_log(
                    "🎯 [SERVICEMONITOR] DLHD channel detected: " + clean_url,
                    "INFO"
                )
                try:
                    from .AppCore import clear_stream_cache
                    clear_stream_cache()
                except Exception as e:
                    enhanced_log(
                        "⚠️ [SERVICEMONITOR] DLHD cache clearing error: " + str(e),
                        "WARNING"
                    )

            # NEWKSO handling
            elif 'newkso.ru' in url_lower:
                enhanced_log(
                    "🎯 [SERVICEMONITOR] NEWKSO channel detected: " + clean_url,
                    "INFO"
                )
                try:
                    from .AppCore import clear_stream_cache
                    clear_stream_cache()
                except Exception as e:
                    enhanced_log(
                        "⚠️ [SERVICEMONITOR] NEWKSO cache clearing error: " + str(e),
                        "WARNING"
                    )

            # Sport99 / CDNLiveTV handling
            if SPORT99_AVAILABLE and is_sport99_link(clean_url):
                enhanced_log(
                    "[SERVICEMONITOR] Sport99/CDNLiveTV channel detected: " + clean_url,
                    "INFO"
                )
                try:
                    from .AppCore import clear_stream_cache()
                    clear_stream_cache()

                    enhanced_log(
                        "[SERVICEMONITOR] Local stream cache cleared for Sport99",
                        "INFO"
                    )
                except Exception as e:
                    enhanced_log(
                        "[SERVICEMONITOR] Sport99 cache clearing error: " + str(e),
                        "WARNING"
                    )

            # Freeshot handling
            freeshot_proxy_url = None

            try:
                # Freeshot channel handling (popcdn.day)
                if FREESHOT_AVAILABLE and is_freeshot_link(clean_url):
                    enhanced_log(
                        "🎯 [SERVICEMONITOR] Freeshot channel detected: " + channel_name,
                        "INFO"
                    )

                    try:
                        resolved_freeshot = freeshot_extractor.extract(clean_url)

                        if resolved_freeshot and resolved_freeshot.get('resolved_url'):
                            enhanced_log(
                                "✅ [SERVICEMONITOR] Freeshot resolved: " +
                                resolved_freeshot['resolved_url'],
                                "INFO"
                            )

                            enhanced_log(
                                "🔍 [SERVICEMONITOR] Extractor headers: " +
                                str(resolved_freeshot.get('headers', {})),
                                "DEBUG"
                            )

                            # Clear cache for Freeshot (uses fMP4, not TS)
                            try:
                                from .AppCore import clear_stream_cache
                                clear_stream_cache()

                                enhanced_log(
                                    "🧹 [SERVICEMONITOR] Cache cleared for Freeshot (fMP4)",
                                    "INFO"
                                )
                            except Exception as cache_e:
                                enhanced_log(
                                    "⚠️ [SERVICEMONITOR] Freeshot cache error: " + str(cache_e),
                                    "WARNING"
                                )

                            # Create proxy URL with custom headers
                            headers_query = "&".join(
                                [
                                    "h_" + quote(k) + "=" + quote(v)
                                    for k, v in resolved_freeshot.get('headers', {}).items()
                                ]
                            )

                            freeshot_proxy_url = (
                                "http://127.0.0.1:7860/proxy/m3u?url="
                                + quote(resolved_freeshot['resolved_url'])
                                + "&"
                                + headers_query
                            )

                            enhanced_log(
                                "✅ [SERVICEMONITOR] Freeshot proxy URL created (fMP4 support)",
                                "INFO"
                            )

                            enhanced_log(
                                "🔍 [SERVICEMONITOR] Full proxy URL: " + freeshot_proxy_url,
                                "DEBUG"
                            )

                    except Exception as e:
                        enhanced_log(
                            "❌ [SERVICEMONITOR] Freeshot resolution error: " + str(e),
                            "ERROR"
                        )
                        freeshot_proxy_url = None

            except Exception as e:
                enhanced_log(
                    "❌ [SERVICEMONITOR] Freeshot handling error: " + str(e),
                    "ERROR"
                )
                freeshot_proxy_url = None

         # TVTap handling
        tvtap_proxy_url = None

        try:
            # TVTap WMS channels (stream.mardio.link with wmsAuthSign)
            if TVTAP_WMS_AVAILABLE and is_wms_tvtap_url(clean_url):
                enhanced_log(
                    "🎯 [SERVICEMONITOR] TVTap WMS channel detected: " + channel_name,
                    "INFO"
                )

                tvtap_proxy_url = get_wms_proxy_url(clean_url, channel_name)

                if tvtap_proxy_url:
                    enhanced_log(
                        "✅ [SERVICEMONITOR] TVTap WMS URL resolved",
                        "INFO"
                    )

                    resolved_data = resolve_wms_tvtap_url(clean_url, channel_name)

                    if resolved_data and resolved_data.get('decoded_info'):
                        valid_minutes = resolved_data['decoded_info'].get('valid_minutes', 'N/A')

                        enhanced_log(
                            "🔑 [SERVICEMONITOR] wmsAuthSign valid for: " +
                            str(valid_minutes) +
                            " minutes",
                            "DEBUG"
                        )

            # Standard TVTap handling
            elif any(pattern in clean_url.lower() for pattern in ['tvtap', 'rocktalk.net', 'taptube.net', 'authsign=']):
                enhanced_log(
                    "🎯 [SERVICEMONITOR] Standard TVTap URL detected: " + clean_url,
                    "INFO"
                )

                tvtap_proxy_url = (
                    "http://127.0.0.1:7860/proxy/m3u?url=" + quote(clean_url)
                )

                enhanced_log(
                    "✅ [SERVICEMONITOR] TVTap URL configured",
                    "INFO"
                )

        except Exception as e:
            enhanced_log(
                "❌ [SERVICEMONITOR] TVTap handling error: " + str(e),
                "ERROR"
            )
            tvtap_proxy_url = None


        # Save original ref
        self.last_original_ref = ref
        self.proxy_active = True
        self._save_channel_info(ref_str, clean_url, channel_name)

        # Use resolved Freeshot URL if available, otherwise TVTap, otherwise determine proxy type
        if freeshot_proxy_url:
            proxy_url = freeshot_proxy_url
            enhanced_log(
                "✅ [SERVICEMONITOR] Using Freeshot proxy URL: " + proxy_url[:100] + "...",
                "INFO"
            )

        elif tvtap_proxy_url:
            proxy_url = tvtap_proxy_url
            enhanced_log(
                "✅ [SERVICEMONITOR] Using TVTap proxy URL: " + proxy_url,
                "INFO"
            )

        else:
            # Determine proxy type
            url_lower = clean_url.lower()

            if (
                url_lower.endswith('.mpd')
                or '/dash/' in url_lower
                or 'browser-dash' in url_lower
            ):
                # MPD stream (DASH)
                enhanced_log(
                    "🎬 [SERVICEMONITOR] Creating MPD proxy for: " + clean_url[:50] + "...",
                    "INFO"
                )

                proxy_url = (
                    "http://127.0.0.1:7860/proxy/mpd?url=" + quote(clean_url)
                )

            else:
                # M3U8 (HLS) or other stream
                proxy_url = (
                    "http://127.0.0.1:7860/proxy/m3u?url=" + quote(clean_url)
                )

            enhanced_log(
                "✅ [SERVICEMONITOR] Created proxy URL: " + proxy_url,
                "INFO"
            )


        prefix = ":".join(parts[0:10])
        safe_name = channel_name or "Stream Proxy"

        new_service_str = ":".join([
            prefix,
            quote(proxy_url),
            safe_name
        ])

        proxy_ref = eServiceReference(new_service_str)

        self._set_current_selection_alternative(proxy_ref)

        return self._call_orig_playService(
            proxy_ref,
            checkParentalControl,
            forceRestart,
            adjust
        )

        except Exception as e:
            enhanced_log(
                "❌ interceptPlayService error: " + str(e),
                "ERROR"
            )
            self._reset_proxy_state()

            return self._call_orig_playService(
                ref,
                checkParentalControl,
                forceRestart,
                adjust
            )

    def _detect_playservice_signature(self):
        """Detect playService method signature for Enigma2"""
        if not self._orig_playService:
            return

        try:
            import inspect
            sig = inspect.signature(self._orig_playService)
            param_names = list(sig.parameters.keys())

            self._playservice_signature = 4  # ref, checkParentalControl, forceRestart, adjust

            enhanced_log(
                "✅ [SERVICEMONITOR] Configured for modern Enigma2",
                "INFO"
            )

        except Exception as e:
            enhanced_log(
                "⚠️ [SERVICEMONITOR] Fallback to standard Enigma2 configuration: " + str(e),
                "WARNING"
            )
            self._playservice_signature = 4

    def _call_orig_playService(
            self,
            ref,
            checkParentalControl=True,
            forceRestart=False,
            adjust=True):
        """Call original playService method with multi-distro compatibility"""

        if not self._orig_playService:
            return False

        if self._playservice_signature == 4:
            try:
                return self._orig_playService(
                    ref, checkParentalControl, forceRestart, adjust
                )
            except Exception as e:
                enhanced_log(
                    "❌ [SERVICEMONITOR] Error with signature 4: " + str(e),
                    "ERROR"
                )
                return False

        elif self._playservice_signature == 3:
            try:
                return self._orig_playService(
                    ref, checkParentalControl, forceRestart
                )
            except Exception as e:
                enhanced_log(
                    "❌ [SERVICEMONITOR] Error with signature 3: " + str(e),
                    "ERROR"
                )
                return False

        elif self._playservice_signature == 2:
            try:
                return self._orig_playService(
                    ref, checkParentalControl
                )
            except Exception as e:
                enhanced_log(
                    "❌ [SERVICEMONITOR] Error with signature 2: " + str(e),
                    "ERROR"
                )
                return False

        elif self._playservice_signature == 1:
            try:
                return self._orig_playService(ref)
            except Exception as e:
                enhanced_log(
                    "❌ [SERVICEMONITOR] Error with signature 1: " + str(e),
                    "ERROR"
                )
                return False

        try:
            return self._orig_playService(
                ref, checkParentalControl, forceRestart
            )

        except TypeError as e:
            if "unexpected keyword argument" in str(e):
                try:
                    # Fallback: only ref + checkParentalControl (OpenPLi style)
                    enhanced_log(
                        "🔄 [SERVICEMONITOR] Fallback to playService with 2 parameters",
                        "DEBUG"
                    )

                    self._playservice_signature = 2  # Cache for future calls

                    return self._orig_playService(
                        ref, checkParentalControl
                    )

                except TypeError:
                    try:
                        # Final fallback: only ref (very old versions)
                        enhanced_log(
                            "🔄 [SERVICEMONITOR] Fallback to playService with 1 parameter",
                            "DEBUG"
                        )

                        self._playservice_signature = 1  # Cache for future calls

                        return self._orig_playService(ref)

                    except Exception as final_e:
                        enhanced_log(
                            "❌ [SERVICEMONITOR] All fallbacks failed: " + str(final_e),
                            "ERROR"
                        )
                        return False
            else:
                enhanced_log(
                    "❌ [SERVICEMONITOR] Unhandled playService error: " + str(e),
                    "ERROR"
                )
                return False

        except Exception as e:
            enhanced_log(
                "❌ [SERVICEMONITOR] Generic playService error: " + str(e),
                "ERROR"
            )
            return False

    def _clear_ts_cache(self):
        """Clear TS segments and stream data cache"""
        try:
            # Enigma2 cache cleanup for TS segments
            from enigma import eServiceCenter
            serviceCenter = eServiceCenter.getInstance()

            if hasattr(serviceCenter, 'clearCache'):
                serviceCenter.clearCache()

                enhanced_log(
                    "🧹 [SERVICEMONITOR] Enigma2 cache cleared",
                    "DEBUG"
                )

        except Exception as e:
            enhanced_log(
                "⚠️ [SERVICEMONITOR] TS cache clearing error: " + str(e),
                "DEBUG"
            )


    def _set_current_selection_alternative(self, proxy_ref):
        """Set alternative selection for UI compatibility"""
        try:
            # Find active ChannelSelection
            from Screens.InfoBar import InfoBar

            if InfoBar.instance:
                session = InfoBar.instance.session

                if hasattr(session, 'current_dialog'):
                    current = session.current_dialog

                    if hasattr(current, 'setCurrentSelectionAlternative'):
                        current.setCurrentSelectionAlternative(proxy_ref)

                        enhanced_log(
                            "🎯 [SERVICEMONITOR] setCurrentSelectionAlternative set",
                            "DEBUG"
                        )

        except Exception as e:
            enhanced_log(
                "⚠️ [SERVICEMONITOR] setCurrentSelectionAlternative error: " + str(e),
                "DEBUG"
            )


    def _should_proxy(self, url: str) -> bool:
        """Check if URL requires proxy - ONLY authorized domains"""

        if not url:
            return False

        url_lower = url.lower()
        domain_part = ""

        try:
            if url_lower.startswith("http://") or url_lower.startswith("https://"):
                url_without_protocol = url_lower.split("://", 1)[1]
                domain_part = url_without_protocol.split("/")[0]

        except Exception:
            domain_part = url_lower

        # DOMINI AUTORIZZATI - Solo questi vengono proxati
        authorized_domains = (
            # DaddyLive e derivati
            "daddy", "dlhd", "thedaddy", "daddylive", "newkso.ru",
            # Vavoo
            "vavoo",
            # SportOnline
            "sportzonline", "sportsonline", "sportonline", "sportssonline",
            # Sport99 / CDNLiveTV
            "cdnlivetv.tv", "streamsports99.su", "sports99", "sport99",
            # TVTap
            "tvtap", "rocktalk.net", "taptube.net", "wmsauthsign", "stream.mardio.link",
            # Mixdrop (tutti i mirror)
            "mixdrop.co", "mixdrop.vip", "m1xdrop.bz", "m1xdrop.net", "mixdrop.ch", "mixdrop.ps", "mixdrop.ag", "mxcontent.net",
            # Maxstream/Uprot
            "uprot.net", "maxstream.video", "stayonline.pro",
            # Freeshot
            "popcdn.day", "freeshot://", "freeshot.live", "lovecdn.ru", "planetary.lovecdn.ru", "beautifulpeople.lovecdn.ru"
        )

        # Domini VIX - controllo specifico solo nel dominio
        vix_domains = ("vix", "vixcloud", "vixsrc")

        # Verifica domini VIX solo nella parte del dominio
        if any(vix_domain in domain_part for vix_domain in vix_domains):
            enhanced_log(
                f"✅ [SERVICEMONITOR] Dominio VIX autorizzato rilevato: {
                    [
                        d for d in vix_domains if d in domain_part][0]}",
                "DEBUG")
            return True

        # Verifica altri domini autorizzati nell'intero URL
        if any(domain in url_lower for domain in authorized_domains):
            enhanced_log(
                f"✅ [SERVICEMONITOR] Dominio autorizzato rilevato in URL: {
                    [
                        d for d in authorized_domains if d in url_lower][0]}",
                "DEBUG")
            return True

        # Tutti gli altri URL NON vengono proxati
        enhanced_log(
            f"🔄 [SERVICEMONITOR] URL non autorizzato, passthrough diretto",
            "DEBUG")
        return False

    def _is_proxy_ref_string(self, ref_str: str) -> bool:
        return any(p in (ref_str or "") for p in self.PROXY_PATTERNS)

    def _is_already_proxy_url(self, url: str) -> bool:
        """Verifica se URL è già un proxy URL (da plugin esterno)"""
        if not url:
            return False
        url_lower = url.lower()
        return ("127.0.0.1:7860" in url_lower or
                "localhost:7860" in url_lower) and "/proxy" in url_lower

    def _extract_original_url_from_proxy_url(self, proxy_url: str) -> str:
        """Estrae URL originale da proxy URL (formato: http://127.0.0.1:7860/proxy?url=...)"""
        try:
            if "url=" in proxy_url:
                url_start = proxy_url.find("url=") + 4
                url_end = proxy_url.find("&", url_start)
                if url_end == -1:
                    original_url = proxy_url[url_start:]
                else:
                    original_url = proxy_url[url_start:url_end]
                original_url = unquote(original_url)
                return original_url
            return None
        except Exception as e:
            enhanced_log(
                f"❌ [SERVICEMONITOR] Errore estrazione URL da proxy URL: {e}",
                "ERROR")
            return None

    def _extract_original_url_from_proxy(self, ref_str: str) -> str:
        """Estrae URL originale da riferimento proxy (per plugin esterni)"""
        try:
            # Cerca pattern proxy/m3u?url=...
            if "proxy/m3u?url=" in ref_str or "proxy%2Fm3u?url=" in ref_str:
                # Estrai parte URL
                parts = ref_str.split(":")
                if len(parts) > 10:
                    url_part = parts[10]
                    # Decodifica URL
                    decoded = unquote(url_part)
                    # Cerca parametro url=
                    if "url=" in decoded:
                        url_start = decoded.find("url=") + 4
                        # Estrai fino al prossimo & o fine stringa
                        url_end = decoded.find("&", url_start)
                        if url_end == -1:
                            original_url = decoded[url_start:]
                        else:
                            original_url = decoded[url_start:url_end]
                        # Decodifica ulteriormente se necessario
                        original_url = unquote(original_url)
                        enhanced_log(
                            f"✅ [SERVICEMONITOR] URL estratto da proxy: {original_url[:100]}...", "DEBUG")
                        return original_url
            return None
        except Exception as e:
            enhanced_log(
                f"❌ [SERVICEMONITOR] Errore estrazione URL da proxy: {e}",
                "ERROR")
            return None

    def _force_exteplayer3_for_mpd(self, ref, mpd_url):
        """Forza l'uso di exteplayer3 per stream MPD/DASH"""
        try:
            from enigma import eServiceReference
            mpd_ref_str = ref.toString()
            parts = mpd_ref_str.split(':')
            if len(parts) > 0:
                parts[0] = '5001'
                new_ref_str = ':'.join(parts)
                enhanced_log(
                    f"✅ [SERVICEMONITOR] Riferimento modificato per exteplayer3 (5001)",
                    "INFO")
                return eServiceReference(new_ref_str)
        except Exception as e:
            enhanced_log(
                f"❌ [SERVICEMONITOR] Errore forzatura exteplayer3: {e}",
                "ERROR")
        return ref

    def _reset_proxy_state(self):
        self.proxy_active = False
        self.last_original_ref = None

    def _save_channel_info(
            self,
            service_str: str,
            url: str,
            channel_name: str):
        try:
            cfg = {"last_service_ref": service_str,
                   "last_channel_name": channel_name or "Stream Proxy"}
            tmp = self.config_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.config_file)
        except Exception as e:
            enhanced_log(f"❌ Errore salvataggio config: {e}", "ERROR")

    def cleanup(self):
        nav = getattr(self.session, "nav", None)
        if nav and self._orig_playService:
            nav.playService = self._orig_playService
        for name, fn in self._orig_getters.items():
            if hasattr(nav, name):
                setattr(nav, name, fn)
        self._orig_getters.clear()
        self._orig_playService = None
        self._reset_proxy_state()
        enhanced_log("🧹 Cleanup completato", "INFO")
