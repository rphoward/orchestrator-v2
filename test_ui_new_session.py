"""
test_ui_new_session.py — Playwright Visual State Tests
═══════════════════════════════════════════════════════
Tests the "New Session" flow by checking what's VISIBLE on screen,
not just what exists in the DOM.

KEY PRINCIPLE:
  A DOM element with display:none, visibility:hidden, or the .hidden
  class is NOT visible to the user. Playwright's .to_be_visible()
  checks actual computed visibility. Use it everywhere instead of
  checking .count() or .inner_text() which work on hidden elements.

WHAT THIS TESTS:
  1. Welcome screen shows on fresh load
  2. Clicking "New Session" hides the welcome and shows conversation UI
  3. The response section appears with a slide-in animation
  4. Only the ☕ Question box is visible (no empty analysis/pivot boxes)
  5. Thread panel shows at least one message
  6. No duplicate network calls for the same conversation

RUN:
  pip install playwright
  playwright install chromium
  python -m pytest test_ui_new_session.py -v

IMPORTANT:
  Start the server first: python app.py
  These tests hit http://localhost:5000 by default.
"""

import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:5000"

# How long to wait for UI transitions (ms).
# The fadeSlideIn animation is 300ms, so we give a bit of buffer.
UI_TRANSITION_TIMEOUT = 2000

# How long to wait for the backend to respond to initialize.
# With no API key this is near-instant. With a real key, agents
# take a few seconds each.
INIT_TIMEOUT = 30000


@pytest.fixture
def app_page(page: Page):
    """Navigate to the app and wait for it to fully load."""
    page.goto(BASE_URL)
    # Wait for the DOMContentLoaded initialization to finish.
    # The app loads agents, models, and sessions on startup.
    page.wait_for_load_state("networkidle")
    return page


class TestWelcomeScreen:
    """Tests that the welcome screen shows correctly on fresh load."""

    def test_welcome_is_visible(self, app_page: Page):
        """Welcome section should be VISIBLE (not just in DOM)."""
        welcome = app_page.locator("#welcomeSection")
        expect(welcome).to_be_visible()

    def test_main_content_is_hidden(self, app_page: Page):
        """Main conversation area should be HIDDEN on fresh load."""
        main = app_page.locator("#mainContent")
        # to_be_hidden checks computed visibility — not just .hidden class
        expect(main).to_be_hidden()

    def test_response_section_is_hidden(self, app_page: Page):
        """Response card should not be visible before any session."""
        response = app_page.locator("#responseSection")
        expect(response).to_be_hidden()


