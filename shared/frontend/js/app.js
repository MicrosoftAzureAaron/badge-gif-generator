/**
 * Badge GIF Generator - Frontend Application
 * Vertical Layout Version with Search and URL Upload
 * @version 1.1.0
 */

// Configuration
const CONFIG = {
    apiBaseUrl: window.location.hostname === 'localhost' 
        ? 'http://localhost:7071/api' 
        : '/api',
    maxFileSize: 10 * 1024 * 1024, // 10MB
    supportedFormats: ['image/png', 'image/jpeg', 'image/gif', 'image/bmp', 'image/webp'],
};

// Application State
const state = {
    uploadedBadges: [], // { id, file, dataUrl, name }
    uploadedLogos: [], // { id, file, dataUrl, name }
    selectedLibraryBadges: [], // { id, filename, url, name }
    selectedLibraryLogos: [], // { id, filename, url, name }
    libraryAssets: { badges: [], logos: [] },
    badgeCategories: [], // Available categories
    selectedBadgeCategory: 'all',
    badgeSearchQuery: '',
    logoSearchQuery: '',
    orderedItems: [], // Combined ordered list for preview
};

// Badge Categories Configuration - icons/logos for known categories
// Unknown categories (from folder names) will auto-generate with folder name as label
const BADGE_CATEGORY_CONFIG = {
    'all': { name: 'All', icon: '🏆' },
    'azure': { name: 'Azure', icon: '☁️' },
    'microsoft': { name: 'Microsoft', icon: '🪟' },
    'aws': { name: 'AWS', icon: '🔶' },
    'google': { name: 'Google Cloud', icon: '🌐' },
    'cisco': { name: 'Cisco', icon: '🔧' },
    'comptia': { name: 'CompTIA', icon: '💻' },
    'itil': { name: 'ITIL', icon: '📋' },
    'lpi': { name: 'LPI', icon: '🐧' },
    'other': { name: 'Other', icon: '📦' },
};

// Get category display config - auto-generates for unknown categories
function getCategoryConfig(category) {
    const cat = category.toLowerCase();
    if (BADGE_CATEGORY_CONFIG[cat]) {
        return BADGE_CATEGORY_CONFIG[cat];
    }
    // Auto-generate config for unknown categories (e.g., new folders)
    // Capitalize first letter or use all-caps for short names (3 chars or less)
    const name = cat.length <= 3 
        ? cat.toUpperCase() 
        : cat.charAt(0).toUpperCase() + cat.slice(1);
    return { name: name, icon: '🏅' };
}

// DOM Elements
const elements = {
    // Badge library
    badgeSearchInput: document.getElementById('badgeSearchInput'),
    clearBadgeSearch: document.getElementById('clearBadgeSearch'),
    badgeCategoryTabs: document.getElementById('badgeCategoryTabs'),
    badgeLibraryGrid: document.getElementById('badgeLibraryGrid'),
    uploadZoneBadges: document.getElementById('uploadZoneBadges'),
    badgeInput: document.getElementById('badgeInput'),
    badgeUrlInput: document.getElementById('badgeUrlInput'),
    addBadgeUrlBtn: document.getElementById('addBadgeUrlBtn'),
    uploadedBadges: document.getElementById('uploadedBadges'),
    
    // Logo library
    logoSearchInput: document.getElementById('logoSearchInput'),
    clearLogoSearch: document.getElementById('clearLogoSearch'),
    logoLibraryGrid: document.getElementById('logoLibraryGrid'),
    uploadZoneLogos: document.getElementById('uploadZoneLogos'),
    logoInput: document.getElementById('logoInput'),
    logoUrlInput: document.getElementById('logoUrlInput'),
    addLogoUrlBtn: document.getElementById('addLogoUrlBtn'),
    uploadedLogos: document.getElementById('uploadedLogos'),
    
    // Settings
    canvasSize: document.getElementById('canvasSize'),
    customSizeGroup: document.getElementById('customSizeGroup'),
    backgroundColorPicker: document.getElementById('backgroundColorPicker'),
    backgroundColor: document.getElementById('backgroundColor'),
    transparentBg: document.getElementById('transparentBg'),
    removeWhiteBg: document.getElementById('removeWhiteBg'),
    
    // Preview & Generate
    selectionSummary: document.getElementById('selectionSummary'),
    reorderHint: document.getElementById('reorderHint'),
    previewArea: document.getElementById('previewArea'),
    clearAllBtn: document.getElementById('clearAllBtn'),
    generateBtn: document.getElementById('generateBtn'),
    loadingOverlay: document.getElementById('loadingOverlay'),
    
    // Result
    resultSection: document.getElementById('resultSection'),
    resultPreview: document.getElementById('resultPreview'),
    downloadBtn: document.getElementById('downloadBtn'),
    createAnotherBtn: document.getElementById('createAnotherBtn'),
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    initializeSearch();
    initializeCategoryTabs();
    initializeUpload();
    initializeSettings();
    initializeActions();
    loadLibraryAssets();
});

