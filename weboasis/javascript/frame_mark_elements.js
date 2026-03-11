/**
 * Go through all DOM elements in the frame (including shadowDOMs), give them unique element
 * identifiers (bid), and store custom data in the aria-roledescription attribute.
 */
async ([parent_bid, bid_attr_name]) => {

    // standard html tags
    // https://www.w3schools.com/tags/
    const html_tags = new Set([
        "a", "abbr", "acronym", "address", "applet", "area", "article", "aside", "audio",
        "b", "base", "basefont", "bdi", "bdo", "big", "blockquote", "body", "br", "button",
        "canvas", "caption", "center", "cite", "code", "col", "colgroup", "data", "datalist",
        "dd", "del", "details", "dfn", "dialog", "dir", "div", "dl", "dt", "em", "embed",
        "fieldset", "figcaption", "figure", "font", "footer", "form", "frame", "frameset",
        "h1", "h2", "h3", "h4", "h5", "h6", "head", "header", "hgroup", "hr", "html", "i",
        "iframe", "img", "input", "ins", "kbd", "label", "legend", "li", "link", "main",
        "map", "mark", "menu", "meta", "meter", "nav", "noframes", "noscript", "object",
        "ol", "optgroup", "option", "output", "p", "param", "picture", "pre", "progress",
        "q", "rp", "rt", "ruby", "s", "samp", "script", "search", "section", "select",
        "small", "source", "span", "strike", "strong", "style", "sub", "summary", "sup",
        "svg", "table", "tbody", "td", "template", "textarea", "tfoot", "th", "thead",
        "time", "title", "tr", "track", "tt", "u", "ul", "var", "video", "wbr"
    ]);
    // set_of_marks_tags removed - no longer used

    let first_visit = false;
    // if no yet set, set the frame (local) element counter to 0
    if (!("dom_elem_counter" in window)) {
        window.dom_elem_counter = 0;
        window.dom_frame_id_generator = new IFrameIdGenerator();
        first_visit = true;
    }

    let all_bids = new Set();
    warning_msgs = new Array();

    // CRITICAL: Wait for page stability BEFORE processing elements
    // This prevents issues with dynamic content (chat windows, forms, etc.) that are still loading
    // and avoids triggering Chrome extension message errors when modifying input values
    
    // Step 1: Wait for DOM to be ready
    if (document.readyState !== 'complete') {
        await new Promise(resolve => {
            if (document.readyState === 'complete') {
                resolve();
            } else {
                window.addEventListener('load', resolve, { once: true });
                // Fallback timeout
                setTimeout(resolve, 5000);
        }
        });
    }
    
    // Step 2: Wait for chat-like interfaces to stabilize BEFORE processing elements
    // This is critical - chat windows often load messages dynamically, and we don't want
    // to modify input values while messages are still loading (which triggers Chrome extension errors)
    const chatSelectors = [
        'div#chatWindow',
        'div#chatbot', 
        'div[class*="chat"]',
        'div[id*="chat"]',
        'div[class*="conversation"]',
        'div[class*="message"]',
        'div[role="log"]'
    ];
    
    let chatWindow = null;
    for (const selector of chatSelectors) {
        chatWindow = document.querySelector(selector);
        if (chatWindow) {
            break;
        }
    }
    
    if (chatWindow) {
        // Dynamic waiting: wait until no new messages AND text content is stable
        const thresholds = {
            inactivity: 3000,      // ms to wait after last message
            textStability: 2000,    // ms to wait after last text content change
            maxWait: 10000,         // ms, absolute max wait
            checkInterval: 100      // ms between checks
        };
        
        const state = {
            lastMutationTime: Date.now(),
            lastTextContent: chatWindow.textContent || '',
            lastTextChangeTime: Date.now(),
            startTime: Date.now()
        };
    
        // Update state on mutations
        const mutation_observer = new MutationObserver(() => {
            state.lastMutationTime = Date.now();
            const currentText = chatWindow.textContent || '';
            if (currentText !== state.lastTextContent) {
                state.lastTextContent = currentText;
                state.lastTextChangeTime = Date.now();
            }
        });
        mutation_observer.observe(chatWindow, { 
            childList: true, 
            subtree: true, 
            characterData: true,
            attributes: false
        });
    
        // Check stability conditions
        const checkStability = () => {
            const now = Date.now();
            const times = {
                sinceMutation: now - state.lastMutationTime,
                sinceTextChange: now - state.lastTextChangeTime,
                total: now - state.startTime
            };
            
            // Check for active animations
            const hasActiveAnimations = () => {
                for (const el of chatWindow.querySelectorAll('*')) {
                    const style = window.getComputedStyle(el);
                    if ((style.animationName !== 'none' && style.animationPlayState !== 'paused') ||
                        (style.transitionProperty !== 'none' && parseFloat(style.transitionDuration) > 0)) {
                        return true;
                    }
                }
                return false;
            };
            
            // Check for typing indicators
            const typingSelectors = ['[class*="typing" i]', '[id*="typing" i]', '[aria-label*="typing" i]'];
            const hasTypingIndicator = typingSelectors.some(sel => {
                try { return chatWindow.querySelector(sel); } catch { return false; }
            });
            
            return {
                mutationsStable: times.sinceMutation > thresholds.inactivity,
                textStable: times.sinceTextChange > thresholds.textStability,
                noAnimations: !hasActiveAnimations(),
                noTypingIndicator: !hasTypingIndicator,
                times
            };
        };
    
        // Wait until all conditions are met
        await new Promise(resolve => {
            const check = () => {
                const stability = checkStability();
                const allStable = stability.mutationsStable && stability.textStable && 
                                  stability.noAnimations && stability.noTypingIndicator;
                
                if (allStable) {
                    mutation_observer.disconnect();
                    resolve();
                } else if (stability.times.total > thresholds.maxWait) {
                    mutation_observer.disconnect();
                    resolve();
                } else {
                    setTimeout(check, thresholds.checkInterval);
                }
            };
            check();
        });
    }
    
    // Step 3: Wait for general DOM stability (no rapid changes)
    // This catches any other dynamic content that might still be loading
    await new Promise(resolve => {
        let timeoutId;
        let lastChangeTime = Date.now();
        const checkIdle = () => {
            lastChangeTime = Date.now();
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => {
                const idleTime = Date.now() - lastChangeTime;
                if (idleTime >= 500) {
                    console.log(`DOM stabilized after ${idleTime}ms of inactivity`);
                    observer.disconnect();
                    resolve();
                }
            }, 500); // Wait 500ms of inactivity
        };
        // Start checking immediately
        checkIdle();
        // Also check on any DOM changes
        const observer = new MutationObserver(checkIdle);
        observer.observe(document.body, { childList: true, subtree: true });
        // Fallback: resolve after max wait time
        setTimeout(() => {
            observer.disconnect();
            clearTimeout(timeoutId);
            resolve();
        }, 2000); // Max 2 seconds wait for general stability
    });
    
    console.log('Page stability checks complete, starting element processing...');
    
    // NOW process elements after page is stable
    // get all DOM elements in the current frame (does not include elements in shadowDOMs)
    let [elementCountBefore, processedCount] = processNewElements(bid_attr_name, parent_bid, all_bids, first_visit, html_tags);
    console.log(`Initially processed ${processedCount} elements`);
    console.log(`Found ${elementCountBefore} elements before processing`);

    // Retry loop: keep checking for new elements until no difference in length
    let retryCount = 1;
    const maxRetries = 2;
    const maxWaitTime = 2000; // Maximum 2 seconds to wait
    
    while (retryCount < maxRetries) {
        console.log(`Retry ${retryCount + 1}/${maxRetries}, element count: ${elementCountBefore}`);
        
        // Use built-in MutationObserver for smart waiting
        const elementCountAfter = await waitForElementChanges(elementCountBefore, maxWaitTime);
        console.log(`After waiting, element count: ${elementCountAfter}`);
        
        // If no new elements, we're done
        if (elementCountAfter === elementCountBefore) {
            console.log('No new elements detected, retry complete');
            break;
        }
        
        // Process new elements that appeared during the wait
        const newElementsCount = elementCountAfter - elementCountBefore;
        console.log(`Found ${newElementsCount} new elements, processing them...`);

        // Process new elements using the same logic as the main loop
        [elementCountBefore, processedCount] = processNewElements(bid_attr_name, parent_bid, all_bids, first_visit, html_tags);
        
        console.log(`Processed ${processedCount} new elements in retry ${retryCount + 1}`);
        retryCount++;
    }
    
    console.log(`Element processing complete after ${retryCount} attempts`);

    // Handle video transcript collection (after elements are processed)
    const video = document.querySelector('video');
    let transcript = "";
    if (video && isVideoPlaying(video)) {
        // Collect transcript if available
        if (video.textTracks && video.textTracks.length > 0) {
            const track = video.textTracks[0];
            track.mode = "showing";
            track.addEventListener("cuechange", () => {
                for (let i = 0; i < track.activeCues.length; i++) {
                    transcript += track.activeCues[i].text + "\n";
                }
            });
        }
        // Wait for video to end
        await new Promise(resolve => {
            video.addEventListener('ended', resolve, { once: true });
        });
        // Optionally, you can log or return the transcript
        warning_msgs.push("Video transcript:\n" + transcript);
    }

    // Return both warning messages and the count of marked elements
    return [warning_msgs, all_bids.size];
}

