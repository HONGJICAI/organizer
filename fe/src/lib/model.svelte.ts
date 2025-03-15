import { config } from '$lib/config.svelte';
import type { ComicEntity } from './client';
import { separateFilename } from './utility';

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

export enum MediaFileComparison {
	None = -1,
	Size = 0,
	Name = 1,
	UpdatedDate = 2,
	ViewedDate = 3,
	Path = 4,
	Random = 5,
	Id = 6
}
export enum ComicComparison {
	Page = 100,
	SizePerPage = 101
}

export enum VideoComparison {
	Duration = 200,
	SizePerSecond = 201
}

export type MediaFileComparisonType = MediaFileComparison | ComicComparison | VideoComparison;

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
	favorited = $state(false);
	archived = $state(false);
	entityUpdateTime: string;
	get viewed(): boolean {
		return !!this.lastViewedTime;
	}
	get coverId(): string {
		return `cover-${this.id}`;
	}
	get coverUrl(): string {
		return `${config.staticServer}/${this.type}s/${this.name}`;
	}
	get lastViewedLabel(): string {
		if (this.lastViewedTime) {
			return this.lastViewed + ' at ' + this.lastViewedTime;
		}
		return '';
	}
	get tags(): string[] {
		return separateFilename(this.name);
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
		this.entityUpdateTime = json.entityUpdateTime;
	}
	compareTo(other: MediaFile, comparison: MediaFileComparisonType): number {
		switch (comparison) {
			case MediaFileComparison.Size:
				return this.size - other.size;
			case MediaFileComparison.Name:
				return this.name.localeCompare(other.name);
			case MediaFileComparison.UpdatedDate:
				return this.updateDate.getTime() - other.updateDate.getTime();
			case MediaFileComparison.ViewedDate:
				return (this.lastViewedDate?.getTime() ?? 0) - (other.lastViewedDate?.getTime() ?? 0);
			case MediaFileComparison.Path:
				return this.path.localeCompare(other.path);
			case MediaFileComparison.Random:
				return Math.random() > 0.5 ? 1 : -1;
			default:
				return 0;
		}
	}
}
export class Comic extends MediaFile {
	page: number;
	get coverUrl(): string {
		return `${config.staticServer}/${this.type}s/${this.id}_0.jpg`;
	}
	constructor(json: ComicEntity) {
		super(MediaType.Comic, json);
		this.page = json.page;
	}
	compareTo(other: Comic, comparison: MediaFileComparisonType): number {
		switch (comparison) {
			case ComicComparison.Page:
				return this.page - other.page;
			case ComicComparison.SizePerPage:
				return this.size / this.page - other.size / other.page;
			default:
				return super.compareTo(other, comparison);
		}
	}
}
export class Video extends MediaFile {
	durationInSecond: number;
	get coverUrl(): string {
		return `${config.staticServer}/${this.type}s/${this.id}.jpg`;
	}
	constructor(json: any) {
		super(MediaType.Video, json);
		this.durationInSecond = json.durationInSecond;
	}
	compareTo(other: Video, comparison: MediaFileComparisonType): number {
		switch (comparison) {
			case VideoComparison.Duration:
				return this.durationInSecond - other.durationInSecond;
			case VideoComparison.SizePerSecond:
				return this.size / this.durationInSecond - other.size / other.durationInSecond;
			default:
				return super.compareTo(other, comparison);
		}
	}
}

type NotificationKind = 'error' | 'info' | 'info-square' | 'success' | 'warning' | 'warning-alt';

export class Notification {
	kind: NotificationKind;
	title = '';
	subtitle = '';
	caption = new Date().toLocaleString();
	timeout: number | undefined = undefined;
	constructor(kind: NotificationKind, title: string, subtitle?: string, timeout?: number) {
		this.kind = kind;
		this.title = title;
		this.subtitle = subtitle ?? '';
		this.timeout = timeout;
	}
}

interface NotificationOptions {
	subtitle?: string;
	timeout?: number;
}

export class SuccessNotification extends Notification {
	constructor(options: NotificationOptions) {
		options = { ...{ timeout: 3000 }, ...options };
		super('success', 'Success', options?.subtitle, options?.timeout);
	}
}

export class ErrorNotification extends Notification {
	constructor(options: NotificationOptions) {
		super('error', `Error`, options?.subtitle, options?.timeout);
	}
}
