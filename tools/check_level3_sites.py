#!/usr/bin/env python3
"""Check which NEXRAD sites have Level 3 data available on AWS."""

import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

try:
    from lib.s3_utils import get_s3_client
    from radar.radar_nodd_utils import list_nexrad_files
    from config.radar_config import L3_PRODUCTS
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure to run from the project root directory")
    sys.exit(1)

# Get S3 client
s3_client = get_s3_client()

# List of common NEXRAD sites to check
all_sites = [
    # CONUS
    "KABR", "KABX", "KAMA", "KAMX", "KAPX", "KARX", "KATX", "KBBX", "KBGM", "KBHX",
    "KBIS", "KBLX", "KBMX", "KBOX", "KBRO", "KBUF", "KBYX", "KCAE", "KCBW", "KCBX",
    "KCCX", "KCLE", "KCLX", "KCRP", "KCXX", "KCYS", "KDAX", "KDDC", "KDFX", "KDGX",
    "KDIX", "KDLH", "KDMX", "KDOX", "KDTX", "KDVN", "KDYX", "KEAX", "KEMX", "KENX",
    "KEOX", "KEPZ", "KESX", "KEVX", "KEWX", "KEYX", "KFCX", "KFDR", "KFDX", "KFFC",
    "KFSD", "KFSX", "KFTG", "KFWS", "KGGW", "KGJX", "KGLD", "KGRB", "KGRK", "KGRR",
    "KGSX", "KGWX", "KGYX", "KHDC", "KHDX", "KHGX", "KHNX", "KHPX", "KHTX", "KICT",
    "KICX", "KILN", "KILX", "KIND", "KINX", "KIWA", "KIWX", "KJAX", "KJGX", "KJKL",
    "KLBB", "KLCH", "KLGX", "KLIX", "KLNX", "KLOT", "KLSX", "KLTX", "KLVX", "KLWX",
    "KLZK", "KMAF", "KMAX", "KMKX", "KMLB", "KMOB", "KMRX", "KMSX", "KMTX", "KMUX",
    "KMVX", "KMXX", "KNKX", "KNQA", "KOAX", "KOHX", "KOKX", "KOTX", "KPAH", "KPDT",
    "KPOE", "KPUX", "KRAX", "KRGX", "KRIW", "KRLX", "KRTX", "KSOX", "KSRX", "KSHV",
    "KSJT", "KSGF", "KTBW", "KTFX", "KTLH", "KTLX", "KTWX", "KTYX", "KUDX", "KUEX",
    "KVAX", "KVBX", "KVNX", "KVTX", "KVWX", "KYCX", "KMHX", "KACX",
    # Alaska
    "PAHG", "PABC", "PACG", "PAEC", "PAPD", "PAIH", "PAKC",
    # Hawaii
    "PHKM", "PHKI", "PHMO", "PHWA",
    # Puerto Rico
    "TJUA",
    # Remote/International
    "PGUA", "RKSG", "RKJK", "RODN",
]

# Get current time window
end_dt = datetime.now(timezone.utc)
start_dt = end_dt - timedelta(hours=24)

print(f"Checking Level 3 availability from {start_dt.date()} to {end_dt.date()}\n")

# Pick a common product to check
product = "N0B"  # Base reflectivity

sites_with_data = defaultdict(list)
sites_without_data = []

for site in sorted(all_sites):
    try:
        files = list_nexrad_files(
            s3_client,
            "Level 3",
            site,
            product,
            start_dt,
            end_dt,
            provider="aws",
            latest_only=False,
        )

        if files:
            sites_with_data[site] = files[:3]  # Keep first 3 as sample
            print(f"✓ {site}: {len(files)} files")
        else:
            sites_without_data.append(site)
            print(f"✗ {site}: No data")
    except Exception as e:
        sites_without_data.append(site)
        print(f"✗ {site}: Error - {type(e).__name__}")

print(f"\n{'='*60}")
print(f"\nSUMMARY:")
print(f"Sites with Level 3 data: {len(sites_with_data)}")
print(f"Sites without Level 3 data: {len(sites_without_data)}")

print(f"\n\nSites WITH Level 3 {product} data:")
print("-" * 40)
for site in sorted(sites_with_data.keys()):
    print(f"  {site}")

print(f"\n\nSites WITHOUT Level 3 {product} data:")
print("-" * 40)
for site in sorted(sites_without_data):
    print(f"  {site}")
