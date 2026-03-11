from playwright.sync_api import sync_playwright, BrowserContext, Page
from playwright.async_api import async_playwright
import asyncio
import os
import logging
import traceback
import platform
from abc import ABC
from typing import Optional

from weboasis.ui_manager.constants import MARK_ELEMENTS_JS, ADD_OUTLINE_ELEMENTS_JS, REMOVE_OUTLINE_ELEMENTS_JS, IDENTIFY_INTERACTIVE_ELEMENTS_JS, SHOW_DECISION_MAKING_PROCESS_JS, INJECT_DEVELOPER_PANEL_JS, HIDE_DEVELOPER_ELEMENTS_JS, SHOW_DEVELOPER_ELEMENTS_JS, EXTRACT_ACCESSIBILITY_TREE_JS
from weboasis.ui_manager.base_manager import SyncWEBManager
from weboasis.act_book.engines.playwright.playwright_automator import PlaywrightAutomator
from weboasis.ui_manager.parsers.simple_parser import SimpleParser
import time

logger = logging.getLogger(__name__)


class SyncPlaywrightManager(SyncWEBManager, PlaywrightAutomator):
    """Playwright implementation of SyncWEBManager with element marking capabilities.
    
    This class provides methods for managing web pages and marking DOM elements
    for automated testing and interaction.
    
    Example usage:
        # Basic element marking (fastest, no additional checks)
        count = manager.mark_elements()
        
        # Element marking with page readiness checks (more reliable)
        count = manager.mark_elements(check_page_readiness=True)
        
        # Check if page is ready before marking
        if manager.is_page_ready_for_marking():
            count = manager.mark_elements()
        
        # Wait for page to be fully loaded, then mark elements
        if manager.is_page_loaded():
            count = manager.mark_elements()
    """
    
    def __init__(self, parser=SimpleParser, test_id_attribute: str = "data-testid", interactive_class_patterns: list[str] = None, 
                 extra_http_headers: dict = None, proxy: dict = None, user_agent: str = None):
        """
        Initialize the Playwright manager.
        
        Args:
            parser: Parser class for parsing actions
            test_id_attribute: Attribute name for test IDs (default: "data-testid")
            interactive_class_patterns: List of class patterns to identify interactive elements
            extra_http_headers: Dictionary of additional HTTP headers to send with every request
            proxy: Proxy configuration dict with 'server' key, optionally 'username' and 'password'
                  Example: {'server': 'http://proxy.example.com:8080', 'username': 'user', 'password': 'pass'}
            user_agent: Custom user agent string. If None, uses a realistic default Chrome user agent
        """
        # Initialize base classes
        SyncWEBManager.__init__(self)
        
        self._playwright = sync_playwright().start()
        # TODO: support other browsers
        if os.path.exists('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'):
            executable_path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        else:
            executable_path = None
        self._browser = self._playwright.chromium.launch(headless=False,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--disable-password-generation",
                "--disable-features=VizDisplayCompositor",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=TranslateUI",
                "--disable-ipc-flooding-protection"
            ],
            executable_path=executable_path)
        # self._browser = self._playwright.webkit.launch(headless=False)
        
        # Build context options
        context_options = {
            "viewport": {"width": 1440, "height": 900},
            "device_scale_factor": 0.6,
        }
        
        # # Set user agent (use realistic Chrome user agent if not provided)
        # if user_agent is None:
        #     # Realistic Chrome user agent based on platform
        #     if platform.system() == "Darwin":  # macOS
        #         user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        #     elif platform.system() == "Linux":
        #         user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        #     else:  # Windows
        #         user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        # context_options["user_agent"] = user_agent
        
        # # Build default headers for more human-like behavior
        # default_headers = {
        #     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        #     "Accept-Language": "en-US,en;q=0.9",
        #     "Accept-Encoding": "gzip, deflate, br",
        #     "Connection": "keep-alive",
        #     "Upgrade-Insecure-Requests": "1",
        #     "Sec-Fetch-Dest": "document",
        #     "Sec-Fetch-Mode": "navigate",
        #     "Sec-Fetch-Site": "none",
        #     "Sec-Fetch-User": "?1",
        #     "Cache-Control": "max-age=0",
        # }
        
        # Merge with user-provided headers (user headers take precedence)
        # if extra_http_headers:
        #     default_headers.update(extra_http_headers)
        
        # context_options["extra_http_headers"] = default_headers
        
        # Add proxy configuration
        if proxy:
            context_options["proxy"] = proxy
        
        self._context = self._browser.new_context(**context_options)
        self._page = self._context.new_page()
        self._demo_mode = "default"     
        # Default parser
        self._parser = parser
        self._test_id_attribute = test_id_attribute  # This sets the inherited _test_id_attribute attribute
        self._interactive_class_patterns = interactive_class_patterns
    
    @property
    def parser(self):
        return self._parser

    @parser.setter
    def parser(self, parser_class):
        self._parser = parser_class
        
    @property
    def page(self):
        return self._page
    
    @property
    def context(self):
        return self._context
    
    @property
    def browser(self):
        return self._browser
    
    @property
    def playwright(self):
        return self._playwright
    
    @property
    def test_id_attribute(self):
        return self._test_id_attribute
    
    @property
    def selectors(self):
        '''
        Playwright supports shorthand for selecting elements using certain attributes. Currently, only the following attributes are supported:

        # id
        # data-testid
        # data-test-id
        # data-test
        ''' 
        return self._playwright.selectors
    
    def set_test_id_attribute(self, attribute):
        self._test_id_attribute = attribute


    def is_page_loaded(self, timeout: int = 10000) -> bool:
        """
        Check if the page is fully loaded and ready for element marking.
        This includes waiting for network idle, DOM stability, and dynamic content.
        
        Args:
            timeout (int): Maximum time to wait in milliseconds
            
        Returns:
            bool: True if page is ready, False if timeout exceeded
        """
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout//2)
            # 2) Brief settle: no active animations and DOM stable for ~800ms
            self.page.wait_for_function("""
                () => new Promise((resolve) => {
                const hasAnims = () => (document.getAnimations?.() || []).length > 0;
                if (!hasAnims()) {
                    let last = document.querySelectorAll('*').length;
                    let idle = 0;
                    const obs = new MutationObserver(() => { idle = 0; });
                    obs.observe(document.body, {childList: true, subtree: true});
                    const tick = () => {
                    const now = document.querySelectorAll('*').length;
                    idle += 100;
                    if (now !== last) { last = now; idle = 0; }
                    if (idle >= 800) { obs.disconnect(); resolve(true); }
                    else setTimeout(tick, 100);
                    };
                    tick();
                } else {
                    // Wait a bit for animations to stop then resolve anyway
                    setTimeout(() => resolve(true), 1000);
                }
                })
            """, timeout=timeout//2)
                
            return True
            
        except Exception as e:
            logger.warning(f"Page load waiting failed: {e}. Page may not be fully loaded.")
            return False

    def mark_elements(self, check_page_readiness: bool = True):
        """
        Pre-extraction routine, marks DOM elements (set bid and dynamic attributes like value and checked)
        
        Args:
            check_page_readiness (bool): Whether to perform additional page readiness checks before marking.
                                       Default is True for reliability. Set to False for performance.
        
        Returns:
            int: Total number of elements marked across all frames
        """
        # Wait for page to be fully loaded and stable before marking elements
        if check_page_readiness:
            if not self.is_page_loaded():
                logger.warning("Page load check failed, but proceeding with element marking...")
        
        total_marked = 0  # Track total marked elements
        
        def mark_frames_recursive(frame, frame_bid: str):
            nonlocal total_marked
            assert frame_bid == "" or (frame_bid.islower() and frame_bid.isalpha())

            # Mark all DOM elements in the frame using the universal wrapper
            try:
                result = frame.evaluate(
                    MARK_ELEMENTS_JS,
                    [frame_bid, self._test_id_attribute],
                )
                
                # Extract warning messages and count from result
                if isinstance(result, list) and len(result) >= 2:
                    warning_msgs = result[0]
                    marked_count = result[1]  # JavaScript returns [warnings, count]
                    total_marked += marked_count
                else:
                    # Fallback if JavaScript doesn't return expected format
                    warning_msgs = result if isinstance(result, list) else []
                    marked_count = 0
                
                # Print warning messages if any
                for msg in warning_msgs:
                    logger.warning(msg)
            
                
            except Exception as e:
                logger.error(f"JavaScript execution failed for frame '{frame_bid or 'main'}': {e}")
                marked_count = 0
                total_marked += marked_count

            # Process child frames efficiently
            try:
                child_frames = frame.child_frames
                if child_frames:
                    
                    for child_frame in child_frames:
                        try:
                            # Skip detached frames
                            if child_frame.is_detached():
                                continue
                            
                            # Skip problematic frames
                            child_frame_elem = child_frame.frame_element()
                            if not child_frame_elem.content_frame() == child_frame:
                                logger.warning(f"Skipping frame '{child_frame.name}' for marking, seems problematic.")
                                continue
                            
                            # Skip sandboxed frames with blocked script execution
                            sandbox_attr = child_frame_elem.get_attribute("sandbox")
                            if sandbox_attr is not None and "allow-scripts" not in sandbox_attr.split():
                                continue
                            
                            # Get child frame bid and process recursively
                            # Use evaluate to get the full attribute value directly from DOM
                            # This ensures we get the complete value (e.g., "aa" not just "a")
                            test_id_attr = self._test_id_attribute
                            js_code = f'(el) => {{ const attr = el.attributes.getNamedItem("{test_id_attr}"); return attr ? attr.value : null; }}'
                            child_frame_bid = child_frame_elem.evaluate(js_code)
                            if child_frame_bid is None:
                                logger.warning("Cannot mark a child frame without a bid.")
                            else:
                                mark_frames_recursive(child_frame, frame_bid=child_frame_bid)
                                
                        except Exception as e:
                            logger.warning(f"Error processing child frame: {e}")
                            continue
                            
            except Exception as e:
                logger.warning(f"Error processing child frames: {e}")

        # Mark all frames recursively
        mark_frames_recursive(self.page.main_frame, frame_bid="")
        
        # Quick retry only if no elements were marked (single attempt)
        if total_marked == 0:
            logger.warning("No elements marked on first attempt. Quick retry...")
            self.page.wait_for_timeout(1000)  # Brief wait for page stability
            
            # Reset and retry
            total_marked = 0
            mark_frames_recursive(self.page.main_frame, frame_bid="")
            
            if total_marked == 0:
                logger.error("Failed to mark any elements after retry!")
            else:
                logger.debug(f"Successfully marked {total_marked} elements after retry")
        
        logger.debug(f"Total elements marked across all frames: {total_marked}")
        return total_marked
        
        
    def outline_interactive_elements(self, interactive_elements: list[dict], max_retries=3, retry_delay=1000):
        for attempt in range(max_retries):
            highlighted_count = self.page.evaluate(ADD_OUTLINE_ELEMENTS_JS, [self._test_id_attribute])
            if highlighted_count == len(interactive_elements):
                logger.debug(f"All {highlighted_count} elements highlighted successfully.")
                return

            logger.debug(
                f"Attempt {attempt + 1}: Highlighted {highlighted_count}/{len(interactive_elements)} elements. Retrying in {retry_delay}ms...")
            self.page.wait_for_timeout(retry_delay)

        logger.warning(f"Warning: Only {highlighted_count}/{len(interactive_elements)} elements were highlighted after {max_retries} attempts.")

        
        
    def remove_outline_elements(self):
        self.page.evaluate(REMOVE_OUTLINE_ELEMENTS_JS)
        
        
    def inject_developer_panel(self):
        self.is_page_loaded()
        self.page.evaluate(INJECT_DEVELOPER_PANEL_JS)
        
         
    
    def locate_element(self,extracted_number):
        try:
            # Define selectors for potentially interactive elements
            selectors = [
                'a', 'button', 'input', 'select', 'textarea', 'summary', 
                'video', 'audio', 'iframe', 'embed', 'object', 'menu', 
                'label', 'fieldset', 'datalist', 'output', 'details', 
                'dialog', 'option', '[role="button"]', '[role="link"]', 
                '[role="checkbox"]', '[role="radio"]', '[role="menuitem"]', 
                '[role="tab"]', '[tabindex]', '[contenteditable="true"]'
            ]
            
            # Verify page is valid
            if not self.page or not self.page.evaluate('() => document.readyState') == 'complete':
                print("Page is not ready or invalid")
                return {}

            # Search for element by ID first (more efficient)
            element =  self.page.query_selector(f'[{self._test_id_attribute}="{extracted_number}"], [id="{extracted_number}"]')
            
            # If not found, then search through individual selectors
            if not element:
                for selector in selectors:
                    try:
                        elements = self.page.query_selector_all(selector)
                        if not elements:
                            continue
                            
                        for el in elements:
                            bid = el.get_attribute(f'{self._test_id_attribute}') or el.get_attribute('id') or ''
                            if bid == extracted_number:
                                element = el
                                break
                        if element:
                            break
                    except Exception as e:
                        print(f"Error searching selector {selector}: {str(e)}")
                        continue
            
            if not element:
                print(f"No element found with ID {extracted_number}")
                return {}
                
            # Extract element properties
            result = {}
            try:
                result = {
                    'text': element.inner_text(),
                    'type': element.get_attribute('type'),
                    'tag': element.evaluate('el => el.tagName.toLowerCase()'),
                    'id': element.get_attribute('id'),
                    'href': element.get_attribute('href'),
                    'title': element.get_attribute('title'),
                    'ariaLabel': element.get_attribute('aria-label'),
                    'name': element.get_attribute('name'),
                    'value': element.get_attribute('value'),
                    'placeholder': element.get_attribute('placeholder'),
                    'class': element.get_attribute('class'),
                    'role': element.get_attribute('role')
                }
                
                # Clean up None values
                result = {k: v for k, v in result.items() if v is not None}
                
            except Exception as e:
                print(f"Error extracting element properties: {str(e)}")
                return {}
                    
            return result

        except Exception as e:
            print(f"Error in locate_element: {str(e)}")
            return {}
        
        
    def show_decision_making_process(self, description):
        # avoid showing the password in the decision making process
        if "password" in description.lower():
            description = "***PASSWORD HIDDEN***"
        
        try:
            # Try to show the decision making process via JavaScript
            self.page.evaluate(SHOW_DECISION_MAKING_PROCESS_JS, [description, False])
        except Exception as e:
            logger.warning(f"Failed to show decision making process via JavaScript: {e}")
            # Fallback: just log the description
            logger.debug(f"Decision making process: {description}")
        
    # def identify_interactive_elements(self):
    #     return self.page.evaluate(IDENTIFY_INTERACTIVE_ELEMENTS_JS, self._test_id_attribute)

    def identify_interactive_elements(self, max_retries=3, retry_delay=1000):
        """
        Identify interactive elements on the page with retry logic for navigation scenarios.
        Processes all frames recursively (main page + all iframes) to identify interactive elements.
        
        Args:
            max_retries (int): Maximum number of retry attempts
            retry_delay (int): Delay between retries in milliseconds
            
        Returns:
            list: List of interactive elements from all frames
        """
        all_interactive_elements = []  # Collect elements from all frames
        
        def identify_frames_recursive(frame, frame_name="main"):
            """Recursively identify interactive elements in all frames."""
            nonlocal all_interactive_elements
            try:
                # Check if frame is accessible (for cross-origin frames, this might fail)
                try:
                    # Try to access frame's document to check if it's accessible
                    # Also wait a bit for iframe content to load
                    ready_state = frame.evaluate("() => document.readyState")
                    if ready_state != "complete":
                        logger.debug(f"Frame '{frame_name}' not fully loaded (state: {ready_state}), waiting...")
                        try:
                            frame.wait_for_load_state("domcontentloaded", timeout=2000)
                        except:
                            pass  # Continue anyway
                except Exception as e:
                    error_str = str(e).lower()
                    if "cross-origin" in error_str or "crossorigin" in error_str:
                        logger.debug(f"Skipping cross-origin frame '{frame_name}' - cannot access content")
                        return
                    elif "target closed" in error_str or "frame was detached" in error_str:
                        logger.debug(f"Frame '{frame_name}' was detached or closed")
                        return
                    else:
                        logger.warning(f"Frame '{frame_name}' may not be accessible: {e}")
                        # Try to continue anyway - might still work
                
                # Identify interactive elements in this frame
                result = frame.evaluate(IDENTIFY_INTERACTIVE_ELEMENTS_JS, 
                                      [self._test_id_attribute, self._interactive_class_patterns])
                
                if isinstance(result, list):
                    # result is a list (could be empty or have elements)
                    if len(result) > 0:
                        all_interactive_elements.extend(result)
                        logger.info(f"Identified {len(result)} interactive elements in frame '{frame_name}'")
                        # Log some examples for debugging
                        if logger.isEnabledFor(logging.DEBUG):
                            examples = result[:3]  # First 3 elements
                            for elem in examples:
                                logger.debug(f"  - {elem.get('test_id', 'unknown')}: {elem.get('tag', 'unknown')} {elem.get('role', '')}")
                    else:
                        logger.debug(f"No interactive elements found in frame '{frame_name}' (empty list)")
                elif result is None:
                    logger.debug(f"No interactive elements found in frame '{frame_name}' (None)")
                else:
                    logger.warning(f"Unexpected result type from frame '{frame_name}': {type(result)} - {result}")
                
            except Exception as e:
                error_msg = str(e).lower()
                if "cross-origin" in error_msg or "crossorigin" in error_msg:
                    logger.debug(f"Cannot access cross-origin frame '{frame_name}' content")
                elif "target closed" in error_msg or "frame was detached" in error_msg:
                    logger.debug(f"Frame '{frame_name}' was detached or closed during identification")
                else:
                    logger.warning(f"Error identifying interactive elements in frame '{frame_name}': {e}")
            
            # Process child frames recursively
            try:
                child_frames = frame.child_frames
                if child_frames:
                    logger.debug(f"Found {len(child_frames)} child frames in '{frame_name}'")
                    for i, child_frame in enumerate(child_frames):
                        try:
                            # Skip detached frames
                            if child_frame.is_detached():
                                logger.debug(f"Child frame {i} in '{frame_name}' is detached, skipping")
                                continue
                            
                            # Get frame name for logging
                            try:
                                child_frame_name = child_frame.name or f"frame_{i}"
                            except:
                                child_frame_name = f"frame_{i}"
                            
                            # Skip problematic frames
                            try:
                                child_frame_elem = child_frame.frame_element()
                                if not child_frame_elem.content_frame() == child_frame:
                                    logger.debug(f"Child frame '{child_frame_name}' seems problematic, skipping")
                                    continue
                                
                                # Skip sandboxed frames with blocked script execution
                                sandbox_attr = child_frame_elem.get_attribute("sandbox")
                                if sandbox_attr is not None and "allow-scripts" not in sandbox_attr.split():
                                    logger.debug(f"Child frame '{child_frame_name}' has sandbox restrictions, skipping")
                                    continue
                            except Exception as e:
                                logger.debug(f"Could not check child frame '{child_frame_name}' properties: {e}")
                                # Continue anyway - try to process the frame
                            
                            # Recursively process child frame
                            logger.debug(f"Processing child frame '{child_frame_name}'")
                            identify_frames_recursive(child_frame, frame_name=child_frame_name)
                            
                        except Exception as e:
                            logger.warning(f"Error processing child frame {i} in '{frame_name}': {e}")
                            continue
                            
            except Exception as e:
                logger.warning(f"Error processing child frames in '{frame_name}': {e}")
        
        for attempt in range(max_retries):
            try:
                # Wait a bit for page to stabilize after navigation
                if attempt > 0:
                    self.page.wait_for_timeout(retry_delay)
                    logger.info(f"Retry {attempt + 1}/{max_retries} for identifying interactive elements...")
                
                # Reset the list for each attempt
                all_interactive_elements = []
                
                # Process all frames recursively starting from main page
                identify_frames_recursive(self.page.main_frame, frame_name="main")
                
                if len(all_interactive_elements) > 0:
                    logger.debug(f"Identified {len(all_interactive_elements)} total interactive elements across all frames")
                    return all_interactive_elements
                elif attempt < max_retries - 1:
                    logger.warning(f"No interactive elements found on attempt {attempt + 1}, retrying...")
                else:
                    logger.warning("No interactive elements found after all retries")
                    return all_interactive_elements
                    
            except Exception as e:
                if "Execution context was destroyed" in str(e) or "navigation" in str(e).lower():
                    if attempt < max_retries - 1:
                        logger.warning(f"JavaScript execution failed due to navigation (attempt {attempt + 1}/{max_retries}), retrying...")
                        continue
                    else:
                        logger.error(f"JavaScript execution failed after {max_retries} attempts: {e}")
                        return []
                else:
                    logger.error(f"Error identifying interactive elements: {e}")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        return []
        
        return all_interactive_elements
    
    def make_self_intro(self, description):
        self.page.on("load", lambda _: self.inject_profile_button())
        import time
        while True:
            paused = self.page.evaluate("document.getElementById('webagent-pause-btn')?.dataset.paused === 'true'")         
            if not paused:
                break
            else:
                self.page.evaluate(SHOW_DECISION_MAKING_PROCESS_JS, [description, False])
            time.sleep(0.5)
        
    def detect_recaptcha(self) -> bool:
        """
        Detect if reCAPTCHA is present by checking marked elements (elements with test IDs).
        Only checks elements that have been marked by frame_mark_elements.js.
        
        Returns:
            bool: True if reCAPTCHA is detected in marked elements, False otherwise
        """
        try:
            # Check for reCAPTCHA in marked elements across all frames
            def check_frame_for_recaptcha(frame):
                try:
                    # Check if frame is accessible
                    try:
                        frame.evaluate("() => document.readyState")
                    except:
                        return False
                    
                    # Check for reCAPTCHA in marked elements only, and verify if it's already completed
                    has_recaptcha = frame.evaluate(f"""
                        (testIdAttr) => {{
                            // Helper function to check if element is visible
                            function isElementVisible(el) {{
                                if (!el) return false;
                                
                                const style = window.getComputedStyle(el);
                                if (style.display === 'none' || 
                                    style.visibility === 'hidden' || 
                                    style.opacity === '0') {{
                                    return false;
                                }}
                                
                                const rect = el.getBoundingClientRect();
                                // Check if element is on screen (not off-screen)
                                if (rect.width === 0 && rect.height === 0) {{
                                    return false;
                                }}
                                
                                // Check if element is positioned off-screen (like hidden badges)
                                const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
                                const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
                                
                                // If element is completely outside viewport, it's not visible
                                if (rect.right < 0 || rect.bottom < 0 || 
                                    rect.left > viewportWidth || rect.top > viewportHeight) {{
                                    return false;
                                }}
                                
                                return true;
                            }}
                            
                            // Helper function to check if reCAPTCHA is already verified/completed
                            // This checks the entire document/frame, not just within the element
                            function isRecaptchaVerified(el) {{
                                // First, check if challenge iframe is visible (means NOT verified)
                                // The challenge iframe appears when reCAPTCHA needs to be completed
                                const challengeIframes = document.querySelectorAll('iframe[title*="recaptcha challenge"], iframe[title*="challenge expires"]');
                                for (let i = 0; i < challengeIframes.length; i++) {{
                                    const iframe = challengeIframes[i];
                                    const style = window.getComputedStyle(iframe.parentElement || iframe);
                                    // If challenge iframe is visible, reCAPTCHA is NOT verified
                                    if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {{
                                        const rect = iframe.getBoundingClientRect();
                                        if (rect.width > 0 && rect.height > 0) {{
                                            return false; // Challenge is visible, not verified
                                        }}
                                    }}
                                }}
                                
                                // Strategy: Check multiple ways to detect verification
                                // 1. Check entire document for status message (most reliable)
                                const statusEl = document.querySelector('#recaptcha-accessible-status, .rc-anchor-aria-status');
                                if (statusEl) {{
                                    const statusText = (statusEl.textContent || statusEl.innerText || '').trim();
                                    if (statusText.toLowerCase().includes('verified') || 
                                        statusText.toLowerCase().includes('you are verified')) {{
                                        return true;
                                    }}
                                }}
                                
                                // 2. Check entire document for verified checkbox
                                const checkbox = document.querySelector('[id="recaptcha-anchor"], .recaptcha-checkbox, [role="checkbox"][id*="recaptcha"]');
                                if (checkbox) {{
                                    const ariaChecked = checkbox.getAttribute('aria-checked');
                                    const hasCheckedClass = checkbox.classList.contains('recaptcha-checkbox-checked');
                                    const isUnchecked = checkbox.classList.contains('recaptcha-checkbox-unchecked');
                                    
                                    // If explicitly unchecked and not checked, not verified
                                    if (isUnchecked && ariaChecked !== 'true' && !hasCheckedClass) {{
                                        return false;
                                    }}
                                    
                                    // If checked (aria-checked="true" OR has checked class), it's verified
                                    if (ariaChecked === 'true' || hasCheckedClass) {{
                                        return true;
                                    }}
                                }}
                                
                                // 3. Check if g-recaptcha-response textarea has a value (indicates verification)
                                const responseTextarea = document.querySelector('textarea.g-recaptcha-response, textarea[name="g-recaptcha-response"]');
                                if (responseTextarea && responseTextarea.value && responseTextarea.value.trim().length > 0) {{
                                    return true; // Has response token, likely verified
                                }}
                                
                                // 4. Check within the element and its container (for when el is the container)
                                // First, find the reCAPTCHA container (rc-anchor-container or parent with rc-anchor class)
                                let container = el;
                                if (!container.classList.contains('rc-anchor') && !container.id.includes('rc-anchor')) {{
                                    // Try to find parent container
                                    container = el.closest('.rc-anchor-container, .rc-anchor, [id*="rc-anchor"], .g-recaptcha');
                                    if (!container) container = el;
                                }}
                                
                                // Check for checkbox in container
                                const checkboxInContainer = container.querySelector('[id="recaptcha-anchor"], .recaptcha-checkbox, [role="checkbox"][id*="recaptcha"]');
                                if (checkboxInContainer) {{
                                    const ariaChecked = checkboxInContainer.getAttribute('aria-checked');
                                    const hasCheckedClass = checkboxInContainer.classList.contains('recaptcha-checkbox-checked');
                                    if (ariaChecked === 'true' || hasCheckedClass) {{
                                        return true;
                                    }}
                                }}
                                
                                // Check for status in container
                                const statusInContainer = container.querySelector('#recaptcha-accessible-status, .rc-anchor-aria-status');
                                if (statusInContainer) {{
                                    const statusText = (statusInContainer.textContent || statusInContainer.innerText || '').trim();
                                    if (statusText.toLowerCase().includes('verified') || 
                                        statusText.toLowerCase().includes('you are verified')) {{
                                        return true;
                                    }}
                                }}
                                
                                // 5. Check element itself and parents for verification indicators
                                let currentEl = el;
                                let depth = 0;
                                while (currentEl && currentEl !== document.body && depth < 15) {{
                                    // Check for checked class in this element
                                    const className = (currentEl.className || '').toString();
                                    if (className.includes('recaptcha-checkbox-checked')) {{
                                        return true;
                                    }}
                                    
                                    // Check for aria-checked="true" in this element
                                    if (currentEl.getAttribute && currentEl.getAttribute('aria-checked') === 'true') {{
                                        return true;
                                    }}
                                    
                                    // Check text content for verification message
                                    const text = (currentEl.textContent || currentEl.innerText || '').trim();
                                    if (text.toLowerCase().includes('you are verified')) {{
                                        return true;
                                    }}
                                    
                                    currentEl = currentEl.parentElement;
                                    depth++;
                                }}
                                
                                return false;
                            }}
                            
                            // Get all marked elements (elements with test ID attribute)
                            const markedElements = document.querySelectorAll(`[${{testIdAttr}}]`);
                            
                            for (const el of markedElements) {{
                                if (!isElementVisible(el)) {{
                                    continue;
                                }}
                                
                                let isRecaptcha = false;
                                let recaptchaIndicators = 0;
                                
                                // Check if element is a reCAPTCHA iframe (strongest indicator)
                                if (el.tagName.toLowerCase() === 'iframe') {{
                                    const src = el.src || '';
                                    const title = el.title || '';
                                    if (src.includes('recaptcha') || 
                                        src.includes('google.com/recaptcha') ||
                                        title.toLowerCase().includes('recaptcha')) {{
                                        isRecaptcha = true; // iframe with recaptcha is definitive
                                    }}
                                }}
                                
                                // Check for reCAPTCHA-specific classes (must be specific patterns)
                                if (!isRecaptcha) {{
                                    const className = (el.className || '').toLowerCase();
                                    const id = (el.id || '').toLowerCase();
                                    const dataSitekey = el.getAttribute('data-sitekey');
                                    
                                    // Check for specific reCAPTCHA class patterns (not just any "recaptcha" substring)
                                    const recaptchaClassPatterns = [
                                        'recaptcha-checkbox',
                                        'recaptcha-anchor',
                                        'g-recaptcha',
                                        'rc-anchor',
                                        'rc-anchor-checkbox',
                                        'rc-anchor-normal',
                                        'rc-anchor-light',
                                        'rc-anchor-dark'
                                    ];
                                    
                                    const hasRecaptchaClass = recaptchaClassPatterns.some(pattern => 
                                        className.includes(pattern) || id.includes(pattern)
                                    );
                                    
                                    if (hasRecaptchaClass) {{
                                        recaptchaIndicators++;
                                    }}
                                    
                                    // data-sitekey is a strong indicator
                                    if (dataSitekey) {{
                                        recaptchaIndicators += 2; // Strong indicator
                                    }}
                                }}
                                
                                // Check if element contains reCAPTCHA text (must be exact phrase)
                                if (!isRecaptcha) {{
                                    const text = (el.innerText || el.textContent || '').toLowerCase();
                                    // Check for exact phrase, not just substring
                                    if (text.includes("i'm not a robot") || 
                                        text.includes("i am not a robot") ||
                                        text.includes("i'm not a robot.") ||
                                        text.includes("i am not a robot.")) {{
                                        recaptchaIndicators += 2; // Strong indicator
                                    }}
                                }}
                                
                                // Check if element contains reCAPTCHA iframe as child (strong indicator)
                                if (!isRecaptcha) {{
                                    const recaptchaIframe = el.querySelector('iframe[src*="recaptcha"], iframe[src*="google.com/recaptcha"], iframe[title*="recaptcha"]');
                                    if (recaptchaIframe && isElementVisible(recaptchaIframe)) {{
                                        recaptchaIndicators += 2; // Strong indicator
                                    }}
                                }}
                                
                                // Check for reCAPTCHA checkbox element
                                if (!isRecaptcha) {{
                                    const checkbox = el.querySelector('[id="recaptcha-anchor"], .recaptcha-checkbox, [role="checkbox"][id*="recaptcha-anchor"]');
                                    if (checkbox) {{
                                        recaptchaIndicators += 2; // Strong indicator
                                    }}
                                }}
                                
                                // Require at least 2 indicators (or 1 strong indicator) to avoid false positives
                                // Strong indicators count as 2, so we need at least 2 points
                                if (!isRecaptcha && recaptchaIndicators >= 2) {{
                                    isRecaptcha = true;
                                }}
                                
                                // If reCAPTCHA is found, check if it's already verified
                                if (isRecaptcha) {{
                                    // If verified, don't pause - return false
                                    if (isRecaptchaVerified(el)) {{
                                        continue; // Skip this verified reCAPTCHA
                                    }}
                                    // If not verified, return true to pause
                                    return true;
                                }}
                            }}
                            
                            return false;
                        }}
                    """, self._test_id_attribute)
                    
                    if has_recaptcha:
                        return True
                    
                    # Check child frames recursively
                    for child_frame in frame.child_frames:
                        if check_frame_for_recaptcha(child_frame):
                            return True
                    
                    return False
                except:
                    return False
            
            return check_frame_for_recaptcha(self.page.main_frame)
        except Exception as e:
            logger.warning(f"Error detecting reCAPTCHA: {e}")
            return False
    
    def _play_recaptcha_alert(self):
        """
        Play a voice/sound alert to notify the user that reCAPTCHA has been detected.
        Uses JavaScript Web Speech API (SpeechSynthesis) in the browser.
        """
        try:
            # Use JavaScript Web Speech API to speak the alert - pure JavaScript, no Python
            # Trigger a user interaction event first to enable audio (browsers block autoplay)
            self.page.evaluate("""
                () => {
                    // Function to play alert
                    function playAlert() {
                        // Try SpeechSynthesis first
                        if ('speechSynthesis' in window) {
                            try {
                                // Cancel any ongoing speech
                                window.speechSynthesis.cancel();
                                
                                const utterance = new SpeechSynthesisUtterance(
                                    "reCAPTCHA detected. Please complete the verification."
                                );
                                utterance.volume = 1.0;  // Full volume
                                utterance.rate = 1.0;    // Normal speed
                                utterance.pitch = 1.0;   // Normal pitch
                                
                                // Speak the message
                                window.speechSynthesis.speak(utterance);
                                
                                // Also try to play beep sounds as backup
                                playBeeps();
                                return;
                            } catch (e) {
                                console.warn("SpeechSynthesis failed:", e);
                            }
                        }
                        
                        // Fallback to beeps
                        playBeeps();
                    }
                    
                    // Function to play beep sounds
                    function playBeeps() {
                        try {
                            // Resume audio context if suspended (browsers suspend it until user interaction)
                            let audioContext = window.recaptchaAlertAudioContext;
                            if (!audioContext) {
                                audioContext = new (window.AudioContext || window.webkitAudioContext)();
                                window.recaptchaAlertAudioContext = audioContext;
                            }
                            
                            // Resume if suspended
                            if (audioContext.state === 'suspended') {
                                audioContext.resume().then(() => {
                                    playBeepSequence(audioContext);
                                }).catch(e => {
                                    console.warn("Could not resume audio context:", e);
                                });
                            } else {
                                playBeepSequence(audioContext);
                            }
                        } catch (e) {
                            console.error("Could not play audio alert:", e);
                            // Last resort: try to trigger browser notification
                            if (Notification && Notification.permission === 'granted') {
                                new Notification('reCAPTCHA Detected', {
                                    body: 'Please complete the verification in the browser.',
                                    icon: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
                                });
                            }
                        }
                    }
                    
                    // Function to play a sequence of beeps
                    function playBeepSequence(audioContext) {
                        function playBeep(delay, frequency = 800) {
                            setTimeout(() => {
                                try {
                                    const oscillator = audioContext.createOscillator();
                                    const gainNode = audioContext.createGain();
                                    
                                    oscillator.connect(gainNode);
                                    gainNode.connect(audioContext.destination);
                                    
                                    oscillator.frequency.value = frequency;
                                    oscillator.type = 'sine';
                                    
                                    gainNode.gain.setValueAtTime(0.5, audioContext.currentTime);
                                    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);
                                    
                                    oscillator.start(audioContext.currentTime);
                                    oscillator.stop(audioContext.currentTime + 0.3);
                                } catch (e) {
                                    console.warn("Beep failed:", e);
                                }
                            }, delay);
                        }
                        
                        // Play 3 beeps at different frequencies
                        playBeep(0, 800);
                        playBeep(400, 1000);
                        playBeep(800, 1200);
                    }
                    
                    // Trigger a click event on the document to enable audio (browsers require user interaction)
                    // This simulates user interaction to unlock audio
                    const clickEvent = new MouseEvent('click', {
                        view: window,
                        bubbles: true,
                        cancelable: true
                    });
                    document.dispatchEvent(clickEvent);
                    
                    // Try to play immediately
                    playAlert();
                    
                    // Also try again after a short delay (in case audio context needs initialization)
                    setTimeout(playAlert, 100);
                    setTimeout(playAlert, 500);
                }
            """)
        except Exception as e:
            logger.debug(f"Could not execute JavaScript audio alert: {e}")
    
    def pause_for_recaptcha(self):
        """
        Pause execution when reCAPTCHA is detected and wait for user to manually pass it.
        """
        if self.detect_recaptcha():
            # Play voice/sound alert
            self._play_recaptcha_alert()
            
            logger.warning("=" * 80)
            logger.warning("reCAPTCHA DETECTED - Automation paused for manual intervention")
            logger.warning("=" * 80)
            
            # Wait for reCAPTCHA to be completed
            # Check every 2 seconds if reCAPTCHA is still present
            max_wait_time = 300  # 5 minutes max wait
            check_interval = 2  # Check every 2 seconds
            elapsed_time = 0
            
            while elapsed_time < max_wait_time:
                time.sleep(check_interval)
                elapsed_time += check_interval
                
                if not self.detect_recaptcha():
                    logger.info("reCAPTCHA appears to be completed. Resuming automation...")
                    # Wait a bit more to ensure page has updated
                    time.sleep(1)
                    return
                
                # Log progress every 30 seconds
                if elapsed_time % 20 == 0:
                    self._play_recaptcha_alert()
                    logger.info(f"Still waiting for reCAPTCHA completion... ({elapsed_time}s elapsed)")
            
            logger.warning(f"Timeout waiting for reCAPTCHA completion after {max_wait_time}s. Continuing anyway...")
        
    def pause_for_debug(self):
        try:
            self.inject_pause_button()
        except Exception as e:
            logger.warning(f"Failed to inject pause button: {e}")
            return
        # Poll for pause state
        import time
        while True:
            paused = self.page.evaluate("document.getElementById('webagent-pause-btn')?.dataset.paused === 'true'")
            if not paused:
                break
            time.sleep(0.5)
        # Now continue execution
        
    def inject_pause_button(self):
        self.page.evaluate("""
            (function() {
                let btn = document.getElementById('webagent-pause-btn');
                if (btn) return;
                btn = document.createElement('button');
                btn.id = 'webagent-pause-btn';
                btn.setAttribute('developer_elem', ''); 
                btn.innerText = 'Pause';
                btn.style.position = 'fixed';
                btn.style.top = '40px';
                btn.style.right = '20px';
                btn.style.zIndex = 2147483647;
                btn.style.background = '#e67e22';
                btn.style.color = '#fff';
                btn.style.padding = '8px 16px';
                btn.style.border = 'none';
                btn.style.borderRadius = '6px';
                btn.style.fontSize = '14px';
                btn.style.fontFamily = 'monospace';
                btn.style.cursor = 'pointer';
                btn.style.boxShadow = '0 2px 12px rgba(0,0,0,0.15)';
                btn.dataset.paused = 'false';
                btn.onclick = function() {
                    if (btn.dataset.paused === 'false') {
                        btn.innerText = 'Resume';
                        btn.dataset.paused = 'true';
                    } else {
                        btn.innerText = 'Pause';
                        btn.dataset.paused = 'false';
                    }
                };
                document.body.appendChild(btn);
            })();
        """)
        
        
    def inject_profile_button(self):
        self.page.evaluate("""
            (function() {
                let btn = document.getElementById('webagent-profile-btn');
                if (btn) return;
                btn = document.createElement('button');
                btn.id = 'webagent-profile-btn';
                btn.setAttribute('developer_elem', ''); 
                btn.innerText = 'Profile';
                btn.style.position = 'fixed';
                btn.style.top = '10px';
                btn.style.right = '20px';
                btn.style.zIndex = 2147483647;
                btn.style.background = '#e67e22';
                btn.style.color = '#fff';
                btn.style.padding = '8px 8px';
                btn.style.border = 'none';
                btn.style.borderRadius = '6px';
                btn.style.fontSize = '14px';
                btn.style.fontFamily = 'monospace';
                btn.style.cursor = 'pointer';
                btn.style.boxShadow = '0 2px 12px rgba(0,0,0,0.15)';
                btn.dataset.paused = 'false';
                btn.onclick = function() {
                    if (btn.dataset.paused === 'false') {
                        btn.innerText = 'Profile Close';
                        btn.dataset.paused = 'true';
                    } else {
                        btn.innerText = 'Profile';
                        btn.dataset.paused = 'false';
                    }
                };
                document.body.appendChild(btn);
            })();
        """)
        
    def hide_developer_elements(self):
        self.page.evaluate(HIDE_DEVELOPER_ELEMENTS_JS)
        
    def show_developer_elements(self):
        self.page.evaluate(SHOW_DEVELOPER_ELEMENTS_JS)
        
    
    def get_accessibility_tree(self, max_depth: int = 5, max_text_len: int = 80, only_viewport: bool = True, max_nodes: int = 300) -> list[dict]:
        """Extract a simplified accessibility-like tree from the current page.
        Returns a list of compact nodes with tag, role, name, interactivity and viewport rect.
        """
        try:
            options = {
                "testIdAttr": self._test_id_attribute,
                "maxDepth": max_depth,
                "maxTextLen": max_text_len,
                "onlyViewport": only_viewport,
                "maxNodes": max_nodes,
            }
            return self.page.evaluate(EXTRACT_ACCESSIBILITY_TREE_JS, options) or []
        except Exception as e:
            logger.warning(f"Failed to extract accessibility tree: {e}")
            return []

    def close(self):
        """
        Properly close all Playwright resources in the correct order.
        This ensures the internal asyncio loop is stopped, preventing conflicts
        when creating a new instance for the next run.
        """
        try:
            if hasattr(self, '_page') and self._page:
                try:
                    self._page.close()
                except Exception as e:
                    logger.debug(f"Error closing page: {e}")
        except Exception:
            pass
        
        try:
            if hasattr(self, '_context') and self._context:
                try:
                    self._context.close()
                except Exception as e:
                    logger.debug(f"Error closing context: {e}")
        except Exception:
            pass
        
        try:
            if hasattr(self, '_browser') and self._browser:
                try:
                    self._browser.close()
                except Exception as e:
                    logger.debug(f"Error closing browser: {e}")
        except Exception:
            pass
        
        try:
            if hasattr(self, '_playwright') and self._playwright:
                try:
                    self._playwright.stop()
                    logger.debug("Playwright instance stopped successfully")
                except Exception as e:
                    logger.debug(f"Error stopping Playwright: {e}")
        except Exception:
            pass
            
    def is_browser_available(self) -> bool:
        """Check if the browser/page is still available and responsive."""
        try:
            if not self.page:
                return False
            
            # Check if page is closed
            if self.page.is_closed():
                return False
            
            # Try a simple operation to see if page is responsive
            self.page.evaluate("document.readyState")
            return True
            
        except Exception as e:
            logger.debug(f"Browser availability check failed: {e}")
            return False
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        


class AsyncPlaywrightManager(SyncWEBManager, PlaywrightAutomator):
    """Asynchronous Playwright manager that inherits PlaywrightAutomator for operations."""
    
    def __init__(self, test_id_attribute: str = "data-testid"):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._test_id_attribute = test_id_attribute
        
        # Initialize PlaywrightAutomator base class
        PlaywrightAutomator.__init__(self)
        
    async def start(self, extra_http_headers: dict = None, proxy: dict = None, user_agent: str = None):
        """
        Start the async playwright instance.
        
        Args:
            extra_http_headers: Dictionary of additional HTTP headers to send with every request
            proxy: Proxy configuration dict with 'server' key, optionally 'username' and 'password'
            user_agent: Custom user agent string. If None, uses a realistic default Chrome user agent
        """
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=False,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--disable-password-generation",
                "--disable-features=VizDisplayCompositor",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=TranslateUI",
                "--disable-ipc-flooding-protection"
            ])
        
        # Build context options
        context_options = {
            "viewport": {"width": 1440, "height": 900},
            "device_scale_factor": 0.7,
        }
        
        # Set user agent (use realistic Chrome user agent if not provided)
        if user_agent is None:
            # Realistic Chrome user agent based on platform
            if platform.system() == "Darwin":  # macOS
                user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            elif platform.system() == "Linux":
                user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            else:  # Windows
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        context_options["user_agent"] = user_agent
        
        # Build default headers for more human-like behavior
        default_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        
        # Merge with user-provided headers (user headers take precedence)
        if extra_http_headers:
            default_headers.update(extra_http_headers)
        
        context_options["extra_http_headers"] = default_headers
        
        # Add proxy configuration
        if proxy:
            context_options["proxy"] = proxy
        
        self._context = await self._browser.new_context(**context_options)
        self._page = await self._context.new_page()
        
        # Now initialize PlaywrightAutomator base class
        PlaywrightAutomator.__init__(self)
        
        # Set the inherited attributes
        self._page = self._page
        self._test_id_attribute = self._test_id_attribute
        
    async def close(self):
        """
        Properly close all Playwright resources in the correct order (async version).
        This ensures the internal asyncio loop is stopped, preventing conflicts
        when creating a new instance for the next run.
        """
        try:
            if hasattr(self, '_page') and self._page:
                try:
                    await self._page.close()
                except Exception as e:
                    logger.debug(f"Error closing page: {e}")
        except Exception:
            pass
        
        try:
            if hasattr(self, '_context') and self._context:
                try:
                    await self._context.close()
                except Exception as e:
                    logger.debug(f"Error closing context: {e}")
        except Exception:
            pass
        
        try:
            if hasattr(self, '_browser') and self._browser:
                try:
                    await self._browser.close()
                except Exception as e:
                    logger.debug(f"Error closing browser: {e}")
        except Exception:
            pass
        
        try:
            if hasattr(self, '_playwright') and self._playwright:
                try:
                    await self._playwright.stop()
                    logger.debug("Playwright instance stopped successfully")
                except Exception as e:
                    logger.debug(f"Error stopping Playwright: {e}")
        except Exception:
            pass
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        