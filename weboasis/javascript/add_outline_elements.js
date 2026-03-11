// OUTLINE_INTERACTIVE_ELEMENTS_JS
(testIdAttr) => {
    // Handle both string and array inputs (for backward compatibility)
    if (Array.isArray(testIdAttr) && testIdAttr.length > 0) {
        testIdAttr = testIdAttr[0];
    }
    if (!testIdAttr || typeof testIdAttr !== 'string') return 0;
    // Remove any previous outlines before adding new ones
    document.querySelectorAll('.webagent-outline-box, .webagent-outline-label').forEach(el => el.remove());

    // Elegant color palette
    const colors = [
        "#6C5B7B", "#355C7D", "#F67280", "#C06C84", "#F8B195",
        "#355C7D", "#99B898", "#FECEAB", "#FF847C", "#E84A5F"
    ];

    let highlightedCount = 0;
    
    // ---------- helpers to compute live rects from DOM elements ----------
    function computeRectForElement(el) {
        try {
            const tag = el.tagName && el.tagName.toLowerCase();
            // Special handling for <area> elements in image maps: they often have no layout box,
            // so getBoundingClientRect() returns zeros. We approximate their box from the
            // associated <img usemap="..."> and this area's `coords`.
            if (tag === 'area') {
                const mapEl = el.parentElement;
                const mapName = mapEl && mapEl.name;
                if (!mapName) return null;

                const img = document.querySelector(`img[usemap="#${CSS.escape(mapName)}"]`);
                if (!img) return null;

                const imgRect = img.getBoundingClientRect();
                const coordsAttr = el.getAttribute('coords');
                if (!coordsAttr) return null;

                const nums = coordsAttr.split(',').map(n => parseFloat(n.trim())).filter(n => !Number.isNaN(n));
                if (nums.length < 4) return null;

                const xs = [];
                const ys = [];
                for (let i = 0; i + 1 < nums.length; i += 2) {
                    xs.push(nums[i]);
                    ys.push(nums[i + 1]);
                }
                if (!xs.length || !ys.length) return null;

                const minX = Math.min(...xs);
                const maxX = Math.max(...xs);
                const minY = Math.min(...ys);
                const maxY = Math.max(...ys);

                // Account for image scaling between intrinsic size and rendered size.
                const naturalWidth = img.naturalWidth || imgRect.width;
                const naturalHeight = img.naturalHeight || imgRect.height;
                const scaleX = naturalWidth ? imgRect.width / naturalWidth : 1;
                const scaleY = naturalHeight ? imgRect.height / naturalHeight : 1;

                const left = imgRect.left + minX * scaleX;
                const top = imgRect.top + minY * scaleY;
                const width = (maxX - minX) * scaleX;
                const height = (maxY - minY) * scaleY;

                return { left, top, width, height };
            }

            const r = el.getBoundingClientRect();
            return { left: r.left, top: r.top, width: r.width, height: r.height };
        } catch {
            return null;
        }
    }

    const overlays = new Map(); // Element -> { outline, label, el }
    let rafPending = false;
    function updatePositions() {
        rafPending = false;
        overlays.forEach(({ outline, label, el }) => {
            const rect = computeRectForElement(el);
            if (!rect) return;
            // position: fixed uses viewport coords; do NOT add window.scrollX/Y
            outline.style.left = `${rect.left}px`;
            outline.style.top = `${rect.top}px`;
            outline.style.width = `${rect.width}px`;
            outline.style.height = `${rect.height}px`;
            label.style.left = `${rect.left + 4}px`;
            label.style.top = `${rect.top - 4}px`;
        });
    }
    function scheduleUpdate() {
        if (!rafPending) {
            rafPending = true;
            requestAnimationFrame(updatePositions);
        }
    }
    const elements = document.querySelectorAll('[webagent-interactive-elem]');
    elements.forEach((el, idx) => {
        const rect = computeRectForElement(el);
        if (!rect) return;
        const color = colors[idx % colors.length];

        // Create outline box
        const outline = document.createElement('div');
        outline.className = 'webagent-outline-box';
        outline.style.position = 'fixed';
        outline.style.left = `${rect.left}px`;
        outline.style.top = `${rect.top}px`;
        outline.style.width = `${rect.width}px`;
        outline.style.height = `${rect.height}px`;
        outline.style.border = `1.5px dashed ${color}`; // Thinner border
        outline.style.zIndex = 2147483647;
        outline.style.pointerEvents = 'none';
        outline.style.boxSizing = 'border-box';
        outline.style.borderRadius = '6px';
        outline.style.background = 'none';

        // Create label
        const label = document.createElement('div');
        label.className = 'webagent-outline-label';
        // Safely get testId value - testIdAttr is already normalized to string at the top
        let testIdValue = '';
        try {
            // Try multiple methods to get the attribute value to ensure we get the full value
            // Method 1: Direct attribute access via attributes collection
            let attrValue = null;
            if (el.attributes && el.attributes[testIdAttr]) {
                attrValue = el.attributes[testIdAttr].value;
            }
            
            // Method 2: Fallback to getAttribute if method 1 didn't work
            if (!attrValue) {
                attrValue = el.getAttribute(testIdAttr);
            }
            
            // Method 3: Try getAttributeNode as another fallback
            if (!attrValue && el.getAttributeNode) {
                const attrNode = el.getAttributeNode(testIdAttr);
                if (attrNode) {
                    attrValue = attrNode.value;
                }
            }
            
            // Ensure we have a valid value and convert to string
            if (attrValue !== null && attrValue !== undefined) {
                // Force string conversion and ensure we get the full value
                // Use template literal to ensure proper string conversion
                testIdValue = `${attrValue}`;
                
                // Additional safety: verify the value is not being truncated
                // If the original value was longer, this should preserve it
            }
        } catch (e) {
            // Silently handle errors - testIdValue remains empty string
            console.warn('Error getting test ID value:', e);
            testIdValue = '';
        }
        
        // Show only the bid (testIdValue) - ensure we set the full value
        // Use textContent for reliable text setting that preserves the full string
        label.textContent = testIdValue;
        label.style.position = 'fixed';
        label.style.left = `${rect.left + 4}px`;
        label.style.top = `${rect.top - 4}px`;
        label.style.padding = '1px 5px'; // Smaller padding
        label.style.background = color;
        label.style.color = '#fff';
        label.style.fontSize = '10px'; // Smaller font size
        label.style.fontFamily = 'monospace';
        label.style.borderRadius = '4px';
        label.style.zIndex = 2147483647;
        label.style.pointerEvents = 'none';
        label.style.boxShadow = '0 2px 6px rgba(0,0,0,0.08)';
        label.style.whiteSpace = 'nowrap';

        document.body.appendChild(outline);
        document.body.appendChild(label);
        overlays.set(el, { outline, label, el });

        highlightedCount++;
    });

    // Keep overlays synced on any scroll/resize (capture to catch inner scrollables)
    window.addEventListener('scroll', scheduleUpdate, true);
    document.addEventListener('scroll', scheduleUpdate, true);
    window.addEventListener('resize', scheduleUpdate, true);
    scheduleUpdate();

    return highlightedCount;
}