const MAGIC = 'RWPOLAR1';
const HEADER_PREFIX_BYTES = MAGIC.length + 4;

export function parseRadarPolarArtifact(buffer) {
    const bytes = new Uint8Array(buffer);
    if (bytes.length < HEADER_PREFIX_BYTES) throw new Error('Radar polar artifact is truncated.');
    const magic = new TextDecoder().decode(bytes.subarray(0, MAGIC.length));
    if (magic !== MAGIC) throw new Error('Unsupported Radar polar artifact.');
    const view = new DataView(buffer);
    const headerLength = view.getUint32(MAGIC.length, true);
    const textureOffset = HEADER_PREFIX_BYTES + headerLength;
    if (textureOffset > bytes.length) throw new Error('Radar polar header is truncated.');
    const header = JSON.parse(new TextDecoder().decode(bytes.subarray(HEADER_PREFIX_BYTES, textureOffset)));
    const expected = Number(header.texture_width) * Number(header.texture_height);
    if (!Number.isSafeInteger(expected) || expected <= 0 || bytes.length - textureOffset !== expected) {
        throw new Error('Radar polar texture is incomplete.');
    }
    return { header, texture: bytes.subarray(textureOffset) };
}

function compileShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        const message = gl.getShaderInfoLog(shader) || 'unknown shader error';
        gl.deleteShader(shader);
        throw new Error(message);
    }
    return shader;
}

function createProgram(gl) {
    const vertex = compileShader(gl, gl.VERTEX_SHADER, `#version 300 es
        precision highp float;
        const vec2 POSITIONS[3] = vec2[3](
            vec2(-1.0, -1.0), vec2(3.0, -1.0), vec2(-1.0, 3.0)
        );
        void main() { gl_Position = vec4(POSITIONS[gl_VertexID], 0.0, 1.0); }
    `);
    const fragment = compileShader(gl, gl.FRAGMENT_SHADER, `#version 300 es
        precision highp float;
        precision highp int;
        precision highp usampler2D;
        uniform highp usampler2D u_data;
        uniform vec2 u_pixel_origin;
        uniform float u_world_size;
        uniform float u_viewport_height;
        uniform float u_dpr;
        uniform float u_radar_lat;
        uniform float u_radar_lon;
        uniform float u_range_start;
        uniform float u_range_step;
        uniform int u_ray_count;
        uniform int u_gate_count;
        uniform int u_palette_row;
        uniform int u_palette_entries;
        uniform int u_code_bytes;
        uniform int u_missing_code;
        out vec4 out_color;
        const float PI = 3.14159265358979323846;
        const float TWO_PI = 6.28318530717958647692;

        int byte_at(int x, int y) {
            return int(texelFetch(u_data, ivec2(x, y), 0).r);
        }
        float circular_difference(float left, float right) {
            return abs(atan(sin(left - right), cos(left - right)));
        }
        void main() {
            vec2 local = vec2(
                gl_FragCoord.x / u_dpr,
                u_viewport_height - gl_FragCoord.y / u_dpr
            );
            vec2 world = u_pixel_origin + local;
            float lon = world.x / u_world_size * TWO_PI - PI;
            float mercator = PI - TWO_PI * world.y / u_world_size;
            float lat = atan(sinh(mercator));
            float dlat = lat - u_radar_lat;
            float dlon = lon - u_radar_lon;
            float hav = sin(dlat * 0.5) * sin(dlat * 0.5)
                + cos(u_radar_lat) * cos(lat) * sin(dlon * 0.5) * sin(dlon * 0.5);
            float distance = 6371000.0 * 2.0 * atan(sqrt(max(hav, 0.0)), sqrt(max(1.0 - hav, 0.0)));
            int gate = int(floor((distance - (u_range_start - u_range_step * 0.5)) / u_range_step));
            if (gate < 0 || gate >= u_gate_count) discard;

            float y = sin(dlon) * cos(lat);
            float x = cos(u_radar_lat) * sin(lat)
                - sin(u_radar_lat) * cos(lat) * cos(dlon);
            float bearing = mod(atan(y, x) + TWO_PI, TWO_PI);
            int estimate = int(floor(bearing / TWO_PI * float(u_ray_count) + 0.5));
            int best_ray = 0;
            float best_difference = 10.0;
            for (int offset = -4; offset <= 4; offset++) {
                int ray = estimate + offset;
                ray = ray - int(floor(float(ray) / float(u_ray_count))) * u_ray_count;
                int centidegrees = byte_at(0, ray) + byte_at(1, ray) * 256;
                float azimuth = float(centidegrees) * 0.01 * PI / 180.0;
                float difference = circular_difference(azimuth, bearing);
                if (difference < best_difference) {
                    best_difference = difference;
                    best_ray = ray;
                }
            }
            int gate_x = gate * u_code_bytes + 2;
            int code = byte_at(gate_x, best_ray);
            if (u_code_bytes == 2) code += byte_at(gate_x + 1, best_ray) * 256;
            if (code == u_missing_code) discard;
            int palette_index = code;
            if (u_code_bytes == 2) {
                palette_index = min(
                    int(floor(float(code) / float(u_missing_code - 1) * float(u_palette_entries))),
                    u_palette_entries - 1
                );
            }
            int palette_x = palette_index * 4;
            out_color = vec4(
                float(byte_at(palette_x, u_palette_row)),
                float(byte_at(palette_x + 1, u_palette_row)),
                float(byte_at(palette_x + 2, u_palette_row)),
                float(byte_at(palette_x + 3, u_palette_row))
            ) / 255.0;
            if (out_color.a <= 0.0) discard;
        }
    `);
    const program = gl.createProgram();
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    gl.deleteShader(vertex);
    gl.deleteShader(fragment);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        const message = gl.getProgramInfoLog(program) || 'unknown program error';
        gl.deleteProgram(program);
        throw new Error(message);
    }
    return program;
}