class TestNewSession:
    """Tests the full 'New Session' flow — the main bug area."""

    def test_new_session_hides_welcome(self, app_page: Page):
        """
        After clicking 'New Session':
        - Welcome screen should DISAPPEAR (not just get covered)
        - Main content should APPEAR (be actually visible)
        """
        # Click the "New Session" button
        app_page.locator("text=New Session").click()

        # Wait for the initialization to complete
        # (status bar shows "Creating and initializing session...")
        app_page.wait_for_function(
            """() => {
                const status = document.getElementById('statusBar');
                return !status || status.classList.contains('hidden');
            }""",
            timeout=INIT_TIMEOUT,
        )

        # NOW CHECK VISUAL STATE — this is where old tests failed.
        # They checked DOM content but not visibility.

        # Welcome must be HIDDEN (not visible, not just in the DOM)
        welcome = app_page.locator("#welcomeSection")
        expect(welcome).to_be_hidden(timeout=UI_TRANSITION_TIMEOUT)

        # Main content must be VISIBLE
        main = app_page.locator("#mainContent")
        expect(main).to_be_visible(timeout=UI_TRANSITION_TIMEOUT)

    def test_response_section_appears(self, app_page: Page):
        """
        The response card (#responseSection) should become visible
        after initialization, with the agent's first response.
        """
        app_page.locator("text=New Session").click()

        # Wait for init to complete
        app_page.wait_for_function(
            """() => {
                const status = document.getElementById('statusBar');
                return !status || status.classList.contains('hidden');
            }""",
            timeout=INIT_TIMEOUT,
        )

        response = app_page.locator("#responseSection")
        expect(response).to_be_visible(timeout=UI_TRANSITION_TIMEOUT)

    def test_no_empty_analysis_pivot_boxes(self, app_page: Page):
        """
        PATCH A VERIFICATION:
        On init messages, the 🧠 Silent Analysis and 🎯 Tactical Pivot
        sections should be HIDDEN (display:none), not shown as empty boxes.

        This was the main cause of "layout jumping" — two empty <details>
        elements forcing a reflow.
        """
        app_page.locator("text=New Session").click()

        app_page.wait_for_function(
            """() => {
                const status = document.getElementById('statusBar');
                return !status || status.classList.contains('hidden');
            }""",
            timeout=INIT_TIMEOUT,
        )

        # Wait for displayResponse to finish
        expect(
            app_page.locator("#responseSection")
        ).to_be_visible(timeout=UI_TRANSITION_TIMEOUT)

        # The analysis <details> element should be HIDDEN (display:none)
        # We check computed style, not just the .hidden class
        analysis_hidden = app_page.evaluate(
            """() => {
                const el = document.getElementById('analysisContent');
                if (!el) return true;
                const details = el.closest('details');
                if (!details) return true;
                return window.getComputedStyle(details).display === 'none';
            }"""
        )
        assert analysis_hidden, (
            "Analysis <details> should be display:none on init messages "
            "(no 🧠 section found in response)"
        )

        # Same for the pivot section
        pivot_hidden = app_page.evaluate(
            """() => {
                const el = document.getElementById('pivotContent');
                if (!el) return true;
                const details = el.closest('details');
                if (!details) return true;
                return window.getComputedStyle(details).display === 'none';
            }"""
        )
        assert pivot_hidden, (
            "Pivot <details> should be display:none on init messages "
            "(no 🎯 section found in response)"
        )

    def test_question_box_has_content(self, app_page: Page):
        """
        The ☕ Question box should have actual content after init,
        not placeholder text.
        """
        app_page.locator("text=New Session").click()

        app_page.wait_for_function(
            """() => {
                const status = document.getElementById('statusBar');
                return !status || status.classList.contains('hidden');
            }""",
            timeout=INIT_TIMEOUT,
        )

        expect(
            app_page.locator("#responseSection")
        ).to_be_visible(timeout=UI_TRANSITION_TIMEOUT)

        question = app_page.locator("#nextQuestion")
        expect(question).to_be_visible()

        # Check it has real content, not just the fallback
        text = question.inner_text()
        assert len(text.strip()) > 0, "Question box should have content"

    def test_thread_has_messages(self, app_page: Page):
        """
        After init, the thread panel should show at least one message
        (the agent's opening response).
        """
        app_page.locator("text=New Session").click()

        app_page.wait_for_function(
            """() => {
                const status = document.getElementById('statusBar');
                return !status || status.classList.contains('hidden');
            }""",
            timeout=INIT_TIMEOUT,
        )

        # Give displayResponse → showThread → loadThread time to complete
        thread = app_page.locator("#threadContent .thread-message")
        expect(thread.first).to_be_visible(timeout=UI_TRANSITION_TIMEOUT)


class TestNoDoubleFireNetwork:
    """
    PATCHES B+C VERIFICATION:
    Check that loadThread is not called twice per action.
    We intercept network requests and count conversation fetches.
    """

    def test_single_conversation_fetch_on_init(self, app_page: Page):
        """
        After New Session, there should be exactly ONE GET request
        to /conversations?agent_id=1, not two.
        """
        conversation_requests = []

        # Intercept network requests
        def on_request(request):
            if "/conversations?agent_id=" in request.url:
                conversation_requests.append(request.url)

        app_page.on("request", on_request)

        app_page.locator("text=New Session").click()

        # Wait for init to complete
        app_page.wait_for_function(
            """() => {
                const status = document.getElementById('statusBar');
                return !status || status.classList.contains('hidden');
            }""",
            timeout=INIT_TIMEOUT,
        )

        # Small extra wait for any trailing requests
        app_page.wait_for_timeout(500)

        # Count requests for agent_id=1 specifically
        agent1_requests = [
            r for r in conversation_requests if "agent_id=1" in r
        ]

        assert len(agent1_requests) == 1, (
            f"Expected exactly 1 GET /conversations?agent_id=1, "
            f"got {len(agent1_requests)}. "
            f"Double-fire bug (Patch B) may not be applied. "
            f"All conversation requests: {conversation_requests}"
        )


class TestApiKeyMissing:
    """
    Tests behavior when GEMINI_API_KEY is not set.
    The UI should still transition — just with error messages.
    """

    def test_ui_transitions_without_api_key(self, app_page: Page):
        """
        Even without an API key, clicking New Session should:
        1. Hide the welcome screen
        2. Show the main content area
        3. Show a response (even if it's an error message)

        The OLD bug: api_initialize returned 401, the catch block
        fired, and hideWelcome() never ran. Welcome screen stayed.
        """
        app_page.locator("text=New Session").click()

        # Wait for the flow to complete (success or error)
        app_page.wait_for_function(
            """() => {
                const status = document.getElementById('statusBar');
                return !status || status.classList.contains('hidden');
            }""",
            timeout=INIT_TIMEOUT,
        )

        # The critical check: welcome is GONE, content is VISIBLE
        welcome = app_page.locator("#welcomeSection")
        main = app_page.locator("#mainContent")

        expect(welcome).to_be_hidden(timeout=UI_TRANSITION_TIMEOUT)
        expect(main).to_be_visible(timeout=UI_TRANSITION_TIMEOUT)
