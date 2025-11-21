// General JavaScript functions for the application

// Function to format date
function formatDate(date) {
    const d = new Date(date);
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// Function to show confirmation dialog
function confirmAction(message) {
    return confirm(message);
}

// Function to initialize date pickers
document.addEventListener('DOMContentLoaded', function() {
    // Initialize sidebar toggle
    const sidebarToggle = document.getElementById('sidebarToggle');
    const wrapper = document.getElementById('wrapper');
    
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function(e) {
            e.preventDefault();
            wrapper.classList.toggle('toggled');
            
            // Add overlay for mobile when sidebar is open
            if (window.innerWidth <= 768) {
                let overlay = document.querySelector('.sidebar-overlay');
                if (!overlay) {
                    overlay = document.createElement('div');
                    overlay.className = 'sidebar-overlay';
                    document.body.appendChild(overlay);
                    
                    overlay.addEventListener('click', function() {
                        wrapper.classList.remove('toggled');
                        overlay.classList.remove('active');
                    });
                }
                
                if (wrapper.classList.contains('toggled')) {
                    overlay.classList.add('active');
                } else {
                    overlay.classList.remove('active');
                }
            }
        });
    }
    
    // Close sidebar when clicking on a link in mobile view
    const sidebarLinks = document.querySelectorAll('#sidebar-wrapper .list-group-item');
    sidebarLinks.forEach(link => {
        link.addEventListener('click', function() {
            if (window.innerWidth <= 768) {
                const wrapper = document.getElementById('wrapper');
                const overlay = document.querySelector('.sidebar-overlay');
                
                wrapper.classList.remove('toggled');
                if (overlay) {
                    overlay.classList.remove('active');
                }
            }
        });
    });
    
    // Handle window resize
    window.addEventListener('resize', function() {
        const wrapper = document.getElementById('wrapper');
        const overlay = document.querySelector('.sidebar-overlay');
        
        if (window.innerWidth > 768) {
            wrapper.classList.remove('toggled');
            if (overlay) {
                overlay.classList.remove('active');
            }
        }
    });
    
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            alert.classList.remove('show');
            setTimeout(function() {
                alert.remove();
            }, 150);
        }, 5000);
    });
});

// Function to validate form
function validateForm(formId) {
    const form = document.getElementById(formId);
    if (form.checkValidity()) {
        return true;
    } else {
        form.reportValidity();
        return false;
    }
}