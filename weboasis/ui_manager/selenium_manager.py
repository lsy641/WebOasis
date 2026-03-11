from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
import os
import logging
import traceback
import time
from abc import ABC
from typing import Optional

from weboasis.ui_manager.constants import MARK_ELEMENTS_JS, ADD_OUTLINE_ELEMENTS_JS, REMOVE_OUTLINE_ELEMENTS_JS, IDENTIFY_INTERACTIVE_ELEMENTS_JS, SHOW_DECISION_MAKING_PROCESS_JS, INJECT_DEVELOPER_PANEL_JS, HIDE_DEVELOPER_ELEMENTS_JS, SHOW_DEVELOPER_ELEMENTS_JS, EXTRACT_ACCESSIBILITY_TREE_JS
from weboasis.ui_manager.base_manager import SyncWEBManager
from weboasis.act_book.engines.selenium import SeleniumAutomator
from weboasis.ui_manager.parsers.simple_parser import SimpleParser
from weboasis.ui_manager.js_adapters import SeleniumJSAdapter

logger = logging.getLogger(__name__)


class SyncSeleniumManager(SyncWEBManager, SeleniumAutomator):
    """Synchronous Selenium manager that inherits SeleniumAutomator for operations."""
    
    def __init__(self, parser=SimpleParser, headless=False, executable_path=None, test_id_attribute: str = "data-testid"):
        # Initialize base classes
        super().__init__()
        
        # Set up Chrome options
        chrome_options = Options()
        if not headless:
            chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--autoplay-policy=no-user-gesture-required")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Suppress password save prompts and update reminders
        chrome_options.add_argument("--disable-password-generation")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--disable-background-timer-throttling")
        
        # Disable Chrome's built-in password manager
        chrome_options.add_experimental_option("prefs", {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 1,
            "profile.default_content_setting_values.media_stream": 2
        })
        
        # Prefer Selenium Manager to provision ChromeDriver automatically.
        # If a Chrome browser binary is provided/found, set it on options; do not pass it as driver path.
        chrome_binary_path = None
        if executable_path and os.path.exists(executable_path):
            chrome_binary_path = executable_path
        else:
            # Try to find Chrome in common locations
            for path in [
                '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',  # macOS
                '/usr/bin/google-chrome',  # Linux
                'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',  # Windows
                'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',  # Windows 32-bit
            ]:
                if os.path.exists(path):
                    chrome_binary_path = path
                    break

        if chrome_binary_path:
            chrome_options.binary_location = chrome_binary_path

        # Let Selenium Manager choose the appropriate chromedriver
        service = Service()
        
        # Initialize WebDriver
        try:
            self._driver = webdriver.Chrome(service=service, options=chrome_options)
            # Remove webdriver property to avoid detection
            self._driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome WebDriver: {e}")
            raise
        
        # Set implicit wait
        self._driver.implicitly_wait(10)
        
        # Initialize action chains
        self._action_chains = ActionChains(self._driver)
        
        # Store the driver instance
        driver_instance = self._driver
        
        # Initialize SeleniumAutomator base class
        SeleniumAutomator.__init__(self)
        
        # Set the inherited attributes
        self._driver = driver_instance
        self._test_id_attribute = test_id_attribute
        self._parser = parser
    
    @property
    def driver(self):
        return self._driver
    
    @property
    def parser(self):
        return self._parser

    @parser.setter
    def parser(self, parser_class):
        self._parser = parser_class
    
    @property
    def selectors(self):
        """Selenium uses By class for selectors"""
        return By
    
    def set_test_id_attribute(self, attribute):
        """Selenium doesn't have built-in test ID support like Playwright"""
        logger.info(f"Test ID attribute '{attribute}' set (Selenium doesn't have built-in support)")
        
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
            # Wait for network to be idle (simplified for Selenium - wait for DOM complete)
            wait = WebDriverWait(self._driver, min(10000, timeout) / 1000)
            wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
            # Additional wait for DOM to be stable
            time.sleep(1)
            
            
            # Wait for any ongoing animations or dynamic content to settle
            try:
                wait.until(lambda driver: driver.execute_script("""
                    // Check if page is still loading
                    if (document.readyState !== 'complete') return false;
                    
                    // Check if there are any ongoing animations
                    try {
                        const animations = document.getAnimations();
                        if (animations && animations.length > 0) return false;
                    } catch (e) {
                        // getAnimations might not be supported in all browsers
                        // Continue without this check
                    }
                    
                    return true;
                """))
            except Exception as js_error:
                logger.warning(f"Animation check failed, continuing without it: {js_error}")
                # Continue without the animation check
                
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
        
        def mark_frames_recursive(frame_bid: str):
            nonlocal total_marked
            assert frame_bid == "" or (frame_bid.islower() and frame_bid.isalpha())

            # Mark all DOM elements in the frame using async JavaScript
            try:
                logger.info(f"Executing MARK_ELEMENTS_JS for frame '{frame_bid or 'main'}'")
                
                # Use execute_async_script with the universal wrapper (auto-detects parameter format)
                result = self._driver.execute_async_script(
                    SeleniumJSAdapter.wrap_async_function(MARK_ELEMENTS_JS),
                    [frame_bid, self._test_id_attribute]
                )
                
                logger.info(f"JavaScript execution result: {result}")
                
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
                
                logger.info(f"Frame '{frame_bid or 'main'}' marked {marked_count} elements")
                
            except Exception as e:
                logger.error(f"JavaScript execution failed for frame '{frame_bid or 'main'}': {e}")
                marked_count = 0
                total_marked += marked_count


            
            # Uncomment the code below if you actually need iframe support
                        # Ultra-fast iframe check with timeout protection
            try:
                # Use JavaScript with timeout - fastest possible iframe detection
                iframes = self._driver.execute_script("""
                    // Set a timeout to prevent hanging
                    const startTime = Date.now();
                    const timeout = 1000; // 1 second max
                    
                    try {
                        const iframes = document.querySelectorAll('iframe');
                        // Check if we're taking too long
                        if (Date.now() - startTime > timeout) {
                            console.warn('iframe search taking too long, returning empty');
                            return [];
                        }
                        return iframes;
                    } catch (e) {
                        console.warn('Error finding iframes:', e);
                        return [];
                    }
                """)
                
                if len(iframes) == 0:
                    logger.info("No iframes found - skipping iframe processing")
                else:
                    logger.info(f"Found {len(iframes)} iframes - processing them")
                    for i, iframe in enumerate(iframes):
                        logger.info(f"Processing iframe {i+1}/{len(iframes)}")
                        try:
                            # Deal with detached frames
                            if not iframe.is_displayed():
                                continue
                            
                            # Deal with weird frames (pdf viewer in <embed>)
                            iframe_elem = iframe
                            if not iframe_elem.is_displayed():
                                logger.warning(
                                    f"Skipping frame for marking, seems problematic."
                                )
                                continue
                            
                            # Deal with sandboxed frames with blocked script execution
                            sandbox_attr = iframe_elem.get_attribute("sandbox")
                            if sandbox_attr is not None and "allow-scripts" not in sandbox_attr.split():
                                continue
                                
                            child_frame_bid = iframe_elem.get_attribute(self._test_id_attribute)
                            if child_frame_bid is None:
                                logger.info("Cannot mark a child frame without a bid.")
                            else:
                                # Switch to iframe, mark elements, then switch back
                                self._driver.switch_to.frame(iframe_elem)
                                mark_frames_recursive(child_frame_bid)
                                self._driver.switch_to.parent_frame()
                                
                        except Exception as e:
                            logger.warning(f"Error processing iframe: {e}")
                            # Try to switch back to parent frame
                            try:
                                self._driver.switch_to.default_content()
                            except:
                                pass
                                
            except Exception as e:
                logger.warning(f"Error processing iframes: {e}")

        # Mark all frames recursively
        mark_frames_recursive("")
        
        # Quick retry only if no elements were marked (single attempt)
        # retry 2 times
        for _ in range(2):
            total_marked = 0
            mark_frames_recursive("")    
        return total_marked
            
            
        
    
    
    def outline_interactive_elements(self, interactive_elements: list[dict], max_retries=3, retry_delay=1000):
        """Outline interactive elements with visual highlighting"""
        highlighted_count = 0  # Initialize to prevent None reference error
        
        logger.info(f"Outlining {len(interactive_elements)} interactive elements")
        
        for attempt in range(max_retries):
            try:
                # For sync functions, use execute_script directly with raw JS
                highlighted_count = self._driver.execute_script(
                    SeleniumJSAdapter.wrap_sync_function(ADD_OUTLINE_ELEMENTS_JS), 
                    self._test_id_attribute
                )
                
                # Ensure highlighted_count is not None
                if highlighted_count is None:
                    highlighted_count = 0
                
                if highlighted_count == len(interactive_elements):
                    logger.info(f"All {highlighted_count} elements highlighted successfully.")
                    return
                
                logger.info(
                    f"Attempt {attempt + 1}: Highlighted {highlighted_count}/{len(interactive_elements)} elements. Retrying in {retry_delay}ms...")
                time.sleep(retry_delay / 1000)
                
            except Exception as e:
                logger.error(f"Error highlighting elements (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay / 1000)
        
        logger.info(f"Warning: Only {highlighted_count}/{len(interactive_elements)} elements were highlighted after {max_retries} attempts.")
        
    def remove_outline_elements(self):
        """Remove outline elements"""
        try:
            # For sync functions, use execute_script directly with raw JS
            self._driver.execute_script(SeleniumJSAdapter.wrap_sync_function(REMOVE_OUTLINE_ELEMENTS_JS))
        except Exception as e:
            logger.error(f"Error removing outline elements: {e}")
    
    def inject_developer_panel(self):
        """Inject developer panel wrapper script (same behavior as Playwright)."""
        try:
            self.is_page_loaded()
            self._driver.execute_script(SeleniumJSAdapter.wrap_sync_function(INJECT_DEVELOPER_PANEL_JS))
        except Exception as e:
            logger.error(f"Error injecting developer panel: {e}")
    
    def hide_developer_elements(self):
        """Hide elements marked with developer_elem attribute."""
        try:
            self._driver.execute_script(SeleniumJSAdapter.wrap_sync_function(HIDE_DEVELOPER_ELEMENTS_JS))
        except Exception as e:
            logger.error(f"Error hiding developer elements: {e}")
    
    def show_developer_elements(self):
        """Re-show previously hidden developer elements."""
        try:
            self._driver.execute_script(SeleniumJSAdapter.wrap_sync_function(SHOW_DEVELOPER_ELEMENTS_JS))
        except Exception as e:
            logger.error(f"Error showing developer elements: {e}")
    
    def locate_element(self, extracted_number):
        """Locate an element by its bid or ID"""
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
            
            # Verify page is ready
            try:
                ready_state = self._driver.execute_script("return document.readyState")
                if ready_state != 'complete':
                    print("Page is not ready")
                    return {}
            except:
                print("Page is not valid")
                return {}

            # Search for element by bid first (more efficient)
            try:
                element = self._driver.find_element(
                    By.CSS_SELECTOR, 
                    f'[{self._test_id_attribute}="{extracted_number}"], [id="{extracted_number}"]'
                )
            except:
                element = None
            
            # If not found, then search through individual selectors
            if not element:
                for selector in selectors:
                    try:
                        elements = self._driver.find_elements(By.CSS_SELECTOR, selector)
                        if not elements:
                            continue
                            
                        for el in elements:
                            bid = el.get_attribute(self._test_id_attribute) or el.get_attribute('id') or ''
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
                    'text': element.text,
                    'type': element.get_attribute('type'),
                    'tag': element.tag_name.lower(),
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
        """Show decision making process on the page"""
        # Avoid showing the password in the decision making process
        if "password" in description.lower():
            description = "***PASSWORD HIDDEN***"        
        try:
            # For sync functions, use execute_script directly with raw JS
            self._driver.execute_script(SeleniumJSAdapter.wrap_sync_function(SHOW_DECISION_MAKING_PROCESS_JS), [description, True])
        except Exception as e:
            logger.warning(f"Failed to show decision making process via JavaScript: {e}")
            # Fallback: just log the description
            logger.info(f"Decision making process: {description}")
    
    def identify_interactive_elements(self):
        """Identify interactive elements on the page"""
        try:
            # For sync functions, use execute_script directly with raw JS
            return self._driver.execute_script(SeleniumJSAdapter.wrap_sync_function(IDENTIFY_INTERACTIVE_ELEMENTS_JS), self._test_id_attribute)
        except Exception as e:
            logger.error(f"Error identifying interactive elements: {e}")
            return []
    
    def make_self_intro(self, description):
        """Make self introduction with profile button"""
        try:
            # Inject profile button
            self.inject_profile_button()
            
            # Wait for user interaction
            while True:
                try:
                    paused = self._driver.execute_script(
                        "return document.getElementById('webagent-profile-btn')?.dataset.paused === 'true'"
                    )
                    if not paused:
                        break
                    else:
                        # For sync functions, use execute_script directly with raw JS
                        self._driver.execute_script(SeleniumJSAdapter.wrap_sync_function(SHOW_DECISION_MAKING_PROCESS_JS), [description, False])
                    time.sleep(0.5)
                except:
                    break
        except Exception as e:
            logger.error(f"Error in make_self_intro: {e}")
    
    def detect_recaptcha(self) -> bool:
        """
        Detect if reCAPTCHA is present by checking marked elements (elements with test IDs).
        Only checks elements that have been marked by frame_mark_elements.js.
        
        Returns:
            bool: True if reCAPTCHA is detected in marked elements, False otherwise
        """
        try:
            # Check for reCAPTCHA in marked elements only, and verify if it's already completed
            has_recaptcha = self._driver.execute_script(f"""
                (function(testIdAttr) {{
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
                            // If verified, don't pause - continue to next element
                            if (isRecaptchaVerified(el)) {{
                                continue; // Skip this verified reCAPTCHA
                            }}
                            // If not verified, return true to pause
                            return true;
                        }}
                    }}
                    
                    return false;
                }})('{self._test_id_attribute}');
            """)
            return bool(has_recaptcha)
        except Exception as e:
            logger.warning(f"Error detecting reCAPTCHA: {e}")
            return False
    
    def pause_for_recaptcha(self):
        """
        Pause execution when reCAPTCHA is detected and wait for user to manually pass it.
        """
        if self.detect_recaptcha():
            logger.warning("=" * 80)
            logger.warning("reCAPTCHA DETECTED - Automation paused for manual intervention")
            logger.warning("=" * 80)
            logger.warning("Please manually complete the reCAPTCHA in the browser.")
            logger.warning("The automation will resume automatically once reCAPTCHA is passed.")
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
                if elapsed_time % 30 == 0:
                    logger.info(f"Still waiting for reCAPTCHA completion... ({elapsed_time}s elapsed)")
            
            logger.warning(f"Timeout waiting for reCAPTCHA completion after {max_wait_time}s. Continuing anyway...")
    
    def pause_for_debug(self):
        """Pause execution for debugging"""
        try:
            # Inject pause button
            self.inject_pause_button()
            
            # Poll for pause state
            while True:
                try:
                    paused = self._driver.execute_script(
                        "return document.getElementById('webagent-pause-btn')?.dataset.paused === 'true'"
                    )
                    if not paused:
                        break
                    time.sleep(0.5)
                except:
                    break
        except Exception as e:
            logger.error(f"Error in pause_for_debug: {e}")

    def get_accessibility_tree(self, max_depth: int = 5, max_text_len: int = 80, only_viewport: bool = True, max_nodes: int = 300) -> list[dict]:
        """Extract a simplified accessibility-like tree via JavaScript evaluation."""
        try:
            options = {
                "testIdAttr": self._test_id_attribute,
                "maxDepth": max_depth,
                "maxTextLen": max_text_len,
                "onlyViewport": only_viewport,
                "maxNodes": max_nodes,
            }
            return self._driver.execute_script(
                SeleniumJSAdapter.wrap_sync_function(EXTRACT_ACCESSIBILITY_TREE_JS),
                options
            ) or []
        except Exception as e:
            logger.warning(f"Failed to extract accessibility tree: {e}")
            return []
    
    def inject_pause_button(self):
        """Inject pause button into the page"""
        try:
            self._driver.execute_script("""
                (function() {
                    let btn = document.getElementById('webagent-pause-btn');
                    if (btn) return;
                    btn = document.createElement('button');
                    btn.setAttribute('developer_elem', '');
                    btn.id = 'webagent-pause-btn';
                    btn.innerText = 'Pause';
                    btn.style.position = 'fixed';
                    btn.style.top = '60px';
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
        except Exception as e:
            logger.error(f"Error injecting pause button: {e}")
    
    def inject_profile_button(self):
        """Inject profile button into the page"""
        try:
            self._driver.execute_script("""
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
        except Exception as e:
            logger.error(f"Error injecting profile button: {e}")
    
    def close(self):
        """
        Properly close all Selenium resources in the correct order.
        This ensures the browser and driver are properly cleaned up.
        """
        try:
            if hasattr(self, '_driver') and self._driver:
                try:
                    self._driver.quit()
                    logger.debug("Selenium driver closed successfully")
                except Exception as e:
                    logger.debug(f"Error closing driver: {e}")
        except Exception:
            pass
            
    def is_browser_available(self) -> bool:
        """Check if the browser/page is still available and responsive."""
        try:
            if not self._driver:
                return False
            
            # Check if driver is still responsive
            current_url = self._driver.current_url
            return True
            
        except Exception as e:
            logger.debug(f"Browser availability check failed: {e}")
            return False
    
    def __del__(self):
        """Destructor to ensure browser is closed"""
        self.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    

