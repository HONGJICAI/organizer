export enum ViewMode {
	Width = 0,
	Height = 1,
	Contain = 2,
	Scroll = 3
}

export enum PageWidthMode {
	Original = 0,
	Device = 1,
	Custom = 2
}

interface Config {
	apiServer: string;
	viewMode: ViewMode;
	pageWidthMode: PageWidthMode;
	pageWidthCustom: number;
	// Reader header shows the current page's file name and size.
	showPageInfo: boolean;
	// Default thumbnail size level of the page overview (0 = S … 3 = XL). The
	// overview's own size control changes it for the session only.
	overviewSize: number;
	OrderByPosition: 'NextToSearchBar' | 'InFilterPanel';
	DeviceType?: 'Desktop' | 'Mobile';
}

const DefaultConfig: Config = {
	apiServer: '',
	viewMode: ViewMode.Contain,
	pageWidthMode: PageWidthMode.Original,
	pageWidthCustom: 1080,
	showPageInfo: false,
	overviewSize: 0,
	OrderByPosition: 'NextToSearchBar',
	DeviceType: 'Desktop'
};

const DesktopConfig: Config = {
	...DefaultConfig
};

const MobileConfig: Config = {
	...DefaultConfig,
	viewMode: ViewMode.Width,
	OrderByPosition: 'InFilterPanel',
	DeviceType: 'Mobile'
};

// User preferences persisted across sessions. apiServer is excluded: the
// connect flow owns it (organizer-server-url).
const CONFIG_KEY = 'organizer-config';

function loadPrefs(): Partial<Config> {
	if (typeof localStorage === 'undefined') return {};
	let raw: unknown;
	try {
		raw = JSON.parse(localStorage.getItem(CONFIG_KEY) ?? '{}');
	} catch {
		return {};
	}
	if (typeof raw !== 'object' || raw === null) return {};
	const saved = raw as Record<string, unknown>;
	const prefs: Partial<Config> = {};
	if (typeof saved.viewMode === 'number' && saved.viewMode in ViewMode)
		prefs.viewMode = saved.viewMode;
	if (typeof saved.pageWidthMode === 'number' && saved.pageWidthMode in PageWidthMode)
		prefs.pageWidthMode = saved.pageWidthMode;
	if (typeof saved.pageWidthCustom === 'number' && saved.pageWidthCustom > 0)
		prefs.pageWidthCustom = saved.pageWidthCustom;
	if (typeof saved.showPageInfo === 'boolean') prefs.showPageInfo = saved.showPageInfo;
	if (
		typeof saved.overviewSize === 'number' &&
		Number.isInteger(saved.overviewSize) &&
		saved.overviewSize >= 0 &&
		saved.overviewSize <= 3
	)
		prefs.overviewSize = saved.overviewSize;
	return prefs;
}

export function savePrefs() {
	if (typeof localStorage === 'undefined') return;
	localStorage.setItem(
		CONFIG_KEY,
		JSON.stringify({
			viewMode: config.viewMode,
			pageWidthMode: config.pageWidthMode,
			pageWidthCustom: config.pageWidthCustom,
			showPageInfo: config.showPageInfo,
			overviewSize: config.overviewSize
		})
	);
}

export const config = $state({ ...DefaultConfig, ...loadPrefs() });

function configAssign(c: Config) {
	// Device presets carry display defaults only. apiServer belongs to the
	// connect flow; copying the preset's empty one would point the client back
	// at the page's own origin after connecting.
	const { apiServer, ...defaults } = c;
	void apiServer;
	// Saved preferences win over device defaults.
	Object.assign(config, defaults, loadPrefs());
}

export function setDesktopConfig() {
	configAssign(DesktopConfig);
}

export function setMobileConfig() {
	configAssign(MobileConfig);
}
