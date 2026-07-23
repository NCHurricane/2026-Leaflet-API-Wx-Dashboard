# Satellite v2 Phase 2 results

Phase 2 moves live supertile neighbor warming behind the requested-tile
response and deduplicates concurrent work by final tile path.

The proposed single 3x3 rasterio canvas was tested first and rejected: all
nine GOES Channel13 hashes changed, including real pixel differences. The
accepted fallback retains the byte-stable 1x1 warp for each tile, renders only
the requested tile synchronously, then submits neighbors to the existing live
thread pool. Raw runs remain under ignored `cache/satellite/.bench/` storage.

