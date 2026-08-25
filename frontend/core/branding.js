export const BRAND_ASSET_URL = '/img/chuck-copeland-weather-logo.svg?v=20260826a';
export const BRAND_NAME = 'Chuck Copeland Weather';

export function renderHeaderBrand(navRoot) {
    const brandRoot = navRoot?.closest('.core-header')?.querySelector('.core-brand');
    if (!brandRoot) return;

    const link = document.createElement('a');
    link.href = '/';
    link.className = 'core-brand-link';
    link.setAttribute('aria-label', `${BRAND_NAME} home`);

    const image = document.createElement('img');
    image.src = BRAND_ASSET_URL;
    image.alt = '';
    image.className = 'core-brand-logo';
    image.decoding = 'async';

    link.append(image);
    brandRoot.replaceChildren(link);
}
