export function workspaceFrameTimestampMs(frame) {
    const value = frame?.timestamp_utc || frame?.timestamp || '';
    const parsed = new Date(value).getTime();
    return Number.isFinite(parsed) ? parsed : Number.NaN;
}

export function workspaceFrameIndexAtOrBefore(frames, timestamp) {
    const targetMs = new Date(timestamp || '').getTime();
    if (!Number.isFinite(targetMs)) return -1;
    let matchedIndex = -1;
    let matchedMs = Number.NEGATIVE_INFINITY;
    (Array.isArray(frames) ? frames : []).forEach((frame, index) => {
        const frameMs = workspaceFrameTimestampMs(frame);
        if (Number.isFinite(frameMs) && frameMs <= targetMs && frameMs > matchedMs) {
            matchedIndex = index;
            matchedMs = frameMs;
        }
    });
    return matchedIndex;
}

export function workspaceFrameWindowWithPredecessor(frames, cutoffTimestamp) {
    const cutoffMs = new Date(cutoffTimestamp || '').getTime();
    if (!Number.isFinite(cutoffMs)) {
        return { renderFrames: [], timelineFrames: [] };
    }
    const ordered = (Array.isArray(frames) ? frames : [])
        .filter((frame) => Number.isFinite(workspaceFrameTimestampMs(frame)))
        .sort((left, right) => workspaceFrameTimestampMs(left) - workspaceFrameTimestampMs(right));
    const timelineFrames = ordered.filter((frame) => workspaceFrameTimestampMs(frame) >= cutoffMs);
    const predecessors = ordered.filter((frame) => workspaceFrameTimestampMs(frame) < cutoffMs);
    const predecessor = predecessors.at(-1);
    return {
        renderFrames: predecessor ? [predecessor, ...timelineFrames] : timelineFrames,
        timelineFrames,
    };
}

export function workspaceTimelineSource(frameSets) {
    return ['radar', 'mrms', 'satellite', 'rtma']
        .find((source) => Array.isArray(frameSets?.[source]) && frameSets[source].length) || '';
}
