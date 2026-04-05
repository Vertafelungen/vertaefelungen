document.addEventListener('DOMContentLoaded', () => {
  initDrawerNavigation();
  initProductsMegaMenu();
});

function initDrawerNavigation() {
  const button = document.querySelector('[data-testid="hamburger-button"]');
  const drawer = document.getElementById('nav-drawer');

  if (!(button instanceof HTMLButtonElement) || !(drawer instanceof HTMLElement)) {
    return;
  }

  const overlay = drawer.querySelector('[data-testid="nav-drawer-overlay"]');
  const panel = drawer.querySelector('.nav-drawer__panel');
  let lastFocused = null;

  const setDrawerState = (isOpen) => {
    drawer.classList.toggle('is-open', isOpen);
    drawer.setAttribute('aria-hidden', String(!isOpen));
    button.setAttribute('aria-expanded', String(isOpen));
    document.body.classList.toggle('nav-drawer-open', isOpen);
  };

  const openDrawer = () => {
    if (drawer.classList.contains('is-open')) return;
    lastFocused = document.activeElement;
    setDrawerState(true);
    if (panel instanceof HTMLElement) {
      panel.focus();
    }
  };

  const closeDrawer = () => {
    if (!drawer.classList.contains('is-open')) return;
    setDrawerState(false);
    if (lastFocused instanceof HTMLElement) {
      lastFocused.focus();
    } else {
      button.focus();
    }
  };

  button.addEventListener('click', () => {
    if (drawer.classList.contains('is-open')) {
      closeDrawer();
    } else {
      openDrawer();
    }
  });

  if (overlay instanceof HTMLElement) {
    overlay.addEventListener('click', closeDrawer);
  }

  drawer.addEventListener('click', (event) => {
    if (event.target instanceof HTMLAnchorElement) {
      closeDrawer();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && drawer.classList.contains('is-open')) {
      event.preventDefault();
      closeDrawer();
    }
  });
}

function initProductsMegaMenu() {
  const trigger = document.querySelector('[data-products-mega-trigger]');
  const panel = document.querySelector('[data-products-mega]');

  if (!(trigger instanceof HTMLButtonElement) || !(panel instanceof HTMLElement)) {
    return;
  }

  const desktopQuery = window.matchMedia('(max-width: 960px)');
  let isOpen = false;

  const setOpenState = (nextOpen) => {
    isOpen = nextOpen;
    trigger.setAttribute('aria-expanded', String(nextOpen));
    panel.setAttribute('aria-hidden', String(!nextOpen));
    panel.hidden = !nextOpen;

    if (nextOpen) {
      const firstFocusable = panel.querySelector('a, button, [tabindex]:not([tabindex="-1"])');
      if (firstFocusable instanceof HTMLElement) {
        firstFocusable.focus();
      }
    }
  };

  const closePanel = () => {
    if (!isOpen) return;
    setOpenState(false);
    trigger.focus();
  };

  trigger.addEventListener('click', () => {
    if (desktopQuery.matches) {
      setOpenState(false);
      return;
    }

    setOpenState(!isOpen);
  });

  document.addEventListener('click', (event) => {
    if (!isOpen) return;
    const target = event.target;
    if (!(target instanceof Node)) return;

    if (!panel.contains(target) && !trigger.contains(target)) {
      setOpenState(false);
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && isOpen) {
      event.preventDefault();
      closePanel();
    }
  });

  const handleMediaChange = () => {
    if (desktopQuery.matches) {
      setOpenState(false);
    }
  };

  if (typeof desktopQuery.addEventListener === 'function') {
    desktopQuery.addEventListener('change', handleMediaChange);
  } else if (typeof desktopQuery.addListener === 'function') {
    desktopQuery.addListener(handleMediaChange);
  }
}
