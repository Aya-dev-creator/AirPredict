/**
 * MENU MOBILE - Script pour gérer le menu hamburger sur téléphone
 * Ce script gère l'ouverture/fermeture du menu latéral sur mobile
 */

// Fonction pour initialiser le menu mobile
function initMobileMenu() {
    console.log('📱 Initialisation du menu mobile...');
    
    // Vérifier si on est sur mobile (largeur < 769px)
    const isMobile = window.innerWidth < 769;
    
    if (isMobile) {
        // Créer le bouton hamburger s'il n'existe pas
        if (!document.querySelector('.mobile-menu-button')) {
            createMobileMenuButton();
        }
        
        // Créer l'overlay (fond noir transparent) s'il n'existe pas
        if (!document.querySelector('.sidebar-overlay')) {
            createSidebarOverlay();
        }
        
        // Attacher les événements
        attachMobileMenuEvents();
        
        console.log('✓ Menu mobile initialisé');
    }
}

// Fonction pour créer le bouton hamburger
function createMobileMenuButton() {
    const button = document.createElement('button');
    button.className = 'mobile-menu-button';
    button.innerHTML = '<i class="fas fa-bars"></i>';
    button.setAttribute('aria-label', 'Ouvrir le menu');
    document.body.appendChild(button);
}

// Fonction pour créer l'overlay (fond noir transparent)
function createSidebarOverlay() {
    const overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';
    document.body.appendChild(overlay);
}

// Fonction pour attacher les événements au menu mobile
function attachMobileMenuEvents() {
    const menuButton = document.querySelector('.mobile-menu-button');
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    
    if (!menuButton || !sidebar || !overlay) {
        console.warn('⚠️ Éléments du menu mobile non trouvés');
        return;
    }
    
    // Ouvrir le menu au clic sur le bouton hamburger
    menuButton.addEventListener('click', function(e) {
        e.stopPropagation();
        openMobileMenu();
    });
    
    // Fermer le menu au clic sur l'overlay
    overlay.addEventListener('click', function() {
        closeMobileMenu();
    });
    
    // Fermer le menu au clic sur un lien de navigation
    const navLinks = sidebar.querySelectorAll('.nav-item');
    navLinks.forEach(link => {
        link.addEventListener('click', function() {
            closeMobileMenu();
        });
    });
    
    // Fermer le menu avec la touche Échap
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeMobileMenu();
        }
    });
}

// Fonction pour ouvrir le menu mobile
function openMobileMenu() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    const menuButton = document.querySelector('.mobile-menu-button');
    
    if (sidebar && overlay) {
        sidebar.classList.add('open');
        overlay.classList.add('show');
        
        // Changer l'icône du bouton
        if (menuButton) {
            menuButton.innerHTML = '<i class="fas fa-times"></i>';
            menuButton.setAttribute('aria-label', 'Fermer le menu');
        }
        
        // Empêcher le scroll du body
        document.body.style.overflow = 'hidden';
        
        console.log('Menu mobile ouvert');
    }
}

// Fonction pour fermer le menu mobile
function closeMobileMenu() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    const menuButton = document.querySelector('.mobile-menu-button');
    
    if (sidebar && overlay) {
        sidebar.classList.remove('open');
        overlay.classList.remove('show');
        
        // Remettre l'icône hamburger
        if (menuButton) {
            menuButton.innerHTML = '<i class="fas fa-bars"></i>';
            menuButton.setAttribute('aria-label', 'Ouvrir le menu');
        }
        
        // Réactiver le scroll du body
        document.body.style.overflow = '';
        
        console.log('Menu mobile fermé');
    }
}

// Fonction pour gérer le redimensionnement de la fenêtre
function handleResize() {
    const isMobile = window.innerWidth < 769;
    
    if (isMobile) {
        // Réinitialiser le menu mobile si nécessaire
        if (!document.querySelector('.mobile-menu-button')) {
            initMobileMenu();
        }
    } else {
        // Sur desktop, s'assurer que le menu est fermé
        closeMobileMenu();
        
        // Retirer le bouton hamburger et l'overlay
        const menuButton = document.querySelector('.mobile-menu-button');
        const overlay = document.querySelector('.sidebar-overlay');
        
        if (menuButton) menuButton.remove();
        if (overlay) overlay.remove();
    }
}

// Initialiser au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    initMobileMenu();
    
    // Gérer le redimensionnement de la fenêtre (avec debounce pour performance)
    let resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() {
            handleResize();
        }, 250);
    });
});

// Détecter les changements d'orientation sur mobile
window.addEventListener('orientationchange', function() {
    setTimeout(function() {
        handleResize();
    }, 100);
});

console.log('✓ Script menu mobile chargé');