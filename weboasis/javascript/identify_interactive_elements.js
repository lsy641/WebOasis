(args) => {
    // Extract arguments from array (Playwright evaluate only accepts one argument)
    // Handle case where args might be undefined or not an array
    if (!args || !Array.isArray(args)) {
        console.error('[identify_interactive_elements] ERROR: args must be an array');
        return [];
    }
    
    const webagentIdAttribute = args[0];
    const interactiveClassPatterns = args[1];
    try {
        console.log('[identify_interactive_elements] Function called with:', {
            webagentIdAttribute: webagentIdAttribute,
            interactiveClassPatterns: interactiveClassPatterns,
            argsLength: args ? args.length : 0
        });
        
        // MOTIVATION: Making interactive class patterns configurable allows users to customize
        // which CSS class name patterns are used to identify interactive elements (divs/spans).
        // This is useful because:
        // 1. Different web applications use different naming conventions (e.g., 'slidenumber', 'slide-number')
        // 2. Users may want to add domain-specific patterns for their application
        // 3. Users may want to remove patterns that cause false positives in their specific context
        // 4. The default patterns work well for most cases, but customization improves accuracy
        // 
        // The patterns are matched using substring search (classNames.includes(pattern)), so partial
        // matches work (e.g., 'option' matches 'omOption', 'selectOption', etc.)
        
        // Validate webagentIdAttribute
        if (!webagentIdAttribute) {
            console.error('[identify_interactive_elements] ERROR: webagentIdAttribute is required');
            return [];
        }
        
        // Default interactive class patterns
        const defaultInteractiveClassPatterns = [
            'option',      // Option/choice elements (e.g., omOption, selectOption)
            'button',      // Button-like elements (e.g., customButton, btn)
            'clickable',   // Explicitly marked as clickable
            'selectable',  // Selectable items (e.g., selectableItem)
            'choice',      // Choice/selection elements
            'item',        // List/menu items (e.g., menuItem, listItem)
            'card',        // Card elements that are clickable
            'tab',         // Tab elements
            'link',        // Link-like elements
            'menu',        // Menu-related elements
            'dropdown',    // Dropdown elements
            'target'       // Drop target elements (e.g., omTarget, dropTarget)
        ];
        
        // Use provided patterns or default
        // Handle null/undefined from Python None, and ensure it's an array with length > 0
        let classPatterns;
        if (interactiveClassPatterns !== null && 
            interactiveClassPatterns !== undefined &&
            Array.isArray(interactiveClassPatterns) && 
            interactiveClassPatterns.length > 0) {
            classPatterns = interactiveClassPatterns;
            console.log(`[identify_interactive_elements] Using custom class patterns: ${classPatterns.join(', ')}`);
        } else {
            classPatterns = defaultInteractiveClassPatterns;
            console.log(`[identify_interactive_elements] Using default class patterns: ${classPatterns.join(', ')}`);
        }
    
    // Primary interactive elements (highest priority) - defined at top level for reuse
    const primaryInteractiveTags = [
        'button', 'input', 'select', 'textarea', 'a', 'video', 'audio'
    ];
    
    function isInteractive(element) {
        const tag = element.tagName.toLowerCase();
        const type = element.type ? element.type.toLowerCase() : null;
        
        // Iframes should NEVER be marked as interactive - they are containers
        // The interactive elements are inside the iframe, not the iframe itself
        if (tag === 'iframe' || tag === 'frame') {
            return false;
        }
        
        // Conditional interactive elements - interactive only if they don't have interactive children
        // These elements might be interactive, but if they contain interactive children,
        // they're probably just containers and shouldn't be marked as interactive themselves
        // NOTE: We intentionally exclude <label> here, because many labels in this task
        // (e.g., section headings like "Selected Weather Stations") are not true click
        // targets and confuse the web agent if treated as interactive.
        const conditionalInteractiveTags = [
            'summary', 'details', 'dialog', 'option', 'img',  // Secondary interactive elements
            'fieldset', 'datalist', 'output', 'menu',          // Container elements
            'td'
        ];
        
        // Check if element has more specific interactive children
        function hasInteractiveChildren(el) {
            // Treat as interactive children:
            //  - native controls (button, input, select, textarea, a, video, audio)
            //  - anything with an explicit click handler
            //  - elements with interactive ARIA roles (button, checkbox, radio, etc.)
            //  - elements with non-negative tabindex
            //  - divs/span with interactive class patterns
            // This prevents marking wrapper containers (like nav divs) as interactive
            // when they only exist to hold real clickable elements.
            // Note: We exclude slideNumber elements from this check because they are themselves
            // interactive children that should be detected, not containers
            const interactiveRolesSelector = [
                'button', 'input', 'select', 'textarea', 'a', 'video', 'audio',
                '[onclick]',
                '[role="button"]', '[role="checkbox"]', '[role="radio"]',
                '[role="link"]', '[role="menuitem"]', '[role="option"]', '[role="tab"]',
                '[role="slider"]', '[role="spinbutton"]', '[role="combobox"]',
                '[role="textbox"]', '[role="listbox"]', '[role="gridcell"]',
                '[role="row"]', '[role="cell"]', '[role="treeitem"]',
                '[tabindex]:not([tabindex="-1"])'
            ].join(', ');
            const interactiveChildren = el.querySelectorAll(interactiveRolesSelector);
            
            // Also check for divs/span with interactive class patterns
            const patternChildren = el.querySelectorAll(
                '[class*="option"], [class*="target"], [class*="button"], [class*="clickable"], ' +
                '[class*="selectable"], [class*="choice"], [class*="item"], [class*="card"], ' +
                '[class*="tab"], [class*="link"], [class*="menu"], [class*="dropdown"]'
            );
            
            // Also check for slide number elements that are direct children (not nested)
            const slideNumbers = Array.from(el.children).filter(child => {
                const childClass = child.className && typeof child.className === 'string' 
                    ? child.className.toLowerCase() : '';
                return childClass.includes('slidenumber') || childClass.includes('slide-number');
            });
            
            return interactiveChildren.length > 0 || patternChildren.length > 0 || slideNumbers.length > 0;
        }
        
        // Helper function to check if element would have cursor:pointer on hover
        // This checks: inline styles, computed styles, and stylesheet :hover rules
        // Needed because getComputedStyle doesn't show :hover styles unless element is actually hovered
        function wouldShowPointerOnHover(el) {
            // Check 1: Inline style
            if (el.style.cursor === 'pointer' || el.style.cursor === 'grab' || el.style.cursor === 'grabbing') {
                return true;
            }
            
            // Check 2: Computed style (current state - may not include :hover if not hovered)
            const computed = window.getComputedStyle(el);
            if (computed.cursor === 'pointer' || computed.cursor === 'grab' || computed.cursor === 'grabbing') {
                return true;
            }
            
            // Check 3: Check stylesheets for :hover rules that would apply
            // This is a heuristic - we check if any stylesheet rule matches this element and has cursor:pointer in :hover
            try {
                const sheets = document.styleSheets;
                for (let i = 0; i < sheets.length; i++) {
                    try {
                        const rules = sheets[i].cssRules || sheets[i].rules;
                        if (!rules) continue;
                        
                        for (let j = 0; j < rules.length; j++) {
                            const rule = rules[j];
                            // Check for :hover rules
                            if (rule.selectorText && rule.selectorText.includes(':hover')) {
                                // Check if this element matches the selector (without :hover)
                                const baseSelector = rule.selectorText.replace(':hover', '').trim();
                                try {
                                    // Try to match - if element matches and rule has cursor:pointer
                                    if (el.matches && el.matches(baseSelector)) {
                                        const styleText = rule.style ? rule.style.cssText : '';
                                        if (styleText.includes('cursor') && 
                                            (styleText.includes('pointer') || styleText.includes('grab'))) {
                                            return true;
                                        }
                                    }
                                } catch (e) {
                                    // Selector might be invalid, skip
                                }
                            }
                        }
                    } catch (e) {
                        // Cross-origin stylesheet, skip
                    }
                }
            } catch (e) {
                // Can't access stylesheets, skip
            }
            
            return false;
        }
        
        // Primary interactive elements - always return true
        if (primaryInteractiveTags.includes(tag)) {
            return true;
        }
        
        // Define tabIndex early so it can be used in checks below
        const tabIndex = element.tabIndex;

        // For <label>, treat it as interactive only when it clearly acts as a control:
        //  - it is associated via `for=` with an underlying input/select/etc.
        //  - OR later generic signals (tabindex/onclick) mark it interactive.
        // Plain static labels (section headings) should not be interactive.
        if (tag === 'label') {
            const forId = element.getAttribute('for');
            if (forId) {
                const target = document.getElementById(forId);
                if (target) {
                    const targetTag = target.tagName.toLowerCase();
                    if (primaryInteractiveTags.includes(targetTag)) {
                        return true;
                    }
                }
            }
            // Otherwise fall through and let generic tabindex/onclick logic decide.
        }

        // Special-case: images should only be interactive if they have actual interactive signals
        // Regular images (like slide images) are not clickable unless they have onclick, href, cursor pointer, etc.
        if (tag === 'img') {
            // Known non-interactive preview avatar image
            const idLower = (element.id || '').toLowerCase();
            const classLowerForImg = (typeof element.className === 'string'
                ? element.className.toLowerCase()
                : '');
            if (idLower === 'studentavatar' || classLowerForImg.includes('studentavatar')) {
                return false;
            }
            
            // Check if image has actual interactive signals
            // Images should only be interactive if they have: onclick, href (in parent <a>), cursor pointer, role, etc.
            const hasOnclick = typeof element.onclick === 'function' || element.getAttribute('onclick');
            const hasHref = element.closest('a') && element.closest('a').hasAttribute('href');
            const role = element.getAttribute('role');
            const hasRole = role && ['button', 'link'].includes(role.toLowerCase());
            const hasCursorPointer = wouldShowPointerOnHover(element);
            const hasTabIndex = tabIndex >= 0;
            
            // Only mark as interactive if it has at least one interactive signal
            // If it has signals, continue to normal checks (hasInteractiveChildren, etc.)
            // If it doesn't have signals, it's just a regular image - not clickable
            if (!hasOnclick && !hasHref && !hasRole && !hasCursorPointer && !hasTabIndex) {
                return false; // Regular image without interactive signals - not clickable
            }
            // If it has signals, fall through to secondaryInteractiveTags check below
        }

        // Image map AREA elements: treat as interactive if they have an href or click handler.
        // Their visual region is handled by the associated <img usemap="...">; AREA itself often
        // has zero-sized bounding boxes, so we handle visibility later specially.
        if (tag === 'area') {
            if (element.getAttribute('href') || typeof element.onclick === 'function' || element.getAttribute('onclick')) {
                return true;
            }
        }
        
        // Conditional interactive elements - interactive only if they don't have interactive children
        // NOTE: Images are handled separately above and require interactive signals before reaching here
        // SPECIAL CASE: <td> elements - if they contain interactive children, mark the <td> as interactive
        // (the whole cell is clickable, not just the children)
        if (conditionalInteractiveTags.includes(tag)) {
            // Special handling for <td>: if it has interactive children, mark it as interactive
            // (the whole cell acts as a clickable area)
            if (tag === 'td') {
                if (hasInteractiveChildren(element)) {
                    return true; // Mark <td> as interactive if it contains interactive children
                }
                // If <td> has no interactive children, check if it has other interactive signals
                // (like onclick, cursor pointer, etc.)
                const hasOnclick = typeof element.onclick === 'function' || element.getAttribute('onclick');
                const hasCursorPointer = wouldShowPointerOnHover(element);
                const hasTabIndex = tabIndex >= 0;
                if (hasOnclick || hasCursorPointer || hasTabIndex) {
                    return true;
                }
                return false; // <td> with no interactive signals is not interactive
            }
            // For other conditional interactive elements, if they have interactive children,
            // they're probably just containers and shouldn't be marked as interactive
            if (hasInteractiveChildren(element)) {
                return false;
            }
            return true;
        }
        
        // Other interactive checks
        // Check tabindex - but only if it's >= 0 (tabindex="-1" means NOT keyboard accessible)
        // Note: tabIndex is already defined above
        if (tabIndex >= 0) return true;
        
        if (element.getAttribute('contenteditable') === 'true') return true;
        if (typeof element.onclick === 'function') return true;
        if (element.getAttribute('onclick')) return true;
        
        // Check for draggable elements (drag and drop functionality)
        if (element.getAttribute('draggable') === 'true') return true;
        
        // General check for clickable divs: look for data attributes that suggest interactivity
        // Many frameworks use data attributes like data-testid, data-action, data-click, etc.
        const dataAttrs = Array.from(element.attributes)
            .filter(attr => attr.name.startsWith('data-'))
            .map(attr => attr.name.toLowerCase());
        const interactiveDataAttrs = ['data-click', 'data-action', 'data-handler', 'data-interactive', 
                                      'data-selectable', 'data-toggle', 'data-target', 'data-bs-toggle'];
        if (interactiveDataAttrs.some(attr => dataAttrs.includes(attr))) {
            if (!hasInteractiveChildren(element)) {
                return true;
            }
        }
        
        // Check for common interactive ARIA roles
        // Elements with interactive roles should be identified, even if they have non-interactive children
        const role = element.getAttribute('role');
        const interactiveRoles = ['button', 'link', 'menuitem', 'option', 'tab', 'radio', 'checkbox', 
                                  'slider', 'spinbutton', 'combobox', 'textbox', 'listbox', 'gridcell',
                                  'row', 'cell', 'treeitem'];
        if (role && interactiveRoles.includes(role.toLowerCase())) {
            // Elements with interactive roles are interactive themselves
            // Only filter them out if they contain OTHER interactive elements (not just presentation/structural children)
            // This ensures elements like <span role="checkbox"> are identified even if they have <div role="presentation"> children
            if (!hasInteractiveChildren(element)) {
                return true;
            }
            // Even if it has interactive children, if it has an interactive role AND tabindex/onclick,
            // it should still be identified (it's both a container and interactive itself)
            // But we'll prefer the children in the containment filter
            const hasDirectInteractiveSignals = tabIndex >= 0 || 
                typeof element.onclick === 'function' || 
                element.getAttribute('onclick');
            if (hasDirectInteractiveSignals) {
                return true; // Identify it - containment filter will handle parent/child priority
            }
        }
        
        // Check for elements with event listeners attached (general interactivity indicator)
        // This is a heuristic - elements with click/drag handlers are likely interactive
        // Note: We can't easily detect addEventListener, but we can check for common patterns
        if (element.getAttribute('ondragstart') || element.getAttribute('ondrag') || 
            element.getAttribute('ondrop') || element.getAttribute('ondragover')) {
            if (!hasInteractiveChildren(element)) {
                return true;
            }
        }
        
        // General check for clickable divs/span: primary check is cursor pointer (hovering handler)
        // This is the most reliable general indicator of interactivity
        if (tag === 'div' || tag === 'span') {
            // Check class names for common interactive patterns
            // These patterns help detect clickable divs/span elements that may not have
            // cursor: pointer in their CSS but are clearly interactive based on naming conventions
            const classNames = (element.className && typeof element.className === 'string')
                ? element.className.toLowerCase() : '';
            // Use the configurable class patterns (from parameter or default)
            const hasInteractiveClass = classPatterns.some(pattern => 
                classNames.includes(pattern)
            );
            
            // If it has an interactive class pattern, check if it's not just a container
            if (hasInteractiveClass && !hasInteractiveChildren(element)) {
                const rect = element.getBoundingClientRect();
                const area = rect.width * rect.height;
                if (area > 0) {
                    // Additional check: not too large (likely a container)
                    // For "target", "option", and "slidenumber" elements, be more lenient with size (they're often small interactive elements)
                    const isTargetOrOptionOrSlide = classNames.includes('target') || classNames.includes('option') || 
                                                     classNames.includes('slidenumber') || classNames.includes('slide-number');
                    const viewportArea = (window.innerWidth || document.documentElement.clientWidth) * 
                                       (window.innerHeight || document.documentElement.clientHeight);
                    const sizeThreshold = isTargetOrOptionOrSlide ? 0.8 : 0.5; // More lenient for target/option/slidenumber elements
                    if (area < viewportArea * sizeThreshold) {
                    return true;
                }
            }
        }
        
            try {
                const style = window.getComputedStyle(element);
                // Primary check: cursor pointer/hand indicates interactivity
                // Check if element would show pointer cursor on hover (even if not currently hovered)
                if (wouldShowPointerOnHover(element) || style.cursor === 'pointer' || style.cursor === 'grab' || style.cursor === 'grabbing') {
                    // Check if element has independent interactive signals (tabindex, onclick, role, etc.)
                    const dataAttrs = Array.from(element.attributes)
                        .filter(attr => attr.name.startsWith('data-'))
                        .map(attr => attr.name.toLowerCase());
                    const interactiveDataAttrs = ['data-click', 'data-action', 'data-handler', 'data-interactive', 
                                                  'data-selectable', 'data-toggle', 'data-target', 'data-bs-toggle'];
                    const role = element.getAttribute('role');
                    const interactiveRoles = ['button', 'link', 'menuitem', 'option', 'tab', 'radio', 'checkbox', 
                                              'slider', 'spinbutton', 'combobox', 'textbox', 'listbox', 'gridcell',
                                              'row', 'cell', 'treeitem'];
                    const hasIndependentSignals = 
                        tabIndex >= 0 ||
                        element.getAttribute('contenteditable') === 'true' ||
                        typeof element.onclick === 'function' ||
                        element.getAttribute('onclick') ||
                        element.getAttribute('draggable') === 'true' ||
                        (role && interactiveRoles.includes(role.toLowerCase())) ||
                        interactiveDataAttrs.some(attr => dataAttrs.includes(attr));
                    
                    // Cursor pointer is a strong signal - trust it if element is reasonably sized
                    const rect = element.getBoundingClientRect();
                    const area = rect.width * rect.height;
                    if (area > 0) {
                        const viewportArea = (window.innerWidth || document.documentElement.clientWidth) * 
                                           (window.innerHeight || document.documentElement.clientHeight);
                        
                        // If it has independent signals, always trust it (regardless of children)
                        if (hasIndependentSignals) {
                            if (area < viewportArea * 0.8) {
                                return true;
                            }
                        }
                        // If no independent signals, trust cursor pointer for reasonably sized elements
                        // Small elements (< 50% viewport) are likely interactive even if they have children
                        // Medium elements (< 60% viewport) are interactive if they have no interactive children
                        else {
                            const hasChildren = hasInteractiveChildren(element);
                            if (area < viewportArea * 0.5) {
                                // Small/medium elements with cursor pointer are likely interactive
                                // Trust the cursor signal - if computed style shows pointer, it will show pointer on hover
                                return true;
                            } else if (!hasChildren && area < viewportArea * 0.6) {
                                // Larger elements without children are interactive
                                return true;
                            }
                        }
                    }
                }
                // Secondary check: user-select: none with pointer cursor is a common pattern for clickable divs
                const userSelect = style.userSelect || style.webkitUserSelect || style.mozUserSelect || style.msUserSelect;
                if (userSelect === 'none' && (style.cursor === 'pointer' || style.cursor === 'grab')) {
                    if (!hasInteractiveChildren(element)) {
                        const rect = element.getBoundingClientRect();
                        const area = rect.width * rect.height;
                        if (area > 0) {
                            const viewportArea = (window.innerWidth || document.documentElement.clientWidth) * 
                                               (window.innerHeight || document.documentElement.clientHeight);
                            if (area < viewportArea * 0.8) {
                    return true;
                            }
                        }
                    }
                }
            } catch (e) {
                // If we can't get computed style, skip this check
            }
        }
        
        // General cursor pointer check for all elements (not just divs)
        try {
            const style = window.getComputedStyle(element);
            // Check if element would show pointer cursor on hover (even if not currently hovered)
            if (wouldShowPointerOnHover(element) || style.cursor === 'pointer' || style.cursor === 'grab' || style.cursor === 'grabbing' || style.cursor === 'move') {
                // Check if element has independent interactive signals
                const dataAttrs = Array.from(element.attributes)
                    .filter(attr => attr.name.startsWith('data-'))
                    .map(attr => attr.name.toLowerCase());
                const interactiveDataAttrs = ['data-click', 'data-action', 'data-handler', 'data-interactive', 
                                              'data-selectable', 'data-toggle', 'data-target', 'data-bs-toggle'];
                const role = element.getAttribute('role');
                const interactiveRoles = ['button', 'link', 'menuitem', 'option', 'tab', 'radio', 'checkbox', 
                                          'slider', 'spinbutton', 'combobox', 'textbox', 'listbox', 'gridcell',
                                          'row', 'cell', 'treeitem'];
                const hasIndependentSignals = 
                    tabIndex >= 0 ||
                    element.getAttribute('contenteditable') === 'true' ||
                    typeof element.onclick === 'function' ||
                    element.getAttribute('onclick') ||
                    element.getAttribute('draggable') === 'true' ||
                    (role && interactiveRoles.includes(role.toLowerCase())) ||
                    interactiveDataAttrs.some(attr => dataAttrs.includes(attr));
                
                // Cursor pointer is a very strong signal - trust it if element is reasonably sized
                // getComputedStyle already tells us what cursor would appear on hover
                    const rect = element.getBoundingClientRect();
                    const area = rect.width * rect.height;
                if (area > 0) {
                    const viewportArea = (window.innerWidth || document.documentElement.clientWidth) * 
                                       (window.innerHeight || document.documentElement.clientHeight);
                    
                    // If it has independent signals, always trust it (regardless of children)
                    if (hasIndependentSignals) {
                        if (area < viewportArea * 0.8) {
                            return true;
                        }
                    }
                    // If no independent signals, trust cursor pointer for reasonably sized elements
                    // Small elements (< 40% viewport) are likely interactive even if they have children
                    // Medium elements (< 60% viewport) are interactive if they have no interactive children
                    else {
                        const hasChildren = hasInteractiveChildren(element);
                        if (area < viewportArea * 0.4) {
                            // Small elements with cursor pointer are likely interactive
                            return true;
                        } else if (!hasChildren && area < viewportArea * 0.6) {
                            // Medium elements without children are interactive
            return true;
                        }
                    }
                }
            }
        } catch (e) {
            // If we can't get computed style, skip this check
        }
        
        // Check if element can be focused - but only if tabIndex >= 0
        if (typeof element.focus === 'function' && tabIndex >= 0) return true;
        
        return false;
    }

    function isElementNotOverlapped(element) {
        const rect = element.getBoundingClientRect();
        const test_id = element.getAttribute(webagentIdAttribute);
        
        // Skip elements with zero or negative dimensions
        if (rect.width <= 0 || rect.height <= 0) {
            return false;
        }
        
        // Test a grid of points across the element to detect overlap more accurately
        // Use more points for larger elements, fewer for smaller ones
        const gridSize = Math.max(3, Math.min(7, Math.floor(Math.min(rect.width, rect.height) / 20)));
        const testPoints = [];
        
        // Generate a grid of test points
        for (let i = 0; i <= gridSize; i++) {
            for (let j = 0; j <= gridSize; j++) {
                const x = rect.left + (rect.width * i / gridSize);
                const y = rect.top + (rect.height * j / gridSize);
                // Skip points too close to edges (avoid border/outline issues)
                if (i > 0 && i < gridSize && j > 0 && j < gridSize) {
                    testPoints.push([x, y]);
                } else if (i === 0 || i === gridSize || j === 0 || j === gridSize) {
                    // For edge points, add a small offset to avoid borders
                    const offsetX = i === 0 ? 2 : (i === gridSize ? -2 : 0);
                    const offsetY = j === 0 ? 2 : (j === gridSize ? -2 : 0);
                    testPoints.push([x + offsetX, y + offsetY]);
                }
            }
        }
        
        let visiblePoints = 0;
        const totalPoints = testPoints.length;
        
        if (totalPoints === 0) {
            return false; // No valid test points
        }
        
        for (const [x, y] of testPoints) {
            const elementAtPoint = document.elementFromPoint(x, y);
            
            // Check if our element is at this point or contains it
            if (elementAtPoint === element || 
                elementAtPoint?.closest(`[${webagentIdAttribute}="${test_id}"]`) === element) {
                visiblePoints++;
            }
        }
        
        // Element is considered visible if at least 50% of test points are accessible
        // This threshold ensures elements significantly covered by other elements are filtered out
        const visibilityRatio = visiblePoints / totalPoints;
        const threshold = 0.8; // 50% visibility threshold
        return visibilityRatio >= threshold;
    }
    
    // Helper to decide if a child is a "viable" interactive replacement for its parent.
    // We only want to drop a parent in favor of children that are themselves interactive
    // AND would survive our visibility/overlap filters. This prevents cases where all
    // children are effectively non-clickable (e.g., tiny/overlapped spans), in which
    // case we should keep the parent as the best interactive target.
    function isInteractiveChildViable(child) {
        if (!child) return false;
        if (!isInteractive(child)) return false;
        if (!isElementFullyVisible(child)) return false;
        if (!isElementNotOverlapped(child)) return false;
        return true;
    }
    
    function isElementFullyVisible(element) {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        
        // Check CSS properties that might hide the element
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
            return false;
        }
        
        // Check if element has zero dimensions
        // For very small elements (like radio button labels), allow tiny dimensions
        // as they might be clickable even if small
        if (rect.width <= 0 || rect.height <= 0) {
            return false;
        }
        
        // Check if element is outside viewport
        if (rect.right < 0 || rect.bottom < 0 || rect.left > window.innerWidth || rect.top > window.innerHeight) {
            return false;
        }
        
        // Check if element is disabled
        if (element.disabled || element.hasAttribute('disabled')) {
            return false;
        }
        
        // Check for disabled classes
        if (element.className && typeof element.className === 'string' && 
            element.className.includes('disabled')) {
            return false;
        }
        
        // Check for grayed out appearance (but allow disabled elements)
        // Note: aria-hidden doesn't affect visibility for clickability - elements can be
        // aria-hidden but still clickable (like decorative radio button visuals)
        if (style.opacity && parseFloat(style.opacity) < 0.5 && !element.disabled && !element.hasAttribute('disabled')) {
            return false;
        }
        
        return true;
    }

    // Unmark any previously marked interactive elements (attribute-based)
    // This is critical to ensure disabled elements from previous runs don't remain marked
    const previouslyMarked = document.querySelectorAll('[webagent-interactive-elem]');
    console.log(`[identify_interactive_elements] Removing ${previouslyMarked.length} previously marked elements`);
    previouslyMarked.forEach(el => {
        el.removeAttribute('webagent-interactive-elem');
    });

    // Simple console logging - will be captured by Playwright's console listener
    console.log('[identify_interactive_elements] Starting to identify interactive elements...');

    // Helper function to check if element is disabled - use this consistently everywhere
    function isElementDisabled(element) {
        if (!element) return false;
        
        const tag = element.tagName.toLowerCase();
        const isPrimaryInteractive = primaryInteractiveTags.includes(tag);
        
        if (!isPrimaryInteractive) return false;
        
        // Check 1: hasAttribute - most reliable, works even for empty attributes like disabled=""
        if (element.hasAttribute('disabled')) {
            return true;
        }
        
        // Check 2: disabled property - handle all truthy values
        if (element.disabled === true || element.disabled === '') {
            return true;
        }
        
        // Check 3: getAttribute - explicit check for disabled attribute
        if (element.getAttribute('disabled') !== null) {
            return true;
        }
        
        // Check 4: aria-disabled attribute
        if (element.getAttribute('aria-disabled') === 'true') {
            disabledReason = 'aria-disabled="true"';
            return true;
        }
        
        // Check 5: disabled classes (like "disabled", "disabledButton", but NOT "btnSubmit.disabled")
        const className = element.className;
        if (className && typeof className === 'string') {
            const classList = className.split(/\s+/);
            const hasClearDisabledClass = classList.some(cls => {
                const clsLower = cls.toLowerCase();
                return clsLower === 'disabled' || 
                       clsLower === 'disabledbutton' ||
                       clsLower === 'is-disabled' ||
                       clsLower.startsWith('disabled-') ||
                       clsLower.endsWith('-disabled') ||
                       (clsLower.includes('disabled') && !clsLower.includes('.') && 
                        (clsLower.includes('btn') || clsLower.includes('button')));
            });
            if (hasClearDisabledClass) {

                return true;
            }
        }
        
        
        return false;
    }

    var vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
    var vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);

    var items = Array.prototype.slice
        .call(document.querySelectorAll("*"))
        .map(function (element) {
            var test_id = element.getAttribute(webagentIdAttribute) || "";
            if (element.hasAttribute('developer_elem')) {
                return null;
            }
            
            // Enhanced filtering: check interactivity, visibility, and overlap
            if (test_id === "" || !isInteractive(element)) {
                return null;
            }
            
            const tag = element.tagName.toLowerCase();
            const isPrimaryInteractive = primaryInteractiveTags.includes(tag);

            // Special-case: <area> elements in image maps typically have 0-sized DOM rects and will
            // fail normal visibility / overlap / geometry checks. If it is interactive (href/onclick)
            // and has a test_id, include it with a forced non-zero area.
            if (tag === 'area') {
                return {
                    include: true,
                    area: 100,
                    rects: [],
                    text: (element.getAttribute("title") || element.getAttribute("alt") || "").trim(),
                    type: 'area',
                    ariaLabel: element.getAttribute("aria-label") || "",
                    test_id: test_id,
                    tag: 'area',
                    id: element.id || null,
                    class: typeof element.className === 'string' ? element.className : null,
                    href: element.getAttribute("href") || null,
                    title: element.getAttribute("title") || null,
                    value: null
                };
            }
            
            // CRITICAL: Check for disabled state FIRST, before any other processing
            // Use the helper function to ensure consistency
            if (isElementDisabled(element)) {
                return null;
            }

            
            // Early filter: If element is not a primary interactive element and has interactive children,
            // filter it out immediately (it's likely a container, not the actual interactive element)
            // This is critical to ensure children are identified instead of parents
            // NOTE: Iframes are already excluded in isInteractive(), but we add an extra check here for safety
            // EXCEPTION 1: Labels associated with inputs via `for` attribute should NOT be filtered out,
            // because clicking the label is a valid way to interact with the input
            // EXCEPTION 2: <td> elements that contain interactive children should be marked as interactive
            // themselves (the whole cell is clickable), so we don't filter them out here
            if (!isPrimaryInteractive && tag !== 'iframe' && tag !== 'frame' && tag !== 'td') {
                // Special case: Labels with `for` attribute pointing to an input should not be filtered out
                // even if the input is also interactive, because clicking the label is a valid interaction
                if (tag === 'label') {
                    const forId = element.getAttribute('for');
                    if (forId) {
                        const target = document.getElementById(forId);
                        if (target) {
                            const targetTag = target.tagName.toLowerCase();
                            // If label is associated with an input via `for`, keep the label
                            // Both label and input can be interactive - clicking label activates input
                            if (['input', 'select', 'textarea', 'button'].includes(targetTag)) {
                                // Don't filter out this label - it's a valid interactive element
                                // Continue to visibility/overlap checks
                            } else {
                                // Label points to non-interactive element, check for interactive children
                                const interactiveRolesSelector = [
                                    'button', 'input', 'select', 'textarea', 'a',
                                    '[role="button"]', '[role="checkbox"]', '[role="radio"]',
                                    '[role="link"]', '[role="menuitem"]', '[role="option"]', '[role="tab"]',
                                    '[role="slider"]', '[role="spinbutton"]', '[role="combobox"]',
                                    '[role="textbox"]', '[role="listbox"]', '[role="gridcell"]',
                                    '[role="row"]', '[role="cell"]', '[role="treeitem"]',
                                    '[tabindex]:not([tabindex="-1"])'
                                ].join(', ');
                                const interactiveChildren = element.querySelectorAll(interactiveRolesSelector);
                                const hasInteractiveChildrenWithTestId = Array.from(interactiveChildren).some(child => {
                                    return child.hasAttribute(webagentIdAttribute) &&
                                           child.getAttribute(webagentIdAttribute) &&
                                           isInteractiveChildViable(child);
                                });
                                if (hasInteractiveChildrenWithTestId) {
                                    return null; // Filter out label that contains interactive children
                                }
                            }
                        }
                    } else {
                        // Label without `for` attribute - check if it contains interactive children
                        const interactiveRolesSelector = [
                            'button', 'input', 'select', 'textarea', 'a',
                            '[role="button"]', '[role="checkbox"]', '[role="radio"]',
                            '[role="link"]', '[role="menuitem"]', '[role="option"]', '[role="tab"]',
                            '[role="slider"]', '[role="spinbutton"]', '[role="combobox"]',
                            '[role="textbox"]', '[role="listbox"]', '[role="gridcell"]',
                            '[role="row"]', '[role="cell"]', '[role="treeitem"]',
                            '[tabindex]:not([tabindex="-1"])'
                        ].join(', ');
                        const interactiveChildren = element.querySelectorAll(interactiveRolesSelector);
                        const hasInteractiveChildrenWithTestId = Array.from(interactiveChildren).some(child => {
                            return child.hasAttribute(webagentIdAttribute) &&
                                   child.getAttribute(webagentIdAttribute) &&
                                   isInteractiveChildViable(child);
                        });
                        if (hasInteractiveChildrenWithTestId) {
                            return null; // Filter out label that contains interactive children
                        }
                    }
                } else {
                    // Not a label - apply normal containment filter
                    const interactiveRolesSelector = [
                        'button', 'input', 'select', 'textarea', 'a',
                        '[role="button"]', '[role="checkbox"]', '[role="radio"]',
                        '[role="link"]', '[role="menuitem"]', '[role="option"]', '[role="tab"]',
                        '[role="slider"]', '[role="spinbutton"]', '[role="combobox"]',
                        '[role="textbox"]', '[role="listbox"]', '[role="gridcell"]',
                        '[role="row"]', '[role="cell"]', '[role="treeitem"]',
                        '[tabindex]:not([tabindex="-1"])'
                    ].join(', ');
                    const interactiveChildren = element.querySelectorAll(interactiveRolesSelector);
                    // Filter out parent if it has interactive children with test_id (they should be identified instead)
                    // Check if any of the interactive children have the test_id attribute (they're in our scope)
                    const hasInteractiveChildrenWithTestId = Array.from(interactiveChildren).some(child => {
                        return child.hasAttribute(webagentIdAttribute) && child.getAttribute(webagentIdAttribute);
                    });
                    if (hasInteractiveChildrenWithTestId) {
                        return null; // Filter out parent - children will be identified instead
                    }
                }
            }
            
            // Check visibility - for primary interactive elements, be lenient but still check viewport
            if (isPrimaryInteractive) {
                // For primary interactive elements, check if truly hidden
                const style = window.getComputedStyle(element);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                    return null;
                }
                // Check if element has zero dimensions
                const rect = element.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) {
                    return null;
                }
                
                // CRITICAL: Check if element is actually in the viewport/visible on current page
                // Elements from previous pages might still be in DOM but outside viewport
                // Element must have at least some part visible in the viewport
                // Check if element is completely outside viewport
                if (rect.right < 0 || rect.bottom < 0 || rect.left > vw || rect.top > vh) {
                    return null; // Element is completely outside viewport
                }
                
                // Additional check: element should have some visible area in viewport
                // Calculate intersection of element rect with viewport
                const visibleLeft = Math.max(0, rect.left);
                const visibleTop = Math.max(0, rect.top);
                const visibleRight = Math.min(vw, rect.right);
                const visibleBottom = Math.min(vh, rect.bottom);
                const visibleWidth = Math.max(0, visibleRight - visibleLeft);
                const visibleHeight = Math.max(0, visibleBottom - visibleTop);
                const visibleArea = visibleWidth * visibleHeight;
                
                // Element must have at least 10 pixels of visible area in viewport
                if (visibleArea < 10) {
                    return null; // Element has no meaningful visible area in viewport
                }
                
                // CRITICAL: Check overlap for primary interactive elements too
                // Elements significantly covered (>50%) by other elements should not be identified as interactive
                if (!isElementNotOverlapped(element)) {
                    return null; // Element is too overlapped to be reliably interactive
                }
                
                // Note: Disabled check (including disabled classes) is already done earlier
            } else {
                // For non-primary interactive elements, use strict checks
                if (!isElementFullyVisible(element) || !isElementNotOverlapped(element)) {
                    return null;
                }
            }
            
            // Filter rects by center point accessibility (for all elements)
            // This checks if the center point is actually on the element (not overlapped)
            var rects = [...element.getClientRects()]
                .filter((bb) => {
                    var center_x = bb.left + bb.width / 2;
                    var center_y = bb.top + bb.height / 2;
                    var elAtCenter = document.elementFromPoint(center_x, center_y);
                    // Check if the element at center is our element or a child of our element
                    if (elAtCenter === element) {
                        return true;
                    }
                    // Check if element at center is within our element (using test_id selector)
                    if (elAtCenter && test_id) {
                        const closest = elAtCenter.closest(`[${webagentIdAttribute}="${test_id}"]`);
                        if (closest === element) {
                            return true;
                        }
                    }
                    return false;
                })
                .map((bb) => {
                    const rect = {
                        left: Math.max(0, bb.left),
                        top: Math.max(0, bb.top),
                        right: Math.min(vw, bb.right),
                        bottom: Math.min(vh, bb.bottom),
                    };
                    return {
                        ...rect,
                        width: rect.right - rect.left,
                        height: rect.bottom - rect.top,
                    };
                });
            
            // If no rects passed the center-point check, but it's a primary interactive element,
            // use all rects anyway (element might be partially overlapped but still interactive)
            if (rects.length === 0 && isPrimaryInteractive) {
                rects = [...element.getClientRects()].map((bb) => {
                    const rect = {
                        left: Math.max(0, bb.left),
                        top: Math.max(0, bb.top),
                        right: Math.min(vw, bb.right),
                        bottom: Math.min(vh, bb.bottom),
                    };
                    return {
                        ...rect,
                        width: rect.right - rect.left,
                        height: rect.bottom - rect.top,
                    };
                });
            }
            
            var area = rects.reduce((acc, rect) => acc + rect.width * rect.height, 0);
            // For <area> elements in image maps, the DOM rects are often zero-sized.
            // We still want to expose them as interactive (agent can click by test_id),
            // so if this is an AREA with test_id, force a minimal non-zero area.
            if (element.tagName.toLowerCase() === 'area' && test_id) {
                area = Math.max(area, 100);
            }
            return {
                include: true,
                area: area,
                rects: rects,
                text: element.textContent.trim().replace(/\\s{2,}/g, " "),
                type: element.tagName.toLowerCase(),
                ariaLabel: element.getAttribute("aria-label") || "",
                test_id: test_id,
                tag: element.tagName.toLowerCase(),
                id: element.id || null,
                class: typeof element.className === 'string' ? element.className : null,
                href: element.getAttribute("href") || null,
                title: element.getAttribute("title") || null,
                value: typeof element.value === 'string' ? element.value : null
            };
        })
        .filter((item) => item !== null && item.area >= 10);
   

    // Robust containment filter - prioritize interactive children over parents
    // Rule: If a parent element contains interactive children, filter out the parent (keep children)
    items = items.filter((x) => {
        const xElem = document.querySelector(`[${webagentIdAttribute}="${x.test_id}"]`);
        if (!xElem) return false;
        
        const tag = x.tag || xElem.tagName.toLowerCase();
        
        // Iframes should NEVER be in the interactive elements list - they are containers
        // The interactive elements are inside the iframe, not the iframe itself
        if (tag === 'iframe' || tag === 'frame') {
            return false;
        }
        
        const isPrimaryInteractive = ['input', 'textarea', 'button', 'select', 'a'].includes(tag);
        
        // Check if this element is contained by another interactive element in items
        // If both parent and child are interactive, prefer the child (more specific)
        // BUT: Don't filter out elements with "target", "option", or "slidenumber" classes even if contained,
        // as they are specific interactive targets that should be clickable
        const xClassNames = (xElem.className && typeof xElem.className === 'string')
            ? xElem.className.toLowerCase() : '';
        const isTargetOrOptionOrSlide = xClassNames.includes('target') || xClassNames.includes('option') || 
                                         xClassNames.includes('slidenumber') || xClassNames.includes('slide-number');
        
        // Check if x is contained by another element y in items
        // If both are interactive, we want to keep the child (x) and filter out the parent (y)
        // So we don't filter out x here - instead, we'll filter out y in the "contains" check below
        // Only filter out x if it's not a special case (target/option/slidenumber)
        const isContained = items.some((y) => {
            if (x === y) return false;
            const yElem = document.querySelector(`[${webagentIdAttribute}="${y.test_id}"]`);
            if (!yElem) return false;
            // If x is a target/option/slidenumber element, don't filter it out even if contained by parent
            if (isTargetOrOptionOrSlide) return false;
            // Check if y contains x (y is parent of x)
            // If both are interactive, we prefer the child, so don't filter out x here
            // The parent y will be filtered out in the "contains" check
            return false; // Don't filter out children - filter out parents instead
        });
        // Note: We're not using isContained to filter here - we want to keep children
        
        // CRITICAL: Check if this element contains other interactive elements
        // If it does, filter it out (we want the child elements, not the parent)
        // This ensures children are identified instead of parents
        // EXCEPTION: <td> elements - if a <td> is interactive, keep it and filter out its children
        // (the whole cell is clickable, not individual children)
        
        // First, check if it contains other elements in the items list
        const containsInteractiveInItems = items.some((y) => {
            if (x === y) return false;
            const yElem = document.querySelector(`[${webagentIdAttribute}="${y.test_id}"]`);
            if (!yElem) return false;
            // Check if xElem contains yElem (x is parent of y)
            if (xElem.contains(yElem) && xElem !== yElem) {
                // Special case: If x is a <td> and contains y, keep the <td> (don't filter it out)
                // The child y will be filtered out in the check below
                if (tag === 'td') {
                    return false; // Don't filter out the <td> - we'll filter out the child instead
                }
                // If x contains y (both are in items), filter out x (the parent)
                // This ensures we identify children instead of parents
                return true;
            }
            return false;
        });
        if (containsInteractiveInItems) return false;
        
        // Special case for <td>: If this element is a child of a <td> that's in the items list,
        // filter out this child (we want the <td> itself, not its children)
        if (tag !== 'td') {
            const parentTd = xElem.closest('td');
            if (parentTd) {
                const parentTdTestId = parentTd.getAttribute(webagentIdAttribute);
                if (parentTdTestId) {
                    // Check if the parent <td> is in the items list
                    const parentTdInItems = items.some((y) => {
                        if (x === y) return false;
                        return y.test_id === parentTdTestId;
                    });
                    if (parentTdInItems) {
                        return false; // Filter out this child - the parent <td> is interactive
                    }
                }
            }
        }
        
        // Additional check: if element is not primary interactive, check if it has any interactive children in DOM
        // (not just in the items list, but any interactive children with test_id)
        // If it has interactive children with test_id, filter it out (prefer children)
        // EXCEPTION 1: Labels associated with inputs via `for` attribute should NOT be filtered out,
        // because clicking the label is a valid way to interact with the input
        // EXCEPTION 2: <td> elements that contain interactive children should be marked as interactive
        // themselves (the whole cell is clickable), so we don't filter them out here
        if (!isPrimaryInteractive && tag !== 'td') {
            // Special case: Labels with `for` attribute pointing to an input should not be filtered out
            // even if the input is also interactive, because clicking the label is a valid interaction
            if (tag === 'label') {
                const forId = xElem.getAttribute('for');
                if (forId) {
                    const target = document.getElementById(forId);
                    if (target) {
                        const targetTag = target.tagName.toLowerCase();
                        // If label is associated with an input via `for`, keep the label
                        // Both label and input can be interactive - clicking label activates input
                        if (['input', 'select', 'textarea', 'button'].includes(targetTag)) {
                            // Don't filter out this label - it's a valid interactive element
                            // The input might also be in the list, but that's okay - both are valid
                            return true;
                        }
                    }
                }
            }
            
            // Check for all interactive roles, not just button and link
            const interactiveRolesSelector = [
                'button', 'input', 'select', 'textarea', 'a',
                '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="radio"]',
                '[role="menuitem"]', '[role="option"]', '[role="tab"]',
                '[role="slider"]', '[role="spinbutton"]', '[role="combobox"]',
                '[role="textbox"]', '[role="listbox"]', '[role="gridcell"]',
                '[role="row"]', '[role="cell"]', '[role="treeitem"]',
                '[tabindex]:not([tabindex="-1"])'
            ].join(', ');
            const interactiveChildren = xElem.querySelectorAll(interactiveRolesSelector);
            // Check if any of the interactive children have the test_id attribute (they're in our scope)
            // AND are themselves viable interactive targets (i.e., would not be filtered out later).
            const hasInteractiveChildrenWithTestId = Array.from(interactiveChildren).some(child => {
                return child.hasAttribute(webagentIdAttribute) &&
                       child.getAttribute(webagentIdAttribute) &&
                       isInteractiveChildViable(child);
            });
            if (hasInteractiveChildrenWithTestId) {
                return false; // Filter out parent - children should be identified instead
            }
        }
        
        return true;
    });

    // Mark only the final filtered elements that pass the disabled check
    // This ensures perfect consistency: only elements that are actually marked are returned
    const finalItems = [];
    items.forEach((x) => {
        try {
            const el = document.querySelector(`[${webagentIdAttribute}="${x.test_id}"]`);
            if (!el) return;
            

            
            // Final safety check: double-check that element is not disabled before marking
            // Use the same helper function to ensure consistency
            if (isElementDisabled(el)) {
                return; // Don't mark disabled elements - they won't be in finalItems
            }
            
            // Mark the element
            el.setAttribute('webagent-interactive-elem', '');
            // Only add to finalItems if it was actually marked
            finalItems.push(x);
        } catch (e) {
            // Error handling - element will be skipped
        }
    });

        // Return only the elements that were actually marked
        // This ensures perfect consistency between what's marked and what's returned
        console.log(`[identify_interactive_elements] Returning ${finalItems.length} interactive elements`);
        return finalItems;
    } catch (e) {
        console.error(`[identify_interactive_elements] FATAL ERROR: ${e.message}`);
        console.error(e.stack);
        return [];
    }
}