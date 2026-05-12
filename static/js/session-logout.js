/**
 * Auto-logout on window/tab close - DISABLED
 * This was causing automatic logout on normal page navigation
 * 
 * Previous behavior: When user clicks filter/navigate, 'pagehide' event triggered logout
 * New behavior: Rely on Django session timeout for security
 * 
 * Note: If we need auto-logout on browser close, this should be reimplemented with
 * more sophisticated detection to NOT trigger on same-site navigation
 */

(function() {
    // Handle the manual logout button
    window.closeSessionOnLogout = function() {
        // This is called when user clicks logout manually
        // The normal redirect will handle it
        return true;
    };
})();
