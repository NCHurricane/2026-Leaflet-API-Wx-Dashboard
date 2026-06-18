(function () {
    'use strict';

    function createSpcEngine(context) {
        function currentSelectionKey() {
            const day = context.getSpcDay();
            const fireDay = context.getSpcFireDay();
            const hazards = context.getSelectedHazards(day);
            const supplemental = context.getSupplementalSelections();
            return context.spcSelectionKey(day, fireDay, hazards, supplemental);
        }

        function canApplyResponse(requestSeq, selectionKey) {
            return requestSeq === context.getSpcRequestSeq()
                && context.canApplySpcResponse()
                && selectionKey === currentSelectionKey();
        }

        async function refreshSpc() {
            return context.doRefreshSpc();
        }

        async function loadArchive(dtFrom) {
            const day = context.getSpcDay();
            const hazard = context.getPrimarySpcHazard(day);
            const localFrom = context.getArchiveFromValue();
            const date = localFrom.slice(0, 10) || dtFrom.slice(0, 10);
            const url = context.apiUrl(
                `/api/archive/spc?day=${day}&hazard=${encodeURIComponent(hazard)}&date=${date}`
            );

            try {
                context.setArchiveProgress(true, 50, 'Fetching archived SPC outlook...');
                const resp = await fetch(url);
                if (!resp.ok) {
                    const error = await resp.json().catch(() => ({}));
                    throw new Error(error.detail || resp.statusText);
                }
                const data = await resp.json();
                context.onArchiveFramesReady([{
                    timestamp: `${data.date}T12:00:00Z`,
                    features: data.features,
                    type: 'FeatureCollection',
                }]);
            } catch (err) {
                context.setArchiveProgress(true, 0, `Error: ${err.message}`);
                context.setStatus(`Archive SPC error: ${err.message}`);
            }
        }

        return Object.freeze({ canApplyResponse, loadArchive, refreshSpc });
    }

    window.NCHSpcEngine = Object.freeze({ createSpcEngine });
}());
