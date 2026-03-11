// Extract simplified accessibility-like tree (compact and bounded)
// Usage (testIdAttr is REQUIRED):
// page.evaluate(EXTRACT_ACCESSIBILITY_TREE_JS, {
//   maxDepth: 3, maxTextLen: 80, onlyViewport: true, maxNodes: 300, testIdAttr: 'web-testid'
// })
(options) => {
    const cfg = Object.assign({ maxDepth: 3, maxTextLen: 80, onlyViewport: true, maxNodes: 300, testIdAttr: null }, options || {});
    const testIdAttr = cfg.testIdAttr && String(cfg.testIdAttr);
    if (!testIdAttr) {
        throw new Error('extract_accessbility_tree: "testIdAttr" option is required');
    }

    // Interactive marking is handled elsewhere (identify_interactive_elements.js)
    // Detect interactive elements via attribute set by identify_interactive_elements.js
    const isMarkedInteractive = (el) => el instanceof Element && el.hasAttribute('webagent-interactive-elem');

    const inViewport = (el) => {
        if (!cfg.onlyViewport) return true;
        try {
            const r = el.getBoundingClientRect();
            const vw = window.innerWidth || document.documentElement.clientWidth;
            const vh = window.innerHeight || document.documentElement.clientHeight;
            // Consider partially visible
            return r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
        } catch { return true; }
    };

    const trimText = (t) => {
        if (!t) return "";
        const s = (t || "").replace(/\s+/g, " ").trim();
        return s.length > cfg.maxTextLen ? s.slice(0, cfg.maxTextLen) + "…" : s;
    };

    const tree = [];
    let nodeCount = 0;
    let preorderIndex = 0; // position in preorder traversal

    const walk = (node, depth, path) => {
        if (!node || depth > cfg.maxDepth || nodeCount >= cfg.maxNodes) return;
        if (!(node instanceof Element)) {
            // Skip non-element nodes
            Array.from(node.childNodes || []).forEach((c) => walk(c, depth, path));
            return;
        }

        if (!inViewport(node)) {
            Array.from(node.children).forEach((c, i) => walk(c, depth + 1, path.concat(i)));
            return;
        }

        const role = node.getAttribute("role") || node.tagName.toLowerCase();
        const ariaLabel = node.getAttribute("aria-label") || node.getAttribute("aria-labelledby") || "";
        const text = trimText(node.textContent || "");
        const interactive = isMarkedInteractive(node);
        const id = node.id || "";
        const testId = node.getAttribute(testIdAttr) || "";

        if (interactive || ariaLabel || text) {
            // Minimal box info for spatial grounding (viewport coords)
            let rect = null;
            try {
                const r = node.getBoundingClientRect();
                rect = { left: Math.round(r.left), top: Math.round(r.top), width: Math.round(r.width), height: Math.round(r.height) };
            } catch { rect = null; }

            const entry = {
                tag: node.tagName.toLowerCase(),
                role,
                name: trimText(ariaLabel || text),
                interactive,
                id: id || undefined,
                rect,
                depth,
                index: preorderIndex++,
                path: path.length ? path.join('.') : '0'
            };
            // Use dynamic key for test id attribute
            entry[testIdAttr] = testId || undefined;
            tree.push(entry);
            nodeCount += 1;
        }

        Array.from(node.children).forEach((c, i) => walk(c, depth + 1, path.concat(i)));
    };

    walk(document.body, 0, []);
    return tree.slice(0, cfg.maxNodes);
}