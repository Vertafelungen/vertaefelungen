document.addEventListener('DOMContentLoaded', () => {
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
});