// ==================== Search ====================

function initializeSearch() {
    // Badge search
    elements.badgeSearchInput.addEventListener('input', (e) => {
        state.badgeSearchQuery = e.target.value;
        renderBadgeLibrary();
    });
    
    elements.clearBadgeSearch.addEventListener('click', () => {
        elements.badgeSearchInput.value = '';
        state.badgeSearchQuery = '';
        renderBadgeLibrary();
    });
    
    // Logo search
    elements.logoSearchInput.addEventListener('input', (e) => {
        state.logoSearchQuery = e.target.value;
        renderLogoLibrary();
    });
    
    elements.clearLogoSearch.addEventListener('click', () => {
        elements.logoSearchInput.value = '';
        state.logoSearchQuery = '';
        renderLogoLibrary();
    });
}

// ==================== Category Tabs ====================

function initializeCategoryTabs() {
    // Will be populated after assets load
}

function renderCategoryTabs() {
    // Get unique categories from badges
    const categories = new Set(['all']);
    state.libraryAssets.badges.forEach(badge => {
        if (badge.category) {
            categories.add(badge.category.toLowerCase());
        }
    });
    
    // Sort categories: 'all' first, then alphabetically
    state.badgeCategories = Array.from(categories).sort((a, b) => {
        if (a === 'all') return -1;
        if (b === 'all') return 1;
        return a.localeCompare(b);
    });
    
    elements.badgeCategoryTabs.innerHTML = state.badgeCategories.map(cat => {
        const config = getCategoryConfig(cat);
        const isActive = state.selectedBadgeCategory === cat;
        
        let iconHtml = '';
        if (config.logo) {
            iconHtml = `<img src="${config.logo}" alt="${config.name}">`;
        } else if (config.icon) {
            iconHtml = `<span class="category-icon">${config.icon}</span>`;
        }
        
        return `
            <button class="category-tab ${isActive ? 'active' : ''}" 
                    data-category="${cat}"
                    onclick="selectBadgeCategory('${cat}')">
                ${iconHtml}
                <span>${config.name}</span>
            </button>
        `;
    }).join('');
}

function selectBadgeCategory(category) {
    state.selectedBadgeCategory = category;
    renderCategoryTabs();
    renderBadgeLibrary();
}

// ==================== Library ====================

async function loadLibraryAssets() {
    elements.badgeLibraryGrid.innerHTML = '<div class="loading-spinner">Loading badges...</div>';
    elements.logoLibraryGrid.innerHTML = '<div class="loading-spinner">Loading logos...</div>';
    
    try {
        const response = await fetch(`${CONFIG.apiBaseUrl}/list-assets`);
        
        if (!response.ok) {
            throw new Error('Failed to load assets');
        }
        
        const data = await response.json();
        
        const transformAsset = (asset, container) => ({
            ...asset,
            url: asset.url || `${CONFIG.apiBaseUrl}/asset/${container}/${asset.filename}`
        });
        
        state.libraryAssets = {
            badges: (data.badges || []).map(a => transformAsset(a, 'ms-badges')),
            logos: (data.logos || []).map(a => transformAsset(a, 'ms-logos')),
        };
        
        renderCategoryTabs();
        renderBadgeLibrary();
        renderLogoLibrary();
    } catch (error) {
        console.error('Error loading assets:', error);
        elements.badgeLibraryGrid.innerHTML = `
            <div class="no-results">
                <p>Could not load badge library.</p>
                <p style="font-size: 12px; margin-top: 8px;">You can still upload your own badges.</p>
            </div>
        `;
        elements.logoLibraryGrid.innerHTML = `
            <div class="no-results">
                <p>Could not load logo library.</p>
                <p style="font-size: 12px; margin-top: 8px;">You can still upload your own logos.</p>
            </div>
        `;
    }
}

