/**
 * Accessible, dependency-free image inspection for the 3D case studies.
 * Supports keyboard navigation, focus restoration and mobile layouts.
 */
(() => {
  'use strict';

  const buttons = [...document.querySelectorAll('[data-zoom]')];
  const dialog = document.querySelector('[data-gallery-dialog]');
  if (!buttons.length || !dialog) return;

  const closeButton = dialog.querySelector('[data-gallery-close]');
  const previousButton = dialog.querySelector('[data-gallery-prev]');
  const nextButton = dialog.querySelector('[data-gallery-next]');
  const image = dialog.querySelector('[data-gallery-image]');
  const caption = dialog.querySelector('[data-gallery-caption]');
  const counter = dialog.querySelector('[data-gallery-counter]');
  const background = [...document.querySelectorAll('header, main, footer')];
  const controls = [previousButton, nextButton, closeButton];
  let index = -1;
  let trigger = null;

  function show(nextIndex) {
    index = (nextIndex + buttons.length) % buttons.length;
    const button = buttons[index];
    const source = button.querySelector('img');
    if (!source) return;
    image.src = source.currentSrc || source.src;
    image.alt = source.alt || 'Expanded project render';
    caption.textContent = button.closest('figure')?.querySelector('figcaption')?.textContent || source.alt;
    counter.textContent = String(index + 1).padStart(2, '0') + ' / ' + String(buttons.length).padStart(2, '0');
  }

  function open(nextIndex, button) {
    trigger = button;
    show(nextIndex);
    dialog.hidden = false;
    document.body.classList.add('project-lightbox-open');
    if ('inert' in HTMLElement.prototype) {
      for (const element of background) element.inert = true;
    }
    closeButton.focus();
  }

  function close() {
    if (dialog.hidden) return;
    dialog.hidden = true;
    document.body.classList.remove('project-lightbox-open');
    for (const element of background) element.inert = false;
    image.removeAttribute('src');
    if (trigger?.isConnected) trigger.focus();
    index = -1;
  }

  buttons.forEach((button, buttonIndex) => {
    button.addEventListener('click', () => open(buttonIndex, button));
  });

  closeButton.addEventListener('click', close);
  previousButton.addEventListener('click', () => show(index - 1));
  nextButton.addEventListener('click', () => show(index + 1));
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) close();
  });

  document.addEventListener('keydown', (event) => {
    if (dialog.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      show(index - 1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      show(index + 1);
    } else if (event.key === 'Tab') {
      const current = controls.indexOf(document.activeElement);
      if (current === -1) {
        event.preventDefault();
        closeButton.focus();
      } else if (event.shiftKey && current === 0) {
        event.preventDefault();
        closeButton.focus();
      } else if (!event.shiftKey && current === controls.length - 1) {
        event.preventDefault();
        previousButton.focus();
      }
    }
  });
})();
