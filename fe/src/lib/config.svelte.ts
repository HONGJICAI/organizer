export enum ViewMode {
	Width = 0,
	Height = 1
	// Screen = 2,
}

interface Config {
	apiServer: string;
	staticServer: string;
	viewMode: ViewMode;
	OrderByPosition: 'NextToSearchBar' | 'InFilterPanel';
	DeviceType?: 'Desktop' | 'Mobile';
}

const DefaultConfig: Config = {
	apiServer: '',
	staticServer: '',
	viewMode: ViewMode.Height,
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

export const config = $state(DefaultConfig);

function configAssign(c: Config) {
	Object.assign(config, c);
}

export function setDesktopConfig() {
	configAssign(DesktopConfig);
}

export function setMobileConfig() {
	configAssign(MobileConfig);
}