async function until(f, timeout, interval=40) {
    return new Promise((resolve, reject) => {
        const start_time = Date.now();
        // immediate check
        if (f()) {
            resolve();
        }
        // loop check
        const wait = setInterval(() => {
            if (f()) {
                clearInterval(wait);
                resolve();
            } else if (Date.now() - start_time > timeout) {
                clearInterval(wait);
                reject();
            }
        }, interval);
    });
}


function whoCapturesCenterClick(element){
    var rect = element.getBoundingClientRect();
    var x = (rect.left + rect.right) / 2 ;
    var y = (rect.top + rect.bottom) / 2 ;
    var element_at_center = elementFromPoint(x, y); // return the element in the foreground at position (x,y)
    if (!element_at_center) {
        return "nobody";
    } else if (element_at_center === element) {
        return "self";
    } else if (element.contains(element_at_center)) {
        return "child";
    } else {
        return "non-descendant";
    }
}

function elementFromPoint(x, y) {
    let dom = document;
    let last_elem = null;
    let elem = null;

    do {
        last_elem = elem;
        elem = dom.elementFromPoint(x, y);
        dom = elem?.shadowRoot;
    } while(dom && elem !== last_elem);

    return elem;
}

// https://stackoverflow.com/questions/12504042/what-is-a-method-that-can-be-used-to-increment-letters#answer-12504061
class IFrameIdGenerator {
    constructor(chars = 'abcdefghijklmnopqrstuvwxyz') {
      this._chars = chars;
      this._nextId = [0];
    }

