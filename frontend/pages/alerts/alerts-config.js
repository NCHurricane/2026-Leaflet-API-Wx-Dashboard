export const ALERT_DEFAULT_COLOR = '#6699cc';

// Presentation-only overrides for alert text on the dashboard's dark surfaces.
// Polygon, border, and legend colors continue to use the official values below.
export const ALERT_TEXT_COLORS = Object.freeze({
    'Flash Flood Warning': '#ff6b6b',
});

export const ALERT_COLORS = Object.freeze({
    'Tornado Warning': '#FF0000', 'Extreme Wind Warning': '#FF8C00',
    'Severe Thunderstorm Warning': '#FFA500', 'Flash Flood Warning': '#8B0000',
    'Flash Flood Statement': '#8B0000', 'Severe Weather Statement': '#00FFFF',
    'Special Marine Warning': '#FFA500', 'Tornado Watch': '#FFFF00',
    'Severe Thunderstorm Watch': '#DB7093', 'Flash Flood Watch': '#2E8B57',
    'Flood Warning': '#00FF00', 'Flood Statement': '#00FF00', 'Flood Watch': '#2E8B57',
    'Flood Advisory': '#00FF7F', 'Hydrologic Outlook': '#90EE90',
    'Winter Storm Warning': '#FF69B4', 'Blizzard Warning': '#FF4500',
    'Ice Storm Warning': '#8B008B', 'Winter Weather Advisory': '#7B68EE',
    'Winter Storm Watch': '#4682B4', 'Snow Squall Warning': '#C71585',
    'Freeze Warning': '#483D8B', 'Freeze Watch': '#00FFFF', 'Frost Advisory': '#6495ED',
    'Extreme Cold Warning': '#0000FF', 'Extreme Cold Watch': '#5F9EA0',
    'Cold Weather Advisory': '#AFEEEE', 'Red Flag Warning': '#FF1493',
    'Fire Weather Watch': '#FFDEAD', 'Fire Warning': '#A0522D',
    'Heat Advisory': '#FF7F50', 'Extreme Heat Warning': '#C71585',
    'Extreme Heat Watch': '#800000', 'Coastal Flood Warning': '#228B22',
    'Coastal Flood Watch': '#66CDAA', 'Coastal Flood Advisory': '#7CFC00',
    'Storm Surge Warning': '#B524F7', 'Storm Surge Watch': '#DB7FF7',
    'High Surf Warning': '#228B22', 'High Surf Advisory': '#BA55D3',
    'Rip Current Statement': '#40E0D0', 'Beach Hazards Statement': '#40E0D0',
    'Gale Warning': '#DDA0DD', 'Gale Watch': '#FFC0CB', 'Storm Warning': '#9400D3',
    'Small Craft Advisory': '#D8BFD8', 'Hazardous Seas Warning': '#D8BFD8',
    'Hurricane Warning': '#DC143C', 'Hurricane Watch': '#FF00FF',
    'Tropical Storm Warning': '#B22222', 'Tropical Storm Watch': '#F08080',
    'High Wind Warning': '#DAA520', 'High Wind Watch': '#B8860B',
    'Wind Advisory': '#D2B48C', 'Dense Fog Advisory': '#708090',
    'Dense Smoke Advisory': '#F0E68C', 'Dust Storm Warning': '#FFE4C4',
    'Air Quality Alert': '#808080', 'Earthquake Warning': '#8B4513',
    'Tsunami Warning': '#FD6347', 'Tsunami Watch': '#FF00FF',
    'Tsunami Advisory': '#D2691E', 'Volcano Warning': '#2F4F4F',
    'Civil Danger Warning': '#FFB6C1', 'Hazardous Materials Warning': '#4B0082',
    'Local Area Emergency': '#C0C0C0', 'Radiological Hazard Warning': '#4B0082',
    'Hazardous Weather Outlook': '#EEE8AA', 'Short Term Forecast': '#98FB98',
    'Special Weather Statement': '#FFE4B5', 'Marine Weather Statement': '#FFDAB9',
});

