"""
Structural validation tests for the Chrome extension.
Verifies file structure, manifest validity, and code correctness.
Cannot test actual Chrome APIs without a browser, but validates everything else.
"""

import json
import os

EXTENSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extension")


def test_manifest_is_valid_json():
    with open(os.path.join(EXTENSION_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    assert manifest["manifest_version"] == 3
    assert manifest["name"] == "ContextHub"
    assert "version" in manifest


def test_manifest_permissions():
    with open(os.path.join(EXTENSION_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    assert "activeTab" in manifest["permissions"]
    assert "storage" in manifest["permissions"]
    assert "clipboardWrite" in manifest["permissions"]


def test_manifest_host_permissions():
    with open(os.path.join(EXTENSION_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    assert "https://claude.ai/*" in manifest["host_permissions"]


def test_manifest_content_scripts():
    with open(os.path.join(EXTENSION_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    cs = manifest["content_scripts"]
    assert len(cs) == 2
    assert "https://claude.ai/*" in cs[0]["matches"]
    assert "content-scripts/claude.js" in cs[0]["js"]


def test_manifest_background():
    with open(os.path.join(EXTENSION_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    assert manifest["background"]["service_worker"] == "background.js"


def test_manifest_action():
    with open(os.path.join(EXTENSION_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    action = manifest["action"]
    assert action["default_popup"] == "popup/popup.html"
    assert "16" in action["default_icon"]
    assert "48" in action["default_icon"]
    assert "128" in action["default_icon"]


def test_all_referenced_files_exist():
    with open(os.path.join(EXTENSION_DIR, "manifest.json")) as f:
        manifest = json.load(f)

    # Content scripts
    for cs in manifest["content_scripts"]:
        for js_file in cs["js"]:
            assert os.path.exists(os.path.join(EXTENSION_DIR, js_file)), f"Missing: {js_file}"

    # Background
    bg = manifest["background"]["service_worker"]
    assert os.path.exists(os.path.join(EXTENSION_DIR, bg)), f"Missing: {bg}"

    # Popup
    popup = manifest["action"]["default_popup"]
    assert os.path.exists(os.path.join(EXTENSION_DIR, popup)), f"Missing: {popup}"

    # Icons
    for size, path in manifest["action"]["default_icon"].items():
        assert os.path.exists(os.path.join(EXTENSION_DIR, path)), f"Missing icon: {path}"


def test_icon_files_are_png():
    for size in [16, 48, 128]:
        path = os.path.join(EXTENSION_DIR, f"icons/icon{size}.png")
        with open(path, "rb") as f:
            header = f.read(8)
        # PNG magic bytes
        assert header[:4] == b"\x89PNG", f"icon{size}.png is not a valid PNG"


def test_background_js_has_api_base():
    with open(os.path.join(EXTENSION_DIR, "background.js")) as f:
        content = f.read()
    assert "http://localhost:8001" in content
    assert "api/threads" in content


def test_background_js_handles_push():
    with open(os.path.join(EXTENSION_DIR, "background.js")) as f:
        content = f.read()
    assert '"push"' in content
    assert "POST" in content


def test_background_js_handles_get_recent():
    with open(os.path.join(EXTENSION_DIR, "background.js")) as f:
        content = f.read()
    assert '"get_recent"' in content
    assert "limit=5" in content


def test_background_js_handles_get_context():
    with open(os.path.join(EXTENSION_DIR, "background.js")) as f:
        content = f.read()
    assert '"get_context"' in content
    assert "/context" in content
    assert "/pull" in content


def test_content_script_has_scrape_function():
    with open(os.path.join(EXTENSION_DIR, "content-scripts/claude.js")) as f:
        content = f.read()
    assert "function scrapeConversation" in content
    assert "chrome.runtime.onMessage" in content
    assert '"scrape"' in content


def test_content_script_has_api_strategy():
    """Content script should use Claude's internal API as primary strategy."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/claude.js")) as f:
        content = f.read()
    assert "scrapeViaAPI" in content
    assert "getOrganizationId" in content
    assert "extractMessagesFromTree" in content
    assert "/api/organizations" in content
    assert "chat_conversations" in content
    assert "credentials" in content


def test_content_script_has_dom_fallback():
    """Content script should fall back to DOM scraping if API fails."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/claude.js")) as f:
        content = f.read()
    assert "scrapeViaDOM" in content
    assert "data-testid" in content
    assert '"user"' in content
    assert '"assistant"' in content


def test_content_script_has_role_detection():
    with open(os.path.join(EXTENSION_DIR, "content-scripts/claude.js")) as f:
        content = f.read()
    assert '"human"' in content
    assert '"user"' in content
    assert '"assistant"' in content


def test_content_script_has_two_strategies():
    with open(os.path.join(EXTENSION_DIR, "content-scripts/claude.js")) as f:
        content = f.read()
    assert "STRATEGY 1" in content
    assert "STRATEGY 2" in content


def test_popup_html_structure():
    with open(os.path.join(EXTENSION_DIR, "popup/popup.html")) as f:
        content = f.read()
    assert "push-btn" in content
    assert "recent-list" in content
    assert "dashboard-link" in content
    assert "popup.css" in content
    assert "popup.js" in content


def test_popup_js_has_push_handler():
    with open(os.path.join(EXTENSION_DIR, "popup/popup.js")) as f:
        content = f.read()
    assert "push-btn" in content
    assert "scrape" in content
    assert "Pushing..." in content
    assert "Pushed!" in content


def test_popup_js_has_recent_loader():
    with open(os.path.join(EXTENSION_DIR, "popup/popup.js")) as f:
        content = f.read()
    assert "loadRecent" in content
    assert "get_recent" in content


def test_popup_js_has_copy_handler():
    with open(os.path.join(EXTENSION_DIR, "popup/popup.js")) as f:
        content = f.read()
    assert "get_context" in content
    assert "clipboard" in content
    assert "Copied!" in content


def test_popup_js_has_time_ago():
    with open(os.path.join(EXTENSION_DIR, "popup/popup.js")) as f:
        content = f.read()
    assert "function timeAgo" in content
    assert "just now" in content


def test_popup_js_has_dashboard_link():
    with open(os.path.join(EXTENSION_DIR, "popup/popup.js")) as f:
        content = f.read()
    assert "localhost:3000" in content


def test_popup_css_has_required_styles():
    with open(os.path.join(EXTENSION_DIR, "popup/popup.css")) as f:
        content = f.read()
    assert "380px" in content
    assert "500px" in content
    assert ".push-btn" in content
    assert ".context-card" in content
    assert ".pushing" in content
    assert ".success" in content
    assert ".error" in content


# ============================================================
# Pull into Chat tests
# ============================================================


def test_popup_js_has_pull_handler():
    """Popup JS should have a pull button handler that injects context."""
    with open(os.path.join(EXTENSION_DIR, "popup/popup.js")) as f:
        content = f.read()
    assert "pull-btn" in content
    assert "inject_context" in content
    assert "Injected" in content


def test_popup_has_pull_button():
    """Popup JS should render a Pull into Chat button with card-actions wrapper."""
    with open(os.path.join(EXTENSION_DIR, "popup/popup.js")) as f:
        content = f.read()
    assert "pull-btn" in content
    assert "card-actions" in content


def test_content_script_has_inject_handler():
    """Content script should handle inject_context action with send."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/claude.js")) as f:
        content = f.read()
    assert "inject_context" in content
    assert "injectIntoInput" in content
    assert "findInputField" in content
    assert "findSendButton" in content
    assert "injectAndSend" in content


def test_content_script_has_prosemirror_selectors():
    """Content script should try ProseMirror, contenteditable, and send-button selectors."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/claude.js")) as f:
        content = f.read()
    assert "ProseMirror" in content
    assert "contenteditable" in content
    assert "composer-input" in content
    assert "send-button" in content


def test_popup_css_has_pull_btn_styles():
    """Popup CSS should have styles for pull button and its states."""
    with open(os.path.join(EXTENSION_DIR, "popup/popup.css")) as f:
        content = f.read()
    assert ".pull-btn" in content
    assert ".pulling" in content
    assert ".sent" in content
    assert ".pull-error" in content
    assert ".card-actions" in content


# ============================================================
# Pull into Memory tests
# ============================================================


def test_content_script_has_memory_handler():
    """Content script should handle inject_memory action with memory write functions."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/claude.js")) as f:
        content = f.read()
    assert "inject_memory" in content
    assert "writeMemoryItems" in content
    assert "clearContextHubMemories" in content


def test_background_js_handles_memory():
    """Background JS should handle get_thread_for_memory action."""
    with open(os.path.join(EXTENSION_DIR, "background.js")) as f:
        content = f.read()
    assert '"get_thread_for_memory"' in content
    assert "key_takeaways" in content
    assert "open_threads" in content


def test_popup_js_has_memory_handler():
    """Popup JS should have a memory button handler that saves to Claude memory."""
    with open(os.path.join(EXTENSION_DIR, "popup/popup.js")) as f:
        content = f.read()
    assert "memory-btn" in content
    assert "inject_memory" in content
    assert "Saved to Memory!" in content


def test_popup_css_has_memory_btn_styles():
    """Popup CSS should have styles for memory button and its states."""
    with open(os.path.join(EXTENSION_DIR, "popup/popup.css")) as f:
        content = f.read()
    assert ".memory-btn" in content
    assert ".saving" in content
    assert ".memorized" in content
    assert ".memory-error" in content


# ============================================================
# ChatGPT Support tests
# ============================================================


def test_manifest_has_chatgpt_host_permission():
    """Manifest should include chatgpt.com in host_permissions."""
    with open(os.path.join(EXTENSION_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    assert "https://chatgpt.com/*" in manifest["host_permissions"]


def test_manifest_has_chatgpt_content_script():
    """Manifest should register chatgpt.js for chatgpt.com."""
    with open(os.path.join(EXTENSION_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    cs = manifest["content_scripts"]
    chatgpt_entries = [c for c in cs if "https://chatgpt.com/*" in c["matches"]]
    assert len(chatgpt_entries) == 1
    assert "content-scripts/chatgpt.js" in chatgpt_entries[0]["js"]


def test_chatgpt_content_script_exists():
    """ChatGPT content script file should exist."""
    assert os.path.exists(os.path.join(EXTENSION_DIR, "content-scripts/chatgpt.js"))


def test_chatgpt_content_script_has_scrape_function():
    """ChatGPT content script should have scrape function and message listener."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/chatgpt.js")) as f:
        content = f.read()
    assert "scrapeConversation" in content
    assert "chrome.runtime.onMessage" in content
    assert '"scrape"' in content


def test_chatgpt_content_script_has_api_strategy():
    """ChatGPT content script should use ChatGPT's backend API as primary strategy."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/chatgpt.js")) as f:
        content = f.read()
    assert "scrapeViaAPI" in content
    assert "backend-api/conversation" in content
    assert "current_node" in content
    assert "mapping" in content


def test_chatgpt_content_script_has_dom_fallback():
    """ChatGPT content script should fall back to DOM scraping with ChatGPT selectors."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/chatgpt.js")) as f:
        content = f.read()
    assert "scrapeViaDOM" in content
    assert "data-message-author-role" in content


def test_chatgpt_content_script_returns_chatgpt_source():
    """ChatGPT content script should return 'chatgpt' as source."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/chatgpt.js")) as f:
        content = f.read()
    assert '"chatgpt"' in content


def test_chatgpt_content_script_has_inject_handler():
    """ChatGPT content script should handle inject_context with input injection."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/chatgpt.js")) as f:
        content = f.read()
    assert "inject_context" in content
    assert "injectIntoInput" in content
    assert "findInputField" in content
    assert "findSendButton" in content
    assert "injectAndSend" in content


def test_chatgpt_content_script_has_chatgpt_selectors():
    """ChatGPT content script should use ChatGPT-specific input selectors."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/chatgpt.js")) as f:
        content = f.read()
    assert "prompt-textarea" in content
    assert "contenteditable" in content


def test_chatgpt_content_script_has_memory_handler():
    """ChatGPT content script should handle inject_memory with ChatGPT memory API."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/chatgpt.js")) as f:
        content = f.read()
    assert "inject_memory" in content
    assert "writeMemoryItems" in content
    assert "clearContextHubMemories" in content
    assert "backend-api/memories" in content


def test_chatgpt_content_script_has_url_pattern():
    """ChatGPT content script should check for /c/ URL pattern."""
    with open(os.path.join(EXTENSION_DIR, "content-scripts/chatgpt.js")) as f:
        content = f.read()
    assert "/c/" in content


def test_popup_supports_chatgpt():
    """Popup JS should reference chatgpt.com for site detection."""
    with open(os.path.join(EXTENSION_DIR, "popup/popup.js")) as f:
        content = f.read()
    assert "chatgpt.com" in content


def test_popup_has_site_detection():
    """Popup JS should detect both claude.ai and chatgpt.com."""
    with open(os.path.join(EXTENSION_DIR, "popup/popup.js")) as f:
        content = f.read()
    assert "claude.ai" in content
    assert "chatgpt.com" in content
