//
// Copyright IBM Corp. 2024 - 2026
// SPDX-License-Identifier: Apache-2.0
//

/**
 * Configuration Handler
 * 
 * This script handles dynamic configuration loaded from /api/config endpoint.
 * It applies runtime settings like authentication visibility and session timeout.
 */

(function() {
    'use strict';
    
    // Wait for config to be loaded (from /api/config script tag)
    document.addEventListener('DOMContentLoaded', function() {
        const config = window.APP_CONFIG || {};
        
        // Handle logout button visibility based on authentication setting
        if (config.enableAuth) {
            const logoutContainer = document.getElementById('logout-container');
            if (logoutContainer) {
                logoutContainer.style.display = 'block';
            }
        }
        
        // Log configuration (for debugging)
        if (config.debug) {
            console.log('App Configuration:', config);
        }
        
        // Store config globally for other scripts to use
        window.appConfig = config;
    });
})();

