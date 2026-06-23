#!/usr/bin/env python3
# diagnostics.py - Complete diagnostic for StreamProxy system

import sys
import os
import requests
import traceback


def check_server_status():
    """Check HTTP server status"""
    print("HTTP SERVER CHECK")
    print("-" * 40)

    ports_to_check = [7860, 8081, 8088]

    for port in ports_to_check:
        try:
            url = f"http://127.0.0.1:{port}/"
            response = requests.get(url, timeout=2)
            print(f"[OK] Port {port}: ACTIVE (Status: {response.status_code})")

            endpoints = ["/proxy/m3u?test=1", "/proxy/resolve?test=1"]
            for endpoint in endpoints:
                try:
                    test_url = f"http://127.0.0.1:{port}{endpoint}"
                    test_response = requests.get(test_url, timeout=2)
                    print(f"   +-- {endpoint}: {test_response.status_code}")
                except BaseException:
                    print(f"   +-- {endpoint}: [FAIL] NOT RESPONDING")

        except Exception as e:
            print(f"[FAIL] Port {port}: INACTIVE ({str(e)})")

    print()


def check_appcore_integration():
    """Check AppCore integration"""
    print("APPCORE CHECK")
    print("-" * 40)

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)

        from AppCore import service_monitor_callback, AppCore
        print("AppCore imported successfully")

        try:
            result = service_monitor_callback(
                '/proxy/m3u', url='test', test='1')
            print(f"[OK] Callback working: {type(result)}")
        except Exception as e:
            print(f"[FAIL] Callback error: {str(e)}")

        try:
            app = AppCore()
            print("AppCore instance created", str(app))
        except Exception as e:
            print(f"[FAIL] AppCore instance error: {str(e)}")

    except Exception as e:
        print(f"[FAIL] AppCore import error: {str(e)}")
        traceback.print_exc()

    print()


def check_service_monitor():
    """Check ServiceMonitor (simulated)"""
    print("SERVICE MONITOR CHECK")
    print("-" * 40)

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)

        from ServiceMonitor import StreamProxyServiceMonitor
        print("[OK] ServiceMonitor imported successfully")

        methods_to_check = [
            '_proxy_play_service',
            '_ensure_server_running',
            'notify_m3u']
        for method in methods_to_check:
            if hasattr(StreamProxyServiceMonitor, method):
                print(f"[OK] Method {method}: FOUND")
            else:
                print(f"[FAIL] Method {method}: MISSING")

    except Exception as e:
        print(f"[FAIL] ServiceMonitor error: {str(e)}")
        traceback.print_exc()

    print()


def check_pipeline():
    """Check Pipeline"""
    print("PIPELINE CHECK")
    print("-" * 40)

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)

        from Pipeline import Pipeline, process_content
        print("[OK] Pipeline imported successfully")

        pipeline = Pipeline()
        print("[OK] Pipeline instance created", str(pipeline))

        test_content = "#EXTM3U\n#EXTINF:10.0,\ntest.ts\n"
        result = process_content(
            test_content,
            "application/vnd.apple.mpegurl",
            "test_url")
        print(f"[OK] Test processing: {result}")

    except Exception as e:
        print(f"[FAIL] Pipeline error: {str(e)}")
        traceback.print_exc()

    print()


def check_file_structure():
    """Check file structure"""
    print("FILE STRUCTURE CHECK")
    print("-" * 40)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    required_files = [
        'server.py',
        'http_response.py',
        'AppCore.py',
        'ServiceMonitor.py',
        'Pipeline.py',
        'plugin.py',
        'StreamProxyLog.py'
    ]

    for file in required_files:
        file_path = os.path.join(current_dir, file)
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            print(f"[OK] {file}: FOUND ({size} bytes)")
        else:
            print(f"[FAIL] {file}: MISSING")

    print()


def test_url_processing():
    """Test complete URL processing"""
    print("URL PROCESSING TEST")
    print("-" * 40)

    test_urls = [
        "https://vavoo.to/play/875922788/index.m3u8",
        "http://example.com/stream.m3u8",
        "https://daddylive.sx/stream/123.php"
    ]

    for url in test_urls:
        print(f"Test URL: {url}")
        try:
            from urllib.parse import quote
            proxy_url = f"http://127.0.0.1:7860/proxy/m3u?url={quote(url)}"
            print(f"  +-- Proxy URL: {proxy_url[:80]}...")

            try:
                response = requests.get(proxy_url, timeout=5)
                print(f"  +-- Response: {response.status_code}")
            except BaseException:
                print("  +-- Response: [FAIL] Server not responding")

        except Exception as e:
            print(f"  +-- Error: {str(e)}")

    print()


def main():
    """Run all diagnostic checks"""
    print("=" * 50)
    print("STREAMPROXY DIAGNOSTIC")
    print("=" * 50)
    print()

    check_file_structure()
    check_server_status()
    check_appcore_integration()
    check_service_monitor()
    check_pipeline()
    test_url_processing()

    print("=" * 50)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    main()