function renderBadgeLibrary() {
    let filtered = state.libraryAssets.badges;
    
    // Filter by category
    if (state.selectedBadgeCategory && state.selectedBadgeCategory !== 'all') {
        filtered = filtered.filter(asset => 
            asset.category && asset.category.toLowerCase() === state.selectedBadgeCategory
        );
    }
    
    // Filter by search query
    if (state.badgeSearchQuery) {
        const query = state.badgeSearchQuery.toLowerCase();
        filtered = filtered.filter(asset => 
            asset.name.toLowerCase().includes(query) ||
            (asset.tags && asset.tags.some(tag => tag.toLowerCase().includes(query))) ||
            (asset.category && asset.category.toLowerCase().includes(query))
        );
    }

    if (filtered.length === 0) {
        elements.badgeLibraryGrid.innerHTML = `
            <div class="no-results">
                ${state.badgeSearchQuery 
                    ? `No badges found matching "${state.badgeSearchQuery}"` 
                    : 'No badges available in the library'}
            </div>
        `;
        return;
    }

    const selectedIds = state.selectedLibraryBadges.map(b => b.id);

    elements.badgeLibraryGrid.innerHTML = filtered.map(asset => `
        <div class="library-item ${selectedIds.includes(asset.id) ? 'selected' : ''}" 
             data-id="${asset.id}"
             data-type="badge"
             data-filename="${asset.filename}"
             data-url="${asset.url}"
             data-name="${asset.name}"
             onclick="toggleLibraryItem(this)">
            <img src="${asset.url}" alt="${asset.name}" loading="lazy">
            <span class="item-name">${asset.name}</span>
        </div>
    `).join('');
}

function renderLogoLibrary() {
    let filtered = state.libraryAssets.logos;
    
    if (state.logoSearchQuery) {
        const query = state.logoSearchQuery.toLowerCase();
        filtered = filtered.filter(asset => 
            asset.name.toLowerCase().includes(query) ||
            (asset.tags && asset.tags.some(tag => tag.toLowerCase().includes(query)))
        );
    }

    if (filtered.length === 0) {
        elements.logoLibraryGrid.innerHTML = `
            <div class="no-results">
                ${state.logoSearchQuery 
                    ? `No logos found matching "${state.logoSearchQuery}"` 
                    : 'No logos available in the library'}
            </div>
        `;
        return;
    }

    const selectedIds = state.selectedLibraryLogos.map(l => l.id);

    elements.logoLibraryGrid.innerHTML = filtered.map(asset => `
        <div class="library-item ${selectedIds.includes(asset.id) ? 'selected' : ''}" 
             data-id="${asset.id}"
             data-type="logo"
             data-filename="${asset.filename}"
             data-url="${asset.url}"
             data-name="${asset.name}"
             onclick="toggleLibraryItem(this)">
            <img src="${asset.url}" alt="${asset.name}" loading="lazy">
            <span class="item-name">${asset.name}</span>
        </div>
    `).join('');
}

function toggleLibraryItem(element) {
    const { id, type, filename, url, name } = element.dataset;
    const collection = type === 'badge' 
        ? state.selectedLibraryBadges 
        : state.selectedLibraryLogos;
    
    const index = collection.findIndex(item => item.id === id);
    
    if (index === -1) {
        collection.push({ id, filename, url, name });
        element.classList.add('selected');
    } else {
        collection.splice(index, 1);
        element.classList.remove('selected');
    }
    
    updatePreview();
}

// ==================== Upload ====================

