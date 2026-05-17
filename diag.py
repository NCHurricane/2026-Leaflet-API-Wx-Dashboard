import numpy as np
import os
import sys
sys.path.append(os.getcwd())
try:
    from satellite_v2.renderer import SatelliteTileRenderer
    src = r'$newestFile'
    print(f"File: {src}")
    r = SatelliteTileRenderer('Channel13', src)
    for z, x, y in [(5, 7, 12), (5, 6, 12), (6, 14, 25)]:
        print(f"\nTile {z}/{x}/{y}:")
        t = r.render_tile(z, x, y).astype(float)
        c = r.render_zoom_canvas(z, x, y).astype(float)
        dists = {
            'as-is': np.mean(np.abs(t - c)),
            'flip-ud': np.mean(np.abs(t - np.flipud(c))),
            'flip-lr': np.mean(np.abs(t - np.fliplr(c))),
            'flip-both': np.mean(np.abs(t - np.flipud(np.fliplr(c))))
        }
        for k, v in dists.items():
            print(f"  {k} MAD: {v:.4f}")
        print(f"  Best: {min(dists, key=dists.get)}")
except Exception as e:
    print(e)
