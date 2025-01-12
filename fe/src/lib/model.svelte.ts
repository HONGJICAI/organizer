import {config} from '$lib/config';

export enum MediaType {
	Comic = 'comic',
	Video = 'video',
	Image = 'image'
}

export enum Category {
	Home = 0,
	Favorite = 1,
	History = 2,
	Archive = 3
}

export class MediaFile {
	name = $state('');
	path: string;
	size: number;
	type: MediaType;
	id: number;
	updateTime: string;
	updateDate: Date;
	lastViewed: number;
    lastViewedTime = $state<string | null>(null);
    lastViewedDate: Date | null;
	favorited = false;
	archived = $state(false);
	get viewed(): boolean {
		return !!this.lastViewedTime;
	}
	get coverUrl(): string {
		return `${config.apiServer}/${this.type}s/${this.name}`;
	}
	get lastViewedLabel(): string {
		if (this.lastViewedDate) {
			return this.lastViewed + ' at ' + this.lastViewedDate;
		}
		return '';
	}
	constructor(type: MediaType, json: any) {
		this.type = type;
		this.name = json.name ?? '';
		this.path = json.path;
		// size is in bytes, convert to MB with 2 decimal places
		this.size = Math.round((json.size / 1024 / 1024) * 100) / 100;
		this.id = json.id;
		this.updateTime = json.updateTime;
		this.updateDate = new Date(json.updateTime);
        
		this.lastViewedTime = json.lastViewedTime;
		this.lastViewed = json.lastViewedPosition ?? 0;
		this.lastViewedDate = json.lastViewedTime ? new Date(json.lastViewedTime) : null;
		this.favorited = json.favorited ?? false;
		this.archived = json.archived ?? false;
	}
}
export class Comic extends MediaFile {
	page: number;
	get coverUrl(): string {
		return `${config.apiServer}/${this.type}s/${this.id}_0.jpg`;
	}
	constructor(json: any) {
		super(MediaType.Comic, json);
		this.page = json.page;
	}
}
export class Video extends MediaFile {
	durationInSecond: number;
	get coverUrl(): string {
		return `${config.apiServer}/${this.type}s/${this.id}.jpg`;
	}
	constructor(json: any) {
		super(MediaType.Video, json);
		this.durationInSecond = json.durationInSecond;
	}
}
