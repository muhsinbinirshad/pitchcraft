"""Browser walk-through of every screen (Playwright + system Chrome).

    python tests/ui_smoke.py http://127.0.0.1:8601 admin e2e-password-1 <out_dir> [not-a-proposal.docx]

Signs in, opens each page, checks key elements, saves screenshots and fails
on browser console errors.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main() -> int:
    base, user, pw, out = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
    junk = Path(sys.argv[5]) if len(sys.argv) > 5 else None
    out.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/google-chrome")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

        def shot(name: str) -> None:
            page.wait_for_timeout(600)
            page.screenshot(path=str(out / f"{name}.png"))
            print("shot", name)

        # signed out: any page goes to login
        page.goto(f"{base}/")
        page.wait_for_url("**/login/**")
        expect(page.get_by_role("heading", name="Sign in")).to_be_visible()
        shot("01_login")
        page.get_by_label("Username").fill(user)
        page.get_by_label("Password").fill(pw)
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_url("**/proposals/**")

        expect(page.get_by_role("heading", name="Proposals", exact=True)).to_be_visible()
        page.wait_for_selector(".sq", timeout=20000)
        page.wait_for_timeout(2500)  # thumbnails render on first view
        shot("02_proposals")
        page.locator(".pill-chip").nth(1).click()
        shot("03_proposals_tag_filter")
        page.locator(".pill-chip").first.click()
        page.get_by_label("Status").click()
        shot("03b_status_menu")
        page.keyboard.press("Escape")

        # Ctrl+K search across chats
        page.keyboard.press("Control+k")
        page.wait_for_selector(".sx input")
        page.keyboard.type("scope")
        page.wait_for_selector(".sx-item")
        page.wait_for_timeout(300)
        shot("03d_search")
        page.keyboard.press("Enter")
        page.wait_for_url("**/p/?id=*")

        # workspace
        page.wait_for_selector(".bubble")
        page.wait_for_selector(".pv-page canvas", timeout=180000)
        page.wait_for_timeout(2000)
        shot("04_workspace_document")
        page.locator(".ai-card").first.get_by_role("button", name="Show the").click()
        shot("05_workspace_edits")
        page.locator(".pv-scroll").evaluate("el => el.scrollTo(0, 2600)")
        page.wait_for_timeout(1500)
        shot("06_workspace_page_breaks")
        page.get_by_role("button", name="Checks", exact=True).click()
        shot("07_workspace_checks")
        page.get_by_role("button", name="Versions").click()
        shot("08_workspace_versions")
        page.get_by_role("button", name="Details", exact=True).click()
        shot("09_workspace_details")
        page.get_by_role("button", name="Document", exact=True).click()
        page.get_by_label("Version shown").click()
        shot("10_version_menu")
        page.locator(".sel-opt").last.click()
        page.wait_for_selector(".pv-page canvas", timeout=60000)
        page.wait_for_timeout(1500)
        shot("10b_workspace_v0_original")
        page.get_by_label("Options").click()
        expect(page.get_by_text("Apply automatically")).to_be_visible()
        page.get_by_label("Effort").click()
        shot("11_composer_options_effort")
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Done").click()

        # new proposal: everything lives in the chat box
        page.goto(f"{base}/new/")
        page.wait_for_selector(".cbox textarea")
        shot("12_new_chat")
        page.get_by_title("Choose the template (style) for this proposal").click()
        page.wait_for_selector(".pk")
        shot("13_template_picker")
        page.get_by_role("button", name="Done").click()
        page.get_by_title("Upload a proposal with a different style").click()
        page.wait_for_selector(".ns-drop")
        shot("13b_new_style_dialog")
        if junk:
            with page.expect_file_chooser() as fc:
                page.locator(".ns-drop").click()
            fc.value.set_files(str(junk))
            page.wait_for_selector(".dialog .banner.err", timeout=60000)
            expect(page.get_by_text("can't be used as a template")).to_be_visible()
            shot("14_new_style_rejected")
        page.get_by_role("button", name="Cancel").click()

        for path, name, sel in (("/templates/", "15_templates", ".sq"), ("/settings/", "17_settings", ".st-hero")):
            page.goto(f"{base}{path}")
            page.wait_for_selector(sel)
            shot(name)

        page.goto(f"{base}/templates/")
        page.locator(".sq:not(.sq-add)").first.click()
        page.wait_for_selector(".dialog .pv-page canvas", timeout=60000)
        page.wait_for_timeout(1000)
        shot("18_template_preview")
        page.keyboard.press("Escape")

        # mobile
        m = browser.new_context(viewport={"width": 390, "height": 844}, storage_state=ctx.storage_state())
        mp = m.new_page()
        mp.on("pageerror", lambda e: errors.append(f"mobile pageerror: {e}"))
        mp.goto(f"{base}/proposals/")
        mp.wait_for_selector(".sq")
        mp.wait_for_timeout(1500)
        mp.screenshot(path=str(out / "19_mobile_proposals.png"))
        mp.locator(".sq").first.click()
        mp.wait_for_selector(".bubble")
        mp.wait_for_timeout(800)
        mp.screenshot(path=str(out / "20_mobile_chat.png"))
        mp.get_by_role("button", name="Document", exact=True).click()
        mp.wait_for_selector(".pv-page canvas", timeout=60000)
        mp.wait_for_timeout(800)
        mp.screenshot(path=str(out / "21_mobile_document.png"))
        print("shot mobile x3")

        # sign out
        page.goto(f"{base}/proposals/")
        page.get_by_title("Account").click()
        page.get_by_role("menuitem", name="Sign out").click()
        page.wait_for_url("**/login/**")
        browser.close()

    real = [e for e in errors if "favicon" not in e]
    print("console errors:", len(real))
    for e in real[:20]:
        print("  ", e[:300])
    return 1 if real else 0


if __name__ == "__main__":
    raise SystemExit(main())
