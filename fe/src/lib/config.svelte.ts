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
	staticServer: string;
	viewMode: ViewMode;
	pageWidthMode: PageWidthMode;
	pageWidthCustom: number;
	OrderByPosition: 'NextToSearchBar' | 'InFilterPanel';
	DeviceType?: 'Desktop' | 'Mobile';
}

const DefaultConfig: Config = {
	apiServer: '',
	staticServer: '',
	viewMode: ViewMode.Contain,
	pageWidthMode: PageWidthMode.Original,
	pageWidthCustom: 1080,
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
	if (typeof saved.staticServer === 'string') prefs.staticServer = saved.staticServer;
	if (typeof saved.viewMode === 'number' && saved.viewMode in ViewMode)
		prefs.viewMode = saved.viewMode;
	if (typeof saved.pageWidthMode === 'number' && saved.pageWidthMode in PageWidthMode)
		prefs.pageWidthMode = saved.pageWidthMode;
	if (typeof saved.pageWidthCustom === 'number' && saved.pageWidthCustom > 0)
		prefs.pageWidthCustom = saved.pageWidthCustom;
	return prefs;
}

export function savePrefs() {
	if (typeof localStorage === 'undefined') return;
	localStorage.setItem(
		CONFIG_KEY,
		JSON.stringify({
			staticServer: config.staticServer,
			viewMode: config.viewMode,
			pageWidthMode: config.pageWidthMode,
			pageWidthCustom: config.pageWidthCustom
		})
	);
}

export const config = $state({ ...DefaultConfig, ...loadPrefs() });

function configAssign(c: Config) {
	// Saved preferences win over device defaults.
	Object.assign(config, c, loadPrefs());
}

export function setDesktopConfig() {
	configAssign(DesktopConfig);
}

export function setMobileConfig() {
	configAssign(MobileConfig);
}