function initializeUpload() {
    // Badge file upload
    elements.uploadZoneBadges.addEventListener('click', () => elements.badgeInput.click());
    elements.badgeInput.addEventListener('change', (e) => {
        handleFiles(e.target.files, 'badge');
        e.target.value = '';
    });
    
    // Badge drag and drop
    setupDragDrop(elements.uploadZoneBadges, 'badge');
    
    // Badge URL
    elements.addBadgeUrlBtn.addEventListener('click', () => {
        addImageFromUrl(elements.badgeUrlInput.value, 'badge');
    });
    elements.badgeUrlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            addImageFromUrl(elements.badgeUrlInput.value, 'badge');
        }
    });
    
    // Logo file upload
    elements.uploadZoneLogos.addEventListener('click', () => elements.logoInput.click());
    elements.logoInput.addEventListener('change', (e) => {
        handleFiles(e.target.files, 'logo');
        e.target.value = '';
    });
    
    // Logo drag and drop
    setupDragDrop(elements.uploadZoneLogos, 'logo');
    
    // Logo URL
    elements.addLogoUrlBtn.addEventListener('click', () => {
        addImageFromUrl(elements.logoUrlInput.value, 'logo');
    });
    elements.logoUrlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            addImageFromUrl(elements.logoUrlInput.value, 'logo');
        }
    });
}

function setupDragDrop(zone, type) {
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('drag-over');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('drag-over');
    });

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        handleFiles(e.dataTransfer.files, type);
    });
}

