/**
 * Optional, on-demand GLB inspection for the three 3D case studies.
 * The poster remains visible until a model has loaded successfully.
 * No external script or GLB is fetched before the visitor opts in.
 */
(() => {
  'use strict';

  const sources = [
    'https://cdn.jsdelivr.net/npm/@google/model-viewer@3.5.0/dist/model-viewer.min.js',
    'https://unpkg.com/@google/model-viewer@3.5.0/dist/model-viewer.min.js'
  ];

  const timeout = (promise, ms) => {
    let timer;
    return Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = window.setTimeout(() => reject(new Error('Timed out')), ms);
      })
    ]).finally(() => window.clearTimeout(timer));
  };

  let modulePromise;
  async function loadViewerLibrary() {
    if (window.customElements?.get('model-viewer')) return;
    if (!modulePromise) {
      modulePromise = (async () => {
        let lastError;
        for (const url of sources) {
          try {
            await timeout(import(url), 14000);
            await timeout(window.customElements.whenDefined('model-viewer'), 3000);
            return;
          } catch (error) {
            lastError = error;
          }
        }
        throw lastError || new Error('3D library unavailable');
      })().catch((error) => {
        modulePromise = null;
        throw error;
      });
    }
    return modulePromise;
  }

  for (const stage of document.querySelectorAll('[data-model-preview]')) {
    const launch = stage.querySelector('[data-model-launch]');
    const reset = stage.querySelector('[data-model-reset]');
    const feedback = stage.parentElement.querySelector('[data-model-feedback]');
    const src = stage.dataset.modelSrc;
    const poster = stage.dataset.modelPoster;
    const alt = stage.dataset.modelAlt || 'Interactive 3D model';
    const initialOrbit = stage.dataset.modelOrbit || '35deg 70deg auto';
    const initialExposure = stage.dataset.modelExposure || '1';

    if (!launch || !reset || !feedback || !src || !poster) continue;
    launch.hidden = false;
    let activeViewer = null;
    let busy = false;

    const announce = (message) => { feedback.textContent = message; };

    const fail = (message) => {
      if (activeViewer) {
        activeViewer.remove();
        activeViewer = null;
      }
      stage.classList.remove('is-ready');
      stage.classList.remove('is-loading');
      launch.disabled = false;
      launch.hidden = false;
      reset.hidden = true;
      busy = false;
      announce(message || 'The interactive preview is unavailable. The image and GLB download still work.');
    };

    launch.addEventListener('click', async () => {
      if (busy || activeViewer) return;
      busy = true;
      launch.disabled = true;
      stage.classList.add('is-loading');
      announce('Preparing the interactive 3D viewer…');

      try {
        if (!window.customElements || !document.createElement('canvas').getContext('webgl2')) {
          throw new Error('WebGL 2 is unavailable');
        }
        await loadViewerLibrary();

        const viewer = document.createElement('model-viewer');
        viewer.setAttribute('src', src);
        viewer.setAttribute('poster', poster);
        viewer.setAttribute('alt', alt);
        viewer.setAttribute('camera-controls', '');
        viewer.setAttribute('touch-action', 'pan-y');
        viewer.setAttribute('interaction-prompt', 'none');
        viewer.setAttribute('environment-image', 'neutral');
        viewer.setAttribute('shadow-intensity', '0.65');
        viewer.setAttribute('exposure', initialExposure);
        viewer.setAttribute('loading', 'eager');
        viewer.setAttribute('camera-orbit', initialOrbit);
        viewer.setAttribute('reveal', 'auto');

        activeViewer = viewer;
        const loaded = new Promise((resolve, reject) => {
          viewer.addEventListener('load', resolve, { once: true });
          viewer.addEventListener('error', () => reject(new Error('Model failed to load')), { once: true });
        });

        stage.appendChild(viewer);
        await timeout(loaded, 30000);
        if (activeViewer !== viewer) return;
        stage.classList.remove('is-loading');
        stage.classList.add('is-ready');
        launch.hidden = true;
        reset.hidden = false;
        busy = false;
        announce('3D viewer ready. Drag to rotate; scroll or pinch to zoom.');
      } catch (error) {
        fail('Interactive 3D could not start on this device or connection. The still image and GLB download remain available.');
      }
    });

    reset.addEventListener('click', () => {
      if (!activeViewer) return;
      activeViewer.cameraOrbit = initialOrbit;
      activeViewer.cameraTarget = 'auto auto auto';
      if (typeof activeViewer.jumpCameraToGoal === 'function') activeViewer.jumpCameraToGoal();
      announce('Camera view reset.');
    });
  }
})();