    next() {
      const r = [];
      for (const char of this._nextId) {
        r.unshift(this._chars[char]);
      }
      this._increment();
      return r.join('');
    }

    _increment() {
      for (let i = 0; i < this._nextId.length; i++) {
        const val = ++this._nextId[i];
        if (val < this._chars.length) {
          return;
        }
        this._nextId[i] = 0;
      }
      this._nextId.push(0);
    }

    *[Symbol.iterator]() {
      while (true) {
        yield this.next();
      }
    }
  }



function processNewElements(bid_attr_name, parent_bid, all_bids, first_visit=false, html_tags) {
    let elements = Array.from(document.querySelectorAll('*'));
    let elementCountBefore = elements.length;
    let i = 0;
    let processedCount = 0;
    
    while (i < elements.length) {
        const elem = elements[i];
        
        // add shadowDOM elements to the elements array, preserving order
        if (elem.shadowRoot !== null) {
            elements = new Array(
                ...Array.prototype.slice.call(elements, 0, i + 1),
                ...Array.from(elem.shadowRoot.querySelectorAll("*")),
                ...Array.prototype.slice.call(elements, i + 1)
            );
        }
        i++;

        if (elem.hasAttribute(bid_attr_name)) {
            all_bids.add(elem.getAttribute(bid_attr_name));
            continue;
        }
        
        // we will mark only standard HTML tags
        if (!elem.tagName || !html_tags.has(elem.tagName.toLowerCase())) {
            continue;  // stop and move on to the next element
        }
        
        // Processing element
        // write dynamic element values to the DOM
        // IMPORTANT: Avoid modifying input/textarea elements to prevent triggering website event handlers
        // that manage form state (like enabling/disabling submit buttons). Modifying the value attribute
        // can trigger mutation observers or event handlers that disable form elements.
        // We skip modifying value attributes on form elements entirely to avoid interfering with website behavior.
        const isFormElement = (elem.tagName && ['INPUT', 'TEXTAREA'].includes(elem.tagName.toUpperCase()));
        const isFocusedInput = document.activeElement === elem && typeof elem.value !== 'undefined';
        
        // Skip modifying value attribute on form elements to avoid triggering website's form state management
        // The website's JavaScript may listen for attribute changes and disable form elements as a result
        if (typeof elem.value !== 'undefined' && !isFormElement && !isFocusedInput) {
            // Only modify value attribute for non-form elements (like output, etc.)
            const currentAttrValue = elem.getAttribute("value");
            const currentPropValue = String(elem.value || "");
            // Only update if different to avoid triggering input events unnecessarily
            if (currentAttrValue !== currentPropValue) {
                try {
                    const originalValue = elem.value;
                    // Set attribute - this might trigger events, but we've skipped form elements
                    elem.setAttribute("value", currentPropValue);
                    // Restore the actual value property if it was changed by setAttribute
                    // (some browsers sync value property when attribute changes)
                    if (elem.value !== originalValue) {
                        elem.value = originalValue;
                    }
                } catch (e) {
                    // Silently ignore errors - attribute setting is best-effort
                    // Log only in debug mode to avoid console spam
                    if (console.debug) {
                        console.debug('Could not set value attribute:', e);
                    }
                }
            }
        }
        // write dynamic checked properties to the DOM
        if (typeof elem.checked !== 'undefined') {
            const currentCheckedAttr = elem.hasAttribute("checked");
            if (elem.checked === true && !currentCheckedAttr) {
                try {
                    elem.setAttribute("checked", "");
                } catch (e) {
                    console.debug('Could not set checked attribute:', e);
                }
            }
            else if (elem.checked === false && currentCheckedAttr) {
                try {
                    elem.removeAttribute("checked");
                } catch (e) {
                    console.debug('Could not remove checked attribute:', e);
                }
            }
        }
        
        // add the element global id to a custom HTML attribute
        // https://playwright.dev/docs/locators#locate-by-test-id
        // recover the element id if it has one already, else compute a new element id
        let elem_global_bid = null;
        let elem_local_id = null;
        // iFrames get alphabetical ids: 'a', 'b', ..., 'z'.
        // if more than 26 iFrames are present, raise an Error
        if (['iframe', 'frame'].includes(elem.tagName.toLowerCase())) {
            elem_local_id = `${window.dom_frame_id_generator.next()}`;
            if (elem_local_id.length > 1) {
                throw new Error(`Maximum 26 iframes supported.`);
            }
        }
        // other elements get numerical ids: '0', '1', '2', ...
        else {
            elem_local_id = `${window.dom_elem_counter++}`;
        }
        if (parent_bid == "") {
            elem_global_bid = `${elem_local_id}`;
        }
        else {
            elem_global_bid = `${parent_bid}${elem_local_id}`;
        }
        elem.setAttribute(bid_attr_name, `${elem_global_bid}`);
        all_bids.add(elem_global_bid);

        let original_content = "";
        if (elem.hasAttribute("aria-roledescription")) {
            original_content = elem.getAttribute("aria-roledescription");
            // Check if this element is already marked by looking for bid prefix
            if (original_content.includes("_") && original_content.split("_")[0].startsWith("bid")) {
                continue; // Skip already marked elements
            }
        }       
        let new_content = `${elem_global_bid}_${original_content}`
        elem.setAttribute("aria-roledescription", new_content);
        
        processedCount++;
    }
    
    console.log('processNewElements finished, processed', processedCount, 'elements');
    return [elementCountBefore, processedCount];
}

/**
 * Built-in MutationObserver function to wait for element changes
 * Much more efficient than manual polling
 */
async function waitForElementChanges(initialCount, maxWaitTime) {
    return new Promise((resolve) => {
        let timeoutId;
        let observer;
        
        // Set timeout fallback
        timeoutId = setTimeout(() => {
            if (observer) observer.disconnect();
            const finalCount = document.querySelectorAll('*').length;
            resolve(finalCount);
        }, maxWaitTime);
        
        // Use MutationObserver to watch for DOM changes
        observer = new MutationObserver((mutations) => {
            const currentCount = document.querySelectorAll('*').length;
            
            // If element count changed, resolve immediately
            if (currentCount !== initialCount) {
                clearTimeout(timeoutId);
                observer.disconnect();
                resolve(currentCount);
            }
        });
        
        // Observe the entire document for changes
        observer.observe(document.body, {
            childList: true,      // Watch for new/removed child elements
            subtree: true,        // Watch the entire DOM tree
            attributes: false,    // Don't watch attribute changes (only structure)
            characterData: false  // Don't watch text changes
        });
    });
  }

function isVideoPlaying(video) {
    return !!(video && !video.paused && !video.ended && video.readyState > 2);
}
