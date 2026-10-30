"""
scripts/record_demo_video.py
Automated Playwright script to record a complete backup demo video of DisruptionIQ.
Outputs a .webm video to demo_videos/disruptioniq_demo_backup.webm.
"""
import os
import sys
import time
import socket
import shutil
import subprocess
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 20.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.5)
    return False


def main():
    print("=" * 70)
    print(" DISRUPTIONIQ: RECORDING BACKUP DEMO VIDEO")
    print("=" * 70)

    demo_dir = PROJECT_ROOT / "demo_videos"
    demo_dir.mkdir(parents=True, exist_ok=True)
    temp_video_dir = demo_dir / "raw_capture"
    if temp_video_dir.exists():
        shutil.rmtree(temp_video_dir)
    temp_video_dir.mkdir(parents=True, exist_ok=True)

    # 1. Start backend server
    print("[1/5] Launching backend FastAPI server on port 8000...")
    env = os.environ.copy()
    env["DEMO_MODE"] = "true"
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 2. Start frontend static server on port 5173
    print("[2/5] Launching frontend server on port 5173...")
    frontend_dist = PROJECT_ROOT / "frontend" / "dist"
    frontend_proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", "5173", "--directory", str(frontend_dist)],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        if not wait_for_port(8000):
            raise RuntimeError("Backend server failed to bind to port 8000")
        if not wait_for_port(5173):
            raise RuntimeError("Frontend server failed to bind to port 5173")
        print("[OK] Both servers responding.")

        # 3. Launch Playwright
        print("[3/5] Starting Playwright Chromium with video recording...")
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                record_video_dir=str(temp_video_dir),
                record_video_size={"width": 1280, "height": 720},
                viewport={"width": 1280, "height": 720},
            )
            page = context.new_page()

            # Step 1: Login
            print("  -> Step 1: Navigating to DisruptionIQ portal...")
            page.goto("http://localhost:5173", wait_until="networkidle")
            page.wait_for_timeout(1500)

            # Fill login form if login screen appears
            username_input = page.locator("input[type='text'], input[placeholder*='User'], input[name='username']")
            if username_input.count() > 0:
                print("  -> Authenticating as Administrator (admin)...")
                username_input.first.fill("admin")
                page.wait_for_timeout(500)
                page.locator("input[type='password']").first.fill("admin123")
                page.wait_for_timeout(500)
                page.locator("button[type='submit'], button:has-text('Sign In'), button:has-text('Login')").first.click()
                page.wait_for_timeout(2000)

            # Step 2: Demo Bar Reset
            print("  -> Step 2: Exercising Demo Bar Reset...")
            reset_btn = page.locator("button:has-text('Reset')")
            if reset_btn.count() > 0:
                reset_btn.first.click()
                page.wait_for_timeout(2500)

            # Step 3: Open Live Event Feed
            print("  -> Step 3: Inspecting Live Event Feed...")
            feed_btn = page.locator("button:has-text('Live Events')")
            if feed_btn.count() > 0:
                feed_btn.first.click()
                page.wait_for_timeout(2500)
                # Close drawer
                close_btn = page.locator("button:has-text('✕'), button:has-text('Close')")
                if close_btn.count() > 0:
                    close_btn.first.click()
                    page.wait_for_timeout(1000)

            # Step 4: Run Scenario 1
            print("  -> Step 4: Triggering Scenario 1 (Supplier Inbound Delay)...")
            scen1_btn = page.locator("button:has-text('Run Scenario 1')")
            if scen1_btn.count() > 0:
                scen1_btn.first.click()
                page.wait_for_timeout(3500)

            # Step 5: Natural Language Search Query
            print("  -> Step 5: Testing Natural Language Query Filter...")
            search_input = page.locator("input[placeholder*='hospital'], input[placeholder*='query'], input[placeholder*='Search']")
            if search_input.count() > 0:
                search_input.first.fill("Which hospital orders are at risk this week?")
                page.wait_for_timeout(1000)
                search_btn = page.locator("button:has-text('Search'), button:has-text('Query')")
                if search_btn.count() > 0:
                    search_btn.first.click()
                    page.wait_for_timeout(2500)

            # Step 6: Disruption Inspection & Cascade Map
            print("  -> Step 6: Inspecting Disruption Profile & Risk Breakdown...")
            disr_row = page.locator("tr:has-text('SH-001'), tr:has-text('SUPPLIER_DELAY'), div:has-text('SH-001')")
            if disr_row.count() > 0:
                disr_row.first.click()
                page.wait_for_timeout(2500)
                # Scroll smoothly down to reveal Cascade Map and Recovery Options
                page.mouse.wheel(0, 400)
                page.wait_for_timeout(2000)
                page.mouse.wheel(0, 400)
                page.wait_for_timeout(2500)

            # Step 7: Drafts View
            print("  -> Step 7: Viewing Drafted Customer Communications...")
            drafts_nav = page.locator("button:has-text('Drafts'), a:has-text('Drafts')")
            if drafts_nav.count() > 0:
                drafts_nav.first.click()
                page.wait_for_timeout(2500)

            # Step 8: Audit Log View
            print("  -> Step 8: Verifying Append-Only Audit Trail...")
            audit_nav = page.locator("button:has-text('Audit'), a:has-text('Audit')")
            if audit_nav.count() > 0:
                audit_nav.first.click()
                page.wait_for_timeout(2500)

            # Step 9: Return to Dashboard & Run Scenario 2
            print("  -> Step 9: Returning to Dashboard and Triggering Scenario 2...")
            orders_nav = page.locator("button:has-text('Disruptions'), button:has-text('Orders'), a:has-text('Disruptions')")
            if orders_nav.count() > 0:
                orders_nav.first.click()
                page.wait_for_timeout(1500)

            scen2_btn = page.locator("button:has-text('Run Scenario 2')")
            if scen2_btn.count() > 0:
                scen2_btn.first.click()
                page.wait_for_timeout(3500)

            print("  -> Step 10: Final pause for video capture...")
            page.wait_for_timeout(3000)

            context.close()
            browser.close()

        # 4. Locate and rename video
        print("[4/5] Finalizing video file...")
        recorded_files = list(temp_video_dir.glob("*.webm"))
        if recorded_files:
            target_video = demo_dir / "disruptioniq_demo_backup.webm"
            if target_video.exists():
                target_video.unlink()
            shutil.move(str(recorded_files[0]), str(target_video))
            size_mb = target_video.stat().st_size / (1024 * 1024)
            print(f"[OK] Video saved to: {target_video} ({size_mb:.2f} MB)")
        else:
            print("[WARNING] No webm file found in temporary directory.")

    finally:
        # 5. Clean up subprocesses
        print("[5/5] Shutting down background processes...")
        frontend_proc.terminate()
        backend_proc.terminate()
        frontend_proc.wait()
        backend_proc.wait()
        if temp_video_dir.exists():
            shutil.rmtree(temp_video_dir, ignore_errors=True)
        print("[OK] Video recording process completed successfully.")


if __name__ == "__main__":
    main()
