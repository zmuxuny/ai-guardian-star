// Evaluate in the monitoring page. Browser-only fixture; no device mutation.
(async () => {
    const originalFetch = window.fetch;
    const previousStream = streamOk;
    const originalSetStreamOk = setStreamOk;
    const fixture = {
        fps: 7.5, detections: 0, status: '正常', camera_connected: true,
        uptime_seconds: 10, frame_count: 1, fall_count: 0, sit_count: 0,
        stranger_count: 0, faces: [], mqtt_connected: false,
        care: {mode: 'off', audio_available: false, people: []}
    };
    try {
        const deadline = Date.now() + 6000;
        while (fetchStats.pending && Date.now() < deadline) {
            await new Promise(resolve => setTimeout(resolve, 50));
        }
        if (fetchStats.pending) throw new Error('stats request still pending');
        streamOk = false; // Statistics can arrive before the first video frame.
        setStreamOk = () => {}; // Keep concurrent MJPEG frames out of this case.
        window.fetch = (url, options) => String(url).startsWith('/api/stats')
            ? Promise.resolve(new Response(JSON.stringify(fixture), {status: 200}))
            : originalFetch(url, options);
        await fetchStats();
        const mode = document.getElementById('care-mode').textContent;
        if (mode !== '已关闭') throw new Error('valid stats incorrectly shown as ' + mode);
        return {status: 'PASS', case: 'stats_before_first_video_frame'};
    } finally {
        window.fetch = originalFetch;
        streamOk = previousStream;
        setStreamOk = originalSetStreamOk;
    }
})()