export const ALERT_CATEGORIES = Object.freeze({
    'Severe Weather Warnings': ['Tornado Warning', 'Severe Thunderstorm Warning', 'Flash Flood Warning', 'Severe Weather Statement', 'Special Marine Warning'],
    'Severe Weather Alerts': ['Tornado Warning', 'Severe Thunderstorm Warning', 'Flash Flood Warning', 'Special Marine Warning', 'Tornado Watch', 'Severe Thunderstorm Watch', 'Extreme Wind Warning', 'Severe Weather Statement'],
    'Severe Weather Watches': ['Tornado Watch', 'Severe Thunderstorm Watch', 'Flash Flood Watch'],
    'Hydrology Alerts': ['Flash Flood Warning', 'Flood Warning', 'Flash Flood Watch', 'Flood Watch', 'Flood Advisory', 'Flash Flood Statement', 'Flood Statement', 'Hydrologic Outlook', 'Coastal Flood Statement', 'Lakeshore Flood Advisory', 'Lakeshore Flood Statement', 'Lakeshore Flood Warning', 'Lakeshore Flood Watch'],
    'Flash Flood Alerts': ['Flash Flood Warning', 'Flash Flood Watch', 'Flash Flood Statement'],
    'Winter Alerts': ['Winter Storm Warning', 'Blizzard Warning', 'Ice Storm Warning', 'Winter Weather Advisory', 'Winter Storm Watch', 'Lake Effect Snow Warning', 'Snow Squall Warning', 'Freeze Warning', 'Freeze Watch', 'Frost Advisory', 'Extreme Cold Warning', 'Extreme Cold Watch', 'Heavy Freezing Spray Warning', 'Avalanche Advisory', 'Avalanche Watch', 'Avalanche Warning', 'Freezing Fog Advisory', 'Heavy Freezing Spray Watch'],
    'Cold Alerts': ['Extreme Cold Warning', 'Extreme Cold Watch', 'Freeze Warning', 'Freeze Watch', 'Frost Advisory', 'Cold Weather Advisory'],
    'Fire Alerts': ['Red Flag Warning', 'Fire Weather Watch', 'Extreme Fire Danger', 'Fire Warning'],
    'Heat Alerts': ['Heat Advisory', 'Extreme Heat Warning', 'Extreme Heat Watch'],
    'Coastal Alerts': ['Coastal Flood Warning', 'Coastal Flood Watch', 'Coastal Flood Advisory', 'High Surf Warning', 'High Surf Advisory', 'Rip Current Statement', 'Storm Surge Warning', 'Storm Surge Watch', 'Beach Hazards Statement'],
    'Marine Alerts': ['Special Marine Warning', 'Marine Weather Statement', 'Gale Warning', 'Gale Watch', 'Hurricane Force Wind Warning', 'Storm Warning', 'Small Craft Advisory', 'Hazardous Seas Warning', 'Hazardous Seas Watch', 'Heavy Freezing Spray Warning', 'Brisk Wind Advisory', 'Freezing Spray Advisory', 'Low Water Advisory', 'Storm Watch'],
    'Tropical Cyclone Alerts': ['Hurricane Warning', 'Hurricane Watch', 'Tropical Storm Warning', 'Tropical Storm Watch', 'Storm Surge Warning', 'Storm Surge Watch', 'Extreme Wind Warning', 'Tropical Cyclone Local Statement', 'Hurricane Force Wind Warning', 'Hurricane Force Wind Watch', 'Typhoon Warning', 'Typhoon Watch'],
    'Non-Precipitation Alerts': ['High Wind Warning', 'High Wind Watch', 'Wind Advisory', 'Dense Fog Advisory', 'Dense Smoke Advisory', 'Dust Storm Warning', 'Blowing Dust Warning', 'Blowing Dust Advisory', 'Air Quality Alert', 'Ashfall Warning', 'Ashfall Advisory', 'Air Stagnation Advisory', 'Dust Advisory', 'Lake Wind Advisory'],
    'Geophysical Alerts': ['Earthquake Warning', 'Tsunami Advisory', 'Tsunami Watch', 'Tsunami Warning', 'Volcano Warning'],
    'Public Safety Alerts': ['Civil Danger Warning', 'Hazardous Materials Warning', 'Local Area Emergency', 'Radiological Hazard Warning'],
    'Informational Alerts': ['Hazardous Weather Outlook', 'Short Term Forecast', 'Special Weather Statement'],
});

export const LSR_CATEGORIES = Object.freeze({
    tornado: ['Tornado / Waterspout / Funnel', '#ef4444', 'fa-solid fa-tornado'],
    hail: ['Hail', '#22c55e', 'fa-solid fa-caret-up'],
    wind: ['Wind', '#f59e0b', 'fa-solid fa-wind'],
    flood: ['Flash Flood / Flood', '#1d4ed8', 'fa-solid fa-house-flood-water'],
    rain: ['Heavy Rain', '#38bdf8', 'fa-solid fa-cloud-showers-water'],
    winter: ['Winter Weather', '#a78bfa', 'fa-solid fa-snowflake'],
    fire: ['Fire / Smoke', '#f97316', 'fa-solid fa-fire'],
    heat: ['Heat', '#fbbf24', 'fa-solid fa-temperature-arrow-up'],
    other: ['Other', '#94a3b8', 'fa-solid fa-location-dot'],
});

export const SEVERE_EVENTS = Object.freeze({
    tor: 'Tornado Warning', svr: 'Severe Thunderstorm Warning',
    ffw: 'Flash Flood Warning', smw: 'Special Marine Warning',
});