export function createRadarWebglLayer({
    leaflet,
    map,
    paneName = 'radar-overlays',
    maxTextures = 4,
    animationEnabled = false,
    onFailure,
} = {}) {
    let canvas = null;
    let gl = null;
    let program = null;
    const textures = new Map();
    let activeIdentity = '';
    let active = false;
    let drawRequest = 0;
    let lastDrawMs = null;

    function syncTextureStats() {
        if (!canvas) return;
        canvas.dataset.radarWebglTextureCount = String(textures.size);
        if (activeIdentity) canvas.dataset.radarWebglIdentity = activeIdentity;
        else delete canvas.dataset.radarWebglIdentity;
    }

    function fail(error) {
        active = false;
        if (canvas) canvas.style.opacity = '0';
        onFailure?.(error);
    }

    function ensureContext() {
        if (gl && program) return true;
        if (!canvas) {
            canvas = document.createElement('canvas');
            canvas.className = 'radar-webgl-overlay';
            canvas.dataset.radarWebglAnimationEnabled = String(animationEnabled === true);
            canvas.style.cssText = [
                'position:absolute',
                'pointer-events:none',
                'z-index:321',
                'opacity:0',
                'transition:opacity 140ms linear',
            ].join(';');
            map.getPane(paneName).appendChild(canvas);
            canvas.addEventListener('webglcontextlost', (event) => {
                event.preventDefault();
                textures.clear();
                activeIdentity = '';
                syncTextureStats();
                fail(new Error('Radar WebGL context lost.'));
            });
            canvas.addEventListener('webglcontextrestored', () => {
                gl = null;
                program = null;
                textures.clear();
                activeIdentity = '';
                syncTextureStats();
                fail(new Error('Radar WebGL context restored; artifact reload required.'));
            });
        }
        gl = canvas.getContext('webgl2', {
            alpha: true,
            antialias: false,
            depth: false,
            premultipliedAlpha: false,
            preserveDrawingBuffer: false,
            stencil: false,
        });
        if (!gl) return false;
        program = createProgram(gl);
        return true;
    }

    function resizeCanvas() {
        if (!canvas) return;
        const size = map.getSize();
        const dpr = Math.min(2, Math.max(1, Number(window.devicePixelRatio) || 1));
        const width = Math.max(1, Math.round(size.x * dpr));
        const height = Math.max(1, Math.round(size.y * dpr));
        canvas.style.width = `${size.x}px`;
        canvas.style.height = `${size.y}px`;
        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
        }
        leaflet.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
    }

    function draw() {
        drawRequest = 0;
        const record = textures.get(activeIdentity);
        if (!active || !gl || !program || !record || !canvas) return;
        const { texture, header } = record;
        const started = performance.now();
        resizeCanvas();
        const bounds = map.getPixelBounds();
        const zoom = map.getZoom();
        const dpr = Math.min(2, Math.max(1, Number(window.devicePixelRatio) || 1));
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.useProgram(program);
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.uniform1i(gl.getUniformLocation(program, 'u_data'), 0);
        gl.uniform2f(gl.getUniformLocation(program, 'u_pixel_origin'), bounds.min.x, bounds.min.y);
        gl.uniform1f(gl.getUniformLocation(program, 'u_world_size'), 256 * (2 ** zoom));
        gl.uniform1f(gl.getUniformLocation(program, 'u_viewport_height'), map.getSize().y);
        gl.uniform1f(gl.getUniformLocation(program, 'u_dpr'), dpr);
        gl.uniform1f(gl.getUniformLocation(program, 'u_radar_lat'), Number(header.radar_lat) * Math.PI / 180);
        gl.uniform1f(gl.getUniformLocation(program, 'u_radar_lon'), Number(header.radar_lon) * Math.PI / 180);
        gl.uniform1f(gl.getUniformLocation(program, 'u_range_start'), Number(header.range_start_m));
        gl.uniform1f(gl.getUniformLocation(program, 'u_range_step'), Number(header.range_step_m));
        gl.uniform1i(gl.getUniformLocation(program, 'u_ray_count'), Number(header.ray_count));
        gl.uniform1i(gl.getUniformLocation(program, 'u_gate_count'), Number(header.gate_count));
        gl.uniform1i(gl.getUniformLocation(program, 'u_palette_row'), Number(header.ray_count));
        gl.uniform1i(gl.getUniformLocation(program, 'u_palette_entries'), Number(header.palette_entries || 256));
        gl.uniform1i(gl.getUniformLocation(program, 'u_code_bytes'), Number(header.code_bytes || 1));
        gl.uniform1i(gl.getUniformLocation(program, 'u_missing_code'), Number(header.missing_code ?? 255));
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        lastDrawMs = performance.now() - started;
        canvas.dataset.radarWebglDrawMs = lastDrawMs.toFixed(3);
        if (gl.getError() !== gl.NO_ERROR) fail(new Error('Radar WebGL redraw failed.'));
    }

    function scheduleDraw() {
        if (!active || drawRequest) return;
        drawRequest = requestAnimationFrame(draw);
    }

    function deleteTexture(identity) {
        const record = textures.get(identity);
        if (!record) return;
        if (gl && record.texture) gl.deleteTexture(record.texture);
        textures.delete(identity);
        if (activeIdentity === identity) {
            activeIdentity = '';
            active = false;
        }
    }

    function retain(identities) {
        const allowed = new Set(identities || []);
        [...textures.keys()].forEach((identity) => {
            if (!allowed.has(identity)) deleteTexture(identity);
        });
        if (!activeIdentity && canvas) {
            canvas.style.opacity = '0';
            canvas.dataset.radarWebglActive = 'false';
        }
        syncTextureStats();
    }

    function release() {
        active = false;
        activeIdentity = '';
        if (canvas) {
            canvas.style.opacity = '0';
            canvas.dataset.radarWebglActive = 'false';
        }
        if (drawRequest) cancelAnimationFrame(drawRequest);
        drawRequest = 0;
        [...textures.keys()].forEach(deleteTexture);
        syncTextureStats();
    }

    async function load(url, identity, signal, expected = {}) {
        if (!ensureContext()) throw new Error('WebGL 2 is unavailable.');
        if (textures.has(identity)) return textures.get(identity).header;
        const response = await fetch(url, { cache: 'force-cache', signal });
        if (!response.ok) throw new Error(`Radar polar artifact returned HTTP ${response.status}.`);
        const parsed = parseRadarPolarArtifact(await response.arrayBuffer());
        if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
        if (
            Number(parsed.header.version) !== Number(expected.version)
            || String(parsed.header.product || '').toUpperCase() !== String(expected.product || '').toUpperCase()
            || ![1, 2].includes(Number(parsed.header.code_bytes || 1))
        ) {
            throw new Error('Radar polar artifact identity is unsupported.');
        }
        const texture = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texImage2D(
            gl.TEXTURE_2D,
            0,
            gl.R8UI,
            Number(parsed.header.texture_width),
            Number(parsed.header.texture_height),
            0,
            gl.RED_INTEGER,
            gl.UNSIGNED_BYTE,
            parsed.texture,
        );
        if (gl.getError() !== gl.NO_ERROR) {
            gl.deleteTexture(texture);
            throw new Error('Radar polar texture upload failed.');
        }
        textures.set(identity, { texture, header: parsed.header });
        while (textures.size > Math.max(1, Number(maxTextures) || 1)) {
            const oldest = [...textures.keys()].find((key) => key !== activeIdentity);
            if (!oldest) break;
            deleteTexture(oldest);
        }
        syncTextureStats();
        return parsed.header;
    }

    function setActive(value, opacity = 0.9, identity = activeIdentity) {
        activeIdentity = value && textures.has(identity) ? identity : '';
        active = !!activeIdentity;
        if (!canvas) return false;
        canvas.style.opacity = active ? String(opacity) : '0';
        canvas.dataset.radarWebglActive = String(active);
        syncTextureStats();
        if (active) scheduleDraw();
        return active;
    }

    function onMapChange() { scheduleDraw(); }
    map.on('move zoom resize', onMapChange);

    return Object.freeze({
        destroy() {
            map.off('move zoom resize', onMapChange);
            release();
            if (gl && program) gl.deleteProgram(program);
            program = null;
            gl = null;
            canvas?.remove();
            canvas = null;
        },
        isReady(identity) { return textures.has(identity); },
        lastDrawMs() { return lastDrawMs; },
        load,
        release,
        retain,
        setActive,
        textureCount() { return textures.size; },
    });
}
