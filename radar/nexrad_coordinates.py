"""Comprehensive NEXRAD site coordinates for all NWS WSR-88D radar sites.

This provides fallback coordinates for sites that may not be in Py-ART's
NEXRAD_LOCATIONS, ensuring all NWS radars are available in the selector.
"""

# NEXRAD site coordinates (lat, lon) derived from NWS WSR-88D radar list
# Reference: https://www.weather.gov/media/tg/wsr88d-radar-list.pdf
NEXRAD_SITE_COORDINATES = {
    # Continental US (K-prefix)
    "KABR": (45.4556, -98.4131),  # Aberdeen, SD
    "KABX": (35.1395, -106.8240),  # Albuquerque, NM
    "KACX": (34.4516, -119.1922),  # Guibert Peak, CA
    "KAMA": (35.3396, -101.7091),  # Amarillo, TX
    "KAMX": (25.6111, -80.3778),   # Miami, FL
    "KAPX": (44.9078, -84.7186),   # Gaylord, MI
    "KARX": (43.8225, -91.1911),   # La Crosse, WI
    "KATX": (48.1947, -122.4963),  # Seattle, WA
    "KBBX": (38.4995, -121.6278),  # Beale AFB, CA
    "KBGM": (42.2008, -75.9784),   # Binghamton, NY
    "KBHX": (40.4986, -124.2917),  # Eureka, CA
    "KBIS": (46.7711, -100.7603),  # Bismarck, ND
    "KBLX": (45.8371, -104.4866),  # Billings, MT
    "KBMX": (33.1719, -86.7684),   # Birmingham, AL
    "KBOX": (42.1256, -71.1369),   # Boston, MA
    "KBRO": (25.9156, -97.4197),   # Brownsville, TX
    "KBUF": (42.9488, -78.7369),   # Buffalo, NY
    "KCAE": (34.2831, -81.1195),   # Columbia, SC
    "KCBW": (46.0394, -67.8065),   # Caribou, ME
    "KCBX": (43.4906, -116.2333),  # Boise, ID
    "KCCX": (40.9231, -77.8633),   # State College, PA
    "KCLE": (41.4131, -81.8586),   # Cleveland, OH
    "KCRP": (27.7842, -97.4306),   # Corpus Christi, TX
    "KCXX": (44.0514, -72.5667),   # Burlington, VT
    "KCYS": (41.1517, -104.8064),  # Cheyenne, WY
    "KDAX": (38.5006, -121.6780),  # Sacramento, CA
    "KDDC": (37.7608, -100.0247),  # Dodge City, KS
    "KDIX": (40.4364, -74.4305),   # Philadelphia, PA
    "KDLH": (46.8364, -92.2097),   # Duluth, MN
    "KDMX": (41.7311, -93.7228),   # Des Moines, IA
    "KDTX": (42.7000, -83.4717),   # Detroit, MI
    "KDVN": (42.4006, -90.5808),   # Davenport, IA
    "KDYX": (32.5388, -99.2542),   # Dyess AFB, TX
    "KEAX": (38.8103, -94.2644),   # Kansas City, MO
    "KESX": (40.7365, -114.8917),  # Las Vegas, NV
    "KEVX": (30.5644, -86.5239),   # Eglin AFB, FL
    "KEYX": (35.0981, -117.6269),  # Edwards AFB, CA
    "KEWX": (29.6739, -98.2841),   # San Antonio, TX
    "KFCX": (37.0244, -80.2744),   # Blacksburg, VA
    "KFDR": (36.7456, -98.9864),   # Frederick, OK
    "KFDX": (34.3636, -103.6198),  # Cannon AFB, NM
    "KFFC": (33.3641, -84.5678),   # Atlanta, GA
    "KFSD": (43.5881, -96.7313),   # Sioux Falls, SD
    "KFSX": (35.3433, -111.1986),  # Flagstaff, AZ
    "KFTG": (39.7867, -104.5453),  # Denver, CO
    "KFWS": (32.5731, -97.3031),   # Ft Worth, TX
    "KGGW": (48.7961, -106.6253),  # Glasgow, MT
    "KGJX": (39.0622, -108.4272),  # Grand Junction, CO
    "KGLD": (39.3667, -101.7000),  # Goodland, KS
    "KGRB": (44.4981, -88.1097),   # Green Bay, WI
    "KGRK": (30.7214, -97.3806),   # Central Texas/Ft Hood, TX
    "KGRR": (42.8942, -85.5450),   # Grand Rapids, MI
    "KGSP": (34.8833, -82.2200),   # Greer, SC
    "KGSX": (37.2758, -121.8022),  # San Jose, CA
    "KGWX": (33.8956, -88.3269),   # Columbus AFB, MS
    "KGYX": (43.8914, -70.2569),   # Portland, ME
    "KHDC": (30.3450, -90.8278),   # Hammond, LA
    "KHDX": (32.6364, -106.1219),  # Holloman AFB, NM
    "KHGX": (29.4719, -95.0792),   # Houston, TX
    "KHNX": (36.3142, -119.6381),  # San Joaquin Valley, CA
    "KHPX": (36.7369, -87.2847),   # Ft Campbell, KY
    "KHTX": (34.7306, -86.0836),   # Huntsville, AL
    "KILN": (39.4204, -84.0186),   # Cincinnati, OH
    "KILX": (40.1253, -88.7527),   # Lincoln, IL
    "KIND": (39.7072, -86.2806),   # Indianapolis, IN
    "KINX": (36.1747, -95.5648),   # Tulsa, OK
    "KIWA": (33.2887, -112.0684),  # Phoenix, AZ
    "KIWX": (41.3879, -85.7000),   # Northern Indiana, IN
    "KJAX": (30.4844, -81.7019),   # Jacksonville, FL
    "KJKL": (37.5853, -82.6058),   # Jackson, KY
    "KJGX": (32.6755, -84.5892),   # Robins AFB, GA
    "KLBB": (33.6542, -101.8142),  # Lubbock, TX
    "KLCH": (30.1256, -93.2161),   # Lake Charles, LA
    "KLGX": (48.3956, -122.0747),  # Langley Hill, WA
    "KLIX": (30.3369, -90.0833),   # New Orleans, LA
    "KLOT": (41.6042, -88.0847),   # Chicago, IL
    "KLSX": (38.6975, -90.6828),   # St Louis, MO
    "KLTX": (34.4268, -77.9558),   # Wilmington, NC
    "KLVX": (38.2508, -85.9439),   # Louisville, KY
    "KLWX": (38.9747, -77.4825),   # Sterling, VA
    "KLZK": (34.8361, -92.2622),   # Little Rock, AR
    "KMAF": (31.9433, -102.1896),  # Midland, TX
    "KMAX": (42.6081, -122.7167),  # Medford, OR
    "KMKX": (43.0208, -88.5556),   # Milwaukee, WI
    "KMLB": (28.1133, -80.6542),   # Melbourne, FL
    "KMOB": (30.6858, -88.2403),   # Mobile, AL
    "KMRX": (36.1686, -83.4019),   # Knoxville, TN
    "KMSX": (47.6419, -113.9867),  # Missoula, MT
    "KMTX": (41.2619, -111.8919),  # Salt Lake City, UT
    "KMUX": (37.1856, -121.8981),  # San Francisco, CA
    "KMVX": (47.5281, -100.4653),  # Grand Forks, ND
    "KMXX": (32.5364, -85.7894),   # Maxwell AFB, AL
    "KNKX": (32.9189, -117.0456),  # San Diego, CA
    "KNQA": (35.3392, -89.8750),   # Memphis, TN
    "KOAX": (41.1306, -95.9225),   # Omaha, NE
    "KOHX": (36.2470, -86.5625),   # Nashville, TN
    "KOKX": (40.8156, -72.8456),   # New York, NY
    "KOTX": (47.6803, -117.6267),  # Spokane, WA
    "KPAH": (37.0683, -88.7692),   # Paducah, KY
    "KPDT": (45.5856, -118.8022),  # Pendleton, OR
    "KPOE": (31.1556, -92.9764),   # Ft Polk, LA
    "KPUX": (38.4596, -104.3061),  # Pueblo, CO
    "KRAX": (35.6656, -78.4897),   # Raleigh, NC
    "KRGX": (39.7542, -119.4623),  # Reno, NV
    "KRIW": (43.0664, -108.4772),  # Riverton, WY
    "KRLX": (38.2989, -81.7236),   # Charleston, WV
    "KRTX": (45.7156, -122.7125),  # Portland, OR
    "KSOX": (33.8186, -117.6358),  # Santa Ana Mountains, CA
    "KSRX": (35.2756, -93.8911),   # Fort Smith, AR
    "KSHV": (32.4506, -93.8425),   # Shreveport, LA
    "KSJT": (31.3728, -100.4931),  # San Angelo, TX
    "KSGF": (37.2350, -93.3867),   # Springfield, MO
    "KTBW": (27.7056, -82.4019),   # Tampa Bay, FL
    "KTFX": (47.4603, -109.6397),  # Great Falls, MT
    "KTLH": (30.3875, -84.2769),   # Tallahassee, FL
    "KTLX": (35.3331, -97.4867),   # Oklahoma City, OK
    "KTWX": (38.9956, -95.6269),   # Topeka, KS
    "KTYX": (43.8556, -75.6800),   # Montague, NY
    "KUDX": (44.1246, -103.7306),  # Rapid City, SD
    "KUEX": (40.3206, -99.4672),   # Hastings, NE
    "KVAX": (32.4747, -83.0017),   # Moody AFB, GA
    "KVBX": (34.8039, -120.4953),  # Vandenberg AFB, CA
    "KVNX": (36.7411, -98.1281),   # Vance AFB, OK
    "KVTX": (34.4117, -119.0181),  # Los Angeles, CA
    "KVWX": (38.2603, -87.7242),   # Evansville, IN
    "KYCX": (32.5236, -116.6186),  # Yuma, AZ

    # Alaska (PA-prefix)
    "PAHG": (60.7253, -151.3525),  # Anchorage/Kenai, AK
    "PABC": (60.7878, -161.8986),  # Bethel, AK
    "PACG": (57.0508, -135.5450),  # Sitka, AK
    "PAEC": (64.5114, -165.4278),  # Nome, AK
    "PAPD": (64.9108, -146.3022),  # Fairbanks, AK
    "PAIH": (57.9500, -152.6000),  # Middleton Island, AK
    "PAKC": (56.6022, -157.5122),  # King Salmon, AK

    # Hawaii (PH-prefix)
    "PHKM": (20.1256, -155.6094),  # Kamuela/Kohala, HI
    "PHKI": (21.8942, -159.5500),  # South Kauai, HI
    "PHMO": (21.1344, -156.8022),  # Molokai, HI
    "PHWA": (19.0950, -155.5608),  # South Shore, HI

    # Puerto Rico (TJ-prefix)
    "TJUA": (18.1156, -65.6631),   # San Juan, PR

    # US Territories - Pacific (P-prefix)
    "PGUA": (13.4549, 144.7981),   # Andersen AFB, Guam

    # Overseas Military (RK/RO-prefix)
    "RKSG": (37.0450, 127.0372),   # Camp Humphreys, South Korea
    "RKJK": (36.8956, 127.1211),   # Kunsan, South Korea
    "RODN": (26.3050, 127.7800),   # Kadena, Japan
}