function handleFiles(files, type) {
    const targetArray = type === 'logo' ? state.uploadedLogos : state.uploadedBadges;
    
    for (const file of files) {
        if (!CONFIG.supportedFormats.includes(file.type)) {
            alert(`Unsupported file format: ${file.name}`);
            continue;
        }

        if (file.size > CONFIG.maxFileSize) {
            alert(`File too large: ${file.name}. Maximum size is 10MB.`);
            continue;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            const id = `upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
            targetArray.push({
                id,
                file,
                dataUrl: e.target.result,
                name: file.name,
            });
            renderUploadedImages();
            updatePreview();
        };
        reader.readAsDataURL(file);
    }
}

async function addImageFromUrl(url, type) {
    if (!url || !url.trim()) {
        return;
    }
    
    url = url.trim();
    
    // Validate URL format
    try {
        new URL(url);
    } catch {
        alert('Please enter a valid URL');
        return;
    }
    
    const targetArray = type === 'logo' ? state.uploadedLogos : state.uploadedBadges;
    const inputElement = type === 'logo' ? elements.logoUrlInput : elements.badgeUrlInput;
    
    try {
        // Create a temporary image to verify the URL works
        const img = new Image();
        img.crossOrigin = 'anonymous';
        
        await new Promise((resolve, reject) => {
            img.onload = resolve;
            img.onerror = () => reject(new Error('Failed to load image'));
            img.src = url;
        });
        
        // Get the image as dataUrl via canvas
        const canvas = document.createElement('canvas');
        canvas.width = img.width;
        canvas.height = img.height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0);
        
        let dataUrl;
        try {
            dataUrl = canvas.toDataURL('image/png');
        } catch {
            // CORS issue - use URL directly
            dataUrl = url;
        }
        
        const id = `url-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const name = url.split('/').pop().split('?')[0] || 'Image from URL';
        
        targetArray.push({
            id,
            file: null,
            dataUrl,
            url, // Keep original URL
            name,
        });
        
        inputElement.value = '';
        renderUploadedImages();
        updatePreview();
        
    } catch (error) {
        alert('Could not load image from URL. Please check the URL and try again.');
        console.error('URL load error:', error);
    }
}

function renderUploadedImages() {
    // Render badges
    if (state.uploadedBadges.length === 0) {
        elements.uploadedBadges.innerHTML = '';
    } else {
        elements.uploadedBadges.innerHTML = state.uploadedBadges.map(badge => `
            <div class="uploaded-badge" data-id="${badge.id}">
                <img src="${badge.dataUrl}" alt="${badge.name}" title="${badge.name}">
                <button class="remove-btn" onclick="removeUploadedImage('${badge.id}', 'badge')">&times;</button>
            </div>
        `).join('');
    }
    
    // Render logos
    if (state.uploadedLogos.length === 0) {
        elements.uploadedLogos.innerHTML = '';
    } else {
        elements.uploadedLogos.innerHTML = state.uploadedLogos.map(logo => `
            <div class="uploaded-badge" data-id="${logo.id}">
                <img src="${logo.dataUrl}" alt="${logo.name}" title="${logo.name}">
                <button class="remove-btn" onclick="removeUploadedImage('${logo.id}', 'logo')">&times;</button>
            </div>
        `).join('');
    }
}

function removeUploadedImage(id, type) {
    if (type === 'logo') {
        state.uploadedLogos = state.uploadedLogos.filter(l => l.id !== id);
    } else {
        state.uploadedBadges = state.uploadedBadges.filter(b => b.id !== id);
    }
    renderUploadedImages();
    updatePreview();
}

// ==================== Settings ====================

function initializeSettings() {
    elements.canvasSize.addEventListener('change', (e) => {
        elements.customSizeGroup.style.display = 
            e.target.value === 'custom' ? 'flex' : 'none';
    });

    elements.backgroundColorPicker.addEventListener('input', (e) => {
        elements.backgroundColor.value = e.target.value.toUpperCase();
    });

    elements.backgroundColor.addEventListener('input', (e) => {
        const value = e.target.value;
        if (/^#[0-9A-Fa-f]{6}$/.test(value)) {
            elements.backgroundColorPicker.value = value;
        }
    });

    elements.transparentBg.addEventListener('change', (e) => {
        const disabled = e.target.checked;
        elements.backgroundColorPicker.disabled = disabled;
        elements.backgroundColor.disabled = disabled;
        elements.backgroundColorPicker.style.opacity = disabled ? '0.5' : '1';
        elements.backgroundColor.style.opacity = disabled ? '0.5' : '1';
    });
}

function getSettings() {
    let size = elements.canvasSize.value;
    
    if (size === 'custom') {
        const width = document.getElementById('customWidth').value || 320;
        const height = document.getElementById('customHeight').value || 180;
        size = `${width}x${height}`;
    }

    const background = elements.transparentBg.checked 
        ? 'transparent' 
        : elements.backgroundColor.value;

    return {
        duration: document.getElementById('duration').value,
        logoDuration: document.getElementById('logoDuration').value,
        size,
        background,
        groupSize: document.getElementById('groupSize').value,
        removeWhiteBg: elements.removeWhiteBg.checked,
    };
}

// ==================== Preview ====================

function rebuildOrderedItems() {
    const newItems = [];
    const existingIds = new Set(state.orderedItems.map(item => item.id));
    
    const currentItems = [
        ...state.uploadedBadges.map(b => ({ id: b.id, type: 'badge', source: 'upload', data: b })),
        ...state.selectedLibraryBadges.map(b => ({ id: b.id, type: 'badge', source: 'library', data: b })),
        ...state.uploadedLogos.map(l => ({ id: l.id, type: 'logo', source: 'upload', data: l })),
        ...state.selectedLibraryLogos.map(l => ({ id: l.id, type: 'logo', source: 'library', data: l })),
    ];
    const currentIds = new Set(currentItems.map(item => item.id));
    
    for (const item of state.orderedItems) {
        if (currentIds.has(item.id)) {
            const current = currentItems.find(c => c.id === item.id);
            if (current) {
                newItems.push(current);
            }
        }
    }
    
    for (const item of currentItems) {
        if (!existingIds.has(item.id)) {
            newItems.push(item);
        }
    }
    
    state.orderedItems = newItems;
}

function updatePreview() {
    const totalBadges = state.uploadedBadges.length + state.selectedLibraryBadges.length;
    const totalLogos = state.uploadedLogos.length + state.selectedLibraryLogos.length;
    const total = totalBadges + totalLogos;

    rebuildOrderedItems();

    // Update summary
    if (total === 0) {
        elements.selectionSummary.innerHTML = '<p>Select badges and logos above to see a preview</p>';
        elements.reorderHint.style.display = 'none';
    } else {
        elements.selectionSummary.innerHTML = `
            <p>
                <span class="count">${totalBadges}</span> badge${totalBadges !== 1 ? 's' : ''} and 
                <span class="count">${totalLogos}</span> logo${totalLogos !== 1 ? 's' : ''} selected
            </p>
        `;
        elements.reorderHint.style.display = total > 1 ? 'flex' : 'none';
    }

    // Update preview area
    if (total === 0) {
        elements.previewArea.innerHTML = `
            <div class="preview-placeholder">
                <svg viewBox="0 0 24 24" width="64" height="64" fill="currentColor" opacity="0.3">
                    <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/>
                </svg>
                <p>Your selected items will appear here</p>
            </div>
        `;
    } else {
        elements.previewArea.innerHTML = `
            <div class="preview-badges" id="sortablePreview">
                ${state.orderedItems.map((item, index) => {
                    const url = item.source === 'upload' ? item.data.dataUrl : item.data.url;
                    const name = item.data.name;
                    return `
                        <div class="preview-item" draggable="true" data-index="${index}" data-id="${item.id}">
                            <img src="${url}" alt="${name}" title="${name}">
                            <span class="item-type-badge ${item.type}-type">${item.type === 'badge' ? 'B' : 'L'}</span>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
        
        initDragAndDrop();
    }

    // Update generate button
    elements.generateBtn.disabled = total === 0;
    
    // Hide result section when selection changes
    elements.resultSection.style.display = 'none';
}

// ==================== Drag and Drop ====================

let draggedItem = null;
let draggedIndex = null;

function initDragAndDrop() {
    const container = document.getElementById('sortablePreview');
    if (!container) return;
    
    const items = container.querySelectorAll('.preview-item');
    
    items.forEach(item => {
        item.addEventListener('dragstart', handleDragStart);
        item.addEventListener('dragend', handleDragEnd);
        item.addEventListener('dragover', handleDragOver);
        item.addEventListener('dragenter', handleDragEnter);
        item.addEventListener('dragleave', handleDragLeave);
        item.addEventListener('drop', handleDrop);
    });
}

function handleDragStart(e) {
    draggedItem = this;
    draggedIndex = parseInt(this.dataset.index);
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', this.dataset.index);
}

function handleDragEnd() {
    this.classList.remove('dragging');
    document.querySelectorAll('.preview-item').forEach(item => {
        item.classList.remove('drag-over');
    });
    draggedItem = null;
    draggedIndex = null;
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
}

function handleDragEnter(e) {
    e.preventDefault();
    if (this !== draggedItem) {
        this.classList.add('drag-over');
    }
}

function handleDragLeave() {
    this.classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    this.classList.remove('drag-over');
    
    if (this === draggedItem) return;
    
    const fromIndex = draggedIndex;
    const toIndex = parseInt(this.dataset.index);
    
    const [movedItem] = state.orderedItems.splice(fromIndex, 1);
    state.orderedItems.splice(toIndex, 0, movedItem);
    
    updatePreviewDisplay();
}

function updatePreviewDisplay() {
    const container = document.getElementById('sortablePreview');
    if (!container) return;
    
    container.innerHTML = state.orderedItems.map((item, index) => {
        const url = item.source === 'upload' ? item.data.dataUrl : item.data.url;
        const name = item.data.name;
        return `
            <div class="preview-item" draggable="true" data-index="${index}" data-id="${item.id}">
                <img src="${url}" alt="${name}" title="${name}">
                <span class="item-type-badge ${item.type}-type">${item.type === 'badge' ? 'B' : 'L'}</span>
            </div>
        `;
    }).join('');
    
    initDragAndDrop();
}

// ==================== Actions ====================

function initializeActions() {
    elements.generateBtn.addEventListener('click', generateGif);
    elements.clearAllBtn.addEventListener('click', clearAll);
    elements.createAnotherBtn.addEventListener('click', () => {
        elements.resultSection.style.display = 'none';
        clearAll();
    });
}

function clearAll() {
    state.uploadedBadges = [];
    state.uploadedLogos = [];
    state.selectedLibraryBadges = [];
    state.selectedLibraryLogos = [];
    state.orderedItems = [];
    renderUploadedImages();
    renderBadgeLibrary();
    renderLogoLibrary();
    updatePreview();
}

async function generateGif() {
    const totalBadges = state.uploadedBadges.length + state.selectedLibraryBadges.length;
    const totalLogos = state.uploadedLogos.length + state.selectedLibraryLogos.length;

    if (totalBadges + totalLogos === 0) {
        alert('Please select at least one badge or logo.');
        return;
    }

    elements.loadingOverlay.classList.add('active');

    try {
        const settings = getSettings();
        const formData = new FormData();

        formData.append('duration', settings.duration);
        formData.append('logoDuration', settings.logoDuration);
        formData.append('size', settings.size);
        formData.append('background', settings.background);
        formData.append('groupSize', settings.groupSize);
        formData.append('removeWhiteBg', settings.removeWhiteBg);

        const orderedBadges = [];
        const orderedLogos = [];
        const uploadedBadgeFiles = [];
        const uploadedLogoFiles = [];
        const selectedBadgeFilenames = [];
        const selectedLogoFilenames = [];
        
        // Process items - handle URL-based uploads
        for (const item of state.orderedItems) {
            if (item.type === 'badge') {
                if (item.source === 'upload') {
                    if (item.data.file) {
                        formData.append('badges', item.data.file);
                    } else if (item.data.dataUrl) {
                        // URL-based upload - convert dataUrl to blob
                        const blob = await dataUrlToBlob(item.data.dataUrl);
                        formData.append('badges', blob, item.data.name);
                    }
                    orderedBadges.push({ type: 'upload', index: uploadedBadgeFiles.length });
                    uploadedBadgeFiles.push(item.data);
                } else {
                    orderedBadges.push({ type: 'library', filename: item.data.filename });
                    selectedBadgeFilenames.push(item.data.filename);
                }
            } else {
                if (item.source === 'upload') {
                    if (item.data.file) {
                        formData.append('logos', item.data.file);
                    } else if (item.data.dataUrl) {
                        const blob = await dataUrlToBlob(item.data.dataUrl);
                        formData.append('logos', blob, item.data.name);
                    }
                    orderedLogos.push({ type: 'upload', index: uploadedLogoFiles.length });
                    uploadedLogoFiles.push(item.data);
                } else {
                    orderedLogos.push({ type: 'library', filename: item.data.filename });
                    selectedLogoFilenames.push(item.data.filename);
                }
            }
        }

        formData.append('selectedBadges', JSON.stringify(selectedBadgeFilenames));
        formData.append('selectedLogos', JSON.stringify(selectedLogoFilenames));
        formData.append('orderedBadges', JSON.stringify(orderedBadges));
        formData.append('orderedLogos', JSON.stringify(orderedLogos));

        const response = await fetch(`${CONFIG.apiBaseUrl}/generate-gif`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to generate GIF');
        }

        const blob = await response.blob();
        const gifUrl = URL.createObjectURL(blob);

        // Show result inline
        elements.resultPreview.innerHTML = `<img src="${gifUrl}" alt="Generated GIF">`;
        elements.downloadBtn.href = gifUrl;
        elements.resultSection.style.display = 'block';
        
        // Scroll to result
        elements.resultSection.scrollIntoView({ behavior: 'smooth', block: 'center' });

    } catch (error) {
        console.error('Error generating GIF:', error);
        alert(`Error: ${error.message}`);
    } finally {
        elements.loadingOverlay.classList.remove('active');
    }
}

async function dataUrlToBlob(dataUrl) {
    // Handle both data URLs and regular URLs
    if (dataUrl.startsWith('data:')) {
        const response = await fetch(dataUrl);
        return response.blob();
    } else {
        // It's a regular URL, try to fetch it
        try {
            const response = await fetch(dataUrl);
            return response.blob();
        } catch {
            // If fetch fails (CORS), create a placeholder
            console.warn('Could not fetch URL, using placeholder');
            return new Blob([''], { type: 'image/png' });
        }
    }
}

// Make functions available globally for inline handlers
window.removeUploadedImage = removeUploadedImage;
window.toggleLibraryItem = toggleLibraryItem;
window.selectBadgeCategory = selectBadgeCategory;
