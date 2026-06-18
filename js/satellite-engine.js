(function () {
    'use strict';

    function requireContextFunction(context, name) {
        if (typeof context?.[name] !== 'function') {
            throw new Error(`Satellite engine context missing function: ${name}`);
        }
        return context[name];
    }

    function createSatelliteEngine(context) {
        const isTypeEnabled = requireContextFunction(context, 'isTypeEnabled');
        const isArchiveMode = requireContextFunction(context, 'isArchiveMode');
        const hasRtmaScrubFrames = requireContextFunction(context, 'hasRtmaScrubFrames');
        const hasMrmsScrubFrames = requireContextFunction(context, 'hasMrmsScrubFrames');
        const isScrubMode = requireContextFunction(context, 'isScrubMode');
        const isCurrentRequestSeq = requireContextFunction(context, 'isCurrentRequestSeq');

        function canApplyResponse(requestSeq) {
            return isCurrentRequestSeq(requestSeq)
                && isTypeEnabled('satellite')
                && !isArchiveMode()
                && !hasRtmaScrubFrames()
                && !hasMrmsScrubFrames()
                && (!isScrubMode() || isTypeEnabled('satellite'));
        }

        async function loadCurrentFrame(options = {}) {
            const {
                activeLookbackHours,
                clearLayer,
                currentFrameRequestWindows,
                fetchFrameSet,
                frameIndexForReload,
                frameTileCount,
                getCurrentFetchController,
                getFrameIndex,
                getFrames,
                nextCurrentRequestSeq,
                primeAnimationLayers,
                setApiMode,
                setCurrentFetchController,
                setFrameIndex,
                setFrames,
                setModeActive,
                setSatelliteStatus,
                setSatelliteTileRefreshToken,
                setSatelliteFrame,
                syncAutoRefresh,
                updateLegend,
            } = context;

            [
                activeLookbackHours,
                clearLayer,
                currentFrameRequestWindows,
                fetchFrameSet,
                frameIndexForReload,
                frameTileCount,
                getCurrentFetchController,
                getFrameIndex,
                getFrames,
                nextCurrentRequestSeq,
                primeAnimationLayers,
                setApiMode,
                setCurrentFetchController,
                setFrameIndex,
                setFrames,
                setModeActive,
                setSatelliteStatus,
                setSatelliteTileRefreshToken,
                setSatelliteFrame,
                syncAutoRefresh,
                updateLegend,
            ].forEach((fn) => {
                if (typeof fn !== 'function') {
                    throw new Error('Satellite engine current-frame context is incomplete.');
                }
            });

            if (!isTypeEnabled('satellite')) return;
            if (isScrubMode()) return;
            setModeActive('current');
            void updateLegend();
            const silent = options.silent === true;
            const refreshCatalog = options.refresh === true || silent;
            const existingFrames = getFrames();
            const previousFrameKey = existingFrames[getFrameIndex()]?.frame_key || '';
            const requestSeq = nextCurrentRequestSeq();

            const currentController = getCurrentFetchController();
            if (currentController) currentController.abort();
            const controller = new AbortController();
            setCurrentFetchController(controller);
            const { signal } = controller;

            try {
                if (!silent) {
                    setSatelliteStatus('Loading current satellite frame...');
                }
                let frameSet = null;
                let requestWindow = null;
                let lastFrameSetError = null;
                for (const candidateWindow of currentFrameRequestWindows()) {
                    try {
                        frameSet = await fetchFrameSet({
                            hours: candidateWindow.hours,
                            maxFrames: candidateWindow.maxFrames,
                            signal,
                            refresh: refreshCatalog,
                            requireTiles: false,
                            minFrames: 1,
                        });
                        requestWindow = candidateWindow;
                        break;
                    } catch (err) {
                        if (err.name === 'AbortError') throw err;
                        lastFrameSetError = err;
                    }
                }
                if (!frameSet || !requestWindow) {
                    throw lastFrameSetError || new Error('Satellite catalog does not have enough frames yet.');
                }
                if (!canApplyResponse(requestSeq)) return;
                setApiMode(frameSet.mode, frameSet.data);

                const frames = Array.isArray(frameSet.frames) ? frameSet.frames : [];
                setFrames(frames);

                if (!frames.length) {
                    clearLayer(true);
                    setSatelliteStatus('No current satellite frame available for this selection.');
                    return;
                }

                const nextFrameIndex = frameIndexForReload(frames);
                setFrameIndex(nextFrameIndex);
                const currentFrameKey = frames[nextFrameIndex]?.frame_key || '';
                const forceReloadSameLayer = (
                    silent
                    && Boolean(currentFrameKey)
                    && currentFrameKey === previousFrameKey
                );
                if (forceReloadSameLayer) {
                    setSatelliteTileRefreshToken(Date.now());
                }
                primeAnimationLayers(nextFrameIndex);
                const frameDisplayed = await setSatelliteFrame(nextFrameIndex, {
                    waitForTiles: false,
                    tileTimeoutMs: context.initialTileReadyTimeoutMs,
                    forceReloadSameLayer,
                });
                if (frameDisplayed) {
                    const fallbackLabel = requestWindow.hours > activeLookbackHours()
                        ? `; latest found within ${requestWindow.hours}h`
                        : '';
                    setSatelliteStatus(`Current satellite frame loaded; tiles will fill as needed (${frameTileCount(frames[nextFrameIndex])} cached tiles${fallbackLabel}).`);
                } else {
                    setSatelliteStatus('Satellite frame listed; tiles will fill as they render.');
                }
                syncAutoRefresh();
            } catch (err) {
                if (err.name === 'AbortError') return;
                if (!canApplyResponse(requestSeq)) return;
                setSatelliteStatus(`Satellite error: ${err.message}`);
            }
        }

        async function loadScrubberFrames() {
            const {
                currentFrameRequestWindow,
                exitMrmsScrubMode,
                exitRtmaScrubMode,
                fetchFrameSet,
                frameIndexForReload,
                getFrameIndex,
                getFrames,
                getLookbackReloadTimer,
                getManualScrubTimer,
                getScrubFetchController,
                getScrubLoadSeq,
                nextScrubLoadSeq,
                primeAnimationLayers,
                setApiMode,
                setArchiveModeButtonInactive,
                setArchiveScrubber,
                setBackgroundWarmSeq,
                setFrameIndex,
                setFrames,
                setLookbackReloadTimer,
                setManualScrubTimer,
                setModeActive,
                setRtmaScrubberStatus,
                setSatelliteAnimateButtonFilling,
                setSatelliteFrame,
                setSatelliteStatus,
                setScrubFetchController,
                setScrubMode,
                setScrubberControlsEnabled,
                stopAutoRefresh,
                stopScrubPlay,
                updateLegend,
                updateRtmaScrubberUi,
                updateSatelliteScrubberUi,
                warmFramesInBackground,
            } = context;

            [
                currentFrameRequestWindow,
                exitMrmsScrubMode,
                exitRtmaScrubMode,
                fetchFrameSet,
                frameIndexForReload,
                getFrameIndex,
                getFrames,
                getLookbackReloadTimer,
                getManualScrubTimer,
                getScrubFetchController,
                getScrubLoadSeq,
                nextScrubLoadSeq,
                primeAnimationLayers,
                setApiMode,
                setArchiveModeButtonInactive,
                setArchiveScrubber,
                setBackgroundWarmSeq,
                setFrameIndex,
                setFrames,
                setLookbackReloadTimer,
                setManualScrubTimer,
                setModeActive,
                setRtmaScrubberStatus,
                setSatelliteAnimateButtonFilling,
                setSatelliteFrame,
                setSatelliteStatus,
                setScrubFetchController,
                setScrubMode,
                setScrubberControlsEnabled,
                stopAutoRefresh,
                stopScrubPlay,
                updateLegend,
                updateRtmaScrubberUi,
                updateSatelliteScrubberUi,
                warmFramesInBackground,
            ].forEach((fn) => {
                if (typeof fn !== 'function') {
                    throw new Error('Satellite engine scrubber context is incomplete.');
                }
            });

            if (!isTypeEnabled('satellite')) return;
            const previousFrameKey = getFrames()[getFrameIndex()]?.frame_key || '';
            const lookbackTimer = getLookbackReloadTimer();
            if (lookbackTimer) {
                clearTimeout(lookbackTimer);
                setLookbackReloadTimer(null);
            }
            const manualTimer = getManualScrubTimer();
            if (manualTimer) {
                clearTimeout(manualTimer);
                setManualScrubTimer(null);
            }
            exitRtmaScrubMode(false);
            exitMrmsScrubMode(false);

            const loadSeq = nextScrubLoadSeq();
            setBackgroundWarmSeq(loadSeq);
            const scrubController = getScrubFetchController();
            if (scrubController) {
                scrubController.abort();
            }
            const controller = new AbortController();
            setScrubFetchController(controller);
            const { signal } = controller;
            setScrubMode(true);
            context.incrementScrubRenderSeq?.();
            stopAutoRefresh();
            stopScrubPlay();
            setModeActive('animate');
            void updateLegend();
            setArchiveModeButtonInactive();
            setArchiveScrubber(true);
            setScrubberControlsEnabled(false);
            setFrames([]);
            setFrameIndex(0);
            updateSatelliteScrubberUi();
            setRtmaScrubberStatus('Loading satellite animation frames...');

            try {
                const requestWindow = currentFrameRequestWindow();
                const frameSet = await fetchFrameSet({
                    hours: requestWindow.hours,
                    maxFrames: requestWindow.maxFrames,
                    signal,
                    requireTiles: false,
                    minFrames: 0,
                });
                if (!isScrubMode() || loadSeq !== getScrubLoadSeq()) return;
                setApiMode(frameSet.mode, frameSet.data);

                const frames = frameSet.frames;
                setFrames(frames);

                if (!frames.length) {
                    setScrubberControlsEnabled(false);
                    updateSatelliteScrubberUi();
                    setRtmaScrubberStatus('No frames found for selected lookback window.');
                    setSatelliteStatus('No animation frames available for this selection.');
                    setSatelliteAnimateButtonFilling(false);
                    return;
                }

                let nextFrameIndex = frameIndexForReload(frames, previousFrameKey);
                setFrameIndex(nextFrameIndex);
                updateRtmaScrubberUi();
                setScrubberControlsEnabled(true);
                primeAnimationLayers(nextFrameIndex);
                let frameDisplayed = await setSatelliteFrame(nextFrameIndex, {
                    waitForTiles: false,
                    tileTimeoutMs: context.initialTileReadyTimeoutMs,
                });
                if (!frameDisplayed) {
                    const fallbackIndex = frameIndexForReload(frames);
                    if (fallbackIndex !== nextFrameIndex) {
                        nextFrameIndex = fallbackIndex;
                        setFrameIndex(nextFrameIndex);
                        updateRtmaScrubberUi();
                        primeAnimationLayers(nextFrameIndex);
                        frameDisplayed = await setSatelliteFrame(nextFrameIndex, {
                            waitForTiles: false,
                            tileTimeoutMs: context.initialTileReadyTimeoutMs,
                        });
                    }
                }
                if (!isScrubMode() || loadSeq !== getScrubLoadSeq()) return;
                updateRtmaScrubberUi();
                if (frameDisplayed) {
                    setRtmaScrubberStatus(`${frames.length} v2 frames loaded (${requestWindow.hours}h window); tiles fill as they render.`);
                    setSatelliteStatus('Animate mode loaded. Press Play to start scrubbing while tiles fill.');
                } else {
                    setRtmaScrubberStatus(`${frames.length} v2 frames listed (${requestWindow.hours}h window).`);
                    setSatelliteStatus('Satellite animation frames listed; tiles will fill as requested.');
                }

                warmFramesInBackground(loadSeq, null);
            } catch (err) {
                if (err.name === 'AbortError') return;
                if (!isScrubMode() || loadSeq !== getScrubLoadSeq()) return;
                setFrames([]);
                setFrameIndex(0);
                updateSatelliteScrubberUi();
                setScrubberControlsEnabled(false);
                setRtmaScrubberStatus(`Error: ${err.message}`);
                setSatelliteStatus(`Satellite animate error: ${err.message}`);
                setSatelliteAnimateButtonFilling(false);
            } finally {
                if (getScrubFetchController()?.signal === signal) {
                    setScrubFetchController(null);
                }
            }
        }

        return Object.freeze({
            canApplyResponse,
            loadCurrentFrame,
            loadScrubberFrames,
        });
    }

    window.NCHSatelliteEngine = Object.freeze({
        createSatelliteEngine,
    });
}());
