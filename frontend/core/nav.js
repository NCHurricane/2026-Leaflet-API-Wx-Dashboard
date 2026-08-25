import { renderHeaderBrand } from './branding.js?v=20260826a';

const PRODUCTS = Object.freeze([
    ['Home', '/workspace', 'fa-home', 'Severe Weather Workspace'],
    ['Current', '/surface', 'fa-thermometer', 'Current Conditions'],
    ['Alerts', '/alerts', 'fa-exclamation-triangle', 'Weather Alerts'],
    ['Radar', '/radar', 'fa-satellite-dish', 'Radar'],
    ['Satellite', '/satellite', 'fa-satellite', 'Satellite'],
    ['SPC', '/spc', 'fa-cloud-bolt', 'Storm Prediction Center'],
    ['RTMA', '/rtma', 'fa-thermometer-half', 'Real-Time Mesoscale Analysis'],
    ['MRMS', '/mrms', 'fa-cloud-rain', 'Multi-Radar Multi-Sensor'],
    ['Drought', '/drought', 'fa-sun-plant-wilt', 'Drought Monitor'],
    ['Tropical', '/tropical', 'fa-hurricane', 'Tropical Systems'],
    ['WPC', '/wpc', 'fa-cloud-showers-heavy', 'Weather Prediction Center'],
    ['Water', '/water', 'fa-water', 'Water Monitoring'],
]);

export function renderProductNav(root, activeLabel) {
    if (!root) return;
    renderHeaderBrand(root);
    root.replaceChildren(...PRODUCTS.map(([label, href, iconName, title]) => {
        const link = document.createElement('a');
        link.href = href;
        link.title = title;
        link.className = 'core-nav-link';
        const icon = document.createElement('i');
        icon.className = `fas ${iconName}`;
        icon.setAttribute('aria-hidden', 'true');
        const text = document.createElement('span');
        text.textContent = label;
        link.append(icon, text);
        if (label.toLowerCase() === String(activeLabel || '').toLowerCase()) {
            link.classList.add('is-active');
            link.setAttribute('aria-current', 'page');
        }
        return link;
    }));
}
