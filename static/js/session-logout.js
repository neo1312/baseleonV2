/**
 * Auto-logout on window/tab close
 * When user closes the browser window or tab, automatically logout
 * Skip CSRF check on sendBeacon since it's simple session cleanup
 */

(function() {
    // Flag to track if we're closing the window
    let isClosing = false;
    
    // Called when window/tab is closing
    window.addEventListener('beforeunload', function() {
        isClosing = true;
    });
    
    // Called when user navigates away or closes window
    window.addEventListener('pagehide', function(event) {
        if (event.persisted === false) {
            // Page is not in the cache, so it's being unloaded
            performLogout();
        }
    });
    
    // For better browser support, also use unload
    window.addEventListener('unload', function() {
        if (isClosing) {
            performLogout();
        }
    });
    
    // Function to perform logout
    function performLogout() {
        // Send an async request to logout endpoint
        // Use sendBeacon for reliability on page close
        const formData = new FormData();
        navigator.sendBeacon('/logout/', formData);
    }
    
    // Also handle the manual logout button
    window.closeSessionOnLogout = function() {
        // This is called when user clicks logout manually
        // The normal redirect will handle it
        return true;
    };
})();
