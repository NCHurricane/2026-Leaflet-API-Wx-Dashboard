(function () {
    'use strict';

    const contexts = new Map();

    function registerProductContext(productType, context) {
        if (!productType || !context) return null;
        const entry = Object.freeze({
            productType,
            ...context,
        });
        contexts.set(productType, entry);
        return entry;
    }

    function productContext(productType) {
        if (!productType) return null;
        return contexts.get(productType) || null;
    }

    function requireProductContext(productType) {
        const context = productContext(productType);
        if (!context) {
            throw new Error(`Product context is not registered: ${productType}`);
        }
        return context;
    }

    window.NCHProductAppContexts = Object.freeze({
        productContext,
        registerProductContext,
        requireProductContext,
    });
}());
